"""Step2 実サービスのユニットテスト（OpenAI 非依存・librosa は合成音声で実行）。

network を踏むのは Whisper/gpt-4o の HTTP 呼び出しのみ。ここではそれをモックし、
純ロジック（フィラー検出・話速/無音などの librosa 算出・LLM 出力のパース/リトライ）を固定する。
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
import soundfile as sf

from src.core.errors import FatalError, RecoverableError
from src.schemas.interview import AudioMetrics, Transcript
from src.services import audio_analysis, llm_evaluation, transcription


def test_find_fillers_longest_match_no_overlap() -> None:
    # 「えーと」は「えー」+「と」に二重計上せず、最長一致で1件になる
    hits = transcription.find_fillers("えーと、あのこれは、なんか難しい。")
    texts = [h.text for h in hits]
    assert "えーと" in texts
    assert texts.count("えー") == 0  # 「えーと」に飲み込まれる
    # オフセットは full_text の実位置
    for h in hits:
        assert "えーと、あのこれは、なんか難しい。"[h.start_char:h.end_char] == h.text


def _write_wav(path: str, seconds: float = 6.0, sr: int = 16000) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    voiced = 0.25 * np.sin(2 * np.pi * 130 * t)
    env = np.zeros_like(t)
    for s, e in [(0.3, 2.5), (3.2, 5.5)]:  # 2 フレーズ + 間の無音
        env[(t >= s) & (t < e)] = 1.0
    sf.write(path, (voiced * env).astype(np.float32), sr)


def test_audio_analysis_real_metrics(tmp_path) -> None:
    wav = str(tmp_path / "s.wav")
    _write_wav(wav)
    transcript = Transcript(
        full_text="これはテストの発話です。" * 10, duration_sec=6.0, segments=[], fillers=[]
    )

    m = audio_analysis.analyze_audio(wav, transcript)

    assert isinstance(m, AudioMetrics)
    assert m.speech_rate_cpm > 0          # 文字数/発話秒 から算出される
    assert 0.0 <= m.silence_ratio <= 1.0
    assert m.silence_segments              # 無音区間が検出される
    assert m.pitch_mean > 0
    assert m.volume_timeline and m.pitch_timeline  # timeline がサンプリングされる


def _valid_llm_json() -> str:
    return json.dumps({
        "content": {"score": 150, "comment": "良い"},   # 範囲外 → clamp 確認
        "structure": {"score": 60, "comment": "普通"},
        "strengths": ["具体例"],
        "improvements": ["結論先出し"],
    })


def test_llm_evaluation_parses_and_clamps(monkeypatch) -> None:
    monkeypatch.setattr(llm_evaluation, "_call_llm", lambda _p: _valid_llm_json())
    t = Transcript(full_text="本日はよろしくお願いします。", duration_sec=5.0, segments=[], fillers=[])  # noqa: E501
    m = AudioMetrics(
        speech_rate_cpm=300.0, filler_count=0, filler_rate=0.0, silence_ratio=0.1,
        silence_segments=[], pitch_mean=140.0, pitch_std=25.0, volume_mean=0.05,
        volume_cv=0.4, volume_timeline=[], pitch_timeline=[],
    )

    result = asyncio.run(llm_evaluation.evaluate(t, m))

    assert result.content.score == 100  # 150 → 0-100 に丸め
    assert result.structure.score == 60
    assert result.strengths == ["具体例"]


def test_llm_evaluation_retries_then_recoverable(monkeypatch) -> None:
    calls = {"n": 0}

    def bad(_p: str) -> str:
        calls["n"] += 1
        return "not json{"

    monkeypatch.setattr(llm_evaluation, "_call_llm", bad)
    t = Transcript(full_text="x", duration_sec=1.0, segments=[], fillers=[])
    m = AudioMetrics(
        speech_rate_cpm=0.0, filler_count=0, filler_rate=0.0, silence_ratio=0.0,
        silence_segments=[], pitch_mean=0.0, pitch_std=0.0, volume_mean=0.0,
        volume_cv=0.0, volume_timeline=[], pitch_timeline=[],
    )

    with pytest.raises(RecoverableError):
        asyncio.run(llm_evaluation.evaluate(t, m))
    assert calls["n"] == 2  # 初回 + 1リトライ


def test_llm_evaluation_refusal_is_fatal_not_retried(monkeypatch) -> None:
    # refusal/空content は FatalError（恒久）→ リトライせず即送出
    calls = {"n": 0}

    def refuse(_p: str) -> str:
        calls["n"] += 1
        raise FatalError("LLM が評価を拒否")

    monkeypatch.setattr(llm_evaluation, "_call_llm", refuse)
    t = Transcript(full_text="x", duration_sec=1.0, segments=[], fillers=[])
    m = AudioMetrics(
        speech_rate_cpm=0.0, filler_count=0, filler_rate=0.0, silence_ratio=0.0,
        silence_segments=[], pitch_mean=0.0, pitch_std=0.0, volume_mean=0.0,
        volume_cv=0.0, volume_timeline=[], pitch_timeline=[],
    )

    with pytest.raises(FatalError):
        asyncio.run(llm_evaluation.evaluate(t, m))
    assert calls["n"] == 1  # リトライされない
