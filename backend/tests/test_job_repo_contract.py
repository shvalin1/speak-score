"""JobRepository 契約テスト。

InMemoryJobRepo と FirestoreJobRepo が同一の振る舞いを満たすことを保証する。
Firestore 側は FIRESTORE_EMULATOR_HOST が設定されているときだけ実行（CI/ローカルで
エミュレータ未起動ならスキップ）。

エミュレータ起動例:
    gcloud emulators firestore start --host-port=127.0.0.1:8085
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 uv run pytest tests/test_job_repo_contract.py
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.repositories.job_repo import InMemoryJobRepo, JobRepository
from src.schemas.interview import AnalysisResult, JobStatus, ProcessingStage

_SAMPLE = Path(__file__).resolve().parents[2] / "shared" / "mock_data" / "sample_result.json"


def _sample_result() -> AnalysisResult:
    return AnalysisResult.model_validate(json.loads(_SAMPLE.read_text(encoding="utf-8")))


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


def _make_firestore_repo() -> JobRepository:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST 未設定（エミュレータ未起動）")
    # conftest の autouse fixture が GCP_PROJECT="" を入れるため直接上書きする
    os.environ["GCP_PROJECT"] = "speakscore-test"
    from src.core.config import get_settings
    from src.repositories.job_repo import FirestoreJobRepo

    get_settings.cache_clear()
    return FirestoreJobRepo()


@pytest.fixture(params=["inmemory", "firestore"])
def repo(request) -> JobRepository:
    if request.param == "inmemory":
        return InMemoryJobRepo()
    return _make_firestore_repo()


def test_create_and_get(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())

    job = repo.get(jid)
    assert job is not None
    assert job.job_id == jid
    assert job.status == JobStatus.awaiting_upload
    assert job.stage is None
    assert repo.get_owner(jid) == "u1"


def test_get_missing_returns_none(repo: JobRepository) -> None:
    assert repo.get("nope-" + uuid.uuid4().hex) is None
    assert repo.get_owner("nope-" + uuid.uuid4().hex) is None


def test_mark_processing_only_once(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())

    assert repo.mark_processing(jid) is True
    # 2回目は遷移不可（二重 enqueue 防止）
    assert repo.mark_processing(jid) is False
    assert repo.get(jid).status == JobStatus.processing


def test_lease_is_exclusive(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())
    repo.mark_processing(jid)

    assert repo.try_acquire_lease(jid, "worker-a") is True
    # 有効なリースがある間は別 worker は取得できない
    assert repo.try_acquire_lease(jid, "worker-b") is False
    assert repo.get(jid).stage == ProcessingStage.extracting_audio


def test_lease_requires_processing(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())
    # awaiting_upload のままではリース取得不可
    assert repo.try_acquire_lease(jid, "worker-a") is False


def test_update_stage(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    repo.update_stage(jid, ProcessingStage.transcribing)
    assert repo.get(jid).stage == ProcessingStage.transcribing


def test_complete_stores_result(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    result = _sample_result()
    repo.complete(jid, result)

    job = repo.get(jid)
    assert job.status == JobStatus.completed
    assert job.stage is None
    assert job.completed_at is not None
    assert job.result is not None
    assert job.result.overall_score == result.overall_score
    assert job.result.transcript.full_text == result.transcript.full_text


def test_fail_sets_user_message(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future())
    repo.mark_processing(jid)

    repo.fail(jid, "処理に失敗しました。")
    job = repo.get(jid)
    assert job.status == JobStatus.failed
    assert job.error == "処理に失敗しました。"


def test_list_is_owner_scoped_and_sorted(repo: JobRepository) -> None:
    owner = "owner-" + uuid.uuid4().hex
    other = "other-" + uuid.uuid4().hex
    ids = []
    for _ in range(2):
        jid = uuid.uuid4().hex
        repo.create(jid, owner_uid=owner, expire_at=_future())
        ids.append(jid)
    repo.create(uuid.uuid4().hex, owner_uid=other, expire_at=_future())

    summaries = repo.list_for_owner(owner)
    assert {s.job_id for s in summaries} == set(ids)
    # created_at 降順
    times = [s.created_at for s in summaries]
    assert times == sorted(times, reverse=True)
