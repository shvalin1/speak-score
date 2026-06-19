// 過去の分析履歴一覧（加藤）。
// 設計根拠: GitHub Issue #7
// TODO(加藤): 完了済みエントリ→詳細（Dashboard）への遷移は、ルーティング実装後（#8）に結線する。

import { Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { InterviewSummary, JobStatus } from "../types/interview";

const STATUS_LABELS: Record<JobStatus, string> = {
  awaiting_upload: "アップロード待ち",
  processing: "分析中",
  completed: "完了",
  failed: "失敗",
};

interface Props {
  items: InterviewSummary[];
  onSelect?: (jobId: string) => void;
}

export function HistoryList({ items, onSelect }: Props) {
  // 新しいものを上に積み上げる（created_at 降順）。
  const sorted = [...items].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>過去の分析履歴</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Inbox className="size-8" />
            まだ分析履歴がありません
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {sorted.map((item) => {
              const isCompleted = item.status === "completed";
              return (
                <li
                  key={item.job_id}
                  onClick={() => isCompleted && onSelect?.(item.job_id)}
                  className={cn(
                    "flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm",
                    isCompleted && "cursor-pointer hover:bg-accent",
                  )}
                >
                  <span className="text-muted-foreground">
                    {new Date(item.created_at).toLocaleString("ja-JP", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <span className="font-semibold">
                    {item.overall_score !== null ? `${item.overall_score} / 100` : "—"}
                  </span>
                  <Badge variant={item.status === "failed" ? "destructive" : "secondary"}>
                    {STATUS_LABELS[item.status]}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
