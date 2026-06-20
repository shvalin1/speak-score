"""librosa による音声特徴量抽出（WAV mono16k を librosa でロード）。

experiments/evaluation/audio_metrics.py で実証したロジックを backend に移植した暫定実装。
  - silence: librosa.effects.split（top_db は実データでチューニング §7 #6・改善は加藤側）
  - pitch: librosa.yin / volume: librosa.feature.rms
  - speech_rate_cpm: transcript の句読点・空白除外文字数 ÷ 発話秒数 × 60（参考値）
timeline は約1秒間隔にサンプリング（repo 側で 200 点に間引かれる）。

設計根拠: design_review_and_frontback.md §4, §5 / step2_plan.md Phase 4b。
"""

from __future__ import annotations

import numpy as np

from ..schemas.interview import AudioMetrics, Segment, TimePoint, Transcript

_SR = 16000
_TOP_DB = 30          # 無音判定閾値（小さいほど無音判定が厳しい・実測調整前提）
_SILENCE_GAP = 0.15   # 150ms 以上のギャップを無音セグメントとみなす
_YIN_FRAME = 2048     # librosa.yin の既定フレーム長。これ未満の極短音声では yin をスキップ
# 句読点・空白（話速の文字数からは除外する）
_PUNCT = set(
    "、。．，・！？!?…「」『』（）()【】 　\n\t"
)


def _count_speech_chars(text: str) -> int:
    return sum(1 for ch in text if ch not in _PUNCT)


def _sample_timeline(
    values: np.ndarray, times: np.ndarray, step_sec: float = 1.0
) -> list[TimePoint]:
    """フレーム系列を step_sec 間隔に間引いて TimePoint 列にする。"""
    if values.size == 0:
        return []
    out: list[TimePoint] = []
    next_t = 0.0
    for t, v in zip(times, values, strict=False):
        if t >= next_t and np.isfinite(v):
            out.append(TimePoint(t=round(float(t), 2), value=round(float(v), 4)))
            next_t = t + step_sec
    return out


def analyze_audio(audio_path: str, transcript: Transcript) -> AudioMetrics:
    import librosa

    y, sr = librosa.load(audio_path, sr=_SR, mono=True)
    total_sec = len(y) / sr if sr else 0.0

    # --- 無音/有声区間 ---
    intervals = librosa.effects.split(y, top_db=_TOP_DB) if y.size else np.empty((0, 2), dtype=int)
    voiced_sec = sum((e - s) for s, e in intervals) / sr if sr else 0.0
    silence_ratio = max(0.0, (total_sec - voiced_sec) / total_sec) if total_sec else 0.0
    silence_segments: list[Segment] = []
    prev_end = 0
    for s, e in intervals:
        if (s - prev_end) > _SILENCE_GAP * sr:
            silence_segments.append(Segment(start=round(prev_end / sr, 2), end=round(s / sr, 2)))
        prev_end = e
    if total_sec - prev_end / sr > _SILENCE_GAP:
        silence_segments.append(Segment(start=round(prev_end / sr, 2), end=round(total_sec, 2)))

    # --- ピッチ（yin） ---
    # 注: librosa.yin は pyin と違い非有声フレームでも値を返すため、無音/無声のピッチも
    # 統計に混入する（finite フィルタは NaN/inf 除けのみ）。精度チューニング（有声判定）は
    # 別レーン（加藤 #22）。frame 長未満の極短音声は ParameterError を避けてスキップ。
    if y.size >= _YIN_FRAME:
        f0 = librosa.yin(y, fmin=70, fmax=400, sr=sr)
        f0_times = librosa.times_like(f0, sr=sr)
    else:
        f0 = np.empty(0)
        f0_times = np.empty(0)
    f0_voiced = f0[np.isfinite(f0)]
    pitch_mean = float(np.mean(f0_voiced)) if f0_voiced.size else 0.0
    pitch_std = float(np.std(f0_voiced)) if f0_voiced.size else 0.0

    # --- 音量（RMS） ---
    if y.size:
        rms = librosa.feature.rms(y=y)[0]
        rms_times = librosa.times_like(rms, sr=sr)
    else:
        rms = np.empty(0)
        rms_times = np.empty(0)
    volume_mean = float(np.mean(rms)) if rms.size else 0.0
    volume_cv = float(np.std(rms) / (np.mean(rms) + 1e-9)) if rms.size else 0.0

    # --- 話速（句読点除外文字数 ÷ 発話秒数 × 60） ---
    speech_chars = _count_speech_chars(transcript.full_text)
    speech_rate_cpm = round(speech_chars / voiced_sec * 60, 1) if voiced_sec > 0 else 0.0

    # --- フィラー（transcript 由来・/分） ---
    filler_count = len(transcript.fillers)
    filler_rate = round(filler_count / (total_sec / 60.0), 2) if total_sec > 0 else 0.0

    return AudioMetrics(
        speech_rate_cpm=speech_rate_cpm,
        filler_count=filler_count,
        filler_rate=filler_rate,
        silence_ratio=round(silence_ratio, 3),
        silence_segments=silence_segments,
        pitch_mean=round(pitch_mean, 1),
        pitch_std=round(pitch_std, 1),
        volume_mean=round(volume_mean, 4),
        volume_cv=round(volume_cv, 3),
        volume_timeline=_sample_timeline(rms, rms_times),
        pitch_timeline=_sample_timeline(f0, f0_times),
    )
