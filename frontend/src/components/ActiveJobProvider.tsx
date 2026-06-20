// AuthProvider.tsxと同じパターン。現在処理中ジョブの状態をApp全体に配る。

import type { ReactNode } from "react";
import { ActiveJobContext, useProvideActiveJob } from "../hooks/useActiveJob";

export function ActiveJobProvider({ children }: { children: ReactNode }) {
  const value = useProvideActiveJob();
  return <ActiveJobContext.Provider value={value}>{children}</ActiveJobContext.Provider>;
}
