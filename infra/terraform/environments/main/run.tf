# backend（FastAPI: API + worker /api/tasks/process）。public・OIDC検証はアプリ内。
resource "google_cloud_run_v2_service" "backend" {
  name     = "speak-score-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    service_account = google_service_account.run.email

    # backend は worker（同期パイプライン）も兼ねる。動画処理は5分の既定を超えうるため延長。
    timeout = "1800s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = 5
    }

    containers {
      image = var.backend_image

      # ffmpeg 抽出 + librosa を捌くため既定(1CPU/512Mi)から増強（OOM/スロットル回避）。
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "GCS_BUCKET"
        value = local.uploads_bucket
      }
      env {
        name  = "TASKS_QUEUE"
        value = local.tasks_queue_name
      }
      env {
        name  = "WORKER_SA"
        value = google_service_account.tasks_invoker.email
      }
      # WORKER_URL / WORKER_AUDIENCE は backend 自身の公開URL。サービス作成前は不明なため
      # 初回 apply 後に出力された backend URL を var.worker_url に入れて再 apply する
      # （Step1b の既知の罠: 自己URL参照の循環を避けるため2パス）。
      env {
        name  = "WORKER_URL"
        value = var.worker_url
      }
      env {
        name  = "WORKER_AUDIENCE"
        value = var.worker_url
      }
      env {
        name  = "FIREBASE_PROJECT"
        value = var.project_id
      }
      # 観測性（Sentry）。DSN は ingest 専用の低機微キーのため plain env で渡す
      # （tfstate には入るが Secret Manager 化はしない）。空なら backend 側で init をスキップ。
      env {
        name  = "SENTRY_DSN"
        value = var.sentry_dsn
      }
      env {
        name  = "SENTRY_ENVIRONMENT"
        value = var.sentry_environment
      }
      # Step2: Whisper + gpt-4o 用。値は Secret Manager（tfstate に入れない・secrets.tf）。
      # 注意: deploy 前に openai-api-key へ版を1つ追加しておくこと（版0だと Run 起動失敗）。
      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "openai-api-key"
            version = "latest"
          }
        }
      }
      # Step1b 実機検証窓のみ true。ユーザーAPIを dev_uid で叩けるようにする。
      # worker の OIDC は worker_oidc_disabled(既定 False)で別管理＝常に必須(fail-closed)。
      dynamic "env" {
        for_each = var.auth_disabled ? [1] : []
        content {
          name  = "AUTH_DISABLED"
          value = "1"
        }
      }
    }
  }

  # CD（deploy.yml）が gcloud run deploy で image を差し替える。terraform はインフラの
  # 土台のみを所有し、image の drift は無視する（次の apply で巻き戻さない）。
  # 初回作成時は var.backend_image を使う（ignore_changes は作成後の drift だけ無視）。
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.services]
}

# frontend（Nginx + ビルド済みSPA）。
resource "google_cloud_run_v2_service" "frontend" {
  name     = "speak-score-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = 3
    }

    containers {
      image = var.frontend_image

      # nginx.conf の reverse proxy 先（${BACKEND_URL} を envsubst 展開）。
      # 未注入だと proxy_pass が空展開になり nginx 起動失敗・/api 不通になる。
      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }

  # backend と同じく image は CD が所有。terraform は drift を無視する。
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.services]
}
