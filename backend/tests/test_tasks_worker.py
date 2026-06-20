"""worker(/api/tasks/process) の堅牢化テスト（OIDC は conftest で無効）。

- attempt_count 上限での fail 転倒（processing 永久滞留の回避・HIGH）
- 非最終試行の一時的失敗は 503（Cloud Tasks 再試行）＋lease 解放
- FatalError 等の恒久的失敗は即 fail
- soft_timeout 超過は一時的失敗扱い

pipeline.run_pipeline をモックしネットワーク非依存。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.core.errors import FatalError, RecoverableError
from src.repositories import job_repo
from src.services import pipeline


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


def _seed_processing_job(attempts: int = 0) -> str:
    """processing 状態のジョブを作る。attempts 回ぶん attempt_count を進める。"""
    repo = job_repo.get_job_repo()
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="dev-user", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    for i in range(attempts):
        w = f"pre-{i}"
        repo.try_acquire_lease(jid, w)
        repo.release_lease(jid, w)
    return jid


def test_recoverable_non_last_attempt_returns_503(client, monkeypatch):
    async def _boom(*a, **k):
        raise RecoverableError("transient")

    monkeypatch.setattr(pipeline, "run_pipeline", _boom)
    jid = _seed_processing_job()  # この呼び出しで attempt=1（max=3 未満）

    res = client.post("/api/tasks/process", json={"job_id": jid})
    assert res.status_code == 503
    repo = job_repo.get_job_repo()
    assert repo.get(jid).status.value == "processing"  # まだ失敗にしない（再試行に委ねる）
    # lease は解放され、次の試行(別worker)が取得できる
    assert repo.try_acquire_lease(jid, "next") is True


def test_recoverable_last_attempt_fails(client, monkeypatch):
    async def _boom(*a, **k):
        raise RecoverableError("transient")

    monkeypatch.setattr(pipeline, "run_pipeline", _boom)
    # 既に2回試行済み → このworker取得で attempt=3（=max_task_attempts）
    jid = _seed_processing_job(attempts=2)

    res = client.post("/api/tasks/process", json={"job_id": jid})
    assert res.status_code == 200
    assert res.json()["status"] == "failed"
    assert job_repo.get_job_repo().get(jid).status.value == "failed"


def test_in_progress_returns_non_2xx(client):
    # 別 worker がリース保持中の重複配信は 2xx で task を消さず、非2xx で再試行保持させる。
    repo = job_repo.get_job_repo()
    jid = _seed_processing_job()
    assert repo.try_acquire_lease(jid, "holder") is True
    res = client.post("/api/tasks/process", json={"job_id": jid})
    assert res.status_code == 409
    assert repo.get(jid).status.value == "processing"


def test_fatal_error_fails_immediately(client, monkeypatch):
    async def _boom(*a, **k):
        raise FatalError("corrupt video")

    monkeypatch.setattr(pipeline, "run_pipeline", _boom)
    jid = _seed_processing_job()  # attempt=1 でも恒久的失敗は即 fail

    res = client.post("/api/tasks/process", json={"job_id": jid})
    assert res.status_code == 200
    assert res.json()["status"] == "failed"
    assert job_repo.get_job_repo().get(jid).status.value == "failed"


def test_soft_timeout_is_recoverable(client, monkeypatch):
    import asyncio

    async def _slow(*a, **k):
        await asyncio.sleep(0.5)

    monkeypatch.setattr(pipeline, "run_pipeline", _slow)
    # 設定の検証(0<soft_timeout<900)を踏まずに即タイムアウトさせるため、構築済み
    # settings インスタンスの属性を直接 0 に差し替える（validate_assignment 無効で素通り）。
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "soft_timeout_seconds", 0)
    jid = _seed_processing_job()  # attempt=1 → タイムアウトは 503
    res = client.post("/api/tasks/process", json={"job_id": jid})
    assert res.status_code == 503
    assert job_repo.get_job_repo().get(jid).status.value == "processing"
