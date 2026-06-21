// 動画横断の設問一覧（"/qa"）。全動画の Q&A を設問カテゴリで名寄せ・絞り込みし、
// スコア順に並べて経時比較できるようにする。各行クリックで該当ジョブの問答タブへ。

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Inbox } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { INTENT_LABELS, intentLabel, scoreClass } from "@/lib/qa";
import { listQa } from "../services/api";
import type { QaIndexEntry, QuestionIntent } from "../types/interview";

type Filter = QuestionIntent | "all";

export function QaListPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<QaIndexEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let cancelled = false;
    listQa()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((err) => console.error("横断一覧の取得に失敗しました", err))
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 実際に出現するカテゴリだけをフィルタチップに出す。
  const presentIntents = useMemo(() => {
    const set = new Set(items.map((e) => e.intent));
    return (Object.keys(INTENT_LABELS) as QuestionIntent[]).filter((i) => set.has(i));
  }, [items]);

  const shown = filter === "all" ? items : items.filter((e) => e.intent === filter);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">設問別ふりかえり（動画横断）</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* カテゴリ絞り込み */}
        {!isLoading && items.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <FilterChip label="すべて" on={filter === "all"} onClick={() => setFilter("all")} />
            {presentIntents.map((i) => (
              <FilterChip
                key={i}
                label={intentLabel(i)}
                on={filter === i}
                onClick={() => setFilter(i)}
              />
            ))}
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14 w-full rounded-xl" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Inbox className="size-8" />
            まだ設問データがありません
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {shown.map((e) => (
              <button
                key={`${e.job_id}_${e.index}`}
                type="button"
                onClick={() => navigate(`/jobs/${e.job_id}?tab=qa`)}
                className="flex items-center gap-3 rounded-xl border border-border px-4 py-3 text-left outline-none transition-colors hover:bg-muted/50"
              >
                <span className="w-16 shrink-0 rounded-full bg-muted px-2 py-0.5 text-center text-xs text-muted-foreground">
                  {intentLabel(e.intent)}
                </span>
                <span className="flex-1 truncate text-sm font-medium">{e.question}</span>
                <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                  {new Date(e.created_at).toLocaleDateString("ja-JP", {
                    month: "numeric",
                    day: "numeric",
                  })}
                </span>
                <span className={cn("w-10 shrink-0 text-right text-base font-bold tabular-nums", scoreClass(e.score))}>
                  {e.score}
                </span>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FilterChip({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-xs font-medium transition-colors outline-none",
        on
          ? "bg-foreground text-background"
          : "bg-muted text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
