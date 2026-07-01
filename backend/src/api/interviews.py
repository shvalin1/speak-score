"""ユーザー向けAPI（要 Firebase 認証）。ロジックは持たず service/repo を呼ぶ。

設計根拠: design_review_and_frontback.md §3.2, §5.2, §10
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core import storage, tasks
from ..core.auth import Principal, get_principal, get_uid, require_writer
from ..core.config import Settings, get_settings
from ..repositories.job_repo import JobRepository, QaIndexEntry, get_job_repo
from ..schemas.interview import (
    CreateInterviewRequest,
    CreateInterviewResponse,
    InterviewJob,
    InterviewSummary,
    JobStatus,
    StartResponse,
)

router = APIRouter(tags=["interviews"])

ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "audio/m4a",
    "audio/wav",
}


class MeResponse(BaseModel):
    """GET /me のレスポンス。フロントが書込UI（アップロード）の出し分けに使う。

    is_writer が唯一の権限表示。実際の書込制御は require_writer が backend で行う
    （フロントの出し分けはあくまで UX で、信頼境界ではない）。
    """

    uid: str
    email: str | None
    is_writer: bool


@router.get("/me")
def get_me(principal: Principal = Depends(get_principal)) -> MeResponse:
    """認証済み主体の権限を返す（reader/writer の判定結果）。未認証は 401。"""
    return MeResponse(
        uid=principal.uid,
        email=principal.email,
        is_writer=principal.is_writer,
    )


@router.post("/interviews", status_code=status.HTTP_201_CREATED)
def create_interview(
    req: CreateInterviewRequest,
    uid: str = Depends(require_writer),
    repo: JobRepository = Depends(get_job_repo),
    settings: Settings = Depends(get_settings),
) -> CreateInterviewResponse:
    if req.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported content type")
    if req.size_bytes <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid size")
    if req.size_bytes > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    job_id = uuid.uuid4().hex
    # 結果TTLは設定しない（デモは結果・qa_index を保持し横断一覧/経時比較を成立させる・§13(A)）。
    # 動画実体(GCS)の1日後削除は別ライフサイクルで維持。
    repo.create(
        job_id,
        owner_uid=uid,
        expire_at=None,
        content_type=req.content_type,
    )
    upload_url, upload_headers = storage.signed_put_url(job_id, req.content_type)
    return CreateInterviewResponse(
        job_id=job_id,
        status=JobStatus.awaiting_upload,
        upload_url=upload_url,
        upload_headers=upload_headers,
    )


@router.post("/interviews/{job_id}/start", status_code=status.HTTP_202_ACCEPTED)
def start_interview(
    job_id: str,
    uid: str = Depends(require_writer),
    repo: JobRepository = Depends(get_job_repo),
    settings: Settings = Depends(get_settings),
) -> StartResponse:
    owner = repo.get_owner(job_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if owner != uid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")

    # GCS メタデータでアップロード完了＋サイズ＋Content-Type 整合を確認（§5.2: Aの実効サイズ制限）。
    # 未アップロードのまま start すると後段で「過大評価」フットガンになるためここで弾く。
    # ローカル（gcs_bucket 空）は GCS 未配線のため短絡スキップ。
    if settings.gcs_bucket:
        content_type = repo.get_content_type(job_id)
        meta = storage.get_metadata(job_id, content_type or "")
        if not meta.exists:
            raise HTTPException(status.HTTP_409_CONFLICT, "アップロードが完了していません")
        if meta.size > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")
        if content_type and meta.content_type and meta.content_type != content_type:
            raise HTTPException(status.HTTP_409_CONFLICT, "content-type mismatch")

    # transaction で awaiting_upload→processing を一度だけ許可（二重enqueue防止）
    if not repo.mark_processing(job_id):
        # 既に processing/completed/failed → 現状態を返す（再enqueueしない）
        job = repo.get(job_id)
        return StartResponse(job_id=job_id, status=job.status if job else JobStatus.processing)

    tasks.enqueue_process(job_id)
    return StartResponse(job_id=job_id, status=JobStatus.processing)


@router.get("/interviews/{job_id}")
def get_interview(
    job_id: str,
    uid: str = Depends(get_uid),
    repo: JobRepository = Depends(get_job_repo),
) -> InterviewJob:
    if repo.get_owner(job_id) not in (uid,):
        # 所有者でない or 存在しない（区別せず404/403）
        owner = repo.get_owner(job_id)
        if owner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
    job = repo.get(job_id)
    assert job is not None
    return job


@router.get("/interviews")
def list_interviews(
    uid: str = Depends(get_uid),
    repo: JobRepository = Depends(get_job_repo),
) -> list[InterviewSummary]:
    return repo.list_for_owner(uid)


@router.get("/qa")
def list_qa(
    uid: str = Depends(get_uid),
    repo: JobRepository = Depends(get_job_repo),
) -> list[QaIndexEntry]:
    """動画横断の設問別一覧（score 降順）。owner_uid でスコープし他人のデータは混ぜない。"""
    return repo.list_qa_for_owner(uid)


class VideoUrlResponse(BaseModel):
    """GET /interviews/{job_id}/video-url のレスポンス。

    凍結契約（AnalysisResult）を汚さないよう、ここにローカル定義する。
    動画が GCS lifecycle で削除済み（1日経過）の場合 video_url は null。
    """

    video_url: str | None


@router.get("/interviews/{job_id}/video-url")
def get_video_url(
    job_id: str,
    uid: str = Depends(get_uid),
    repo: JobRepository = Depends(get_job_repo),
) -> VideoUrlResponse:
    # 他人の動画 URL を取らせないよう owner を照合（get_interview と同じ規約）。
    owner = repo.get_owner(job_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if owner != uid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
    content_type = repo.get_content_type(job_id)
    video_url = storage.signed_get_url(job_id, content_type or "")
    return VideoUrlResponse(video_url=video_url)
