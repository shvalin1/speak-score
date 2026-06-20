"""pipeline の音声抽出配線テスト（GCS DL / ffmpeg はモック・ネットワーク非依存）。

実処理（Whisper/librosa/gpt-4o）は別フェーズ。ここでは「DL→長さ/サイズ検証→抽出→掃除」の
配線とエラー分類（長尺/サイズ超過=FatalError、content_type 欠落=FatalError）を検証する。
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest

from src.core import media, storage
from src.core.errors import FatalError
from src.repositories.job_repo import InMemoryJobRepo
from src.schemas.interview import (
    AudioMetrics,
    Dimension,
    DimensionSource,
    FillerHit,
    Transcript,
    TranscriptSegment,
)
from src.services import audio_analysis, llm_evaluation, pipeline, transcription
from src.services.llm_evaluation import LlmEvaluation


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


def _ready_job(repo: InMemoryJobRepo, content_type: str = "video/mp4") -> str:
    jid = "job-" + content_type.replace("/", "-")
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type=content_type)
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "w1")
    return jid


def _mock_media(monkeypatch, *, duration: float = 30.0, wav_bytes: bytes = b"RIFFxxxx") -> dict:
    """storage.download_to_tmp / media.probe_duration / extract_to_wav を差し替える。"""
    captured: dict[str, str] = {}

    def fake_download(job_id: str, content_type: str, dest_path: str) -> str:
        with open(dest_path, "wb") as f:
            f.write(b"raw-video")
        return dest_path

    def fake_extract(src_path: str, dest_path: str) -> None:
        with open(dest_path, "wb") as f:
            f.write(wav_bytes)
        captured["wav"] = dest_path

    monkeypatch.setattr(storage, "download_to_tmp", fake_download)
    monkeypatch.setattr(media, "probe_duration", lambda _p: duration)
    monkeypatch.setattr(media, "extract_to_wav", fake_extract)
    return captured


def _mock_services(monkeypatch) -> None:
    """Whisper/librosa/gpt-4o を差し替え、配線テストをネットワーク・実音声非依存にする。"""

    async def fake_transcribe(_path: str) -> Transcript:
        text = "本日はよろしくお願いします。えー、自己紹介します。"
        return Transcript(
            full_text=text,
            duration_sec=8.0,
            segments=[TranscriptSegment(start=0.0, end=8.0, text=text)],
            fillers=[FillerHit(text="えー", start_char=14, end_char=16)],
        )

    def fake_analyze(_path: str, transcript: Transcript) -> AudioMetrics:
        return AudioMetrics(
            speech_rate_cpm=320.0, filler_count=len(transcript.fillers), filler_rate=2.0,
            silence_ratio=0.1, silence_segments=[], pitch_mean=140.0, pitch_std=25.0,
            volume_mean=0.05, volume_cv=0.4, volume_timeline=[], pitch_timeline=[],
        )

    async def fake_evaluate(_t: Transcript, _m: AudioMetrics) -> LlmEvaluation:
        return LlmEvaluation(
            content=Dimension(score=75, comment="c", source=DimensionSource.llm),
            structure=Dimension(score=70, comment="s", source=DimensionSource.llm),
            strengths=["具体例がある"], improvements=["結論から話す"],
        )

    monkeypatch.setattr(transcription, "transcribe", fake_transcribe)
    monkeypatch.setattr(audio_analysis, "analyze_audio", fake_analyze)
    monkeypatch.setattr(llm_evaluation, "evaluate", fake_evaluate)


def test_run_pipeline_extracts_and_completes(monkeypatch) -> None:
    repo = InMemoryJobRepo()
    jid = _ready_job(repo)
    captured = _mock_media(monkeypatch)
    _mock_services(monkeypatch)

    result = asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))

    assert result.overall_score >= 0
    assert result.transcript.full_text  # ダミーでも文字起こしが返る
    # 一時ディレクトリは finally で掃除される
    assert not os.path.exists(os.path.dirname(captured["wav"]))


def test_run_pipeline_fatal_on_long_video(monkeypatch) -> None:
    repo = InMemoryJobRepo()
    jid = _ready_job(repo)
    _mock_media(monkeypatch, duration=99999.0)

    with pytest.raises(FatalError):
        asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))


def test_run_pipeline_fatal_on_oversized_audio(monkeypatch) -> None:
    repo = InMemoryJobRepo()
    jid = _ready_job(repo)
    # max_audio_bytes(25MiB) を超える WAV を返させる
    _mock_media(monkeypatch, wav_bytes=b"x" * (26 * 1024 * 1024))

    with pytest.raises(FatalError):
        asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))


def test_run_pipeline_fatal_without_content_type(monkeypatch) -> None:
    repo = InMemoryJobRepo()
    jid = "no-ct"
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="")
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "w1")
    _mock_media(monkeypatch)

    with pytest.raises(FatalError):
        asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))
