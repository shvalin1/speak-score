"""Cloud Tasks worker（OIDC専用・内部）。リース取得→pipeline→complete/fail。

設計根拠: design_review_and_frontback.md §5.1
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..core.config import Settings, get_settings
from ..repositories.job_repo import JobRepository, get_job_repo
from ..services import pipeline

log = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])

USER_FACING_FAIL_MSG = "処理に失敗しました。動画を確認して再アップロードしてください。"


class ProcessRequest(BaseModel):
    job_id: str


class RecoverableError(Exception):
    """一時的失敗。Cloud Tasks に再試行させる（5xxを返す）。"""


def _verify_oidc(request: Request, settings: Settings) -> None:
    """Cloud Tasks の OIDC トークンを検証（発行SA・audience一致）。

    NOTE(石川/Step1b): 本番経路スパイクで Google の oauth2 トークン検証を実装する。
    backend は public のため、worker防御はこのアプリ内検証が唯一（§9）。
    """
    if settings.auth_disabled:
        return  # ローカルは検証スキップ
    # TODO: from google.oauth2 import id_token; id_token.verify_oauth2_token(...)
    return


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
