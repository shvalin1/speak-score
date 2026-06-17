# infra

SpeakScore のインフラ（GCP / Terraform）。

- `terraform/` … 全GCPリソースのIaC。**単一環境**（dev/prod 分割なし）。全リソース `us-central1`。
- `docker/` … ローカル開発用 docker-compose（本番Cloud Run+Nginxと同構図）。
- `k8s/` … Phase 3（ハッカソン後・GKE Autopilot + GPU）で追加。

## Terraform 最小リソースセット（design §8）

| リソース | 用途 |
|----------|------|
| GCS (tfstate) | State（手動で1回ブートストラップ） |
| Artifact Registry | Dockerイメージ |
| Firestore (Native) | ジョブ/結果ストア。ロケーション後変更不可→`us-central1` |
| Firestore TTL field | `expire_at` で orphan 掃除 |
| GCS (uploads) | 動画/音声一時（lifecycle 1日削除・**CORSでフロントoriginからのPUT許可**） |
| Cloud Tasks queue | 非同期キュー（`dispatch_deadline=1800s`・max_attempts/backoff） |
| Cloud Run ×2 | backend / frontend |
| Service Account ×2 | Cloud Run実行用 / Cloud Tasks→worker invoker用 |
| IAM | tasks SAに backend `run.invoker` / 実行SAに自身への `serviceAccountTokenCreator`（署名URL） |
| Secret Manager | APIキー |

- **Firebase Auth（Identity Platform）有効化はTerraform外・コンソール手動**（プロバイダ依存で沼）。

> NOTE(Step1b): Terraform は本番経路スパイクで実装する。ここはまだ雛形ディレクトリのみ。
> `terraform` CLI は未導入。導入後に `modules/` と `environments/main/` を作る。
