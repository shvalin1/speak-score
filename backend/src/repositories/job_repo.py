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


COLLECTION = "interviews"


class FirestoreJobRepo(JobRepository):
    """本番ストア（Firestore Native）。

    ドキュメント形は InMemoryJobRepo の dict を写したもの（collection=interviews / id=job_id）。
    awaiting_upload→processing の一度きり遷移とリース取得は read-check-write を
    @firestore.transactional で原子化し、二重 enqueue / 同時 worker を防ぐ（§5.1, §10）。

    NOTE(石川/Step2): result はインライン保存。AnalysisResult が大きい動画で
    Firestore の 1MiB ドキュメント上限に触れうる（audio timeline + transcript）。
    実データ投入時に閾値超過分を GCS へオフロードする 1MiB 対策を入れる（§5.1, §10）。
    """

    def __init__(self) -> None:
        from google.cloud import firestore  # 遅延import（重い & 本番経路のみ）

        settings = get_settings()
        self._fs = firestore.Client(project=settings.gcp_project or None)
        self._col = self._fs.collection(COLLECTION)

    def _ref(self, job_id: str):
        return self._col.document(job_id)

    def create(self, job_id: str, owner_uid: str, expire_at: datetime) -> None:
        self._ref(job_id).set(
            {
                "job_id": job_id,
                "owner_uid": owner_uid,
                "status": JobStatus.awaiting_upload.value,
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
        )

    def _to_job(self, d: dict) -> InterviewJob:
        result = d.get("result")
        return InterviewJob(
            job_id=d["job_id"],
            status=JobStatus(d["status"]),
            stage=ProcessingStage(d["stage"]) if d.get("stage") else None,
            created_at=d["created_at"],
            completed_at=d.get("completed_at"),
            error=d.get("error"),
            result=AnalysisResult.model_validate(result) if result else None,
        )

    def get(self, job_id: str) -> InterviewJob | None:
        snap = self._ref(job_id).get()
        return self._to_job(snap.to_dict()) if snap.exists else None

    def get_owner(self, job_id: str) -> str | None:
        snap = self._ref(job_id).get()
        return snap.to_dict().get("owner_uid") if snap.exists else None

    def mark_processing(self, job_id: str) -> bool:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(txn) -> bool:
            ref = self._ref(job_id)
            snap = ref.get(transaction=txn)
            if not snap.exists or snap.get("status") != JobStatus.awaiting_upload.value:
                return False
            txn.update(ref, {"status": JobStatus.processing.value})
            return True

        return _txn(self._fs.transaction())

    def try_acquire_lease(self, job_id: str, worker_id: str) -> bool:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(txn) -> bool:
            ref = self._ref(job_id)
            snap = ref.get(transaction=txn)
            if not snap.exists or snap.get("status") != JobStatus.processing.value:
                return False
            lease = snap.get("lease_expires_at")
            if lease is not None and lease > _now():
                return False  # 別 worker が処理中
            txn.update(
                ref,
                {
                    "lease_owner": worker_id,
                    "lease_expires_at": _now() + LEASE_DURATION,
                    "attempt_count": (snap.get("attempt_count") or 0) + 1,
                    "stage": ProcessingStage.extracting_audio.value,
                },
            )
            return True

        return _txn(self._fs.transaction())

    def renew_lease(self, job_id: str, worker_id: str) -> None:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(txn) -> None:
            ref = self._ref(job_id)
            snap = ref.get(transaction=txn)
            if snap.exists and snap.get("lease_owner") == worker_id:
                txn.update(ref, {"lease_expires_at": _now() + LEASE_DURATION})

        _txn(self._fs.transaction())

    def release_lease(self, job_id: str) -> None:
        self._ref(job_id).update({"lease_owner": None, "lease_expires_at": None})

    def update_stage(self, job_id: str, stage: ProcessingStage) -> None:
        self._ref(job_id).update({"stage": stage.value})

    def complete(self, job_id: str, result: AnalysisResult) -> None:
        self._ref(job_id).update(
            {
                "status": JobStatus.completed.value,
                "stage": None,
                "result": result.model_dump(mode="json"),
                "completed_at": _now(),
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )

    def fail(self, job_id: str, user_msg: str) -> None:
        self._ref(job_id).update(
            {
                "status": JobStatus.failed.value,
                "error": user_msg,
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )

    def list_for_owner(self, owner_uid: str) -> list[InterviewSummary]:
        from google.cloud.firestore_v1 import FieldFilter

        # owner_uid 等価フィルタのみ（created_at の並べ替えは Python 側で行い複合インデックス不要）
        docs = self._col.where(filter=FieldFilter("owner_uid", "==", owner_uid)).stream()
        out: list[InterviewSummary] = []
        for snap in docs:
            d = snap.to_dict()
            result = d.get("result")
            out.append(
                InterviewSummary(
                    job_id=d["job_id"],
                    created_at=d["created_at"],
                    overall_score=result["overall_score"] if result else None,
                    status=JobStatus(d["status"]),
                )
            )
        return sorted(out, key=lambda s: s.created_at, reverse=True)


_repo: JobRepository | None = None


def get_job_repo() -> JobRepository:
    """設定に応じてストアを選択。

    gcp_project が設定済みなら Firestore（FIRESTORE_EMULATOR_HOST があれば
    firestore.Client が自動でエミュレータに接続する）。未設定ならローカル in-memory。
    """
    global _repo
    if _repo is None:
        settings = get_settings()
        _repo = FirestoreJobRepo() if settings.gcp_project else InMemoryJobRepo()
    return _repo
