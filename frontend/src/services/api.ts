// APIクライアント（石川が実装し、署名URL3ステップ・トークン付与・モックを隠蔽）。
// 加藤は uploadInterview / getInterview / useInterviewJob を呼ぶだけでよい。
// 設計根拠: design_review_and_frontback.md §6.4, §6.5

import type {
  AnalysisResult,
  CreateInterviewResponse,
  InterviewJob,
  InterviewSummary,
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

interface MockJob {
  job_id: string;
  created_at: string;
  startedAt: number; // /start を押した時刻（performance.now基準）
}

const mockJobs = new Map<string, MockJob>();
const STAGE_TIMELINE: { until: number; stage: ProcessingStage | null }[] = [
  { until: 1500, stage: null }, // queued（enqueue直後・worker未着手）
  { until: 3000, stage: "extracting_audio" },
  { until: 5000, stage: "transcribing" },
  { until: 7000, stage: "analyzing_audio" },
  { until: 9000, stage: "evaluating" },
];
const MOCK_TOTAL_MS = 10000;

async function mockUploadInterview(
  _file: File,
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
  });
  return job_id;
}

async function mockGetInterview(jobId: string): Promise<InterviewJob> {
  await sleep(150);
  const job = mockJobs.get(jobId);
  if (!job) throw new Error("API 404 mock job not found");
  const elapsed = Date.now() - job.startedAt;

  if (elapsed >= MOCK_TOTAL_MS) {
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
  const stage = STAGE_TIMELINE.find((s) => elapsed < s.until)?.stage ?? "evaluating";
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
  return [...mockJobs.values()].map((j) => ({
    job_id: j.job_id,
    created_at: j.created_at,
    overall_score: Date.now() - j.startedAt >= MOCK_TOTAL_MS ? sampleResult.overall_score : null,
    status: Date.now() - j.startedAt >= MOCK_TOTAL_MS ? "completed" : "processing",
  }));
}
