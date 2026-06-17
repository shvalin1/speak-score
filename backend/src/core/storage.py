"""GCS: 署名URL発行(V4 PUT)・メタデータ確認・/tmpへのDL。

鍵ファイルなし署名には実行SAに roles/iam.serviceAccountTokenCreator が必要（§8）。
ローカル（GCS未設定）は署名URLをモックする（実署名URL+CORSは実GCSでDay0スパイク）。
設計根拠: design_review_and_frontback.md §5.2, §9
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .config import get_settings

SIGNED_URL_TTL = timedelta(minutes=15)


@dataclass
class ObjectMeta:
    exists: bool
    size: int


def _object_name(job_id: str, ext: str) -> str:
    return f"{job_id}/source.{ext}"


def _ext_from_content_type(content_type: str) -> str:
    return {
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/webm": "webm",
        "audio/m4a": "m4a",
        "audio/wav": "wav",
    }.get(content_type, "bin")


def signed_put_url(job_id: str, content_type: str) -> tuple[str, dict[str, str]]:
    """(upload_url, upload_headers) を返す。headers はPUT時にそのまま付ける（§5.2 F）。"""
    settings = get_settings()
    ext = _ext_from_content_type(content_type)
    name = _object_name(job_id, ext)
    headers = {"Content-Type": content_type}

    if not settings.gcs_bucket:
        # ローカルモック（実GCSでは下の実装パスを通す）
        return f"http://localhost:9000/mock-upload/{name}", headers

    from google.cloud import storage  # 遅延import

    client = storage.Client(project=settings.gcp_project)
    blob = client.bucket(settings.gcs_bucket).blob(name)
    url = blob.generate_signed_url(
        version="v4",
        method="PUT",
        expiration=SIGNED_URL_TTL,
        content_type=content_type,
    )
    return url, headers


def get_metadata(job_id: str, content_type: str) -> ObjectMeta:
    settings = get_settings()
    if not settings.gcs_bucket:
        return ObjectMeta(exists=False, size=0)  # ローカルは未配線
    from google.cloud import storage

    client = storage.Client(project=settings.gcp_project)
    blob = client.bucket(settings.gcs_bucket).blob(
        _object_name(job_id, _ext_from_content_type(content_type))
    )
    if not blob.exists():
        return ObjectMeta(exists=False, size=0)
    blob.reload()
    return ObjectMeta(exists=True, size=blob.size or 0)


def download_to_tmp(job_id: str, content_type: str, dest_path: str) -> str:
    """GCS source を /tmp にDLしローカルパスを返す（worker用）。"""
    settings = get_settings()
    from google.cloud import storage

    client = storage.Client(project=settings.gcp_project)
    blob = client.bucket(settings.gcs_bucket).blob(
        _object_name(job_id, _ext_from_content_type(content_type))
    )
    blob.download_to_filename(dest_path)
    return dest_path
