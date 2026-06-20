"""ffmpeg/ffprobe による動画→音声変換ユーティリティ（worker 用）。

面接動画から音声を取り出し、transcription API が受け付ける WAV mono 16kHz に変換する。
FLAC は現行 transcription API 非対応のため WAV を採用（step2_plan.md HIGH 参照）。

失敗の扱い: ffprobe/ffmpeg の異常終了は「壊れ動画/非対応形式」= 恒久的失敗とみなし
FatalError を投げる（再試行しても直らない）。一時的 I/O（GCS DL 等）の分類は呼び出し側で行う。
設計根拠: design_review_and_frontback.md §5.1 / step2_plan.md Phase 1。
"""

from __future__ import annotations

import subprocess

from .errors import FatalError

# 抽出パラメータ: mono(-ac 1) / 16kHz(-ar 16000) / 映像破棄(-vn)
_SAMPLE_RATE = 16000


def probe_duration(path: str) -> float:
    """動画/音声の長さ（秒）を ffprobe で取得する。"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise FatalError(f"ffprobe failed: {e.stderr.strip()[:500]}") from e
    out = proc.stdout.strip()
    try:
        return float(out)
    except ValueError as e:
        raise FatalError(f"ffprobe returned no duration: {out!r}") from e


def extract_to_wav(src_path: str, dest_path: str) -> None:
    """src（動画/音声）を WAV mono 16kHz に変換し dest に書き出す。"""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-ac",
        "1",
        "-ar",
        str(_SAMPLE_RATE),
        "-vn",
        dest_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise FatalError(f"ffmpeg failed: {e.stderr.strip()[:500]}") from e
