// 音量・ピッチの時系列グラフ（recharts LineChart）（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AudioMetrics } from "../types/interview";

export function AudioTimeline({ metrics }: { metrics: AudioMetrics }) {
  // volume と pitch を時刻 t で結合（点が無い側は undefined）。
  const byT = new Map<number, { t: number; volume?: number; pitch?: number }>();
  for (const p of metrics.volume_timeline) byT.set(p.t, { ...byT.get(p.t), t: p.t, volume: p.value });
  for (const p of metrics.pitch_timeline) byT.set(p.t, { ...byT.get(p.t), t: p.t, pitch: p.value });
  const data = [...byT.values()].sort((a, b) => a.t - b.t);

  return (
    <Card>
      <CardHeader>
        <CardTitle>声の時系列（音量・ピッチ）</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="t" unit="s" />
            <YAxis yAxisId="vol" orientation="left" />
            <YAxis yAxisId="pitch" orientation="right" />
            <Tooltip />
            <Line yAxisId="vol" type="monotone" dataKey="volume" stroke="#3b82f6" dot={false} name="音量" />
            <Line yAxisId="pitch" type="monotone" dataKey="pitch" stroke="#f59e0b" dot={false} name="ピッチ" />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
