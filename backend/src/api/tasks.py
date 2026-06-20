"""Cloud Tasks worker（OIDC専用・内部）。リース取得→pipeline→complete/fail。

設計根拠: design_review_and_frontback.md §5.1
"""

from __future__ import annotations

import asyncio
import logging
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
    is_last_attempt = repo.get_attempt_count(job_id) >= settings.max_task_attempts

    try:
        # 直列(ffmpeg→Whisper→librosa→gpt-4o)が Cloud Run timeout(1800s)に張り付くのを防ぐ
        # ため、全体を soft_timeout で打ち切る。
        result = await asyncio.wait_for(
            pipeline.run_pipeline(job_id, repo, worker_id),
            timeout=settings.soft_timeout_seconds,
        )
        repo.complete(job_id, result, worker_id)
        return {"status": "completed"}
    except (RecoverableError, TimeoutError) as e:  # asyncio.wait_for は TimeoutError を送出
        if is_last_attempt:
            log.warning("job %s: 最終試行で一時的失敗 → fail に倒す: %s", job_id, e)
            repo.fail(job_id, USER_FACING_FAIL_MSG, worker_id)
            return {"status": "failed"}
        repo.release_lease(job_id, worker_id)
        # Cloud Tasks に再試行させる（FastAPIで5xxを返す）
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="recoverable") from e
    except Exception as e:  # noqa: BLE001 FatalError 含む恒久的失敗は即 fail（再試行しない）
        log.exception("pipeline failed for job %s: %s", job_id, e)
        repo.fail(job_id, USER_FACING_FAIL_MSG, worker_id)
        return {"status": "failed"}
