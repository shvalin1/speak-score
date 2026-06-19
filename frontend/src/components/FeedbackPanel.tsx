// 強み・改善点のリスト表示（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import { Lightbulb, ThumbsUp } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function FeedbackPanel({
  strengths,
  improvements,
}: {
  strengths: string[];
  improvements: string[];
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ThumbsUp className="size-4 text-emerald-500" />
            強み
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2 text-sm">
            {strengths.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-emerald-500">・</span>
                {s}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="size-4 text-amber-500" />
            改善点
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2 text-sm">
            {improvements.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-500">・</span>
                {s}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
