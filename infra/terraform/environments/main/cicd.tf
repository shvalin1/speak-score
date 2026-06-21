# === CD（GitHub Actions → GCP）の認証基盤 ===
# 方式: Workload Identity Federation（WIF）。長期鍵を GitHub に置かず、GitHub の OIDC
# トークンを信頼して deployer SA になりすます。CD は「Cloud Build でイメージをビルド →
# gcloud run deploy で差し替え」だけを行う（terraform state は CI に持ち込まない）。
# ワークフロー実体: .github/workflows/deploy.yml

# --- CD 実行用 SA（GitHub Actions がなりすます先）---
resource "google_service_account" "deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions CD deployer"
}

# deployer のプロジェクト権限（最小限）。
#  run.developer                     … Cloud Run の新リビジョンをデプロイ（image 差し替え）
#  serviceusage.serviceUsageConsumer … gcloud run deploy が quota project を使うための保険
#                                      （serviceusage.services.use を含む）
# ※ イメージは GitHub ランナー上で docker build し AR へ push する方式（cicd.tf 冒頭）。
#   Cloud Build は使わない＝WIF と gcloud builds submit の quota project 相性問題を回避。
#   AR への push 権限はリポジトリスコープで別途付与（下記）。actAs も対象SAだけに絞る。
locals {
  deployer_roles = [
    "roles/run.developer",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(local.deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# gcloud run deploy は各サービスのランタイムSAを actAs する。プロジェクト全体ではなく
# 実際に使う2つのSAだけに serviceAccountUser を絞る。
#  backend  … speak-score-run（Firestore/GCS/署名権限あり＝撒くと危険なので限定が効く）
#  frontend … デフォルト compute SA（run.tf で service_account 未指定のため）
resource "google_service_account_iam_member" "deployer_actas_run" {
  service_account_id = google_service_account.run.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_actas_compute" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${data.google_project.current.number}-compute@developer.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Artifact Registry の speak-score リポジトリへの push 権限（リポジトリスコープ）。
# ランナーで docker build したイメージを push するために必要。プロジェクト全体には撒かない。
resource "google_artifact_registry_repository_iam_member" "deployer_ar_writer" {
  location   = var.region
  repository = google_artifact_registry_repository.docker.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

# --- Workload Identity Pool / Provider（GitHub OIDC を信頼）---
# 注意: pool/provider は削除後30日ソフトデリートされ、同じIDを即再利用できない（要注意）。
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
  description               = "OIDC federation for GitHub Actions CD"

  depends_on = [google_project_service.services]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  # GitHub の OIDC クレームを GCP 属性へマッピング。
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # このリポジトリの main ブランチの OIDC トークンだけを受け付ける。
  # ＝他リポジトリ・他ブランチ・PR・fork からは deployer になりすませない。
  # CD（deploy.yml）は main push と main 上の workflow_dispatch でのみ走る前提と一致させる。
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# 当該リポジトリの principalSet にだけ deployer への workloadIdentityUser を付与。
# ＝ shvalin1/speak-score の GitHub Actions のみが deployer になりすませる
#   （ブランチ絞り込みは provider の attribute_condition で main 限定済み）。
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
