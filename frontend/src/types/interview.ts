// API契約（凍結）: backend/src/schemas/interview.py の TypeScript ミラー。
// 両者は常に一致させること（片方だけ変えない）。
// 設計根拠: design_review_and_frontback.md §6.1

export type JobStatus = "awaiting_upload" | "processing" | "completed" | "failed";
export type ProcessingStage =
  | "extracting_audio" | "diarizing" | "transcribing" | "analyzing_audio" | "evaluating";
export type DimensionSource = "computed" | "llm";

export interface Dimension { score: number; comment: string; source: DimensionSource; }
export interface Dimensions {
  content: Dimension; structure: Dimension; delivery: Dimension; confidence: Dimension;
}
export interface Segment { start: number; end: number; }
export interface TimePoint { t: number; value: number; }

export interface AudioMetrics {
  speech_rate_cpm: number;
  filler_count: number;
  filler_rate: number;
  silence_ratio: number;
  silence_segments: Segment[];
  pitch_mean: number;
  pitch_std: number;
  volume_mean: number;
  volume_cv: number;
  volume_timeline: TimePoint[];
  pitch_timeline: TimePoint[];
}
export interface FillerHit { text: string; start_char: number; end_char: number; }
export interface TranscriptSegment { start: number; end: number; text: string; speaker?: string | null; }
export interface Transcript {
  full_text: string; duration_sec: number;
  segments: TranscriptSegment[]; fillers: FillerHit[];
}
export interface QaAudio {
  pitch_mean: number;
  pitch_std: number;
  speech_rate_cpm: number;
  filler_count: number;
}
export type QuestionIntent =
  | "self_intro" | "motivation" | "strength" | "weakness"
  | "experience" | "reverse" | "other";
export interface QaSegment {
  index: number;
  question: string;
  answer: string;
  start: number;
  end: number;
  score: number;
  comment: string;
  intent: QuestionIntent;
  is_reverse_question: boolean;
  question_inferred: boolean;
  audio?: QaAudio | null;
}
export interface Minutes {
  summary: string;
  topics: string[];
  key_points: string[];
}
export interface AnalysisResult {
  overall_score: number;
  dimensions: Dimensions;
  audio_metrics: AudioMetrics;
  transcript: Transcript;
  strengths: string[];
  improvements: string[];
  // 話者分離→LLM整形エピック（004/005）で追加。旧データは undefined/空配列で素通り。
  minutes?: Minutes | null;
  qa_segments?: QaSegment[];
}
export interface InterviewJob {
  job_id: string; status: JobStatus; stage?: ProcessingStage | null;
  created_at: string; completed_at?: string | null;
  error?: string | null; result?: AnalysisResult | null;
}
export interface CreateInterviewResponse {
  job_id: string; status: JobStatus;
  upload_url: string; upload_headers: Record<string, string>;
}
export interface StartResponse { job_id: string; status: JobStatus; }
export interface InterviewSummary {
  job_id: string; created_at: string; overall_score: number | null; status: JobStatus;
}
