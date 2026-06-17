// 認証ゲート（石川）。未ログインならサインインボタン。Firebase初期化は auth.ts に隠蔽。
// 設計根拠: design_review_and_frontback.md §6.3, §10

import type { ReactNode } from "react";
import { useAuth } from "../services/auth";

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, ready, signIn } = useAuth();

  if (!ready) return <div className="auth-gate">読み込み中…</div>;

  if (!user) {
    return (
      <div className="auth-gate">
        <h1>SpeakScore</h1>
        <p>面接動画をアップロードして、AIフィードバックを受け取りましょう。</p>
        <button type="button" onClick={signIn}>
          はじめる
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
