"""パイプラインのエラー分類。

worker(api/tasks.py) はこの分類で再試行/失敗を切り分ける:
- RecoverableError → 一時的失敗。503 を返し Cloud Tasks に再試行させる（max_attempts=3）。
- FatalError → 恒久的失敗。再試行しても直らない（壊れ動画・長尺・サイズ超過・content_type欠落等）。
  worker の汎用 except に拾われ repo.fail に倒す。

pipeline から参照すると api/tasks.py との循環 import になるため、ここに切り出す。
設計根拠: design_review_and_frontback.md §5.1 / step2_plan.md 横断「エラー分類」。
"""

from __future__ import annotations


class RecoverableError(Exception):
    """一時的失敗。Cloud Tasks に再試行させる（worker が 5xx を返す）。"""


class FatalError(Exception):
    """恒久的失敗。再試行しても直らないため即 fail に倒す。"""
