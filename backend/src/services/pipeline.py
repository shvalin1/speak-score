"""パイプライン orchestration。各stepで repo.update_stage を逐次更新。

音声抽出は実装済み（GCS DL → ffmpeg で WAV mono16k）。文字起こし/音声分析/LLM評価の
各サービスは現状ダミー値だが、配線は実処理を差し込める形になっている（Step2 Phase4 で中身を流す）。

評価は **音声を直接 LLM に渡さず、Whisper の文字起こしテキストを gpt-4o に渡す**設計
（フィラー/言い淀み込みの話し方評価を delivery 側に分離するため）。
設計根拠: design_review_and_frontback.md §2, §5.1 / step2_plan.md Phase 1, 4。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

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
from . import audio_analysis, llm_evaluation, scoring, transcription


def _prepare_audio(job_id: str, content_type: str, settings: Settings) -> str:
    """GCS から元動画を DL → WAV mono16k に変換し、その一時パスを返す（同期・CPU/IO bound）。

    一時ディレクトリは「成功時は WAV を残して呼び出し側が掃除」「失敗時はここで掃除」。
    エラー分類: DL 失敗=一時的(RecoverableError)、変換/長さ/サイズ=恒久的(FatalError)。
    """
    tmp_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    ext = storage.ext_from_content_type(content_type)
    src_path = os.path.join(tmp_dir, f"source.{ext}")
    wav_path = os.path.join(tmp_dir, "audio.wav")
    try:
        try:
            storage.download_to_tmp(job_id, content_type, src_path)
        except Exception as e:  # noqa: BLE001 GCS DL は一時的失敗として再試行に倒す
            raise RecoverableError(f"source download failed: {e}") from e

        duration = media.probe_duration(src_path)
        if duration > settings.max_video_seconds:
            raise FatalError(
                f"動画が長すぎます（{duration:.0f}s > {settings.max_video_seconds}s）"
            )

        media.extract_to_wav(src_path, wav_path)

        size = os.path.getsize(wav_path)
        if size > settings.max_audio_bytes:
            raise FatalError(f"抽出音声が大きすぎます（{size} bytes）")

        os.remove(src_path)  # 元動画は不要、WAV のみ残す
        return wav_path
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


async def run_pipeline(job_id: str, repo: JobRepository, worker_id: str) -> AnalysisResult:
    settings = get_settings()
    # stage=extracting_audio はリース取得時にセット済み。
    repo.renew_lease(job_id, worker_id)

    content_type = repo.get_content_type(job_id)
    if not content_type:
        raise FatalError(f"content_type not found for job {job_id}")

    # DL→ffmpeg は同期 CPU/IO bound のため別スレッドへ（async ループを塞がない）
    wav_path = await asyncio.to_thread(_prepare_audio, job_id, content_type, settings)
    try:
        repo.update_stage(job_id, ProcessingStage.transcribing)
        repo.renew_lease(job_id, worker_id)
        transcript = await transcription.transcribe(wav_path)

        repo.update_stage(job_id, ProcessingStage.analyzing_audio)
        repo.renew_lease(job_id, worker_id)
        # librosa 等は CPU bound のため別スレッドへ
        metrics = await asyncio.to_thread(audio_analysis.analyze_audio, wav_path, transcript)

        repo.update_stage(job_id, ProcessingStage.evaluating)
        repo.renew_lease(job_id, worker_id)
        # 音声でなく文字起こしテキストを LLM に渡す（話し方評価は delivery 側で分離）
        llm = await llm_evaluation.evaluate(transcript, metrics)

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
        )
    finally:
        # Cloud Run インスタンス再利用でディスクが溜まらないよう一時ディレクトリごと削除
        shutil.rmtree(os.path.dirname(wav_path), ignore_errors=True)
