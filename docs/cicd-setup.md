# CD（継続的デプロイ）セットアップ手順

main へ push/merge すると、変更のあったサービスを **Cloud Build でビルド → `gcloud run deploy`
で差し替え**る。認証は **Workload Identity Federation（WIF）**＝GitHub に長期鍵を置かない。

- ワークフロー: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
- WIF/権限の terraform: `infra/terraform/environments/main/cicd.tf`
- ビルド定義: `infra/docker/cloudbuild.backend.yaml` / `cloudbuild.frontend.yaml`

---

## 仕組み（要点）

- **方式選定**: terraform state はローカル・tfvars は gitignored のため、CI に state を持ち込まない
  「`gcloud run deploy` 方式」を採用。terraform はインフラの土台を所有し、**image は CD が所有**する。
- **digest drift 対策**: `run.tf` の両サービスに `lifecycle { ignore_changes = [template[0].containers[0].image] }`
  を入れてあるので、CD がデプロイした後に `terraform apply` しても **image は巻き戻らない**。
  （tfvars の `*_image` は初回作成時のみ使われる値になった。）
- **差分ビルド**: `backend/**` 変更時のみ backend、`frontend/**`・`shared/**` 変更時のみ frontend を
  ビルド＆デプロイ（backend は重いので無駄打ちを避ける）。`workflow_dispatch`（手動）は両方強制。

---

## 一度だけやるセットアップ

### 1. WIF と deployer SA を作成（terraform apply）

state はローカルにあるので、**この端末で**実行する。

```bash
cd infra/terraform/environments/main
terraform apply   # cicd.tf の WIF Pool/Provider・deployer SA・IAM が追加される
```

> apply は `run.tf` の `ignore_changes` 追加も反映する（image 差分は出ない）。

### 2. 出力値を取得

```bash
terraform output workload_identity_provider   # → WIF_PROVIDER
terraform output deployer_sa_email            # → WIF_SERVICE_ACCOUNT
```

### 3. GitHub リポジトリに Secrets を登録

`Settings → Secrets and variables → Actions → New repository secret` で5つ:

| Secret | 値 |
|--------|----|
| `WIF_PROVIDER` | `terraform output workload_identity_provider` の値 |
| `WIF_SERVICE_ACCOUNT` | `terraform output deployer_sa_email` の値 |
| `VITE_FIREBASE_API_KEY` | `frontend/.env.local` と同じ（Firebase Web の public 値） |
| `VITE_FIREBASE_AUTH_DOMAIN` | 同上 |
| `VITE_FIREBASE_PROJECT_ID` | 同上 |

> Firebase Web 設定はクライアントに配布される public 値だが、ログ露出を避けるため Secret に置く。

### 4. 動作確認

- 手動: Actions タブ → **Deploy** → `Run workflow`（両サービス強制デプロイ）。
- 自動: 次の main マージで、変更したサービスが自動デプロイされる。

---

## セキュリティ設計（最小権限）

- **WIF は main ブランチ限定**: provider の `attribute_condition` で `repository == shvalin1/speak-score`
  かつ `ref == refs/heads/main` のトークンのみ受理。他リポジトリ・他ブランチ・PR・fork は
  deployer になりすませない。→ workflow_dispatch（手動）も **main 上で**実行すること。
- **deployer の権限は対象限定**:
  - `serviceAccountUser` はプロジェクト全体でなく **speak-score-run と デフォルトcompute SA の2つだけ**。
  - Storage は **`gs://<project>_cloudbuild`（ビルドのソース staging）への objectAdmin のみ**。
    uploads バケット（ユーザー動画）には触れない。
  - 他は `run.developer` / `cloudbuild.builds.editor` / `logging.viewer`（ログ閲覧）のみ。

## 運用メモ

- **tfvars の digest は普段触らなくてよい**（CD が image を所有）。インフラ構成（env/SA/CPU 等）を
  変えるときだけ `terraform apply` する。
- **WIF Pool/Provider は削除後30日ソフトデリート**され同じIDを即再利用できない（作り直し時の注意）。
- CI（lint/test/build）は別ワークフロー `ci.yml`。Deploy は CI の成否を待たない独立トリガなので、
  必要なら将来 `needs:` や branch protection で「CI 緑のみデプロイ」に締められる。
