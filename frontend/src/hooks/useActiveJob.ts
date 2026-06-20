// アプリ全体で「現在処理中の1ジョブ」を共有するためのContext。
// services/auth.ts の AuthContext/useProvideAuth と同じパターン。
// JobPage自身のポーリング（jobIdを問わず汎用的に見るためのuseInterviewJob）とは独立している。
// FloatingProgressWidgetがページ移動後も進捗を表示できるよう、ここで1本だけポーリングを持つ。

import { createContext, useContext, useState } from "react";
import { useInterviewJob } from "./useInterviewJob";
import type { InterviewJob } from "../types/interview";

export interface ActiveJobContextValue {
  activeJobId: string | null;
  job: InterviewJob | null;
  setActiveJobId: (jobId: string | null) => void;
}

export const ActiveJobContext = createContext<ActiveJobContextValue | null>(null);

/** ActiveJobProvider からのみ呼ぶ。 */
export function useProvideActiveJob(): ActiveJobContextValue {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { job } = useInterviewJob(activeJobId);
  return { activeJobId, job, setActiveJobId };
}

/** HomePage / FloatingProgressWidget が使う。ActiveJobProvider の内側でのみ呼べる。 */
export function useActiveJob(): ActiveJobContextValue {
  const ctx = useContext(ActiveJobContext);
  if (!ctx) throw new Error("useActiveJob must be used within ActiveJobProvider");
  return ctx;
}
