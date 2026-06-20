provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  uploads_bucket   = "${var.project_id}-uploads"
  tasks_queue_name = "speak-score-process"
  ar_repo          = "speak-score"
}
