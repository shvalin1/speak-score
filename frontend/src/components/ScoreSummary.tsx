// 総合スコア + 各dimension（source バッジ付）（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import type { AnalysisResult, Dimension } from "../types/interview";

const LABELS: Record<keyof AnalysisResult["dimensions"], string> = {
  content: "内容",
  structure: "構成",
  delivery: "話し方",
  confidence: "自信",
};

export function ScoreSummary({ result }: { result: AnalysisResult }) {
  const dims = result.dimensions;
  return (
    <div className="score-summary">
      <div className="overall">
        <span className="overall-value">{result.overall_score}</span>
        <span className="overall-unit">/ 100</span>
      </div>
      <ul className="dim-list">
        {(Object.keys(dims) as (keyof typeof dims)[]).map((k) => (
          <li key={k}>
            <span className="dim-label">{LABELS[k]}</span>
            <span className="dim-score">{dims[k].score}</span>
            <SourceBadge source={dims[k].source} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourceBadge({ source }: { source: Dimension["source"] }) {
  return (
    <span className={`source-badge ${source}`}>
      {source === "computed" ? "音声解析" : "AI採点"}
    </span>
  );
}
