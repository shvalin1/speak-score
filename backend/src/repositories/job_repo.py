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

from pydantic import BaseModel

from ..core.config import LEASE_DURATION_SECONDS, get_settings
from ..schemas.interview import (
    AnalysisResult,
    InterviewJob,
    InterviewSummary,
    JobStatus,
    ProcessingStage,
)

LEASE_DURATION = timedelta(seconds=LEASE_DURATION_SECONDS)  # config と単一の出典

# 動画横断の設問一覧用 denormalized 索引コレクション（§5）。
QA_INDEX_COLLECTION = "qa_index"


class QaIndexEntry(BaseModel):
    """`qa_index` 1件（凍結契約ではない内部/レスポンス型）。

    本文 answer は持たず軽量。横断一覧は本索引だけを引き、AnalysisResult のフルロードと
    1MiB トリムの影響を回避する（§5/§13.1）。フロントの TS 型は Phase5 で追加。
    """

    job_id: str
    created_at: datetime
    index: int
    question: str
    score: int
    pitch_mean: float
    intent: str


def _qa_index_payloads(
    job_id: str, owner_uid: str, created_at: datetime, result: AnalysisResult
) -> list[dict]:
    """**トリム前の原本** result.qa_segments から索引ドキュメントを生成する（§13.1）。

    doc id = `{job_id}_{index}` で冪等化（再 complete で上書き）。
    """
    payloads: list[dict] = []
    for seg in result.qa_segments:
        payloads.append(
            {
                "doc_id": f"{job_id}_{seg.index}",
                "job_id": job_id,
                "owner_uid": owner_uid,
                "created_at": created_at,
                "index": seg.index,
                "question": seg.question,
                "score": seg.score,
                "pitch_mean": seg.audio.pitch_mean if seg.audio else 0.0,
                "intent": seg.intent.value,
            }
        )
    return payloads


def _to_qa_entry(d: dict) -> QaIndexEntry:
    return QaIndexEntry(
        job_id=d["job_id"],
        created_at=d["created_at"],
        index=d["index"],
        question=d["question"],
        score=d["score"],
        pitch_mean=d.get("pitch_mean", 0.0),
        intent=d.get("intent", "other"),
    )

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


def _over(result: AnalysisResult) -> bool:
    return len(result.model_dump_json().encode()) > MAX_RESULT_BYTES


def _byte_guard(result: AnalysisResult) -> AnalysisResult:
    """シリアライズ後バイト数が上限内ならそのまま。超過時は重い順に段階的に破棄/切詰める。

    各段で再測定し、上限内に収まった時点で打ち切る hard cap（§13.4）。破棄順は
    「transcript.segments → 自由記述 → qa_segments.answer（transcript と重複）→ 件数 →
    minutes → comment/full_text」。索引（qa_index）は complete 時に**トリム前の原本**から
    生成済みなので、ここで qa_segments を削っても横断一覧は欠落しない（§5/§13.1）。
    """
    if not _over(result):
        return result

    # 1. 最も重い transcript.segments を破棄し、自由記述リストを件数/文字数で詰める
    tr = result.transcript.model_copy(update={"segments": []})
    result = result.model_copy(
        update={
            "transcript": tr,
            "strengths": [s[:2000] for s in result.strengths[:20]],
            "improvements": [s[:2000] for s in result.improvements[:20]],
        }
    )
    if not _over(result):
        return result

    # 2. qa_segments.answer を切詰め（transcript と重複し長尺で効く）
    qa = [s.model_copy(update={"answer": s.answer[:500]}) for s in result.qa_segments]
    result = result.model_copy(update={"qa_segments": qa})
    if not _over(result):
        return result

    # 3. qa_segments の件数を制限
    result = result.model_copy(update={"qa_segments": result.qa_segments[:50]})
    if not _over(result):
        return result

    # 4. minutes を切詰め
    if result.minutes is not None:
        m = result.minutes.model_copy(
            update={
                "summary": result.minutes.summary[:2000],
                "key_points": result.minutes.key_points[:20],
                "topics": result.minutes.topics[:20],
            }
        )
        result = result.model_copy(update={"minutes": m})
    if not _over(result):
        return result

    # 5. 最後の砦: comment と full_text を更に詰める
    qa = [s.model_copy(update={"comment": s.comment[:200]}) for s in result.qa_segments]
    tr = result.transcript.model_copy(update={"full_text": result.transcript.full_text[:5000]})
    result = result.model_copy(update={"qa_segments": qa, "transcript": tr})
    return result


class JobRepository(ABC):
    @abstractmethod
    def create(
        self, job_id: str, owner_uid: str, expire_at: datetime | None, content_type: str
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

    @abstractmethod
    def list_qa_for_owner(self, owner_uid: str) -> list[QaIndexEntry]:
        """owner の全動画横断で設問別索引を返す（score 降順）。横断一覧（GET /qa）用。"""


class InMemoryJobRepo(JobRepository):
    """プロセス内辞書ストア。ローカル開発・テスト用（本番では使わない）。"""

    def __init__(self) -> None:
        self._db: dict[str, dict] = {}
        self._qa_index: dict[str, dict] = {}  # doc_id -> qa_index payload
        self._lock = Lock()

    def create(
        self, job_id: str, owner_uid: str, expire_at: datetime | None, content_type: str
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
                # qa_index は**トリム前の原本**から生成（Lock 下で原子化・§13.1）。
                # 再 complete に備え当該ジョブの旧索引を捨ててから書き直す（doc_id で冪等）。
                self._qa_index = {
                    k: v for k, v in self._qa_index.items() if v["job_id"] != job_id
                }
                for p in _qa_index_payloads(job_id, d["owner_uid"], d["created_at"], result):
                    self._qa_index[p["doc_id"]] = p

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

    def list_qa_for_owner(self, owner_uid: str) -> list[QaIndexEntry]:
        with self._lock:
            entries = [
                _to_qa_entry(v) for v in self._qa_index.values() if v["owner_uid"] == owner_uid
            ]
        return sorted(entries, key=lambda e: e.score, reverse=True)


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
        self._qa_col = self._fs.collection(QA_INDEX_COLLECTION)

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
        self, job_id: str, owner_uid: str, expire_at: datetime | None, content_type: str
    ) -> None:
        self._ref(job_id).set(
            {
                "job_id": job_id,
                "owner_uid": owner_uid,
                "content_type": content_type,
                "status": JobStatus.awaiting_upload.value,
                "stage": None,
                "created_at": _now(),
                # expire_at=None なら結果TTLを設定しない（デモは結果を保持・§13(A)）。
                # 動画(GCS)の1日削除は別ライフサイクルで維持。
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
        """lease 保持者のみ completed に（CAS）。同一 txn で qa_index も書く（§13.1）。

        索引は**トリム前の原本** result.qa_segments から生成。result 本体は _trim_result 後を保存。
        索引 doc id = `{job_id}_{index}` で冪等（再 complete で上書き）。クエリ無し純 set のため
        500 write/txn 上限内で適法（qa_segments は _byte_guard 段で 50 件に制限済み）。
        """
        from google.cloud import firestore

        trimmed = _trim_result(result).model_dump(mode="json")

        @firestore.transactional
        def _txn(txn) -> None:
            ref = self._ref(job_id)
            snap = ref.get(transaction=txn)
            if not (snap.exists and snap.get("lease_owner") == worker_id):
                return
            owner_uid = snap.get("owner_uid")
            created_at = snap.get("created_at")
            txn.update(
                ref,
                {
                    "status": JobStatus.completed.value,
                    "stage": None,
                    "result": trimmed,
                    "completed_at": _now(),
                    "lease_owner": None,
                    "lease_expires_at": None,
                },
            )
            for p in _qa_index_payloads(job_id, owner_uid, created_at, result):
                doc_id = p.pop("doc_id")
                txn.set(self._qa_col.document(doc_id), p)

        _txn(self._fs.transaction())

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

    def list_qa_for_owner(self, owner_uid: str) -> list[QaIndexEntry]:
        from google.cloud.firestore_v1 import FieldFilter

        # owner_uid 等価のみ。score 降順は Python 側で行い複合インデックス不要（§13.15）。
        docs = self._qa_col.where(filter=FieldFilter("owner_uid", "==", owner_uid)).stream()
        entries = [_to_qa_entry(snap.to_dict()) for snap in docs]
        return sorted(entries, key=lambda e: e.score, reverse=True)


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
