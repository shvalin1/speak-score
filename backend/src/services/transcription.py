"""Whisper API 文字起こし + フィラー抽出 + ハルシネーション除去。

TODO(石川/Step2): OpenAI Whisper API を呼び、タイムスタンプ付きセグメント・
no_speech_prob による異常区間除去・フィラーのパターンマッチを実装する。
現状はパイプライン配線確認用のダミー Transcript を返す。
設計根拠: design_review_and_frontback.md §5（services/transcription.py）, §4
"""

from __future__ import annotations

from ..schemas.interview import FillerHit, Transcript, TranscriptSegment

# 日本語フィラーの簡易パターン（Step2で精緻化）
FILLER_PATTERNS = ["えー", "えーと", "あのー", "あの", "その", "まあ", "なんか"]


async def transcribe(flac_path: str) -> Transcript:
    # --- DUMMY（Step2で Whisper 実呼び出しに差し替え） ---
    full_text = "本日はよろしくお願いします。えー、自己紹介をさせていただきます。"
    return Transcript(
        full_text=full_text,
        duration_sec=8.0,
        segments=[
            TranscriptSegment(start=0.0, end=3.0, text="本日はよろしくお願いします。"),
            TranscriptSegment(start=3.0, end=8.0, text="えー、自己紹介をさせていただきます。"),
        ],
        fillers=[FillerHit(text="えー", start_char=14, end_char=16)],
    )
