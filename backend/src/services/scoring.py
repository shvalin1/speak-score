"""決定論的スコアリング（算出系 delivery / confidence）。

同じ入力 → 同じ点数。content/structure は LLM 採点（llm_evaluation.py）。
**定数はすべて暫定ルーブリック（実測でチューニング前提）**。
設計根拠: design_review_and_frontback.md §4
"""

from ..schemas.interview import AudioMetrics, Dimensions


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def penalty_band(x: float, lo: float, hi: float, slope: float = 0.3, cap: float = 40) -> float:
    """快適帯[lo,hi]内なら0。外れた距離×slopeを減点（capで頭打ち）。"""
    if lo <= x <= hi:
        return 0.0
    dist = (lo - x) if x < lo else (x - hi)
    return min(dist * slope, cap)


def score_delivery(m: AudioMetrics) -> int:
    # cpm（文字/分）は漢字/かな比で大きくブレる「参考値」→ 帯を広く取り滅多に減点しない
    rate_pen = penalty_band(m.speech_rate_cpm, lo=200, hi=600)   # 広め（暫定・実測調整）
    filler_pen = min(m.filler_rate * 4, 40)                      # フィラー/分が多いほど減点
    silence_pen = max(0.0, (m.silence_ratio - 0.30) * 100)       # 無音3割超で減点
    return int(clamp(100 - rate_pen - filler_pen - silence_pen, 0, 100))


def score_confidence(m: AudioMetrics) -> int:
    monotone_pen = max(0.0, 40 - m.pitch_std)           # 抑揚（pitch_std）が小さいほど減点
    unstable_pen = max(0.0, (m.volume_cv - 0.5) * 60)   # 音量が不安定(cv大)なほど減点
    return int(clamp(100 - monotone_pen - unstable_pen, 0, 100))


def overall(d: Dimensions) -> int:
    w = {"content": 0.35, "structure": 0.20, "delivery": 0.25, "confidence": 0.20}
    return round(
        d.content.score * w["content"]
        + d.structure.score * w["structure"]
        + d.delivery.score * w["delivery"]
        + d.confidence.score * w["confidence"]
    )
