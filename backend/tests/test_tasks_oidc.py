"""worker(/api/tasks/process) の OIDC ゲートの回帰テスト。

public Cloud Run 上の worker の唯一の防御線が _verify_oidc。conftest は全テストで
WORKER_OIDC_DISABLED=1 を立てるため、検証本体を踏むテストが他に無い。ここでは
worker_oidc_disabled=False（本番相当）に上書きし「トークン無し→401」を確認する。
ゲートが消える/反転する fail-open 回帰をこの1本で検出できる（ネットワーク非依存）。
"""

from fastapi.testclient import TestClient


def _client_with_oidc_enabled(monkeypatch) -> TestClient:
    monkeypatch.setenv("WORKER_OIDC_DISABLED", "0")
    from src.core.config import get_settings

    get_settings.cache_clear()  # conftest が立てた既定を本番相当へ
    from src.main import app

    return TestClient(app)


def test_process_without_token_is_rejected(monkeypatch):
    client = _client_with_oidc_enabled(monkeypatch)
    res = client.post("/api/tasks/process", json={"job_id": "x"})
    assert res.status_code == 401  # missing oidc token


def test_process_with_oidc_disabled_skips_verification(client):
    # 既定（conftest: WORKER_OIDC_DISABLED=1）では検証を素通りし 401 にならない。
    res = client.post("/api/tasks/process", json={"job_id": "does-not-exist"})
    assert res.status_code != 401
