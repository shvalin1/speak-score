# SpeakScore

就活の面接動画をアップロードすると、AIが**文字起こし・音声分析・評価・改善点**を返す
フィードバックツール。テーマ:「**運**に頼らず、実力で内定を掴む」。

> ハックツハッカソン アロカップ 2026.06 出展プロダクト（審査対象として公開）。

## これは何が違うのか（GPTラッパーとの差別化）

1. **音声特徴量の自前計算**: librosa で話速・フィラー率・無音分布・ピッチ変動を抽出（API呼び出しだけではない）。
2. **構造化スコア＋可視化**: 評価軸ごとの定量スコアをレーダーチャート/タイムラインで表示。
   **算出系（delivery/confidence）は音声特徴量から決定論的に算出、LLM系（content/structure）はLLM採点**の2分割。
3. **非同期パイプライン**: Cloud Tasks worker による非同期ジョブ管理（scale-to-zero と両立、進捗ポーリング）。

## アーキテクチャ

```
[React+TS] ──同一オリジン──> [Cloud Run: frontend(Nginx)] ──/api proxy──> [Cloud Run: backend(FastAPI)]
   署名URLでブラウザ→GCSへ動画を直接PUT。/start で Cloud Tasks に enqueue。
   worker(/api/tasks/process, OIDC) が ffmpeg→Whisper→librosa→scoring→LLM を実行し Firestore に逐次更新。
   フロントは job_id をポーリングして進捗・結果を表示。
```

| レイヤ | 技術 |
|--------|------|
| Frontend | React 19 + TypeScript + Vite / recharts / Firebase Auth（匿名） |
| Backend | FastAPI + Python 3.12 / ffmpeg + librosa + Whisper API + Claude/GPT API |
| 非同期 | Cloud Tasks worker |
| Store | Firestore (Native) / GCS（1日で自動削除） |
| Infra | GCP Cloud Run ×2 / Terraform（単一環境・`us-central1`） |
| Monorepo | Turborepo + uv / CI: GitHub Actions |

## クイックスタート

### フロントだけ（モックモード・バックエンド不要）

加藤の標準開発フロー。バックなしで全UI（進捗UI含む）が動く。
**フロント担当の着手ガイドは [`ONBOARDING.md`](./ONBOARDING.md) を参照。**

```bash
cd frontend
npm install
VITE_USE_MOCK=1 npm run dev   # http://localhost:5173
```

### バックエンド（API/health）

```bash
cd backend
uv sync                                   # API のみ（軽い）
AUTH_DISABLED=1 uv run uvicorn src.main:app --reload --port 8080
curl http://localhost:8080/api/health     # {"status":"ok"}
uv run pytest
```

### 一式（本番と同構図・同一オリジン）

```bash
docker compose -f infra/docker/docker-compose.yml up   # http://localhost:8080
```

## ディレクトリ

```
speak-score/
├── AGENTS.md          # エージェント共通ルール（最初に読む）
├── backend/           # FastAPI（api/services/schemas/repositories/core）
├── frontend/          # React+TS+Vite（types/services/hooks/components）
├── shared/mock_data/  # sample_result.json（フロント開発用モック）
├── infra/             # terraform（単一環境）/ docker（compose）/ k8s（Phase3）
└── docs/              # specs / plans / adr / ai_log
```

## ルール

開発ルール・コマンド・設計原則は [`AGENTS.md`](./AGENTS.md) を参照。



test
あいうえおかきくけこさしすせそたちつてと
できてるのかな