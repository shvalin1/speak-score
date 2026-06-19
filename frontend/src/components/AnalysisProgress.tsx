// 処理中の進捗表示（加藤）。App がポーリングした job を受け取り stage を表示する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3
// TODO(加藤): ステップのアニメーション・推定残り時間などを作り込む。

import { useState, useEffect } from "react";
import { Circle, CircleCheck, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { InterviewJob, ProcessingStage } from "../types/interview";

const STAGES: { key: ProcessingStage | "queued"; label: string }[] = [
  { key: "queued", label: "待機中" },
  { key: "extracting_audio", label: "音声を抽出中" },
  { key: "transcribing", label: "文字起こし中" },
  { key: "analyzing_audio", label: "音声を分析中" },
  { key: "evaluating", label: "AIが評価中" },
];

export function AnalysisProgress({ job }: { job: InterviewJob | null }) {
  const [isReady, setIsReady] = useState(false);
  useEffect(() => {
    setIsReady(true);
  }, []);

  const current = job?.stage ?? "queued";
  let currentIdx = STAGES.findIndex((s) => s.key === current);

  if (!isReady || currentIdx === -1) {
    currentIdx = 0;
  }

  return (
    <div className="mx-auto max-w-md text-center">
      <h2 className="text-xl font-semibold">分析しています…</h2>

      <p className="mt-3 mb-6 flex items-center justify-center gap-1.5 text-sm text-muted-foreground">
        <Clock className="size-4" />
        完了まであと <strong className="font-semibold text-foreground">約1〜2分</strong>{" "}
        かかります（動画の長さによって前後します）
      </p>

      <ol className="inline-flex flex-col items-start gap-1 text-left">
        {STAGES.map((s, i) => {
          const isDone = i < currentIdx;
          const isActive = i === currentIdx;

          return (
            <li
              key={s.key}
              className={cn(
                "flex items-center gap-3 py-1.5",
                isActive ? "text-base" : "text-sm",
              )}
            >
              <span className="flex size-6 items-center justify-center">
                {isDone ? (
                  <CircleCheck className="size-5 text-emerald-500" />
                ) : isActive ? (
                  <span className="inline-block size-[18px] animate-fold border-[3px] border-primary">
                    <span className="block h-full w-full animate-fold-inner bg-primary" />
                  </span>
                ) : (
                  <Circle className="size-4 text-muted-foreground" />
                )}
              </span>

              <span
                className={cn(
                  "font-semibold",
                  isActive
                    ? "text-primary"
                    : isDone
                      ? "text-emerald-500"
                      : "text-muted-foreground",
                )}
              >
                {s.label}
                {isActive && " ..."}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
