"""Cloud Tasks worker（OIDC専用・内部）。リース取得→pipeline→complete/fail。

設計根拠: design_review_and_frontback.md §5.1
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..core.config import Settings, get_settings
from ..core.errors import RecoverableError
from ..repositories.job_repo import JobRepository, get_job_repo
from ..services import pipeline

log = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])

USER_FACING_FAIL_MSG = "処理に失敗しました。動画を確認して再アップロードしてください。"

# 後方互換: RecoverableError は core.errors に移動（pipeline との循環 import 回避）。
# 既存の `tasks.RecoverableError` 参照のため re-export しておく。
__all__ = ["RecoverableError", "router"]


def _report_to_sentry(exc: BaseException, *, job_id: str, outcome: str, attempt: int) -> None:
    """恒久的失敗（fatal / 最終試行fail）を Sentry に送る。

    capture_exception は Sentry 未初期化（DSN なし）なら no-op なのでローカル/テストでも安全。
    job_id は高カーディナリティのため tag でなく context に置き、低カーディナリティの
    outcome/error_type/attempt を tag にする（PII は載せない）。一時的失敗(再試行)は送らない。
    """
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("outcome", outcome)
        scope.set_tag("error_type", type(exc).__name__)
        scope.set_tag("attempt", attempt)
        scope.set_context("job", {"job_id": job_id})
        sentry_sdk.capture_exception(exc)


class ProcessRequest(BaseModel):
    job_id: str


def _verify_oidc(request: Request, settings: Settings) -> None:
    """Cloud Tasks の OIDC トークンを検証（Google署名・audience・発行SA一致）。

    backend は public のため、worker エンドポイントの防御はこのアプリ内検証が唯一（§9）。
    Cloud Tasks が tasks_invoker SA で発行した ID トークンを、audience(=worker_url)と
    発行者メール(=worker_sa)で照合する。ローカルは WORKER_OIDC_DISABLED で素通り。
    """
    if settings.worker_oidc_disabled:
        return  # ローカル同期経路のみ検証スキップ（既定 False=本番は常に必須）

    from fastapi import HTTPException

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing oidc token")
    token = auth.split(" ", 1)[1].strip()

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    audience = settings.worker_audience or settings.worker_url
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)
    except Exception as e:  # noqa: BLE001 署名/期限/audience 不一致は全て 401 に倒す
        raise HTTPException(status_code=401, detail="invalid oidc token") from e

    if not claims.get("email_verified", False):
        raise HTTPException(status_code=403, detail="oidc email not verified")
    # tasks_invoker 以外の主体からの呼び出しを拒否（worker_sa 設定時のみ）。
    if settings.worker_sa and claims.get("email") != settings.worker_sa:
        raise HTTPException(status_code=403, detail="unexpected oidc principal")


@router.post("/tasks/process")
async def process(
    req: ProcessRequest,
    request: Request,
    repo: JobRepository = Depends(get_job_repo),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    _verify_oidc(request, settings)
    job_id = req.job_id
    worker_id = uuid.uuid4().hex

    job = repo.get(job_id)
    if job is None:
        return {"status": "ignored"}  # 不正/期限切れ。再試行させない
    if job.status in ("completed", "failed"):
        return {"status": "already_done"}  # べき等

    if not repo.try_acquire_lease(job_id, worker_id):
        # 別 worker が処理中（at-least-once の重複配信時のみ起きる）。ここで 2xx を返すと
        # Cloud Tasks がこの task を ack して削除し、本命 worker が後で一時的失敗しても
        # 再試行 task が消えて processing 滞留しうる。非2xx で返して Cloud Tasks に保持・
        # 再試行させる（本命が完了すれば次の配信は already_done で 2xx になり正常に消える）。
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="in_progress")

    # リース取得で attempt_count はインクリメント済み。max_attempts に達した試行で
    # 一時的失敗を返すと Cloud Tasks が task を破棄し worker が再呼出されず status が
    # processing のまま永久滞留する → 最終試行では明示 fail に倒す（HIGH）。
    attempt = repo.get_attempt_count(job_id)
    is_last_attempt = attempt >= settings.max_task_attempts
    # outcome/attempt/duration を構造化ログに出すための共通フィールド（PII は載せない）。
    base = {"job_id": job_id, "attempt": attempt}
    start = time.perf_counter()

    def _elapsed_ms() -> float:
        return round((time.perf_counter() - start) * 1000, 1)

    try:
        # 直列(ffmpeg→Whisper→librosa→gpt-4o)が Cloud Run timeout(1800s)に張り付くのを防ぐ
        # ため、全体を soft_timeout で打ち切る。
        result = await asyncio.wait_for(
            pipeline.run_pipeline(job_id, repo, worker_id),
            timeout=settings.soft_timeout_seconds,
        )
        repo.complete(job_id, result, worker_id)
        log.info(
            "job_outcome",
            extra={**base, "outcome": "completed", "duration_ms": _elapsed_ms()},
        )
        return {"status": "completed"}
    except (RecoverableError, TimeoutError) as e:  # asyncio.wait_for は TimeoutError を送出
        if is_last_attempt:
            log.warning(
                "job_outcome",
                extra={
                    **base,
                    "outcome": "last_attempt_fail",
                    "duration_ms": _elapsed_ms(),
                    "error_type": type(e).__name__,
                },
            )
            _report_to_sentry(e, job_id=job_id, outcome="last_attempt_fail", attempt=attempt)
            repo.fail(job_id, USER_FACING_FAIL_MSG, worker_id)
            return {"status": "failed"}
        repo.release_lease(job_id, worker_id)
        log.info(
            "job_outcome",
            extra={
                **base,
                "outcome": "recoverable_retry",
                "duration_ms": _elapsed_ms(),
                "error_type": type(e).__name__,
            },
        )
        # Cloud Tasks に再試行させる（FastAPIで5xxを返す）
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="recoverable") from e
    except Exception as e:  # noqa: BLE001 FatalError 含む恒久的失敗は即 fail（再試行しない）
        log.error(
            "job_outcome",
            extra={
                **base,
                "outcome": "fatal_fail",
                "duration_ms": _elapsed_ms(),
                "error_type": type(e).__name__,
            },
            exc_info=e,
        )
        _report_to_sentry(e, job_id=job_id, outcome="fatal_fail", attempt=attempt)
        repo.fail(job_id, USER_FACING_FAIL_MSG, worker_id)
        return {"status": "failed"}
