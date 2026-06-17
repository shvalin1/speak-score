# ADR 003 — スコアリング2系統分離（算出系 / LLM系）

- **状態**: 確定（2026-06-16）
- **決定**: `dimensions` を2系統に分ける。
  - **算出系（delivery / confidence）**: librosa 特徴量から固定式で**決定論的**に算出（`services/scoring.py`）。同じ動画→同じ点数。
  - **LLM系（content / structure）**: 意味判断が要るため LLM が採点（`services/llm_evaluation.py`・temperature=0）。
  - 各 `Dimension.source`（computed / llm）で算出根拠を透明化。
- **背景**: 「点数は機械的・コメントはLLM」という当初原則は content/structure（意味判断）で破綻するため修正。
- **売り**: 一貫性は算出系が決定論であることに置く（差別化の核）。
- **根拠**: `design_review_and_frontback.md` §4。
