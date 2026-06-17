"""API契約（凍結）: フロント/バック共有のデータモデル。

このファイルが SpeakScore の応答契約の唯一の出典（source of truth）。
`frontend/src/types/interview.ts` はこの TypeScript ミラーであり、
両者は常に一致させること（片方だけ変えない）。

設計根拠: design_review_and_frontback.md §3.1
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    awaiting_upload = "awaiting_upload"  # 署名URL発行済み・GCSへのPUT待ち（/start前）
    processing = "processing"            # /start後〜worker処理中（stageで細分）
    completed = "completed"
    failed = "failed"


class ProcessingStage(str, Enum):
    extracting_audio = "extracting_audio"
    transcribing = "transcribing"
    analyzing_audio = "analyzing_audio"
    evaluating = "evaluating"
    # stage=None は「enqueue済み・worker未着手（queued）」を表す


class DimensionSource(str, Enum):
    computed = "computed"   # 音声特徴量から決定論的に算出
    llm = "llm"             # LLMが採点


class Dimension(BaseModel):
    score: int = Field(ge=0, le=100)
    comment: str
    source: DimensionSource


class Dimensions(BaseModel):
    """固定4軸を明示型で保証（dictにしないことでKeyError/欠落を防ぐ）"""

    content: Dimension      # source=llm
    structure: Dimension    # source=llm
    delivery: Dimension     # source=computed
    confidence: Dimension   # source=computed


class Segment(BaseModel):
    start: float  # 秒
    end: float


class TimePoint(BaseModel):
    t: float      # 秒
    value: float


class AudioMetrics(BaseModel):
    speech_rate_cpm: float            # 文字/分（句読点・空白除外。日本語話速プロキシ）
    filler_count: int
    filler_rate: float                # フィラー/分
    silence_ratio: float              # 無音時間の割合 0-1
    silence_segments: list[Segment]
    pitch_mean: float                 # Hz
    pitch_std: float                  # 大=抑揚あり / 小=単調
    volume_mean: float                # rms平均
    volume_cv: float                  # rms変動係数（=std/mean。大きすぎ=不安定）
    volume_timeline: list[TimePoint]  # AudioTimeline用（rms）
    pitch_timeline: list[TimePoint]   # AudioTimeline用（yin）


class FillerHit(BaseModel):
    text: str
    start_char: int   # full_text内の文字オフセット（ハイライト用）
    end_char: int


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None   # 話者分離フェーズで使用


class Transcript(BaseModel):
    full_text: str
    duration_sec: float
    segments: list[TranscriptSegment]
    fillers: list[FillerHit]


class AnalysisResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    dimensions: Dimensions
    audio_metrics: AudioMetrics
    transcript: Transcript
    strengths: list[str]
    improvements: list[str]


class InterviewJob(BaseModel):
    """GET /interviews/{job_id} のレスポンス"""

    job_id: str
    status: JobStatus
    stage: ProcessingStage | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None          # ユーザー向け文言のみ（内部例外は入れない）
    result: AnalysisResult | None = None


class CreateInterviewRequest(BaseModel):
    """POST /interviews のリクエスト（動画は送らず、メタ情報のみで署名URLを得る）"""

    filename: str
    content_type: str          # 例 video/mp4
    size_bytes: int            # クライアント申告サイズ（上限チェック用）


class CreateInterviewResponse(BaseModel):
    """POST /interviews のレスポンス（署名URL発行）"""

    job_id: str
    status: JobStatus          # = awaiting_upload
    upload_url: str            # GCS V4署名URL（PUT・期限15分）
    upload_headers: dict[str, str]  # PUT時に付ける必須ヘッダ（Content-Type等）


class StartResponse(BaseModel):
    """POST /interviews/{job_id}/start のレスポンス"""

    job_id: str
    status: JobStatus          # = processing


class InterviewSummary(BaseModel):
    """GET /interviews 一覧の各要素"""

    job_id: str
    created_at: datetime
    overall_score: int | None
    status: JobStatus
