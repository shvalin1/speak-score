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
FILLER_PATTERNS = [
    "えーと", "ええと", "えっと", "あのー", "そのー", "えー", "あの", "その", "まあ", "なんか",
]

# 形態素解析で文脈判定する対象（「あの人」のような真の連体詞用法と区別が必要な語のみ）。
# まあ/なんか/えーと等は曖昧性が低く、unidic-lite のPOSタグも不安定なためパターンマッチのみで扱う
# （実測: experiments/evaluation/diarization_compare.ipynb の精度比較セル参照）。
_AMBIGUOUS_DETERMINERS = ("あの", "その")

# Whisper にフィラー保持を促す verbatim プロンプト（スタイル誘導）。
_VERBATIM_PROMPT = (
    "えーと、あのー、まあ、なんか、その、といったフィラーも省略せずそのまま書き起こす。"
)

_tagger = None


def _get_tagger():
    """fugashi(MeCab)+unidic-lite の遅延初期化（モジュールロード時のDLは無し・軽量）。"""
    global _tagger
    if _tagger is None:
        import fugashi

        _tagger = fugashi.Tagger()
    return _tagger


def _ambiguous_determiner_spans(text: str) -> set[tuple[int, int]]:
    """「あの/その」のうち、真の連体詞用法（直後に名詞等が続く＝フィラーでない）の char span を返す。

    unidic-lite の品詞タグ（連体詞 / 感動詞-フィラー）は「あの人」のような文脈でも揺れて信頼できないため、
    判定はタグに依らず「直後トークンが補助記号（読点等）か文末か」のみで行う。
    fugashi は空白を読み飛ばすため、トークンの実位置は text.find で復元する
    （Whisper の verbose_json は文中に余分な空白を挟むことがある）。
    """
    tagger = _get_tagger()
    tokens = list(tagger(text))
    spans: list[tuple[int, int]] = []
    cursor = 0
    for tok in tokens:
        s = text.find(tok.surface, cursor)
        e = s + len(tok.surface)
        spans.append((s, e))
        cursor = e

    exclude: set[tuple[int, int]] = set()
    for i, tok in enumerate(tokens):
        if tok.surface not in _AMBIGUOUS_DETERMINERS:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        is_filler_context = nxt is None or nxt.feature.pos1 == "補助記号"
        if not is_filler_context:
            exclude.add(spans[i])
    return exclude


def find_fillers(text: str) -> list[FillerHit]:
    """full_text 内のフィラー出現を最長一致・非重複で列挙する。

    「あの/その」は形態素解析で直後の文脈を見て、真の連体詞用法（例: 「あの人」）を除外する
    （実測で誤検出を減らせることを確認済み。他のパターンは曖昧性が低く対象外）。
    """
    exclude_spans = _ambiguous_determiner_spans(text)
    hits: list[FillerHit] = []
    i = 0
    n = len(text)
    while i < n:
        matched = next((p for p in FILLER_PATTERNS if text.startswith(p, i)), None)
        if matched:
            span = (i, i + len(matched))
            if matched in _AMBIGUOUS_DETERMINERS and span in exclude_spans:
                i += len(matched)
                continue
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
