"""FastAPI エントリ。ルーター登録と /api/health。

同一オリジン（Nginx proxy）前提のため CORSMiddleware は入れない（§9）。
設計根拠: design_review_and_frontback.md §5
"""

from fastapi import FastAPI

from .api import interviews, tasks

app = FastAPI(title="SpeakScore API", version="0.1.0")

app.include_router(interviews.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
