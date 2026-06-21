"""パイプライン orchestration。各stepで repo.update_stage を逐次更新。

音声抽出は実装済み（GCS DL → ffmpeg で WAV mono16k）。文字起こし/音声分析/LLM評価の
各サービスは現状ダミー値だが、配線は実処理を差し込める形になっている（Step2 Phase4 で中身を流す）。

評価は **音声を直接 LLM に渡さず、Whisper の文字起こしテキストを gpt-4o に渡す**設計
（フィラー/言い淀み込みの話し方評価を delivery 側に分離するため）。
設計根拠: design_review_and_frontback.md §2, §5.1 / step2_plan.md Phase 1, 4。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import tempfile

import httpx

from ..core import media, storage
from ..core.config import Settings, get_settings
from ..core.errors import FatalError, RecoverableError
from ..repositories.job_repo import JobRepository
from ..schemas.interview import (
    AnalysisResult,
    Dimension,
    Dimensions,
    DimensionSource,
    ProcessingStage,
)
from . import (
    applicant_id,
    audio_analysis,
    diarization,
    llm_evaluation,
    qa_formatting,
    scoring,
    transcription,
)

log = logging.getLogger(__name__)

# Gladia ポーリング中の lease 維持。LEASE_DURATION(900s)/2=450s より十分小さく取る（§13.2）。
_HEARTBEAT_INTERVAL_SEC = 120


def _prepare_audio(job_id: str, content_type: str, settings: Settings, tmp_dir: str) -> str:
    """GCS から元動画を DL → WAV mono16k に変換し、その一時パスを返す（同期・CPU/IO bound）。

    tmp_dir は呼び出し側(run_pipeline)が作成・掃除する（soft_timeout の cancel で
    この to_thread が中断されても finally で確実に消すため）。
    エラー分類: DL 失敗=一時的(RecoverableError)、変換/長さ/サイズ=恒久的(FatalError)。
    """
    ext = storage.ext_from_content_type(content_type)
    src_path = os.path.join(tmp_dir, f"source.{ext}")
    wav_path = os.path.join(tmp_dir, "audio.wav")
    try:
        storage.download_to_tmp(job_id, content_type, src_path)
    except Exception as e:  # noqa: BLE001 GCS DL は一時的失敗として再試行に倒す
        raise RecoverableError(f"source download failed: {e}") from e

    duration = media.probe_duration(src_path)
    if duration > settings.max_video_seconds:
        raise FatalError(f"動画が長すぎます（{duration:.0f}s > {settings.max_video_seconds}s）")

    media.extract_to_wav(src_path, wav_path)

    size = os.path.getsize(wav_path)
    if size > settings.max_audio_bytes:
        raise FatalError(f"抽出音声が大きすぎます（{size} bytes）")

    return wav_path


async def _diarize_with_heartbeat(
    wav_path: str, key: str, job_id: str, repo: JobRepository, worker_id: str
) -> list[diarization.SpeakerTurn]:
    """Gladia の同期ポーリングを別スレッドで回しつつ、定期 heartbeat で lease を延長する。

    heartbeat 要件（§13.2）: finally で確実に cancel・interval < LEASE/2・
    heartbeat 例外は握り潰し本処理継続・ブロッキング renew_lease は to_thread。
    """
    stop = asyncio.Event()

    async def heartbeat() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=_HEARTBEAT_INTERVAL_SEC)
            except TimeoutError:
                try:
                    await asyncio.to_thread(repo.renew_lease, job_id, worker_id)
                except Exception as e:  # noqa: BLE001 heartbeat 例外は握り潰す
                    log.warning("heartbeat renew_lease 失敗（無視して継続）: %s", e)

    hb = asyncio.create_task(heartbeat())
    try:
        return await asyncio.to_thread(diarization.diarize_gladia, wav_path, key)
    finally:
        stop.set()
        hb.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb


async def _diarize_or_degrade(
    wav_path: str, settings: Settings, job_id: str, repo: JobRepository, worker_id: str
) -> list[diarization.SpeakerTurn]:
    """話者分離を試み、キー未設定/障害/話者1名なら空 turns（単一話者縮退）を返す。"""
    if not settings.gladia_api_key:
        log.info("GLADIA_API_KEY 未設定 → 話者分離をスキップ（単一話者縮退）")
        return []

    repo.update_stage(job_id, ProcessingStage.diarizing)
    repo.renew_lease(job_id, worker_id)
    try:
        turns = await _diarize_with_heartbeat(
            wav_path, settings.gladia_api_key, job_id, repo, worker_id
        )
    except (diarization.GladiaError, httpx.HTTPError) as e:
        log.warning("Gladia 話者分離に失敗 → 単一話者に縮退: %s", e)
        return []

    if diarization.n_speakers(turns) < 2:
        log.info("Gladia 検出話者数 < 2 → 単一話者に縮退")
        return []
    return turns


async def _format_qa_or_degrade(
    segments, metrics, applicant_speaker: str | None
) -> qa_formatting.QaFormatting | None:
    """LLM#2 整形。失敗してもジョブを落とさず縮退（Gladia/Whisper の二重課金を避ける）。"""
    try:
        return await qa_formatting.format_qa(segments, metrics, applicant_speaker)
    except Exception as e:  # noqa: BLE001 整形失敗は縮退（minutes/qa_segments を空に）
        log.warning("qa_formatting 失敗 → minutes/qa_segments を空で縮退: %s", e)
        return None


async def run_pipeline(job_id: str, repo: JobRepository, worker_id: str) -> AnalysisResult:
    settings = get_settings()
    # stage=extracting_audio はリース取得時にセット済み。
    repo.renew_lease(job_id, worker_id)

    content_type = repo.get_content_type(job_id)
    if not content_type:
        raise FatalError(f"content_type not found for job {job_id}")

    # tmp_dir は呼び出し側で作り finally で必ず掃除（soft_timeout の cancel が
    # _prepare_audio の to_thread 中に起きても tmp がリークしないように）。
    tmp_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    try:
        # DL→ffmpeg は同期 CPU/IO bound のため別スレッドへ（async ループを塞がない）
        wav_path = await asyncio.to_thread(_prepare_audio, job_id, content_type, settings, tmp_dir)

        # 話者分離（Gladia・B方式）。キー未設定/障害/1話者なら空 turns で縮退。
        turns = await _diarize_or_degrade(wav_path, settings, job_id, repo, worker_id)

        repo.update_stage(job_id, ProcessingStage.transcribing)
        repo.renew_lease(job_id, worker_id)
        tr = await transcription.transcribe_verbose(wav_path)
        transcript = tr.transcript
        # 話者を充填（full_text/fillers は不変・segments のみ差し替え）。turns 空なら素通り。
        if turns:
            attributed = diarization.attribute_speakers(transcript.segments, tr.words, turns)
            transcript = transcript.model_copy(update={"segments": attributed})

        repo.update_stage(job_id, ProcessingStage.analyzing_audio)
        repo.renew_lease(job_id, worker_id)
        # librosa 等は CPU bound のため別スレッドへ
        metrics = await asyncio.to_thread(audio_analysis.analyze_audio, wav_path, transcript)

        # LLM#0: 応募者の話者を判定（失敗/不確実は縮退・例外を上げない）。
        applicant = await asyncio.to_thread(applicant_id.identify_applicant, transcript.segments)

        repo.update_stage(job_id, ProcessingStage.evaluating)
        repo.renew_lease(job_id, worker_id)
        # LLM#1(評価) と LLM#2(議事録/問答整形) を並行実行。整形失敗はジョブを落とさず縮退。
        llm, qa = await asyncio.gather(
            llm_evaluation.evaluate(transcript, metrics),
            _format_qa_or_degrade(transcript.segments, metrics, applicant.speaker),
        )

        # 算出系（delivery/confidence）は決定論スコアリング、LLM系はllmの採点を使う
        dimensions = Dimensions(
            content=llm.content,
            structure=llm.structure,
            delivery=Dimension(
                score=scoring.score_delivery(metrics),
                comment="話速・フィラー率・無音率から算出。",
                source=DimensionSource.computed,
            ),
            confidence=Dimension(
                score=scoring.score_confidence(metrics),
                comment="音量安定性とピッチ変動から算出。",
                source=DimensionSource.computed,
            ),
        )
        return AnalysisResult(
            overall_score=scoring.overall(dimensions),
            dimensions=dimensions,
            audio_metrics=metrics,
            transcript=transcript,
            strengths=llm.strengths,
            improvements=llm.improvements,
            minutes=qa.minutes if qa else None,
            qa_segments=qa.qa_segments if qa else [],
        )
    finally:
        # Cloud Run インスタンス再利用でディスクが溜まらないよう一時ディレクトリごと削除
        shutil.rmtree(tmp_dir, ignore_errors=True)
