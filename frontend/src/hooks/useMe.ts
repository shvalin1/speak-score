// 現在のユーザーが writer（許可制 Google）か reader（匿名・未許可）かを取得するフック。
// アップロードUIの出し分けに使う（信頼境界は backend の require_writer。ここは UX のみ）。
// AuthGate の内側でのみ使う前提（未ログイン時は /me が 401 になる）。

import { useEffect, useState } from "react";
import { getMe, type Me } from "../services/api";
import { useAuth } from "../services/auth";

export interface UseMe {
  me: Me | null;
  loading: boolean;
}

export function useMe(): UseMe {
  const { user } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  // user.uid をキーにして、アカウント切替（reader→writer 等）で確実に取り直す。
  const uid = user?.uid ?? null;
  useEffect(() => {
    let cancelled = false;
    if (!uid) {
      setMe(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    getMe()
      .then((m) => {
        if (!cancelled) setMe(m);
      })
      .catch(() => {
        // 取得失敗時は安全側（reader 扱い）に倒す。書込は結局 backend が弾く。
        if (!cancelled) setMe(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [uid]);

  return { me, loading };
}
