# ジョブ/結果ストア（Native）。ロケーションは後変更不可 → us-central1 固定。
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # dev 単一環境。terraform destroy で DB ごと片付く（DELETE）。本番運用に移すなら ABANDON に。
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

  # TTL 専用フィールド（検索/ソートしない）。空 index_config で単一フィールドインデックスを
  # 無効化し、書き込みコストを節約する。
  index_config {}
}
