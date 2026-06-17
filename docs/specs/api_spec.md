# API 仕様

応答契約の**唯一の出典**は `backend/src/schemas/interview.py`（Pydantic）。
FastAPI が `/docs`（Swagger）/ `/openapi.json` を自動生成するので、稼働後はそちらが最新。

## エンドポイント（design §3.2）

全 `/api` は `Authorization: Bearer <Firebase IDトークン>` 必須（worker と health を除く）。

| メソッド | パス | 認証 | 正常 | 主なエラー |
|----------|------|------|------|-----------|
| POST | `/api/interviews` | Firebase | 201 `CreateInterviewResponse` | 400 / 413 / 415 |
| PUT | `<upload_url>` (GCS直) | 署名URL | 200 | — |
| POST | `/api/interviews/{job_id}/start` | Firebase | 202 `StartResponse` | 403 / 404 / 409 / 413 |
| GET | `/api/interviews/{job_id}` | Firebase | 200 `InterviewJob` | 403 / 404 |
| GET | `/api/interviews` | Firebase | 200 `InterviewSummary[]`（owner_uidで自分の分のみ） | 401 |
| POST | `/api/tasks/process` | OIDC | 200 | 403 |
| GET | `/api/health` | なし | 200 | — |

詳細・設計判断は docs Vault `design_review_and_frontback.md` §3 を参照。
