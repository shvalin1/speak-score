"""API骨格のスモークテスト（in-memory / 認証無効）。"""


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_create_interview_returns_signed_url(client):
    res = client.post(
        "/api/interviews",
        json={"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 1024},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "awaiting_upload"
    assert "upload_url" in body
    assert body["upload_headers"]["Content-Type"] == "video/mp4"


def test_create_rejects_bad_mime(client):
    res = client.post(
        "/api/interviews",
        json={"filename": "a.txt", "content_type": "text/plain", "size_bytes": 10},
    )
    assert res.status_code == 415


def test_list_is_owner_scoped(client):
    client.post(
        "/api/interviews",
        json={"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 1024},
    )
    res = client.get("/api/interviews")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


def test_start_unknown_job_404(client):
    res = client.post("/api/interviews/does-not-exist/start")
    assert res.status_code == 404


def _seed_job_with_bucket(monkeypatch, content_type="video/mp4"):
    """GCS_BUCKET を設定し、in-memory repo に awaiting_upload のジョブを1件作る。"""
    import uuid
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from src.core.config import get_settings
    from src.repositories import job_repo

    get_settings.cache_clear()
    job_repo._repo = None
    repo = job_repo.get_job_repo()
    jid = uuid.uuid4().hex
    repo.create(
        jid,
        owner_uid="dev-user",  # AUTH_DISABLED の dev uid
        expire_at=datetime.now(UTC) + timedelta(days=1),
        content_type=content_type,
    )
    return jid


def test_start_409_when_not_uploaded(client, monkeypatch):
    from src.core import storage

    jid = _seed_job_with_bucket(monkeypatch)
    monkeypatch.setattr(storage, "get_metadata", lambda *a: storage.ObjectMeta(False, 0))
    res = client.post(f"/api/interviews/{jid}/start")
    assert res.status_code == 409


def test_start_409_on_content_type_mismatch(client, monkeypatch):
    from src.core import storage

    jid = _seed_job_with_bucket(monkeypatch, content_type="video/mp4")
    # 実アップロードが audio/wav で発行時(video/mp4)と不一致
    monkeypatch.setattr(
        storage, "get_metadata", lambda *a: storage.ObjectMeta(True, 1024, "audio/wav")
    )
    res = client.post(f"/api/interviews/{jid}/start")
    assert res.status_code == 409


def test_start_413_when_too_large(client, monkeypatch):
    from src.core import storage

    jid = _seed_job_with_bucket(monkeypatch)
    huge = 300 * 1024 * 1024  # max_upload_bytes(200MiB) 超
    monkeypatch.setattr(
        storage, "get_metadata", lambda *a: storage.ObjectMeta(True, huge, "video/mp4")
    )
    res = client.post(f"/api/interviews/{jid}/start")
    assert res.status_code == 413


def test_start_202_when_uploaded_ok(client, monkeypatch):
    from src.core import storage

    jid = _seed_job_with_bucket(monkeypatch)
    monkeypatch.setattr(
        storage, "get_metadata", lambda *a: storage.ObjectMeta(True, 1024, "video/mp4")
    )
    res = client.post(f"/api/interviews/{jid}/start")
    assert res.status_code == 202
    assert res.json()["status"] == "processing"
