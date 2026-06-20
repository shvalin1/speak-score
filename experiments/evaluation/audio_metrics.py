"""librosa 音声メトリクス スパイク（Step2 audio_analysis の試作・src には入れない）。

目的: 実音声 or 合成音声に対して librosa で話速/フィラー率/無音/ピッチ/音量を算出し、
結果を JSON で目視する。top_db や帯の感度をローカルで触って詰めるための実験台。

使い方:
  # サンプル音声を合成して即実行（ファイル/ffmpeg 不要）
  uv run python _ai/spike/audio_metrics.py --gen-sample /tmp/sample.wav

  # 手元の wav/flac を解析（mp4/mov は先に ffmpeg で wav 化: 下の extract_to_wav）
  uv run python _ai/spike/audio_metrics.py --audio /path/to/speech.wav --chars 250

  # 動画から抽出して解析（ffmpeg 必須）
  uv run python _ai/spike/audio_metrics.py --video /path/to/interview.mp4 --chars 250

注意: speech_rate_cpm は「文字数 ÷ 発話秒数 × 60」。文字数は本番では transcript 由来。
ここでは --chars で手入力（未指定なら無音以外の総秒数からの粗い推定は出さず None）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def gen_sample_wav(path: str, sr: int = 16000, seconds: float = 12.0) -> None:
    """発話っぽい合成音声（有声区間=変調ノイズ＋基音、所々に無音）を WAV で書く。"""
    import soundfile as sf

    rng = np.random.default_rng(0)
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    # 基音 130Hz 付近を緩く揺らす（抑揚っぽさ）
    f0 = 130 + 15 * np.sin(2 * np.pi * 0.3 * t)
    voiced = 0.25 * np.sin(2 * np.pi * np.cumsum(f0) / sr)
    voiced += 0.05 * rng.standard_normal(t.shape)  # 子音っぽいノイズ
    # 発話/無音のエンベロープ（数フレーズ＋ポーズ）
    env = np.zeros_like(t)
    for start, end in [(0.3, 2.8), (3.4, 6.0), (6.0, 6.5), (7.2, 9.5), (10.0, 11.7)]:
        env[(t >= start) & (t < end)] = 1.0
    # ポーズ(6.5-7.2, 9.5-10.0)は env=0 のまま → 無音
    sig = (voiced * env).astype(np.float32)
    sf.write(path, sig, sr)


def extract_to_wav(video_path: str, sr: int = 16000) -> str:
    """ffmpeg で動画→mono wav（本番は FLAC mono16k 相当）。tmp パスを返す。"""
    out = tempfile.mktemp(suffix=".wav")
    cmd = ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", str(sr), "-vn", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def analyze(wav_path: str, chars: int | None, top_db: int) -> dict:
    import librosa

    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    total_sec = len(y) / sr

    # --- 無音/有声区間（top_db が肝。実データでチューニング必要） ---
    intervals = librosa.effects.split(y, top_db=top_db)  # 有声区間 [start,end] サンプル
    voiced_sec = sum((e - s) for s, e in intervals) / sr
    silence_sec = max(0.0, total_sec - voiced_sec)
    silence_ratio = silence_sec / total_sec if total_sec else 0.0
    silence_segments = []
    prev_end = 0
    for s, e in intervals:
        if s - prev_end > 0.15 * sr:  # 150ms 以上のギャップを無音とみなす
            silence_segments.append({"start": round(prev_end / sr, 2), "end": round(s / sr, 2)})
        prev_end = e
    if total_sec - prev_end / sr > 0.15:
        silence_segments.append({"start": round(prev_end / sr, 2), "end": round(total_sec, 2)})

    # --- ピッチ（yin。無声/無音は除外して統計） ---
    f0 = librosa.yin(y, fmin=70, fmax=400, sr=sr)
    f0_voiced = f0[np.isfinite(f0)]
    pitch_mean = float(np.mean(f0_voiced)) if f0_voiced.size else 0.0
    pitch_std = float(np.std(f0_voiced)) if f0_voiced.size else 0.0

    # --- 音量（RMS） ---
    rms = librosa.feature.rms(y=y)[0]
    volume_mean = float(np.mean(rms))
    volume_cv = float(np.std(rms) / (np.mean(rms) + 1e-9))

    # --- 話速（文字数 ÷ 発話秒数 × 60）。chars 未指定なら None ---
    speech_rate_cpm = None
    if chars is not None and voiced_sec > 0:
        speech_rate_cpm = round(chars / voiced_sec * 60, 1)

    return {
        "params": {"top_db": top_db, "chars": chars},
        "total_sec": round(total_sec, 2),
        "voiced_sec": round(voiced_sec, 2),
        "silence_ratio": round(silence_ratio, 3),
        "silence_segments": silence_segments,
        "speech_rate_cpm": speech_rate_cpm,
        "pitch_mean": round(pitch_mean, 1),
        "pitch_std": round(pitch_std, 1),
        "volume_mean": round(volume_mean, 4),
        "volume_cv": round(volume_cv, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--audio", help="wav/flac パス")
    g.add_argument("--video", help="mp4/mov 等（ffmpeg で抽出）")
    g.add_argument("--gen-sample", metavar="OUT", help="合成サンプルwavを書いて解析")
    ap.add_argument("--chars", type=int, default=None, help="発話の文字数（話速算出用）")
    ap.add_argument("--top-db", type=int, default=30, help="無音判定の閾値(小さいほど無音判定が厳しい)")
    args = ap.parse_args()

    if args.gen_sample:
        gen_sample_wav(args.gen_sample)
        print(f"[gen] wrote synthetic sample: {args.gen_sample}", file=sys.stderr)
        wav = args.gen_sample
    elif args.video:
        wav = extract_to_wav(args.video)
        print(f"[ffmpeg] extracted: {wav}", file=sys.stderr)
    else:
        wav = args.audio
        if not Path(wav).exists():
            print(f"not found: {wav}", file=sys.stderr)
            return 1

    result = analyze(wav, args.chars, args.top_db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
