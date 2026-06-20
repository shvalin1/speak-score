"""OpenAI クライアント生成とエラー分類の共通ヘルパ（transcription / llm_evaluation 共用）。

鍵は settings から読む（Cloud Run では Secret Manager 経由で OPENAI_API_KEY を注入）。
エラー分類は pipeline の RecoverableError(=再試行) / FatalError(=即fail) に正規化する:
  - timeout / connection / rate-limit(429) / 5xx → RecoverableError（一時的）
  - その他 4xx（400 bad request・401 auth 等）→ FatalError（再試行しても無駄）
  - 鍵未設定 → FatalError（毎回失敗するため早期に倒す）
設計根拠: step2_plan.md Phase 4（エラー分類粒度 MED）, ADR 004。
"""

from __future__ import annotations

from typing import NoReturn

from ..core.config import get_settings
from ..core.errors import FatalError, RecoverableError

# OpenAI 呼び出しのクライアント側タイムアウト（秒）。soft_timeout(840s) 内に
# リトライ含めて収まるよう、1 リクエストは短めに切る。
_REQUEST_TIMEOUT = 120.0


def get_openai_client(*, for_transcription: bool = False):
    """OpenAI クライアントを生成する。鍵が無ければ FatalError。

    transcription は whisper_api_key を優先（通常は openai_api_key と同一）。
    """
    settings = get_settings()
    if for_transcription:
        key = settings.whisper_api_key or settings.openai_api_key
    else:
        key = settings.openai_api_key
    if not key:
        raise FatalError("OPENAI_API_KEY 未設定（Cloud Run では Secret Manager 経由で注入）")

    from openai import OpenAI

    return OpenAI(api_key=key, timeout=_REQUEST_TIMEOUT)


def _describe(exc: Exception) -> str:
    """ログ/エラーメッセージ用の安全な要約。レスポンス本文（PII 混入リスク）は載せない。

    元例外は from exc で連鎖保持するので、詳細が要るときはトレースバックで辿れる。
    """
    import openai

    if isinstance(exc, openai.APIStatusError):
        return f"{type(exc).__name__}(status={exc.status_code})"
    return type(exc).__name__


def reraise_openai(exc: Exception) -> NoReturn:
    """OpenAI 例外を pipeline のエラー種別に正規化して再送出する。"""
    import openai

    desc = _describe(exc)
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError)):
        raise RecoverableError(f"OpenAI 一時的失敗: {desc}") from exc
    if isinstance(exc, openai.APIStatusError) and (exc.status_code or 0) >= 500:
        raise RecoverableError(f"OpenAI 5xx: {desc}") from exc
    raise FatalError(f"OpenAI 恒久的失敗: {desc}") from exc
