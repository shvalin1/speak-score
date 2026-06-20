// Firebase Auth を隠蔽するヘルパ（石川が実装）。
// 加藤はトークンを一切触らない。api.ts が getIdToken() を内部で呼び全fetchに付与する。
// 設計根拠: design_review_and_frontback.md §10, §6.4
//
// MVPは匿名認証。Googleサインインは永続履歴が欲しくなったら足す（数行）。

import { createContext, useContext, useEffect, useState } from "react";
import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  signInAnonymously,
  signOut as fbSignOut,
  onAuthStateChanged,
  type Auth,
  type User,
} from "firebase/auth";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "1";

// 実Firebaseはモック時に初期化しない（環境変数未設定でも加藤の開発が回るように）。
let app: FirebaseApp | undefined;
let auth: Auth | undefined;

function ensureAuth(): Auth {
  if (auth) return auth;
  app = initializeApp({
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  });
  auth = getAuth(app);
  return auth;
}

/** api.ts が各リクエスト前に呼ぶ。未ログイン/モック時は null（モックはトークン検証しない）。 */
export async function getIdToken(): Promise<string | null> {
  if (USE_MOCK) return "mock-token";
  const user = ensureAuth().currentUser;
  return user ? user.getIdToken() : null;
}

export interface UseAuth {
  user: { uid: string } | null;
  ready: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

/**
 * 認証状態を1つだけ持つための内部フック。AuthProvider からのみ呼ぶ。
 * AuthGate と AppHeader など複数箇所が同じ状態を見られるよう、Context経由で共有する
 * （フックを呼ぶたびに別状態を持つと、モック時の signOut がここでしか反映されず破綻するため）。
 */
export function useProvideAuth(): UseAuth {
  const [user, setUser] = useState<{ uid: string } | null>(
    USE_MOCK ? { uid: "mock-uid" } : null,
  );
  const [ready, setReady] = useState(USE_MOCK);

  useEffect(() => {
    if (USE_MOCK) return;
    const unsub = onAuthStateChanged(ensureAuth(), (u: User | null) => {
      setUser(u ? { uid: u.uid } : null);
      setReady(true);
    });
    return unsub;
  }, []);

  const signIn = async () => {
    if (USE_MOCK) {
      setUser({ uid: "mock-uid" });
      return;
    }
    await signInAnonymously(ensureAuth());
  };
  const signOut = async () => {
    if (USE_MOCK) {
      setUser(null);
      return;
    }
    await fbSignOut(ensureAuth());
  };

  return { user, ready, signIn, signOut };
}

export const AuthContext = createContext<UseAuth | null>(null);

/** AuthGate / AppHeader が使う。AuthProvider（main.tsx）の内側でのみ呼べる。 */
export function useAuth(): UseAuth {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
