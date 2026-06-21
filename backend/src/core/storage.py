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
# 再生中に URL が切れないよう、GET は PUT より長めにする（動画タブの視聴想定）。
SIGNED_GET_URL_TTL = timedelta(minutes=30)


@dataclass
class ObjectMeta:
    exists: bool
    size: int
    content_type: str = ""  # 実アップロードの Content-Type（発行時との整合チェック用）


def _object_name(job_id: str, ext: str) -> str:
    return f"{job_id}/source.{ext}"


def ext_from_content_type(content_type: str) -> str:
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
    ext = ext_from_content_type(content_type)
    name = _object_name(job_id, ext)
    headers = {"Content-Type": content_type}

    if not settings.gcs_bucket:
        # ローカルモック（実GCSでは下の実装パスを通す）
        return f"http://localhost:9000/mock-upload/{name}", headers

    import google.auth  # 遅延import
    from google.auth.transport.requests import Request
    from google.cloud import storage

    # Cloud Run の compute credentials は秘密鍵を持たないため、V4 署名は IAM SignBlob
    # 経由にする（service_account_email + access_token を渡すと iamcredentials.signBlob
    # で署名）。run SA に自己 roles/iam.serviceAccountTokenCreator が必要（§8 / iam.tf）。
    credentials, _ = google.auth.default()
    credentials.refresh(Request())

    client = storage.Client(project=settings.gcp_project, credentials=credentials)
    blob = client.bucket(settings.gcs_bucket).blob(name)
    url = blob.generate_signed_url(
        version="v4",
        method="PUT",
        expiration=SIGNED_URL_TTL,
        content_type=content_type,
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    return url, headers


def signed_get_url(job_id: str, content_type: str) -> str | None:
    """アップロード済み source 動画の署名GET URL（動画タブ再生用）。

    オブジェクトが無い場合（GCS lifecycle で1日後に自動削除済み等）は None を返す。
    署名は PUT と同じ IAM SignBlob 経路（run SA に self tokenCreator）。
    """
    settings = get_settings()
    if not settings.gcs_bucket:
        return None  # ローカル（GCS未配線）は再生 URL なし

    import google.auth  # 遅延import
    from google.auth.transport.requests import Request
    from google.cloud import storage

    credentials, _ = google.auth.default()
    credentials.refresh(Request())

    client = storage.Client(project=settings.gcp_project, credentials=credentials)
    blob = client.bucket(settings.gcs_bucket).blob(
        _object_name(job_id, ext_from_content_type(content_type))
    )
    if not blob.exists():
        return None  # 未アップロード or 期限切れで削除済み
    return blob.generate_signed_url(
        version="v4",
        method="GET",
        expiration=SIGNED_GET_URL_TTL,
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )


def get_metadata(job_id: str, content_type: str) -> ObjectMeta:
    settings = get_settings()
    if not settings.gcs_bucket:
        return ObjectMeta(exists=False, size=0)  # ローカルは未配線
    from google.cloud import storage

    client = storage.Client(project=settings.gcp_project)
    blob = client.bucket(settings.gcs_bucket).blob(
        _object_name(job_id, ext_from_content_type(content_type))
    )
    if not blob.exists():
        return ObjectMeta(exists=False, size=0)
    blob.reload()
    return ObjectMeta(exists=True, size=blob.size or 0, content_type=blob.content_type or "")


def download_to_tmp(job_id: str, content_type: str, dest_path: str) -> str:
    """GCS source を /tmp にDLしローカルパスを返す（worker用）。"""
    settings = get_settings()
    from google.cloud import storage

    client = storage.Client(project=settings.gcp_project)
    blob = client.bucket(settings.gcs_bucket).blob(
        _object_name(job_id, ext_from_content_type(content_type))
    )
    blob.download_to_filename(dest_path)
    return dest_path
