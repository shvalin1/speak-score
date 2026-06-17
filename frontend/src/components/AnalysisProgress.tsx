// 処理中の進捗表示（加藤）。App がポーリングした job を受け取り stage を表示する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3
// TODO(加藤): ステップのアニメーション・推定残り時間などを作り込む。

import type { InterviewJob, ProcessingStage } from "../types/interview";

const STAGES: { key: ProcessingStage | "queued"; label: string }[] = [
  { key: "queued", label: "待機中" },
  { key: "extracting_audio", label: "音声を抽出中" },
  { key: "transcribing", label: "文字起こし中" },
  { key: "analyzing_audio", label: "音声を分析中" },
  { key: "evaluating", label: "AIが評価中" },
];

export function AnalysisProgress({ job }: { job: InterviewJob | null }) {
  // stage=null は queued（enqueue済み・worker未着手）
  const current = job?.stage ?? "queued";
  const currentIdx = STAGES.findIndex((s) => s.key === current);

  return (
    <div className="analysis-progress">
      <h2>分析しています…</h2>
      <ol className="stage-list">
        {STAGES.map((s, i) => (
          <li
            key={s.key}
            className={
              i < currentIdx ? "done" : i === currentIdx ? "active" : "pending"
            }
          >
            {s.label}
          </li>
        ))}
      </ol>
    </div>
  );
}
