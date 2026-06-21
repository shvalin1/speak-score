"""FastAPI エントリ。ルーター登録と /api/health。

同一オリジン（Nginx proxy）前提のため CORSMiddleware は入れない（§9）。
設計根拠: design_review_and_frontback.md §5
"""

from fastapi import FastAPI

from .api import interviews, tasks
from .core.config import Settings, get_settings
from .core.logging import configure_logging


def _init_sentry(settings: Settings) -> None:
    """Sentry を初期化（DSN 未設定なら no-op）。FastAPI/Starlette 連携は 2.x で自動有効。

    send_default_pii=False で面接 PII（リクエスト本文・ユーザー情報）を送らない。
    アプリ内 catch でハンドルする worker の fatal は api/tasks.py から明示 capture する。
    """
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )


_settings = get_settings()
# 構造化ログを最初に設定（Cloud Run が stdout の JSON を jsonPayload に取り込む）。
configure_logging(_settings.log_level)
_init_sentry(_settings)

app = FastAPI(title="SpeakScore API", version="0.1.0")

app.include_router(interviews.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
