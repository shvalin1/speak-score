# ジョブ/結果ストア（Native）。ロケーションは後変更不可 → us-central1 固定。
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # 誤削除防止。破棄したいときは明示的に外す。
  deletion_policy = "DELETE"

  depends_on = [google_project_service.services]
}

# expire_at による orphan 掃除（InterviewJob.expire_at = 作成+1日）。
resource "google_firestore_field" "interviews_ttl" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "interviews"
  field      = "expire_at"

  ttl_config {}

  # TTL 以外のインデックス設定には触れない（既定のまま）。
  index_config {}
}
