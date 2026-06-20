// job_id をポーリングして進捗・結果を返すフック。
// status が completed/failed で停止。間隔は5秒固定（毎回 verify_id_token が走るため詰めすぎない）。
// 設計根拠: design_review_and_frontback.md §6.4

import { useEffect, useRef, useState } from "react";
import type { InterviewJob } from "../types/interview";
import { getInterview } from "../services/api";

const POLL_INTERVAL_MS = 5000;
// モック開発は短縮（VITE_USE_MOCK時のみ）。HistoryPageの定期更新でも同じ間隔を使う。
export const intervalMs = import.meta.env.VITE_USE_MOCK === "1" ? 1000 : POLL_INTERVAL_MS;

export interface UseInterviewJob {
  job: InterviewJob | null;
  isPolling: boolean;
  error: string | null;
}

export function useInterviewJob(jobId: string | null): UseInterviewJob {
  const [job, setJob] = useState<InterviewJob | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setIsPolling(true);
    setError(null);

    const tick = async () => {
      try {
        const next = await getInterview(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "completed" || next.status === "failed") {
          setIsPolling(false);
          return; // 停止
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        // ポーリングは継続（一時的なネットワークエラーで止めない）
      }
      if (!cancelled) timer.current = window.setTimeout(tick, intervalMs);
    };
    tick();

    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
      setIsPolling(false);
    };
  }, [jobId]);

  return { job, isPolling, error };
}
