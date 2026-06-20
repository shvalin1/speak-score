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


def _make_firestore_repo(monkeypatch) -> JobRepository:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST 未設定（エミュレータ未起動）")
    # conftest の autouse fixture が GCP_PROJECT="" を入れるため上書き（teardown で戻る）
    monkeypatch.setenv("GCP_PROJECT", "speakscore-test")
    from src.core.config import get_settings
    from src.repositories.job_repo import FirestoreJobRepo

    get_settings.cache_clear()
    return FirestoreJobRepo()


@pytest.fixture(params=["inmemory", "firestore"])
def repo(request, monkeypatch) -> JobRepository:
    if request.param == "inmemory":
        return InMemoryJobRepo()
    return _make_firestore_repo(monkeypatch)


def test_create_and_get(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")

    job = repo.get(jid)
    assert job is not None
    assert job.job_id == jid
    assert job.status == JobStatus.awaiting_upload
    assert job.stage is None
    assert repo.get_owner(jid) == "u1"
    assert repo.get_content_type(jid) == "video/mp4"
    # 未知ジョブは None
    assert repo.get_content_type("nope-" + uuid.uuid4().hex) is None


def test_get_missing_returns_none(repo: JobRepository) -> None:
    assert repo.get("nope-" + uuid.uuid4().hex) is None
    assert repo.get_owner("nope-" + uuid.uuid4().hex) is None


def test_mark_processing_only_once(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")

    assert repo.mark_processing(jid) is True
    # 2回目は遷移不可（二重 enqueue 防止）
    assert repo.mark_processing(jid) is False
    assert repo.get(jid).status == JobStatus.processing


def test_lease_is_exclusive(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)

    assert repo.try_acquire_lease(jid, "worker-a") is True
    # 有効なリースがある間は別 worker は取得できない
    assert repo.try_acquire_lease(jid, "worker-b") is False
    assert repo.get(jid).stage == ProcessingStage.extracting_audio


def test_lease_requires_processing(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    # awaiting_upload のままではリース取得不可
    assert repo.try_acquire_lease(jid, "worker-a") is False


def test_update_stage(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    repo.update_stage(jid, ProcessingStage.transcribing)
    assert repo.get(jid).stage == ProcessingStage.transcribing


def test_complete_stores_result(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    result = _sample_result()
    repo.complete(jid, result, "worker-a")

    job = repo.get(jid)
    assert job.status == JobStatus.completed
    assert job.stage is None
    assert job.completed_at is not None
    assert job.result is not None
    assert job.result.overall_score == result.overall_score
    assert job.result.transcript.full_text == result.transcript.full_text


def test_fail_sets_user_message(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    repo.fail(jid, "処理に失敗しました。", "worker-a")
    job = repo.get(jid)
    assert job.status == JobStatus.failed
    assert job.error == "処理に失敗しました。"


def test_attempt_count_increments_on_lease(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    assert repo.get_attempt_count(jid) == 0
    repo.try_acquire_lease(jid, "worker-a")
    assert repo.get_attempt_count(jid) == 1


def test_complete_fail_release_require_lease_owner(repo: JobRepository) -> None:
    # CAS: lease を持たない別 worker からの complete/fail/release は no-op。
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)
    repo.try_acquire_lease(jid, "worker-a")

    repo.complete(jid, _sample_result(), "intruder")
    assert repo.get(jid).status == JobStatus.processing  # 上書きされない
    repo.fail(jid, "x", "intruder")
    assert repo.get(jid).status == JobStatus.processing
    repo.release_lease(jid, "intruder")
    assert repo.try_acquire_lease(jid, "worker-b") is False  # lease は保持されたまま

    # 正当な保持者なら成功
    repo.complete(jid, _sample_result(), "worker-a")
    assert repo.get(jid).status == JobStatus.completed


def test_release_lease_allows_reacquire(repo: JobRepository) -> None:
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)

    assert repo.try_acquire_lease(jid, "worker-a") is True
    assert repo.try_acquire_lease(jid, "worker-b") is False  # 保持中
    repo.release_lease(jid, "worker-a")
    # 解放後は別 worker が再取得できる
    assert repo.try_acquire_lease(jid, "worker-b") is True


def test_lease_reacquire_after_expiry(repo: JobRepository, monkeypatch) -> None:
    # リース期間を負にして即失効させ、failover（別workerの再取得）を検証する。
    from src.repositories import job_repo as jr

    monkeypatch.setattr(jr, "LEASE_DURATION", timedelta(seconds=-1))
    jid = uuid.uuid4().hex
    repo.create(jid, owner_uid="u1", expire_at=_future(), content_type="video/mp4")
    repo.mark_processing(jid)

    assert repo.try_acquire_lease(jid, "worker-a") is True  # 取得直後に失効するリース
    # 失効済みなので別 worker が奪取できる（worker クラッシュ時の復帰経路）
    assert repo.try_acquire_lease(jid, "worker-b") is True
    assert repo.get(jid).stage == ProcessingStage.extracting_audio


def test_trim_result_downsamples_and_caps() -> None:
    # repo 非依存の純関数テスト（1MiB 対策）。
    from src.repositories.job_repo import (
        MAX_TIMELINE_POINTS,
        MAX_TRANSCRIPT_CHARS,
        MAX_TRANSCRIPT_SEGMENTS,
        _trim_result,
    )
    from src.schemas.interview import TimePoint, TranscriptSegment

    base = _sample_result()
    big_tl = [TimePoint(t=float(i), value=0.1) for i in range(1000)]
    big_segs = [
        TranscriptSegment(start=float(i), end=float(i) + 1, text="x") for i in range(5000)
    ]
    am = base.audio_metrics.model_copy(
        update={"volume_timeline": big_tl, "pitch_timeline": big_tl}
    )
    tr = base.transcript.model_copy(
        update={"full_text": "あ" * 50000, "segments": big_segs}
    )
    big = base.model_copy(update={"audio_metrics": am, "transcript": tr})

    trimmed = _trim_result(big)
    assert len(trimmed.audio_metrics.volume_timeline) == MAX_TIMELINE_POINTS
    assert len(trimmed.audio_metrics.pitch_timeline) == MAX_TIMELINE_POINTS
    assert len(trimmed.transcript.full_text) == MAX_TRANSCRIPT_CHARS
    assert len(trimmed.transcript.segments) == MAX_TRANSCRIPT_SEGMENTS
    # 間引きは先頭と末尾の点を必ず保持する（チャート端がずれない）
    assert trimmed.audio_metrics.volume_timeline[0] == big_tl[0]
    assert trimmed.audio_metrics.volume_timeline[-1] == big_tl[-1]
    # 上限内の結果は変更せずそのまま返す（不要なコピーを避ける）
    assert _trim_result(base) is base


def test_trim_result_byte_guard() -> None:
    # 個別フィールド暴走（巨大な strengths）でも最終的に 1MiB 安全圏に収める。
    from src.repositories.job_repo import MAX_RESULT_BYTES, _trim_result

    base = _sample_result()
    huge = base.model_copy(update={"strengths": ["あ" * 1_000_000]})
    assert len(huge.model_dump_json().encode()) > MAX_RESULT_BYTES  # 前提: 暴走で超過

    trimmed = _trim_result(huge)
    assert len(trimmed.model_dump_json().encode()) <= MAX_RESULT_BYTES
    assert trimmed.transcript.segments == []  # 重い順に破棄される


def test_list_is_owner_scoped_and_sorted(repo: JobRepository) -> None:
    owner = "owner-" + uuid.uuid4().hex
    other = "other-" + uuid.uuid4().hex
    ids = []
    for _ in range(2):
        jid = uuid.uuid4().hex
        repo.create(jid, owner_uid=owner, expire_at=_future(), content_type="video/mp4")
        ids.append(jid)
    repo.create(uuid.uuid4().hex, owner_uid=other, expire_at=_future(), content_type="video/mp4")

    summaries = repo.list_for_owner(owner)
    assert {s.job_id for s in summaries} == set(ids)
    # created_at 降順
    times = [s.created_at for s in summaries]
    assert times == sorted(times, reverse=True)
