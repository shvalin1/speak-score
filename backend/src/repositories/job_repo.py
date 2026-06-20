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

from ..core.config import LEASE_DURATION_SECONDS, get_settings
from ..schemas.interview import (
    AnalysisResult,
    InterviewJob,
    InterviewSummary,
    JobStatus,
    ProcessingStage,
)

LEASE_DURATION = timedelta(seconds=LEASE_DURATION_SECONDS)  # config と単一の出典

# Firestore の 1MiB ドキュメント上限対策。長尺動画の timeline/transcript で complete が
# 落ちるのを防ぐため、保存前に間引き/切詰めする（§5.1, §10 / step2_plan HIGH）。
MAX_TIMELINE_POINTS = 200
MAX_TRANSCRIPT_CHARS = 20000
MAX_TRANSCRIPT_SEGMENTS = 2000
# 上の上限は要素数/文字数ベースで、segment.text 個別や strengths/improvements の暴走
# （LLM/Whisper 異常出力）は捕捉できない。シリアライズ後バイト数で測る最終防波堤。
# Firestore の 1MiB(=1048576B) に安全マージンを取る。
MAX_RESULT_BYTES = 900 * 1024


def _now() -> datetime:
    return datetime.now(UTC)


def _downsample(points: list, n: int = MAX_TIMELINE_POINTS) -> list:
    """等間隔に最大 n 点へ間引く（先頭と末尾の点を必ず含む）。"""
    if len(points) <= n:
        return points
    last = len(points) - 1
    return [points[round(i * last / (n - 1))] for i in range(n)]


def _trim_result(result: AnalysisResult) -> AnalysisResult:
    """1MiB 対策: timeline を間引き、transcript を上限内に切詰める（必要時のみコピー）。"""
    am = result.audio_metrics
    over_tl = (
        len(am.volume_timeline) > MAX_TIMELINE_POINTS
        or len(am.pitch_timeline) > MAX_TIMELINE_POINTS
    )
    if over_tl:
        am = am.model_copy(
            update={
                "volume_timeline": _downsample(am.volume_timeline),
                "pitch_timeline": _downsample(am.pitch_timeline),
            }
        )
    tr = result.transcript
    if len(tr.full_text) > MAX_TRANSCRIPT_CHARS or len(tr.segments) > MAX_TRANSCRIPT_SEGMENTS:
        tr = tr.model_copy(
            update={
                "full_text": tr.full_text[:MAX_TRANSCRIPT_CHARS],
                "segments": tr.segments[:MAX_TRANSCRIPT_SEGMENTS],
            }
        )
    if am is result.audio_metrics and tr is result.transcript:
        trimmed = result
    else:
        trimmed = result.model_copy(update={"audio_metrics": am, "transcript": tr})
    return _byte_guard(trimmed)


def _byte_guard(result: AnalysisResult) -> AnalysisResult:
    """シリアライズ後バイト数が上限内ならそのまま。超過時は重い順に破棄/切詰める。

    要素数/文字数の上限を抜けた個別フィールドの暴走に対する保険。これにより
    repo.complete の Firestore 書込が 1MiB 超で失敗→ジョブ滞留する経路を塞ぐ。
    """
    if len(result.model_dump_json().encode()) <= MAX_RESULT_BYTES:
        return result
    # 最も重い transcript.segments を破棄し、自由記述リストを件数/文字数で詰める
    tr = result.transcript.model_copy(update={"segments": []})
    result = result.model_copy(
        update={
            "transcript": tr,
            "strengths": [s[:2000] for s in result.strengths[:20]],
            "improvements": [s[:2000] for s in result.improvements[:20]],
        }
    )
    if len(result.model_dump_json().encode()) > MAX_RESULT_BYTES:
        # それでも超えるなら full_text を更に詰める（最後の砦）
        tr = result.transcript.model_copy(update={"full_text": result.transcript.full_text[:5000]})
        result = result.model_copy(update={"transcript": tr})
    return result


class JobRepository(ABC):
    @abstractmethod
    def create(
        self, job_id: str, owner_uid: str, expire_at: datetime, content_type: str
    ) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> InterviewJob | None: ...

    @abstractmethod
    def get_owner(self, job_id: str) -> str | None: ...

    @abstractmethod
    def get_content_type(self, job_id: str) -> str | None:
        """アップロード時の content_type（内部用）。

        抽出（拡張子推定）・/start メタデータ確認で必要。GET レスポンスの
        InterviewJob 契約には載せない（内部情報のため）。
        """

    @abstractmethod
    def mark_processing(self, job_id: str) -> bool:
        """awaiting_upload のときだけ processing に遷移。遷移できたら True（二重enqueue防止）。"""

    @abstractmethod
    def try_acquire_lease(self, job_id: str, worker_id: str) -> bool:
        """status==processing かつリース失効なら取得し stage=extracting_audio に。"""

    @abstractmethod
    def renew_lease(self, job_id: str, worker_id: str) -> None: ...

    @abstractmethod
    def release_lease(self, job_id: str, worker_id: str) -> None:
        """lease 保持者(worker_id 一致時)のみ解放（CAS）。失効後に奪取した別 worker を守る。"""

    @abstractmethod
    def get_attempt_count(self, job_id: str) -> int:
        """これまでのリース取得回数（= 試行回数）。最終試行判定に使う。"""

    @abstractmethod
    def update_stage(self, job_id: str, stage: ProcessingStage) -> None: ...

    @abstractmethod
    def complete(self, job_id: str, result: AnalysisResult, worker_id: str) -> None:
        """lease 保持者のみ completed に（CAS）。result は 1MiB 対策で間引いて保存。"""

    @abstractmethod
    def fail(self, job_id: str, user_msg: str, worker_id: str) -> None:
        """lease 保持者のみ failed に（CAS）。"""

    @abstractmethod
    def list_for_owner(self, owner_uid: str) -> list[InterviewSummary]: ...


class InMemoryJobRepo(JobRepository):
    """プロセス内辞書ストア。ローカル開発・テスト用（本番では使わない）。"""

    def __init__(self) -> None:
        self._db: dict[str, dict] = {}
        self._lock = Lock()

    def create(
        self, job_id: str, owner_uid: str, expire_at: datetime, content_type: str
    ) -> None:
        with self._lock:
            self._db[job_id] = {
                "job_id": job_id,
                "owner_uid": owner_uid,
                "content_type": content_type,
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

    def get_content_type(self, job_id: str) -> str | None:
        with self._lock:
            d = self._db.get(job_id)
            return d.get("content_type") if d else None

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

    def release_lease(self, job_id: str, worker_id: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d and d["lease_owner"] == worker_id:
                d["lease_owner"] = None
                d["lease_expires_at"] = None

    def get_attempt_count(self, job_id: str) -> int:
        with self._lock:
            d = self._db.get(job_id)
            return d["attempt_count"] if d else 0

    def update_stage(self, job_id: str, stage: ProcessingStage) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d:
                d["stage"] = stage

    def complete(self, job_id: str, result: AnalysisResult, worker_id: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d and d["lease_owner"] == worker_id:
                d["status"] = JobStatus.completed
                d["stage"] = None
                d["result"] = _trim_result(result)
                d["completed_at"] = _now()
                d["lease_owner"] = None
                d["lease_expires_at"] = None

    def fail(self, job_id: str, user_msg: str, worker_id: str) -> None:
        with self._lock:
            d = self._db.get(job_id)
            if d and d["lease_owner"] == worker_id:
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
        self._fs = firestore.Client(project=settings.gcp_project)
        self._col = self._fs.collection(COLLECTION)

    def _ref(self, job_id: str):
        return self._col.document(job_id)

    def _safe_update(self, job_id: str, fields: dict) -> None:
        """doc 不在時は no-op（InMemoryJobRepo の `if d:` ガードと契約を揃える）。

        TTL 削除直後の遅延タスク等で対象が消えていても NotFound を投げない。
        """
        from google.api_core.exceptions import NotFound

        try:
            self._ref(job_id).update(fields)
        except NotFound:
            pass

    def _cas_update(self, job_id: str, worker_id: str, fields: dict) -> None:
        """lease_owner == worker_id のときだけ更新する条件付き書込み（CAS）。

        lease 失効後に別 worker が奪取したケースで、旧 worker が完了/失敗/解放を
        上書きするのを防ぐ（§5.1）。
        """
        from google.cloud import firestore

        @firestore.transactional
        def _txn(txn) -> None:
            ref = self._ref(job_id)
            snap = ref.get(transaction=txn)
            if snap.exists and snap.get("lease_owner") == worker_id:
                txn.update(ref, fields)

        _txn(self._fs.transaction())

    def create(
        self, job_id: str, owner_uid: str, expire_at: datetime, content_type: str
    ) -> None:
        self._ref(job_id).set(
            {
                "job_id": job_id,
                "owner_uid": owner_uid,
                "content_type": content_type,
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

    def get_content_type(self, job_id: str) -> str | None:
        snap = self._ref(job_id).get()
        return snap.to_dict().get("content_type") if snap.exists else None

    def get_attempt_count(self, job_id: str) -> int:
        snap = self._ref(job_id).get()
        return (snap.to_dict().get("attempt_count") or 0) if snap.exists else 0

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

    def release_lease(self, job_id: str, worker_id: str) -> None:
        self._cas_update(job_id, worker_id, {"lease_owner": None, "lease_expires_at": None})

    def update_stage(self, job_id: str, stage: ProcessingStage) -> None:
        self._safe_update(job_id, {"stage": stage.value})

    def complete(self, job_id: str, result: AnalysisResult, worker_id: str) -> None:
        self._cas_update(
            job_id,
            worker_id,
            {
                "status": JobStatus.completed.value,
                "stage": None,
                "result": _trim_result(result).model_dump(mode="json"),
                "completed_at": _now(),
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )

    def fail(self, job_id: str, user_msg: str, worker_id: str) -> None:
        self._cas_update(
            job_id,
            worker_id,
            {
                "status": JobStatus.failed.value,
                "error": user_msg,
                "lease_owner": None,
                "lease_expires_at": None,
            },
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
