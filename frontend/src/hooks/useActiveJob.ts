// アプリ全体で「現在処理中の1ジョブ」を共有するためのContext。
// services/auth.ts の AuthContext/useProvideAuth と同じパターン。
// JobPage自身のポーリング（jobIdを問わず汎用的に見るためのuseInterviewJob）とは独立している。
// FloatingProgressWidgetがページ移動後も進捗を表示できるよう、ここで1本だけポーリングを持つ。

import { createContext, useContext, useState } from "react";
import { useInterviewJob } from "./useInterviewJob";
import type { InterviewJob } from "../types/interview";

const STORAGE_KEY = "speakscore:activeJobId";

export interface ActiveJobContextValue {
  activeJobId: string | null;
  job: InterviewJob | null;
  setActiveJobId: (jobId: string | null) => void;
}

export const ActiveJobContext = createContext<ActiveJobContextValue | null>(null);

/**
 * ActiveJobProvider からのみ呼ぶ。
 * リロードで処理中ジョブの追跡を失わないよう、sessionStorageにも書く
 * （タブを閉じたら消える＝今のセッション限定。本番ではサーバー側のジョブ自体は
 * 残るので/historyからも追えるが、ショートカット表示はリロードしても保つ）。
 */
export function useProvideActiveJob(): ActiveJobContextValue {
  const [activeJobId, setActiveJobIdState] = useState<string | null>(() =>
    sessionStorage.getItem(STORAGE_KEY),
  );
  const { job } = useInterviewJob(activeJobId);

  const setActiveJobId = (jobId: string | null) => {
    if (jobId) {
      sessionStorage.setItem(STORAGE_KEY, jobId);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
    setActiveJobIdState(jobId);
  };

  return { activeJobId, job, setActiveJobId };
}

/** HomePage / FloatingProgressWidget が使う。ActiveJobProvider の内側でのみ呼べる。 */
export function useActiveJob(): ActiveJobContextValue {
  const ctx = useContext(ActiveJobContext);
  if (!ctx) throw new Error("useActiveJob must be used within ActiveJobProvider");
  return ctx;
}
