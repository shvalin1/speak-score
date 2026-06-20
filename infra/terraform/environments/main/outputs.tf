output "backend_url" {
  description = "backend Cloud Run の公開URL。初回 apply 後 var.worker_url に設定して再 apply する。"
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "uploads_bucket" {
  value = google_storage_bucket.uploads.name
}

output "tasks_queue" {
  value = google_cloud_tasks_queue.process.id
}

output "run_sa_email" {
  value = google_service_account.run.email
}

output "tasks_invoker_sa_email" {
  value = google_service_account.tasks_invoker.email
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo}"
}
