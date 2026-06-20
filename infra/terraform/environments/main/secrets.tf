# APIキーの器（値は tfstate に入れない。値は CI / コンソールで版を追加する）。
resource "google_secret_manager_secret" "api_keys" {
  for_each  = toset(["anthropic-api-key", "openai-api-key"])
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

# 実行SA に各シークレットの読み取りを許可。
resource "google_secret_manager_secret_iam_member" "run_access" {
  for_each  = google_secret_manager_secret.api_keys
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}
