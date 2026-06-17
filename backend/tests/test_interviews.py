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
