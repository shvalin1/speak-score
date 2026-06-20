# === Service Accounts ===

# Cloud Run（backend）実行SA。Firestore/GCS/署名URL/タスク投入を担う。
resource "google_service_account" "run" {
  account_id   = "speak-score-run"
  display_name = "SpeakScore Cloud Run runtime"
}

# Cloud Tasks が worker を OIDC で叩くときに名乗る invoker SA。
resource "google_service_account" "tasks_invoker" {
  account_id   = "tasks-invoker"
  display_name = "SpeakScore Cloud Tasks OIDC invoker"
}

# === 実行SA のプロジェクト権限 ===

resource "google_project_iam_member" "run_datastore" {
  project = var.project_id
  role    = "roles/datastore.user" # Firestore 読み書き
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_project_iam_member" "run_tasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.run.email}"
}

# uploads バケットへの read/write（署名URL対象オブジェクトの存在確認・worker DL含む）。
resource "google_storage_bucket_iam_member" "run_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run.email}"
}

# V4 署名URL（鍵ファイルなし signBlob）には実行SA自身への tokenCreator が必要（design §8）。
resource "google_service_account_iam_member" "run_sign_self" {
  service_account_id = google_service_account.run.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.run.email}"
}

# Cloud Tasks 作成時に invoker SA を OIDC 主体として指定するには actAs が要る。
resource "google_service_account_iam_member" "run_actas_invoker" {
  service_account_id = google_service_account.tasks_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.run.email}"
}

# === backend Cloud Run の呼び出し許可 ===
# 設計: backend は public（allUsers）。worker エンドポイントの防御はアプリ内 OIDC 検証が担う
# （core/tasks.py _verify_oidc / design §9）。invoker SA にも run.invoker を付けておき、
# 将来 backend を authenticated に締めても OIDC 経路が通るようにする（README §IAM）。
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks_invoker.email}"
}

# frontend は public。
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
