FROM python:3.12-slim

# ffmpeg + 音声処理ライブラリのシステム依存（§8）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
# worker は audio/llm extras を必要とする。本番イメージはフルで入れる。
RUN uv sync --frozen --no-dev --extra audio --extra llm || uv sync --no-dev --extra audio --extra llm

COPY src/ ./src/

# Cloud Run は PORT を注入する（既定 8080）
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
