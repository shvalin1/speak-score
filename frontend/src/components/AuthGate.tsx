// 認証ゲート（石川）。未ログインならサインインボタン。Firebase初期化は auth.ts に隠蔽。
// 設計根拠: design_review_and_frontback.md §6.3, §10

import type { ReactNode } from "react";
import { useAuth } from "../services/auth";
import { Button } from "@/components/ui/button";

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, ready, signIn } = useAuth();

  if (!ready) {
    return <div className="auth-gate text-sm text-muted-foreground">読み込み中…</div>;
  }

  if (!user) {
    return (
      <div className="auth-gate flex flex-col items-center gap-3">
        <h1 className="text-2xl font-bold">SpeakScore</h1>
        <p className="text-pretty text-sm text-muted-foreground">
          面接動画をアップロードして、AIフィードバックを受け取りましょう。
        </p>
        <Button type="button" size="lg" className="mt-2" onClick={signIn}>
          はじめる
        </Button>
      </div>
    );
  }

  return <>{children}</>;
}
