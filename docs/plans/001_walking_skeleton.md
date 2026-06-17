# Plan 001 — Walking Skeleton

> 目標: 動画アップロード → Cloud Tasks → worker → Firestore → ポーリング表示 が
> Cloud Run にデプロイ済みで一周すること。音声特徴量・グラフ・デザインは後回し。

## 並行開発の順序（design §7）

| 順 | 担当 | 内容 | 状態 |
|----|------|------|------|
| 0 | 石川 | API契約凍結（schemas/types/sample_result.json/モックapi.ts）＋認証ヘルパ雛形 | ✅ 済（本scaffold） |
| 1a | 加藤 | UploadZone→AnalysisProgress→Dashboard をモックで構築 | 着手可（雛形あり） |
| 1b | 石川 | **インフラ最小ループを本番経路で一周**（GCS+CORS / Cloud Tasks / worker雛形 / OIDC・ダミー結果） | TODO |
| 2 | 石川 | pipeline 中身（ffmpeg→FLAC→Whisper→librosa→scoring→LLM）を流し込む | TODO |
| 3 | 両者 | API結合（モック→実API・hookのbase切替のみ） | TODO |
| 4 | 石川 | デモ用 min-instances=1 / CI（SAキー簡易版） | TODO |
| 5+ | — | 話者分離API / api・worker分離 / WIF / 一覧UI | 技術点 |

## 本scaffoldで用意済み（Step0）

- API契約: `backend/src/schemas/interview.py` ⇄ `frontend/src/types/interview.ts`（ミラー・凍結）
- モック: `shared/mock_data/sample_result.json` ＋ `frontend/src/services/api.ts`（delay＋状態遷移、`VITE_USE_MOCK`）
- バック骨格: FastAPI（health + interviews + tasks worker）、in-memory repo、scoring.py（決定論・実装済み）
- スタブ（ダミー返却・`TODO(Step2)`）: transcription / audio_analysis / llm_evaluation / pipeline
- 本番経路スタブ（`TODO(Step1b)`）: core/storage（署名URL）、core/tasks（Cloud Tasks）、core/auth（OIDC/Firebase）、FirestoreJobRepo
- ローカル: docker-compose（Nginx+FastAPI 同一オリジン）

## Step1b で潰す罠（クリティカルパス・design §1.2, §7 #6）

- 署名URL発行→ブラウザPUT→GCS CORS（SignBlob/Content-Type一致/期限）の実機検証
- Whisper が FLAC を受けるか（撤退先 wav/m4a）
- Cloud Tasks→Cloud Run の OIDC 配線（backend public + アプリ内OIDC検証）
- FLAC の `top_db` 無音判定チューニング・抽出FLAC実サイズが25MB内か
