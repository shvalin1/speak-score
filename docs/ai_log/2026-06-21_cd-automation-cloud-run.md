# 2026-06-21 CD 自動化（GitHub Actions → Cloud Run）の振り返り

担当: 石川 + Claude Code（Opus 4.8）
範囲: main へ push/merge で Cloud Run へ自動デプロイする CD の構築。WIF 認証・最小権限・差分ビルド。
一次情報: 構成は `.github/workflows/deploy.yml` / `infra/terraform/environments/main/cicd.tf` / 手順書 `docs/cicd-setup.md`。本ファイルは「何で躓き・なぜ・どう方針転換したか」の要約。

関連 PR: #29（初版）/ #30（方針転換の修正）。

---

## ゴールと最初の設計判断

前提として **terraform state はローカル・tfvars は gitignored**。ここが CD 設計の分かれ目になった。

ユーザー選択で次の3点を確定:

1. **デプロイ方式 = `gcloud run deploy` 方式**（terraform apply 方式ではない）。
   state を CI に持ち込まず、CD は「イメージをビルド → `gcloud run deploy` で差し替え」だけを行う。
   terraform=インフラ所有 / CD=image 所有 に分離。
2. **認証 = Workload Identity Federation（WIF）**。長期鍵を GitHub に置かない。
3. **トリガ = main へ push/merge で自動（＋ workflow_dispatch 手動）**。

派生する重要設計:

- **digest-drift の罠を `ignore_changes` で根絶**: `run.tf` の両 Cloud Run に
  `lifecycle { ignore_changes = [template[0].containers[0].image] }` を入れた。
  これが無いと、CD がデプロイした後に `terraform apply` すると tfvars の digest pin に
  **image が巻き戻る**。image は CD が所有、terraform は触らない、を物理的に保証した。
- **差分ビルド**: backend は `shared` を import しないので `backend/**` のみ、
  frontend は `frontend/**`・`shared/**` のみでジョブ起動。手動実行は両方強制。

---

## 躓いたところ と 原因

### 1. 【最大の躓き】WIF + `gcloud builds submit` の quota project 相性問題

- 症状: PR #29 をマージ → 初回 CD が走るも、**両ジョブとも `gcloud builds submit` で即失敗**:
  ```
  ERROR: The user is forbidden from accessing the bucket [speak-score-app_cloudbuild].
  ... if the user has the "serviceusage.services.use" permission.
  ```
- 切り分け: **WIF 認証ステップ自体は成功**（auth ✓）。エラーは Cloud Build の
  **ソースステージング**（`gs://<project>_cloudbuild` への Storage API アクセス）で発生。
- 第一の対処（不発）: deployer SA に `roles/serviceusage.serviceUsageConsumer` を付与、
  さらに staging バケットへ `storage.admin`（buckets.get 込み）を付与。
  → **IAM を正しく付与し5分以上伝播待ちしても同じエラー**。
- 真因: これは **WIF の SA 資格情報と `gcloud builds submit` の quota project の相性問題**。
  Storage API が要求する billing/quota project の解決が外部アカウント資格でうまくいかず、
  `serviceusage.services.use` チェックを通せない。IAM の問題ではないので権限追加では直らない。
- **方針転換（PR #30）**: Cloud Build を CD 経路から外し、**GitHub ランナー上で
  `docker build` → Artifact Registry へ push → `gcloud run deploy`** に変更。
  ランナーには Docker があり、staging バケットと serviceusage 依存を丸ごと回避できる。
  - 認証: `gcloud auth configure-docker <region>-docker.pkg.dev` の credential helper が
    WIF 由来の SA トークンを使うので、AR への `docker push` がそのまま通る。
  - 焦って IAM をいじり続ける前に **gpt-reviewer に方針をレビュー**させ「妥当・ブロッカー無し」を確認してから着手した。

### 2. アップロード/ビルドコンテキストの肥大（衛生）

- `backend/.venv`（584M）・`.env` が Cloud Build / docker のコンテキストに混入しうる問題。
- 対処: `.gcloudignore`（手動 Cloud Build 用）と `.dockerignore` / `backend/.dockerignore`
  （ランナー docker build 用）を整備。frontend は context=リポジトリルートなので
  `.git`・venv・秘密の混入とビルド遅延を防ぐ（gpt-reviewer 指摘）。
  ※ ランナーは fresh checkout で venv/node_modules が存在しない（gitignore）ため実害は小さいが、防御的に絞った。

### 3. セキュリティ: WIF と権限の絞り込み（gpt-reviewer 指摘を反映）

- **WIF を main ブランチ限定**: provider の `attribute_condition` に
  `assertion.ref == 'refs/heads/main'` を追加。他リポジトリ・他ブランチ・PR・fork は
  deployer になりすませない。→ workflow_dispatch も **main 上で**実行する前提と一致。
- **actAs をプロジェクト全体 → 対象2SAのみ**: `serviceAccountUser` は
  `speak-score-run`（backend）と デフォルト compute SA（frontend）だけに付与。
- **AR への push は repo スコープ**: `artifactregistry.writer` を `speak-score` リポジトリにだけ付与。
- 結果、deployer の最終権限は `run.developer` / `serviceUsageConsumer`（run deploy の保険）/
  `artifactregistry.writer`(repo) / `serviceAccountUser`(対象2SA) のみ。

---

## 最終構成

- **deploy.yml**: `changes`(paths-filter) → `backend` / `frontend` の3ジョブ。
  各ジョブで WIF auth → `gcloud auth configure-docker` → `docker build`/`push` → `gcloud run deploy`。
  frontend は build-arg で Firebase Web 設定（public 値）を bundle へ焼き込み、context=リポジトリルート。
  backend は context=`backend/`。
- **cicd.tf**: WIF Pool/Provider（main 限定）・deployer SA・最小権限 IAM。
- **run.tf**: 両 Cloud Run に `ignore_changes=[image]`。
- `cloudbuild.*.yaml` は CD では未使用だが、WSL に docker が無い手元の**手動ビルド用**に残置。

---

## 検証結果（最終）

- PR #30 マージで走った CD: **backend success**（`backend/.dockerignore` 変更で backend ジョブ起動）。
  → 新方式（runner docker build → AR push → run deploy）が **E2E で通ることを実証**。
- 仕上げに `workflow_dispatch`（両ジョブ強制）を実行: **frontend success / backend success**。
  → CD 完全グリーン。以降は main の変更で、変わったサービスだけ自動デプロイされる。

---

## セットアップの既成事実（再実行不要）

- `terraform apply` 済み（WIF・deployer SA・最小権限 IAM）。
- GitHub Secrets 5つ登録済み: `WIF_PROVIDER` / `WIF_SERVICE_ACCOUNT` / `VITE_FIREBASE_*`×3。

---

## こだわった点・教訓

- **state をローカルに置いたまま CD を安全に組む**: `gcloud run deploy` 方式＋`ignore_changes` で
  「terraform=インフラ / CD=image」の所有境界を物理的に分離。次の apply で巻き戻らない。
- **エラーメッセージに引っ張られない**: 「forbidden from accessing the bucket」は IAM 不足に見えるが、
  実体は WIF の quota project 問題。権限を盛り続けるより**経路を変える**のが正解だった。
- **焦って手を動かす前にレビュー**: 方針転換という大きい判断は gpt-reviewer に当ててから着手した。
- **最小権限を後追いで締める**: まず通し、gpt-reviewer 指摘で main 限定・対象SA限定・repoスコープへ収れん。
