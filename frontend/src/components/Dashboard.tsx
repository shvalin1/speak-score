// 結果ダッシュボード（加藤）。子コンポーネントを並べる。
// 設計根拠: design_review_and_frontback.md §6.3

import type { AnalysisResult } from "../types/interview";
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
    <div className="dashboard">
      <div className="dashboard-top">
        <ScoreSummary result={result} />
        <ScoreRadar dimensions={result.dimensions} />
      </div>
      <FeedbackPanel strengths={result.strengths} improvements={result.improvements} />
      <AudioTimeline metrics={result.audio_metrics} />
      <TranscriptView transcript={result.transcript} />
      <button type="button" className="reset-btn" onClick={onReset}>
        別の動画を分析する
      </button>
    </div>
  );
}
