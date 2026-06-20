# 非同期処理キュー。worker（backend /api/tasks/process）を OIDC で起動する。
# dispatch_deadline は enqueue 時にタスク単位で指定する（core/tasks.py）。ここは再試行方針のみ。
resource "google_cloud_tasks_queue" "process" {
  name     = local.tasks_queue_name
  location = var.region

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 10
  }

  retry_config {
    max_attempts       = 3
    min_backoff        = "5s"
    max_backoff        = "60s"
    max_doublings      = 3
    max_retry_duration = "1800s"
  }

  depends_on = [google_project_service.services]
}
