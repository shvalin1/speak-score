"""アプリ設定（pydantic-settings）。環境変数から読み込む。

設計根拠: design_review_and_frontback.md §5（core/config.py）, §8, §10
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# job_repo.LEASE_DURATION(=15分=900秒)と整合させるための上限。重複定義を避けつつ
# 「soft_timeout 内に必ず lease 内で1周完了する」不変条件を config 側で強制する。
LEASE_DURATION_SECONDS = 900


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- GCP ---
    gcp_project: str = ""
    region: str = "us-central1"
    gcs_bucket: str = ""                 # 動画/音声一時保存（uploads）
    tasks_queue: str = ""                # Cloud Tasks queue 名
    worker_url: str = ""                 # backend の .run.app（worker直叩き先）
    worker_sa: str = ""                  # Cloud Tasks が使う invoker SA email
    worker_audience: str = ""            # OIDC audience（= worker_url 等）

    # --- Auth (Firebase) ---
    firebase_project: str = ""
    # ローカル/モック開発で Firebase 検証を無効化し dev uid を返す（ユーザーAPIのみ）
    auth_disabled: bool = False
    # worker(/tasks/process) の OIDC 検証を無効化するか。既定 False=本番で常に必須(fail-closed)。
    # auth_disabled とは独立。ローカル同期経路(core/tasks.py 直叩き)では .env で 1 にする。
    worker_oidc_disabled: bool = False
    dev_uid: str = "dev-user"
    # 匿名ログインは全員この単一 uid に寄せ、評価済みのデモ結果を共有プールで見せる。
    # Google 等の本物のプロバイダは各自の uid で個人スコープに分離する（auth.get_uid）。
    # 注意: 匿名ユーザー同士は結果が相互に見えるため、本利用は Google ログインへ誘導する。
    demo_uid: str = "demo-shared"

    # --- LLM ---
    llm_provider: str = "openai"         # anthropic | openai（Step2 は OpenAI 1本: Whisper+gpt-4o）
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    whisper_api_key: str = ""            # 通常は openai_api_key と同一

    # --- pipeline ---
    max_video_seconds: int = 300         # 動画長5分上限（§5.1）
    max_upload_bytes: int = 200 * 1024 * 1024
    # 抽出後 WAV(mono16k) の上限。transcription API の 25MB 制限に合わせる。
    # WAV16k/300s ≈ 9.6MB なので余裕があるが、想定外の長尺/多chに対する安全弁。
    max_audio_bytes: int = 25 * 1024 * 1024
    soft_timeout_seconds: int = 840      # Cloud Run timeout=1800 に対する soft 上限
    # Cloud Tasks の retry_config.max_attempts と一致させること（tasks.tf）。
    # 最終試行で一時的失敗のとき worker は再呼出されないため、明示 fail に倒す判定に使う。
    max_task_attempts: int = 3

    # --- observability ---
    log_level: str = "INFO"              # 構造化ログの出力レベル（core/logging.py）
    sentry_dsn: str = ""                 # 空なら Sentry 無効（init スキップ）
    sentry_environment: str = ""         # 例: production / staging（空なら未設定）
    sentry_traces_sample_rate: float = 0.0  # 既定はエラーのみ（トレースは課金を考慮し off）

    # --- emulators (local docker-compose) ---
    firestore_emulator_host: str = ""    # FIRESTORE_EMULATOR_HOST
    firebase_auth_emulator_host: str = ""  # FIREBASE_AUTH_EMULATOR_HOST


    @model_validator(mode="after")
    def _check_soft_timeout(self) -> "Settings":
        # lease 失効前に必ず1周完了させる不変条件。これが「最終試行で fail に倒す」
        # 判定と complete/fail の lease-owner CAS の安全性を成立させる（lease 失効中に
        # 別 worker が奪取して上書きする事態を、そもそも起こさない）。誤って 0 や巨大値を
        # 入れると即 fail / lease 跨ぎになるため起動時に弾く。
        if not 0 < self.soft_timeout_seconds < LEASE_DURATION_SECONDS:
            raise ValueError(
                f"soft_timeout_seconds must be in (0, {LEASE_DURATION_SECONDS}); "
                f"got {self.soft_timeout_seconds}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
