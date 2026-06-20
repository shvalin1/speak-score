// APIクライアント（石川が実装し、署名URL3ステップ・トークン付与・モックを隠蔽）。
// 加藤は uploadInterview / getInterview / useInterviewJob を呼ぶだけでよい。
// 設計根拠: design_review_and_frontback.md §6.4, §6.5

import type {
  AnalysisResult,
  CreateInterviewResponse,
  InterviewJob,
  InterviewSummary,
  JobStatus,
  ProcessingStage,
  StartResponse,
} from "../types/interview";
import sampleResult from "@shared/mock_data/sample_result.json";
import { getIdToken } from "./auth";

// 同一オリジンの /api（本番はNginx proxy、ローカルはdocker-compose or vite proxy）。
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
// VITE_USE_MOCK=1 でバックエンド無しでも全UIが動く（加藤の開発用）。
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "1";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---- 実API用の薄いfetchラッパ（Firebase IDトークンを自動付与） -------------

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getIdToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      /* ignore */
    }
    throw new Error(`API ${res.status} ${res.statusText} ${detail}`);
  }
  return (await res.json()) as T;
}

// ---- 公開ヘルパ（加藤が使うのはこれだけ） ----------------------------------

/**
 * 署名URLの3ステップ（POST /interviews → PUT GCS → POST /{id}/start）を内部で吸収する。
 * 返り値は job_id（以降ポーリングに使う）。
 */
export async function uploadInterview(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  if (USE_MOCK) return mockUploadInterview(file, onProgress);

  // 1. ジョブ作成＋署名URL取得
  const created = await jsonOrThrow<CreateInterviewResponse>(
    await authedFetch("/interviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      }),
    }),
  );

  // 2. 署名URLへ動画を直接PUT（進捗%を通知）
  await putToSignedUrl(created.upload_url, created.upload_headers, file, onProgress);

  // 3. アップロード完了通知→enqueue
  await jsonOrThrow<StartResponse>(
    await authedFetch(`/interviews/${created.job_id}/start`, { method: "POST" }),
  );

  return created.job_id;
}

export async function getInterview(jobId: string): Promise<InterviewJob> {
  if (USE_MOCK) return mockGetInterview(jobId);
  return jsonOrThrow<InterviewJob>(await authedFetch(`/interviews/${jobId}`));
}

export async function listInterviews(): Promise<InterviewSummary[]> {
  if (USE_MOCK) return mockListInterviews();
  return jsonOrThrow<InterviewSummary[]>(await authedFetch("/interviews"));
}

// XHRで進捗%を取れる署名URL PUT（fetchはアップロード進捗が取れないためXHR）。
function putToSignedUrl(
  url: string,
  headers: Record<string, string>,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed: ${xhr.status}`));
    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.send(file);
  });
}

// ---- モック実装（delay＋状態遷移マシン） -----------------------------------
// 静的JSONだけだと「ポーリングをどう模すか」で加藤が詰まるため、
// 時間経過で awaiting_upload → processing(各stage) → completed を返すモックを用意する。

// サイズ/フォーマットはUploadZoneのクライアント側検証で弾かれるため、アップロード後の
// サーバー側エラーとしては起こり得ない。アップロード成功後に現実的に起こりうる失敗
// （AGENTS.mdのパイプライン: ffmpeg→Whisper→librosa→scoring→LLM）に合わせる。
type MockFailReason = "audio" | "transcribe" | "server";

interface MockJob {
  job_id: string;
  created_at: string;
  startedAt: number; // /start を押した時刻（performance.now基準）
  failReason: MockFailReason | null; // テスト用: ファイル名に "fail" を含めると失敗扱いにする（Issue #9）
}

// ファイル名に "fail" を含めると失敗をシミュレートする（テスト用）。
// "fail-audio" / "fail-transcribe" で種別を変え、formatJobError（JobPage.tsx）の
// 分岐を動作確認できるようにする。それ以外の "fail" は汎用サーバーエラー（タイムアウト等）扱い。
function detectMockFailure(filename: string): MockFailReason | null {
  const lower = filename.toLowerCase();
  if (!lower.includes("fail")) return null;
  if (lower.includes("audio")) return "audio";
  if (lower.includes("transcribe")) return "transcribe";
  return "server";
}

const MOCK_ERROR_MESSAGES: Record<MockFailReason, string> = {
  audio: "mock: simulated error (failed to extract audio track from video)",
  transcribe: "mock: simulated error (transcription failed - audio too short or silent)",
  server: "mock: simulated server error (timeout calling evaluation API)",
};

// 本物のFirestoreはリロードしても消えないが、Mapだけだとブラウザのメモリ上に
// しか無くリロードで消えてしまう。sessionStorageにも保存し、タブを閉じるまでは
// 永続するようにして本番の挙動に近づける（startedAtは実時刻なので、復元後も
// 経過時間から進捗が正しく再計算される）。
const MOCK_JOBS_STORAGE_KEY = "speakscore:mockJobs";

function loadMockJobs(): Map<string, MockJob> {
  try {
    const raw = sessionStorage.getItem(MOCK_JOBS_STORAGE_KEY);
    return raw ? new Map(JSON.parse(raw) as [string, MockJob][]) : new Map();
  } catch {
    return new Map();
  }
}

function saveMockJobs(): void {
  sessionStorage.setItem(MOCK_JOBS_STORAGE_KEY, JSON.stringify([...mockJobs]));
}

const mockJobs = loadMockJobs();

/**
 * モックの履歴を全消去する。本物のFirebase認証ならログアウト→匿名再ログインで
 * owner_uidが変わり履歴は自然に空になるが、モックは常に同じmock-uidを返すため
 * 明示的にリセットしないとログアウト後も前のユーザーの履歴が残ってしまう。
 * AuthGate がログアウトを検知したタイミングで呼ぶ。
 */
export function resetMockInterviews(): void {
  mockJobs.clear();
  sessionStorage.removeItem(MOCK_JOBS_STORAGE_KEY);
}
const STAGE_TIMELINE: { until: number; stage: ProcessingStage | null }[] = [
  { until: 1500, stage: null }, // queued（enqueue直後・worker未着手）
  { until: 3000, stage: "extracting_audio" },
  { until: 5000, stage: "transcribing" },
  { until: 7000, stage: "analyzing_audio" },
  { until: 9000, stage: "evaluating" },
];
const MOCK_TOTAL_MS = 10000;

async function mockUploadInterview(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  // アップロード進捗を擬似的に進める
  for (let p = 0; p <= 100; p += 20) {
    onProgress?.(p);
    await sleep(120);
  }
  const job_id = `mock-${Math.random().toString(36).slice(2, 10)}`;
  mockJobs.set(job_id, {
    job_id,
    created_at: new Date().toISOString(),
    startedAt: Date.now(),
    failReason: detectMockFailure(file.name),
  });
  saveMockJobs();
  return job_id;
}

async function mockGetInterview(jobId: string): Promise<InterviewJob> {
  await sleep(150);
  const job = mockJobs.get(jobId);
  if (!job) throw new Error("API 404 mock job not found");
  const elapsed = Date.now() - job.startedAt;

  if (elapsed >= MOCK_TOTAL_MS) {
    if (job.failReason) {
      return {
        job_id: jobId,
        status: "failed",
        stage: null,
        created_at: job.created_at,
        completed_at: new Date().toISOString(),
        error: MOCK_ERROR_MESSAGES[job.failReason],
        result: null,
      };
    }
    return {
      job_id: jobId,
      status: "completed",
      stage: null,
      created_at: job.created_at,
      completed_at: new Date().toISOString(),
      error: null,
      result: sampleResult as unknown as AnalysisResult,
    };
  }
  // 注意: STAGE_TIMELINE[0].stage は意図的に null（待機中）。
  // `?? "evaluating"` だと null も「該当なし」と誤判定するため、見つからなかった場合のみ
  // フォールバックするように分けている。
  const match = STAGE_TIMELINE.find((s) => elapsed < s.until);
  const stage = match ? match.stage : "evaluating";
  return {
    job_id: jobId,
    status: "processing",
    stage,
    created_at: job.created_at,
    completed_at: null,
    error: null,
    result: null,
  };
}

async function mockListInterviews(): Promise<InterviewSummary[]> {
  await sleep(150);
  return [...mockJobs.values()].map((j) => {
    const done = Date.now() - j.startedAt >= MOCK_TOTAL_MS;
    const status: JobStatus = done ? (j.failReason ? "failed" : "completed") : "processing";
    return {
      job_id: j.job_id,
      created_at: j.created_at,
      overall_score: status === "completed" ? sampleResult.overall_score : null,
      status,
    };
  });
}
