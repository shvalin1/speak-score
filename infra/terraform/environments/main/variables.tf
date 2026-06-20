variable "project_id" {
  type        = string
  description = "GCP プロジェクトID（課金有効・作成済み）。"
}

variable "region" {
  type        = string
  description = "全リソースのロケーション。Firestore は後変更不可。"
  default     = "us-central1"
}

variable "cors_origins" {
  type        = list(string)
  description = <<-EOT
    uploads バケットへのブラウザPUTを許可するオリジン（署名URLアップロード用）。
    署名URL PUT はクッキー非送信のため "*" でも実害は小さいが、確定後は
    frontend の Cloud Run URL に絞ること（design §5.2）。
  EOT
  default     = ["*"]
}

variable "backend_image" {
  type        = string
  description = <<-EOT
    backend Cloud Run のコンテナイメージ。CI 整備前は apply を通すためのプレースホルダ。
    Step4 で Artifact Registry のビルド済みイメージに差し替える。
  EOT
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "frontend_image" {
  type        = string
  description = "frontend Cloud Run のコンテナイメージ（CI前はプレースホルダ）。"
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "min_instances" {
  type        = number
  description = "Cloud Run の最小インスタンス数。デモ時のみ 1（コールドスタート回避・Step4）。"
  default     = 0
}

variable "worker_url" {
  type        = string
  description = <<-EOT
    backend 自身の公開URL（= Cloud Tasks の宛先 / OIDC audience）。
    初回 apply 後に出力された backend_url を設定して再 apply する（自己URL参照の循環回避）。
  EOT
  default     = ""
}
