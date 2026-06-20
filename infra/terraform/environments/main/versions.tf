terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # tfstate は GCS バックエンド。バケットは手動で1回だけブートストラップする（design §8）:
  #   gcloud storage buckets create gs://<project>-tfstate --location=us-central1 \
  #     --uniform-bucket-level-access --pap=enforced
  #   gcloud storage buckets update gs://<project>-tfstate --versioning
  # その後 `terraform init -backend-config=bucket=<project>-tfstate` で移行する。
  # ブートストラップ前はローカルstateで `terraform init` できるよう、ここはコメントのまま。
  # backend "gcs" {
  #   prefix = "speak-score/main"
  # }
}
