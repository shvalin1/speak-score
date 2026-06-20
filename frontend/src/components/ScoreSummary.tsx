// 総合スコア + 各dimension（source バッジ付）（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import type { AnalysisResult, Dimension } from "../types/interview";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const LABELS: Record<keyof AnalysisResult["dimensions"], string> = {
  content: "内容",
  structure: "構成",
  delivery: "話し方",
  confidence: "自信",
};

export function ScoreSummary({ result }: { result: AnalysisResult }) {
  const dims = result.dimensions;
  return (
    <Card>
      <CardContent className="flex flex-col gap-6">
        <div className="flex items-baseline justify-center gap-1">
          <span className="text-5xl font-extrabold text-primary">
            {result.overall_score}
          </span>
          <span className="text-lg text-muted-foreground">/ 100</span>
        </div>

        <ul className="flex flex-col gap-2">
          {(Object.keys(dims) as (keyof typeof dims)[]).map((k) => (
            <li key={k} className="flex items-center gap-3">
              <span className="w-12 text-sm text-muted-foreground">{LABELS[k]}</span>
              <span className="text-base font-semibold">{dims[k].score}</span>
              <SourceBadge source={dims[k].source} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function SourceBadge({ source }: { source: Dimension["source"] }) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        "ml-auto",
        source === "computed"
          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
          : "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
      )}
    >
      {source === "computed" ? "音声解析" : "AI採点"}
    </Badge>
  );
}
