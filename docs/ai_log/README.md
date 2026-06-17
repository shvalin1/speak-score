# ai_log

AIエージェント（Claude Code / Cursor / Antigravity / Copilot）とのやり取りの要約ログ。

- 1セッション＝1エントリを目安に、何を依頼し何を決めたかを短く残す。
- 詳細な試行錯誤ログ（cursor の jsonl 等）は `_ai/`（gitignore対象）に置く。ここには要約のみ。
- 設計の意思決定は docs Vault（`design_review_and_frontback.md` / `qa_log.md`）が一次情報。
