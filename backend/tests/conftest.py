import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    # ローカル/テストは認証無効・in-memoryストア
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("WORKER_OIDC_DISABLED", "1")
    monkeypatch.setenv("TASKS_QUEUE", "")
    monkeypatch.setenv("GCS_BUCKET", "")
    monkeypatch.setenv("GCP_PROJECT", "")
    # get_settings / get_job_repo のキャッシュをクリア
    from src.core.config import get_settings
    from src.repositories import job_repo

    get_settings.cache_clear()
    job_repo._repo = None
    yield


@pytest.fixture
def client() -> TestClient:
    from src.main import app

    return TestClient(app)
