// 評価軸レーダーチャート（recharts RadarChart）（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import type { Dimensions } from "../types/interview";

export function ScoreRadar({ dimensions }: { dimensions: Dimensions }) {
  const data = [
    { axis: "内容", score: dimensions.content.score },
    { axis: "構成", score: dimensions.structure.score },
    { axis: "話し方", score: dimensions.delivery.score },
    { axis: "自信", score: dimensions.confidence.score },
  ];
  return (
    <div className="score-radar">
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data}>
          <PolarGrid />
          <PolarAngleAxis dataKey="axis" />
          <PolarRadiusAxis domain={[0, 100]} />
          <Radar dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.5} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
