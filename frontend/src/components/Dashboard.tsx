// 結果ダッシュボード（加藤）。子コンポーネントを並べる。
// 設計根拠: design_review_and_frontback.md §6.3

import { Download, FileJson } from "lucide-react";
import type { AnalysisResult } from "../types/interview";
import { Button } from "@/components/ui/button";
import { exportResultJson, exportResultMarkdown } from "@/lib/export";
import { ScoreSummary } from "./ScoreSummary";
import { ScoreRadar } from "./ScoreRadar";
import { FeedbackPanel } from "./FeedbackPanel";
import { TranscriptView } from "./TranscriptView";
import { AudioTimeline } from "./AudioTimeline";

interface Props {
  result: AnalysisResult;
  onReset: () => void;
  /** エクスポート時のファイル名ラベル（例: "6/18 14:30 の分析"）。 */
  exportLabel?: string;
}

export function Dashboard({ result, onReset, exportLabel }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <ScoreSummary result={result} />
        <ScoreRadar dimensions={result.dimensions} />
      </div>
      <FeedbackPanel strengths={result.strengths} improvements={result.improvements} />
      <AudioTimeline metrics={result.audio_metrics} />
      <TranscriptView transcript={result.transcript} />

      {/* エクスポート（Markdown / JSON）。動画は1日で削除されるため結果テキストのみ。 */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => exportResultMarkdown(result, exportLabel)}
        >
          <Download className="size-4" />
          Markdown で保存
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => exportResultJson(result, exportLabel)}
        >
          <FileJson className="size-4" />
          JSON で保存
        </Button>
      </div>

      <Button type="button" variant="outline" className="self-center" onClick={onReset}>
        別の動画を分析する
      </Button>
    </div>
  );
}
