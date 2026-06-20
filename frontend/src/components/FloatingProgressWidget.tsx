// 処理中のジョブをAnalysisページ以外で見ているときに、画面右下で進捗を知らせる通知。
// useActiveJob（hooks/useActiveJob.ts）の追跡対象が processing の間だけ表示する。

import { Loader2, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useActiveJob } from "../hooks/useActiveJob";
import { STAGES } from "@/lib/processingStages";

export function FloatingProgressWidget() {
  const { activeJobId, job, setActiveJobId } = useActiveJob();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  if (!activeJobId) return null;
  if (job && job.status !== "processing") return null;
  if (pathname === `/jobs/${activeJobId}`) return null;

  const stageLabel = STAGES.find((s) => s.key === (job?.stage ?? "queued"))?.label ?? "処理中";

  return (
    <div className="fixed bottom-4 right-4 z-40 flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-lg">
      <Loader2 className="size-5 shrink-0 animate-spin text-primary" />
      <button
        type="button"
        onClick={() => navigate(`/jobs/${activeJobId}`)}
        className="text-left outline-none"
      >
        <div className="text-sm font-semibold">分析中…</div>
        <div className="text-xs text-muted-foreground">{stageLabel}</div>
      </button>
      <button
        type="button"
        onClick={() => setActiveJobId(null)}
        aria-label="閉じる"
        className="text-muted-foreground outline-none hover:text-foreground"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
