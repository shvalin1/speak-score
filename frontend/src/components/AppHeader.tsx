// 全ページ共通ヘッダー（Variation A: アンダーライン / モノクロ）。
// react-router のuseLocation/useNavigateとuseAuthに自己完結で接続する。

import { LogOut, User as UserIcon } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "../services/auth";

type HeaderTab = "home" | "history" | "qa";

const TABS: { key: HeaderTab; path: string; label: string }[] = [
  { key: "home", path: "/", label: "ホーム" },
  { key: "history", path: "/history", label: "履歴" },
  { key: "qa", path: "/qa", label: "設問別" },
];

export function AppHeader() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, signOut } = useAuth();
  const displayName = user?.isAnonymous ? "匿名ユーザー" : user?.displayName ?? "ゲスト";
  // /jobs/:jobId（分析中・結果・エラー画面）は履歴から辿る導線なので「履歴」扱いにする。
  const active: HeaderTab | null = pathname === "/"
    ? "home"
    : pathname.startsWith("/qa")
      ? "qa"
      : pathname.startsWith("/history") || pathname.startsWith("/jobs/")
        ? "history"
        : null;

  return (
    <header className="sticky top-0 z-30 flex h-[60px] items-center justify-between border-b border-border bg-background px-6">
      {/* ロゴ → ホーム */}
      <button
        type="button"
        onClick={() => navigate("/")}
        className="flex items-center gap-2.5 outline-none focus-visible:opacity-70"
      >
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          S
        </span>
        <span className="text-[15px] font-semibold tracking-tight">SpeakScore</span>
      </button>

      {/* タブ（アンダーライン） */}
      <nav className="flex h-full items-stretch gap-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => navigate(t.path)}
            className={cn(
              "flex items-center border-b-2 text-sm font-medium transition-colors outline-none",
              active === t.key
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          {user?.photoURL ? (
            <img
              src={user.photoURL}
              alt=""
              className="size-7 rounded-full object-cover"
            />
          ) : (
            <span className="flex size-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <UserIcon className="size-4" />
            </span>
          )}
          <span className="text-sm font-medium text-foreground">
            {displayName}
          </span>
        </div>
        <Button variant="outline" onClick={signOut}>
          <LogOut />
          ログアウト
        </Button>
      </div>
    </header>
  );
}
