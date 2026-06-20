// 認証状態をAppツリー全体で1つに共有するためのProvider（main.tsxでAppの外側に置く）。
// 実体（onAuthStateChanged購読・signIn/signOut）は services/auth.ts の useProvideAuth。

import type { ReactNode } from "react";
import { AuthContext, useProvideAuth } from "../services/auth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useProvideAuth();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}
