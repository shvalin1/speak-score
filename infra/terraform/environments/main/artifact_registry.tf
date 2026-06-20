# backend / frontend の Docker イメージ置き場。
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = local.ar_repo
  format        = "DOCKER"
  description   = "SpeakScore container images"

  depends_on = [google_project_service.services]
}
