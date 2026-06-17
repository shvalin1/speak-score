"""librosa による音声特徴量抽出（FLACをsoundfileで高速ロード）。

TODO(石川/Step2): librosa で話速・フィラー率・無音分布・ピッチ変動・音量を算出する。
  - silence: librosa.effects.split（top_db は実データでチューニング §7 #6）
  - pitch: librosa.yin / volume: librosa.feature.rms
  - speech_rate_cpm: 句読点・空白を除いた文字数 ÷ 発話秒数 × 60（参考値）
現状はパイプライン配線確認用のダミー AudioMetrics を返す。
設計根拠: design_review_and_frontback.md §5（services/audio_analysis.py）, §4
"""

from __future__ import annotations

from ..schemas.interview import AudioMetrics, Segment, TimePoint, Transcript


def analyze_audio(flac_path: str, transcript: Transcript) -> AudioMetrics:
    # --- DUMMY（Step2で librosa 実計算に差し替え） ---
    return AudioMetrics(
        speech_rate_cpm=380.0,
        filler_count=len(transcript.fillers),
        filler_rate=len(transcript.fillers) / max(transcript.duration_sec / 60.0, 1e-6),
        silence_ratio=0.2,
        silence_segments=[Segment(start=3.0, end=3.4)],
        pitch_mean=140.0,
        pitch_std=28.0,
        volume_mean=0.06,
        volume_cv=0.45,
        volume_timeline=[TimePoint(t=0.0, value=0.05), TimePoint(t=4.0, value=0.07)],
        pitch_timeline=[TimePoint(t=0.0, value=138.0), TimePoint(t=4.0, value=145.0)],
    )
