"""ジョブ/結果ストア。

本番は Firestore（Nativeモード）。ローカル開発/テストは in-memory で同一インターフェースを満たす。
リース方式・status/stage分離・1MiB対策は設計 §5.1, §10 を参照。

NOTE(石川/Step1b): FirestoreJobRepo は本番経路スパイクで実装する。
ここでは InMemoryJobRepo を完成させ、API骨格をローカルで動かせるようにする。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from threading import Lock

from ..core.config import get_settings
from ..schemas.interview import (
    AnalysisResult,
    InterviewJob,
    InterviewSummary,
    JobStatus,
    ProcessingStage,
)

LEASE_DURATION = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(UTC)


class JobRepository(ABC):
    @abstractmethod
    def create(self, job_id: str, owner_uid: str, expire_at: datetime) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> InterviewJob | None: ...

    @abstractmethod
    def get_owner(self, job_id: str) -> str | None: ...

    @abstractmethod
    def mark_processing(self, job_id: str) -> bool:
        """awaiting_upload のときだけ processing に遷移。遷移できたら True（二重enqueue防止）。"""

    @abstractmethod
    def try_acquire_lease(self, job_id: str, worker_id: str) -> bool:
        """status==processing かつリース失効なら取得し stage=extracting_audio に。"""

    @abstractmethod
    def renew_lease(self, job_id: str, worker_id: str) -> None: ...

    @abstractmethod
    def release_lease(self, job_id: str) -> None: ...

    @abstractmethod
    def update_stage(self, job_id: str, stage: ProcessingStage) -> None: ...

    @abstractmethod
    def complete(self, job_id: str, result: AnalysisResult) -> None: ...

    @abstractmethod
    def fail(self, job_id: str, user_msg: str) -> None: ...

    @abstractmethod
    def list_for_owner(self, owner_uid: str) -> list[InterviewSummary]: ...


class InMemoryJobRepo(JobRepository):
    """プロセス内辞書ストア。ローカル開発・テスト用（本番では使わない）。"""

    def __init__(self) -> None:
        self._db: dict[str, dict] = {}
        self._lock = Lock()

    def create(self, job_id: str, owner_uid: str, expire_at: datetime) -> None:
        with self._lock:
            self._db[job_id] = {
                "job_id": job_id,
                "owner_uid": owner_uid,
                "status": JobStatus.awaiting_upload,
                "stage": None,
                "created_at": _now(),
                "expire_at": expire_at,
                "completed_at": None,
                "error": None,
                "result": None,
                "lease_owner": None,
                "lease_expires_at": None,
                "attempt_count": 0,
            }

    def _to_job(self, d: dict) -> InterviewJob:
        return InterviewJob(
            job_id=d["job_id"],
            status=d["status"],
            stage=d["stage"],
            created_at=d["created_at"],
            completed_at=d["completed_at"],
            error=d["error"],
            result=d["result"],
        )

    def get(self, job_id: str) -> InterviewJob | None:
        with self._lock:
            d = self._db.get(job_id)
            return self._to_job(d) if d else None

    def get_owner(self, job_id: str) -> str | None:
        with self._lock:
            d = self._db.get(job_id)
            return d["owner_uid"] if d else None

    def mark_processing(self, job_id: str) -> bool:
        with self._lock:
            d = self._db.get(job_id)
            if not d or d["status"] != JobStatus.awaiting_upload:
                return False
            d["status"] = JobStatus.processing
            return True

    def try_acquire_lease(self, job_id: str, worker_id: str) -> bool:
        with self._lock:
            d = self._db.get(job_id)
            if not d or d["status"] != JobStatus.processing:
                return False
            lease = d["lease_expires_at"]
            if lease is not None and lease > _now():
                return False  # 別workerが処理中
            d["lease_owner"] = worker_id
            d["lease_expires_at"] = _now() + LEASE_DURATION
            d["attempt_count"] += 1
            d["stage"] = ProcessingStage.extracting_audio
            return True

    def renew_lease(self, job_id: str, worker_id: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d and d["lease_owner"] == worker_id:
                d["lease_expires_at"] = _now() + LEASE_DURATION

    def release_lease(self, job_id: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d:
                d["lease_owner"] = None
                d["lease_expires_at"] = None

    def update_stage(self, job_id: str, stage: ProcessingStage) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d:
                d["stage"] = stage

    def complete(self, job_id: str, result: AnalysisResult) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d:
                d["status"] = JobStatus.completed
                d["stage"] = None
                d["result"] = result
                d["completed_at"] = _now()
                d["lease_owner"] = None
                d["lease_expires_at"] = None

    def fail(self, job_id: str, user_msg: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d:
                d["status"] = JobStatus.failed
                d["error"] = user_msg
                d["lease_owner"] = None
                d["lease_expires_at"] = None

    def list_for_owner(self, owner_uid: str) -> list[InterviewSummary]:
        with self._lock:
            out = []
            for d in self._db.values():
                if d["owner_uid"] != owner_uid:
                    continue
                score = d["result"].overall_score if d["result"] else None
                out.append(
                    InterviewSummary(
                        job_id=d["job_id"],
                        created_at=d["created_at"],
                        overall_score=score,
                        status=d["status"],
                    )
                )
            return sorted(out, key=lambda s: s.created_at, reverse=True)


class FirestoreJobRepo(JobRepository):
    """本番ストア。TODO(石川/Step1b): Firestore transaction でリース/遷移を実装。"""

    def __init__(self) -> None:
        raise NotImplementedError(
            "FirestoreJobRepo は Step1b（本番経路スパイク）で実装する。"
            "ローカルは AUTH/Firestore 未設定なので InMemoryJobRepo を使う。"
        )

    def create(self, job_id: str, owner_uid: str, expire_at: datetime) -> None: ...
    def get(self, job_id: str) -> InterviewJob | None: ...
    def get_owner(self, job_id: str) -> str | None: ...
    def mark_processing(self, job_id: str) -> bool: ...
    def try_acquire_lease(self, job_id: str, worker_id: str) -> bool: ...
    def renew_lease(self, job_id: str, worker_id: str) -> None: ...
    def release_lease(self, job_id: str) -> None: ...
    def update_stage(self, job_id: str, stage: ProcessingStage) -> None: ...
    def complete(self, job_id: str, result: AnalysisResult) -> None: ...
    def fail(self, job_id: str, user_msg: str) -> None: ...
    def list_for_owner(self, owner_uid: str) -> list[InterviewSummary]: ...


_repo: JobRepository | None = None


def get_job_repo() -> JobRepository:
    """設定に応じてストアを選択。Firestore未設定ならローカル in-memory。"""
    global _repo
    if _repo is None:
        settings = get_settings()
        if settings.gcp_project and not settings.firestore_emulator_host:
            _repo = FirestoreJobRepo()
        else:
            _repo = InMemoryJobRepo()
    return _repo
