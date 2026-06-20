"""Cloud Tasks worker（OIDC専用・内部）。リース取得→pipeline→complete/fail。

設計根拠: design_review_and_frontback.md §5.1
"""

from __future__ import annotations

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
        return {"status": "in_progress"}  # 別workerが処理中 or 遷移不可

    try:
        result = await pipeline.run_pipeline(job_id, repo, worker_id)
        repo.complete(job_id, result)
        return {"status": "completed"}
    except RecoverableError as e:
        repo.release_lease(job_id)
        # Cloud Tasks に再試行させる（FastAPIで5xxを返す）
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="recoverable") from e
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline failed for job %s: %s", job_id, e)
        repo.fail(job_id, USER_FACING_FAIL_MSG)
        return {"status": "failed"}
