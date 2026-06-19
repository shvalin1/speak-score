// 結果ダッシュボード（加藤）。子コンポーネントを並べる。
// 設計根拠: design_review_and_frontback.md §6.3

import type { AnalysisResult } from "../types/interview";
import { Button } from "@/components/ui/button";
import { ScoreSummary } from "./ScoreSummary";
import { ScoreRadar } from "./ScoreRadar";
import { FeedbackPanel } from "./FeedbackPanel";
import { TranscriptView } from "./TranscriptView";
import { AudioTimeline } from "./AudioTimeline";

interface Props {
  result: AnalysisResult;
  onReset: () => void;
}

export function Dashboard({ result, onReset }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <ScoreSummary result={result} />
        <ScoreRadar dimensions={result.dimensions} />
      </div>
      <FeedbackPanel strengths={result.strengths} improvements={result.improvements} />
      <AudioTimeline metrics={result.audio_metrics} />
      <TranscriptView transcript={result.transcript} />
      <Button type="button" variant="outline" className="self-center" onClick={onReset}>
        別の動画を分析する
      </Button>
    </div>
  );
}
