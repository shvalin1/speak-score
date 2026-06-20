// 履歴ページ（Variation A: 表形式リスト）。"/history" の本体。
// 各行に「成績確認」「動画確認」を配置。completed 以外は操作不可。

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listInterviews } from "../services/api";
import { intervalMs } from "../hooks/useInterviewJob";
import type { InterviewSummary, JobStatus } from "../types/interview";

const isPending = (item: InterviewSummary) =>
  item.status === "processing" || item.status === "awaiting_upload";

type StatusStyle = {
  label: string;
  variant: "secondary" | "destructive";
  className?: string;
};

// ステータスバッジ。配色は既存 ScoreSummary の source バッジ（emerald / 半透明）に揃える。
const STATUS: Record<JobStatus, StatusStyle> = {
  awaiting_upload: { label: "アップロード待ち", variant: "secondary" },
  processing: {
    label: "分析中",
    variant: "secondary",
    className: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  },
  completed: {
    label: "完了",
    variant: "secondary",
    className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  },
  failed: { label: "失敗", variant: "destructive" },
};

export function HistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<InterviewSummary[]>([]);

  // processing/awaiting_uploadの項目が残っている間は、完了/失敗に変わるまで定期的に再取得する。
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const list = await listInterviews();
        if (cancelled) return;
        setItems(list);
        if (list.some(isPending)) {
          timer = window.setTimeout(tick, intervalMs);
        }
      } catch (err) {
        console.error("履歴一覧の取得に失敗しました", err);
        if (!cancelled) timer = window.setTimeout(tick, intervalMs);
      }
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  // 新しいものを上に（created_at 降順）。
  const sorted = [...items].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">分析履歴</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Inbox className="size-8" />
            まだ分析履歴がありません
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            {/* ヘッダ行 */}
            <div className="grid grid-cols-[150px_130px_110px_1fr] items-center gap-3 border-b border-border bg-muted/50 px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground">
              <span>日時</span>
              <span>総合スコア</span>
              <span>ステータス</span>
              <span className="text-right">操作</span>
            </div>

            {/* データ行 */}
            {sorted.map((item) => {
              const st = STATUS[item.status];
              const completed = item.status === "completed";
              return (
                <div
                  key={item.job_id}
                  className="grid grid-cols-[150px_130px_110px_1fr] items-center gap-3 border-b border-border/60 px-4 py-3.5 text-sm last:border-b-0"
                >
                  <span className="text-muted-foreground">
                    {new Date(item.created_at).toLocaleString("ja-JP", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>

                  <span className="text-[15px] font-bold">
                    {item.overall_score !== null ? `${item.overall_score} / 100` : "—"}
                  </span>

                  <span>
                    <Badge variant={st.variant} className={st.className}>
                      {st.label}
                    </Badge>
                  </span>

                  <div className="flex justify-end gap-2">
                    {completed ? (
                      <>
                        <Button
                          size="sm"
                          onClick={() => navigate(`/jobs/${item.job_id}?tab=score`)}
                        >
                          成績確認
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigate(`/jobs/${item.job_id}?tab=video`)}
                        >
                          動画確認
                        </Button>
                      </>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {item.status === "processing" ? "分析中…" : "—"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
