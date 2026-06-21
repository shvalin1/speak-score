# 必要な GCP API を有効化。Cloud Run/Tasks/Firestore/GCS/AR/Secret/IAM。
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "cloudtasks.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com", # 署名URL（signBlob）に必要
    "cloudbuild.googleapis.com",
    "sts.googleapis.com", # WIF のトークン交換（GitHub OIDC → GCP）
  ])
  service            = each.value
  disable_on_destroy = false
}
