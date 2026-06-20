# 動画/音声の一時保存バケット。lifecycle で1日後に自動削除、CORS でフロントからの署名URL PUT を許可。
resource "google_storage_bucket" "uploads" {
  name                        = local.uploads_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true # 一時データのみ。破棄時に中身ごと消す

  lifecycle_rule {
    condition {
      age = 1 # 日
    }
    action {
      type = "Delete"
    }
  }

  cors {
    origin          = var.cors_origins
    method          = ["PUT", "GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.services]
}
