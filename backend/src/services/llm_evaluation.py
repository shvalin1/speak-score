"""LLM評価（content/structure の採点 + strengths/improvements 生成）。

算出系(delivery/confidence)は scoring.py が担当。ここは意味判断が要る2軸＋自由記述のみ。
OpenAI structured outputs（strict json_schema・temperature=0）で JSON を強制する。
audio_metrics は文脈として渡すが点数化はさせない（delivery 採点は scoring 側に分離）。
スキーマ不一致・パース失敗は1回リトライ→失敗で RecoverableError（再試行に倒す）。
**ガードレール: clean_text 生成等の内容捏造はさせない（採点と自由記述のみ）**。

設計根拠: design_review_and_frontback.md §4, §5 / ADR 004 / step2_plan.md Phase 4c。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from ..core.errors import FatalError, RecoverableError
from ..schemas.interview import (
    AudioMetrics,
    Dimension,
    DimensionSource,
    Transcript,
)
from ._openai import get_openai_client, reraise_openai

log = logging.getLogger(__name__)

_MODEL = "gpt-4o-2024-08-06"

_SYSTEM_PROMPT = (
    "あなたは日本語の面接スピーチを評価する採点者です。応募者の回答（文字起こし）と"
    "音声メトリクスを読み、内容(content)と構成(structure)の2軸を0-100で採点します。\n"
    "- content: 主張の具体性・説得力・質問への適合。具体例や数値の有無を重視。\n"
    "- structure: 論理の流れ。PREP法(結論→理由→具体例→結論)の観点。結論が先か。\n"
    "話速・フィラー・抑揚などの delivery 面は別系統で採点するため、ここでは点数化しないこと"
    "（ただしコメントで言及してよい）。\n"
    "採点は甘すぎず辛すぎず、根拠を comment に1-2文で日本語で書く。"
    "strengths/improvements は各2-3個、実行可能な粒度で。必ず指定の JSON スキーマで返す。"
)

# strict structured outputs 用 JSON スキーマ。
# minimum/maximum は strict 非対応のため description に明記し、
# 受領後 _clamp_score で 0-100 に丸める。
_JSON_SCHEMA = {
    "name": "interview_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "content": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "score": {"type": "integer", "description": "0-100の整数"},
                    "comment": {"type": "string"},
                },
                "required": ["score", "comment"],
            },
            "structure": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "score": {"type": "integer", "description": "0-100の整数"},
                    "comment": {"type": "string"},
                },
                "required": ["score", "comment"],
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "improvements": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content", "structure", "strengths", "improvements"],
    },
}


@dataclass
class LlmEvaluation:
    content: Dimension
    structure: Dimension
    strengths: list[str]
    improvements: list[str]


def _clamp_score(x: int) -> int:
    return max(0, min(100, int(x)))


def _build_user_prompt(transcript: Transcript, metrics: AudioMetrics) -> str:
    metrics_ctx = {
        "speech_rate_cpm": metrics.speech_rate_cpm,
        "filler_count": metrics.filler_count,
        "filler_rate": metrics.filler_rate,
        "silence_ratio": metrics.silence_ratio,
        "pitch_std": metrics.pitch_std,
        "volume_cv": metrics.volume_cv,
    }
    return (
        "# 応募者の回答（文字起こし）\n"
        f"{transcript.full_text}\n\n"
        "# 音声メトリクス（参考・点数化しない）\n"
        f"{json.dumps(metrics_ctx, ensure_ascii=False, indent=2)}\n\n"
        "上記を評価し、JSON スキーマに従って返してください。"
    )


def _call_llm(user_prompt: str) -> str:
    client = get_openai_client()
    resp = client.chat.completions.create(
        model=_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": _JSON_SCHEMA},
    )
    msg = resp.choices[0].message
    # Structured Outputs の拒否は content=None で refusal に入る。temperature=0 では
    # 恒久要因のため、リトライせず FatalError に倒す（無駄な再試行を避ける）。
    if getattr(msg, "refusal", None):
        raise FatalError(f"LLM が評価を拒否: {msg.refusal}")
    if not msg.content:
        raise FatalError("LLM 応答が空（content なし）")
    return msg.content


def _parse(raw: str) -> LlmEvaluation:
    data = json.loads(raw)
    return LlmEvaluation(
        content=Dimension(
            score=_clamp_score(data["content"]["score"]),
            comment=str(data["content"]["comment"]),
            source=DimensionSource.llm,
        ),
        structure=Dimension(
            score=_clamp_score(data["structure"]["score"]),
            comment=str(data["structure"]["comment"]),
            source=DimensionSource.llm,
        ),
        strengths=[str(s) for s in data["strengths"]],
        improvements=[str(s) for s in data["improvements"]],
    )


async def evaluate(transcript: Transcript, metrics: AudioMetrics) -> LlmEvaluation:
    import openai

    user_prompt = _build_user_prompt(transcript, metrics)
    last_exc: Exception | None = None
    # strict schema でも稀にパース不能があり得るため最大2回（初回 + 1リトライ）
    for attempt in range(2):
        try:
            raw = await asyncio.to_thread(_call_llm, user_prompt)
            return _parse(raw)
        except openai.OpenAIError as e:
            reraise_openai(e)  # API 例外は分類して即送出（リトライは Cloud Tasks 側）
        except (KeyError, ValueError, TypeError) as e:  # JSON/スキーマ不一致のみリトライ
            last_exc = e
            log.warning("LLM 出力のパースに失敗（attempt=%d）: %s", attempt + 1, e)

    raise RecoverableError(f"LLM 出力のパースに2回失敗: {last_exc}") from last_exc
