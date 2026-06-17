# AGENTS.md — SpeakScore

> 全AIエージェント（Claude Code / Cursor / Antigravity / Copilot）がこのリポジトリで最初に読むルール。
> ルールの実体はこのファイルに置く。`CLAUDE.md` / `.cursorrules` / `.github/copilot-instructions.md` は参照のみ。

## Project

**SpeakScore** — 就活面接動画のAIフィードバックツール。動画をアップロードすると
文字起こし・音声分析・評価・改善点を返す。テーマ:「運に頼らず、実力で内定を掴む」。
詳細設計は docs Vault の `design_review_and_frontback.md`（v2・確定）が出典。

- 石川: バックエンド・インフラ・設計 / 加藤: フロントエンド（React + TS）

## Tech Stack

- Frontend: React 19 + TypeScript + Vite / recharts / Firebase Auth（匿名）
- Backend: FastAPI + Python 3.12 / ffmpeg + librosa + Whisper API + Claude/GPT API
- Async: Cloud Tasks worker（scale-to-zero と本物の非同期を両立）
- Store: Firestore (Native) / GCS（動画一時保存・1日で自動削除）
- Infra: GCP Cloud Run ×2（backend / frontend+Nginx）/ Terraform / 全リソース `us-central1`
- Monorepo: Turborepo + uv / CI: GitHub Actions

## Commands

```bash
# frontend（モックモードでバックエンド不要）
cd frontend && npm install && VITE_USE_MOCK=1 npm run dev
cd frontend && npm run build           # tsc -b && vite build
cd frontend && npm run typecheck

# backend
cd backend && uv sync                   # API/health のみ（軽い）
cd backend && uv sync --extra audio --extra llm   # worker 用（重い）
cd backend && AUTH_DISABLED=1 uv run uvicorn src.main:app --reload --port 8080
cd backend && uv run pytest
cd backend && uv run ruff check src/

# まとめて（ローカル一式・本番と同構図）
docker compose -f infra/docker/docker-compose.yml up
```

## Architecture Rules

- **API契約は凍結成果物**: `backend/src/schemas/interview.py`（Pydantic）が唯一の出典。
  `frontend/src/types/interview.ts` はその TS ミラー。**片方だけ変えない**（必ず両方）。
- ビジネスロジックは `services/` に置く。`api/` ルーターは service/repo を呼ぶだけ。
- 入出力の型は `schemas/`（Pydantic）と `types/`（TypeScript）に集約。フロントの型は石川が定義→加藤が従う。
- **スコアリングは2系統**: delivery/confidence は `services/scoring.py` で決定論算出（computed）、
  content/structure は `services/llm_evaluation.py` で LLM 採点（llm）。各 Dimension に `source` を持たせる。
- 非同期は Cloud Tasks worker（`POST /api/tasks/process`・OIDC）。worker は Nginx を通らず backend 直叩き。
- 認証は Firebase IDトークンを backend が検証し `owner_uid` でスコープ化。worker は Cloud Tasks の OIDC。
- インフラ変更は必ず Terraform（手動変更禁止）。Firebase Auth 有効化のみコンソール手動（Terraform外）。

## Coding Standards

- Python: ruff（format + lint）、type hints 必須、docstring 推奨。`X | None` / `list[...]` を使う。
- TypeScript: strict、`any` 禁止、関数コンポーネントのみ。
- 重い依存（librosa / firebase_admin / google-cloud-*）は **関数内で遅延 import**（API/health を軽く保つ）。
- コミット: Conventional Commits（feat/fix/docs/chore/infra/refactor/test）。

## File Conventions

- `backend/src/` … main.py / api/ / services/ / schemas/ / repositories/ / core/
- `frontend/src/` … types/ / services/（api.ts・auth.ts）/ hooks/ / components/
- `shared/mock_data/sample_result.json` … フロント開発用モック（`AnalysisResult` 準拠）。`@shared` で参照。
- `infra/terraform/` … 単一環境（dev/prod 分割なし）。`infra/docker/` … ローカル compose。
- `docs/specs|plans|adr|ai_log/` … 仕様・計画・意思決定・AIログ。

## 並行開発の現状（Step）

- Step0（済）: API契約凍結（schemas/types/sample_result.json/モックapi.ts）→ 加藤のUI着手を解放。
- Step1b（次）: インフラ最小ループを本番経路で一周（GCS+Cloud Tasks+worker雛形+OIDC、ダミー結果）。
- Step2: pipeline 中身（ffmpeg→FLAC→Whisper→librosa→scoring→LLM）を雛形に流し込む。
- `services/{transcription,audio_analysis,llm_evaluation}.py` と `repositories/job_repo.FirestoreJobRepo`、
  `core/{storage,tasks,auth}.py` の本番経路には `TODO(Step1b/Step2)` を明示。スタブは契約を満たすダミーを返す。
