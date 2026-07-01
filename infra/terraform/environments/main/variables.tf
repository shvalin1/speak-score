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

variable "github_repository" {
  type        = string
  description = "CD の WIF が信頼する GitHub リポジトリ（owner/repo）。これ以外はなりすまし不可。"
  default     = "shvalin1/speak-score"
}

variable "sentry_dsn" {
  type        = string
  description = <<-EOT
    backend の Sentry DSN（エラー監視）。空なら Sentry 無効。DSN は ingest 専用の
    低機微キーだが tracked な .tf に直書きせず terraform.tfvars（gitignore）等で渡す。
  EOT
  default     = ""
  sensitive   = true
}

variable "sentry_environment" {
  type        = string
  description = "Sentry の environment タグ（例: production）。"
  default     = "production"
}

variable "allowed_emails" {
  type        = string
  description = <<-EOT
    書込（アップロード/解析）を許可する Google アカウントのメール（カンマ区切り）。
    ここに載る verified メールの google.com ユーザーだけが writer（個人スコープ＋書込可）。
    それ以外（匿名・未許可 Google）は全員 read-only。空だと誰も書けない（フェイルクローズ）。
    メールは低機微のため平文 env(ALLOWED_EMAILS)で渡す。変更は再 apply/再デプロイで反映。
  EOT
  default     = ""
}

variable "auth_disabled" {
  type        = bool
  description = <<-EOT
    backend のユーザーAPI(Firebase)認証を無効化し dev_uid で叩けるようにする。
    Step1b の実機検証窓だけ true（curl で一周するため）。worker の OIDC は別フラグ
    (worker_oidc_disabled)で制御され、これとは独立に常に有効(fail-closed)。
    検証完了後は false に戻して再 apply すること（design 手順書 §5）。
  EOT
  default     = false
}
