// 認証ゲート（石川）。未ログインならサインインボタン。Firebase初期化は auth.ts に隠蔽。
// 設計根拠: design_review_and_frontback.md §6.3, §10

import { useEffect, useRef, type ReactNode } from "react";
import { useAuth } from "../services/auth";
import { useActiveJob } from "../hooks/useActiveJob";
import { resetMockInterviews } from "../services/api";
import { Button } from "@/components/ui/button";

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, ready, signIn, signInWithGoogle } = useAuth();
  const { setActiveJobId } = useActiveJob();
  const wasSignedIn = useRef(false);

  // ログアウト（user: あり→なし）を検知して、前のユーザーの状態を持ち越さないようにする。
  useEffect(() => {
    if (user) {
      wasSignedIn.current = true;
    } else if (wasSignedIn.current) {
      resetMockInterviews();
      setActiveJobId(null);
      wasSignedIn.current = false;
    }
  }, [user, setActiveJobId]);

  if (!ready) {
    return <div className="auth-gate text-sm text-muted-foreground">読み込み中…</div>;
  }

  if (!user) {
    return (
      <div className="auth-gate flex flex-col items-center gap-3">
        <h1 className="text-2xl font-bold">SpeakScore</h1>
        <p className="text-pretty text-sm text-muted-foreground">
          面接動画をアップロードして、AIフィードバックを受け取りましょう。
          アップロードは許可されたアカウントのみ利用できます。
        </p>
        <Button type="button" size="lg" className="mt-2" onClick={signInWithGoogle}>
          Google でログイン
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={signIn}
        >
          閲覧のみで試す（匿名）
        </Button>
      </div>
    );
  }

  return <>{children}</>;
}
