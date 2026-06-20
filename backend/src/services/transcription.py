"""Whisper API 文字起こし + フィラー抽出。

OpenAI whisper-1 を verbose_json で呼び、タイムスタンプ付きセグメントと duration を取得する。
**verbatim 方針**（ADR 004）: フィラー保持プロンプト + temperature=0 で言い淀みを残す
（既定の Whisper はフィラーを削る／誘導版は内容語に補完して捏造するため）。
フィラーは決定論パターンで char オフセットを付与（delivery 採点と UI ハイライト用）。
no_speech_prob による異常区間除去は Phase 4 改善（加藤 #22）側で精緻化する。

設計根拠: design_review_and_frontback.md §4, §5 / ADR 004 / step2_plan.md Phase 4a。
"""

from __future__ import annotations

import asyncio

from ..schemas.interview import FillerHit, Transcript, TranscriptSegment
from ._openai import get_openai_client, reraise_openai

# 日本語フィラーの簡易パターン（長い順に並べ、最長一致で二重計上を防ぐ）。
# 精緻化（形態素 + UniDic「感動詞-フィラー」）は Phase 4 改善側。
FILLER_PATTERNS = [
    "えーと", "ええと", "あのー", "そのー", "えー", "あの", "その", "まあ", "なんか",
]

# Whisper にフィラー保持を促す verbatim プロンプト（スタイル誘導）。
_VERBATIM_PROMPT = (
    "えーと、あのー、まあ、なんか、その、といったフィラーも省略せずそのまま書き起こす。"
)


def find_fillers(text: str) -> list[FillerHit]:
    """full_text 内のフィラー出現を最長一致・非重複で列挙する。"""
    hits: list[FillerHit] = []
    i = 0
    n = len(text)
    while i < n:
        matched = next((p for p in FILLER_PATTERNS if text.startswith(p, i)), None)
        if matched:
            hits.append(FillerHit(text=matched, start_char=i, end_char=i + len(matched)))
            i += len(matched)
        else:
            i += 1
    return hits


def _call_whisper(audio_path: str):
    client = get_openai_client(for_transcription=True)
    with open(audio_path, "rb") as f:
        return client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ja",
            temperature=0,
            prompt=_VERBATIM_PROMPT,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )


async def transcribe(audio_path: str) -> Transcript:
    import openai

    try:
        # ブロッキング HTTP 呼び出しは別スレッドへ（async ループを塞がない）
        resp = await asyncio.to_thread(_call_whisper, audio_path)
    except openai.OpenAIError as e:
        reraise_openai(e)

    full_text = resp.text or ""
    segments = [
        TranscriptSegment(start=float(s.start), end=float(s.end), text=s.text)
        for s in (getattr(resp, "segments", None) or [])
    ]
    # duration は verbose_json に含まれる。無ければ最終セグメント終端で代替。
    duration = getattr(resp, "duration", None)
    if duration is not None:
        duration_sec = float(duration)
    else:
        duration_sec = segments[-1].end if segments else 0.0

    return Transcript(
        full_text=full_text,
        duration_sec=duration_sec,
        segments=segments,
        fillers=find_fillers(full_text),
    )
