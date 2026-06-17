"""LLM評価（content/structure の採点 + strengths/improvements 生成）。

算出系(delivery/confidence)は scoring.py が担当。ここは意味判断が要る2軸＋自由記述のみ。
TODO(石川/Step2): Claude tool_use / OpenAI structured outputs で JSON を強制（temperature=0）、
スキーマ不一致・タイムアウトは1回リトライ→失敗で RecoverableError。
現状はパイプライン配線確認用のダミーを返す。
設計根拠: design_review_and_frontback.md §4, §5（services/llm_evaluation.py）
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas.interview import (
    AudioMetrics,
    Dimension,
    DimensionSource,
    Transcript,
)


@dataclass
class LlmEvaluation:
    content: Dimension
    structure: Dimension
    strengths: list[str]
    improvements: list[str]


async def evaluate(transcript: Transcript, metrics: AudioMetrics) -> LlmEvaluation:
    # --- DUMMY（Step2で LLM 実呼び出しに差し替え） ---
    return LlmEvaluation(
        content=Dimension(
            score=75,
            comment="（ダミー）具体的なエピソードはあるが結論が後半に来ている。",
            source=DimensionSource.llm,
        ),
        structure=Dimension(
            score=68,
            comment="（ダミー）PREP法の観点で結論を冒頭に置くと改善する。",
            source=DimensionSource.llm,
        ),
        strengths=["（ダミー）具体例を交えて話せている"],
        improvements=["（ダミー）結論から話す", "（ダミー）フィラーを減らす"],
    )
