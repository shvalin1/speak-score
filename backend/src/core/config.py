"""アプリ設定（pydantic-settings）。環境変数から読み込む。

設計根拠: design_review_and_frontback.md §5（core/config.py）, §8, §10
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # ローカル/モック開発で Firebase 検証を無効化し dev uid を返す
    auth_disabled: bool = False
    dev_uid: str = "dev-user"

    # --- LLM ---
    llm_provider: str = "anthropic"      # anthropic | openai
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    whisper_api_key: str = ""            # 通常は openai_api_key と同一

    # --- pipeline ---
    max_video_seconds: int = 300         # 動画長5分上限（§5.1）
    max_upload_bytes: int = 200 * 1024 * 1024
    soft_timeout_seconds: int = 840      # Cloud Run timeout=900 に対する soft 上限

    # --- emulators (local docker-compose) ---
    firestore_emulator_host: str = ""    # FIRESTORE_EMULATOR_HOST
    firebase_auth_emulator_host: str = ""  # FIREBASE_AUTH_EMULATOR_HOST


@lru_cache
def get_settings() -> Settings:
    return Settings()
