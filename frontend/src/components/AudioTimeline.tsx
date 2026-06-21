// 音量・ピッチの時系列グラフ（recharts LineChart）（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AudioMetrics } from "../types/interview";

interface Props {
  metrics: AudioMetrics;
  /** 動画の再生位置（秒）。指定すると再生ヘッド（縦線）を表示し、声と発話を時刻で連動させる。 */
  currentTime?: number;
  /** グラフ上のクリックで該当時刻へシークする（動画タブで使用）。 */
  onSeek?: (t: number) => void;
}

export function AudioTimeline({ metrics, currentTime, onSeek }: Props) {
  // volume と pitch を時刻 t で結合（点が無い側は undefined）。
  const byT = new Map<number, { t: number; volume?: number; pitch?: number }>();
  for (const p of metrics.volume_timeline) byT.set(p.t, { ...byT.get(p.t), t: p.t, volume: p.value });
  for (const p of metrics.pitch_timeline) byT.set(p.t, { ...byT.get(p.t), t: p.t, pitch: p.value });
  const data = [...byT.values()].sort((a, b) => a.t - b.t);

  // recharts の onClick は activeLabel に X 値（=t）を載せる。クリックでシーク。
  const handleClick = (state: { activeLabel?: string | number } | null) => {
    if (!onSeek || state?.activeLabel == null) return;
    const t = Number(state.activeLabel);
    if (Number.isFinite(t)) onSeek(t);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>声の時系列（音量・ピッチ）</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart
            data={data}
            onClick={handleClick}
            style={onSeek ? { cursor: "pointer" } : undefined}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="t" unit="s" />
            <YAxis yAxisId="vol" orientation="left" />
            <YAxis yAxisId="pitch" orientation="right" />
            <Tooltip />
            {currentTime != null && (
              <ReferenceLine
                yAxisId="vol"
                x={data.reduce(
                  (best, d) =>
                    Math.abs(d.t - currentTime) < Math.abs(best - currentTime) ? d.t : best,
                  data[0]?.t ?? 0,
                )}
                stroke="#ef4444"
                strokeWidth={2}
              />
            )}
            <Line yAxisId="vol" type="monotone" dataKey="volume" stroke="#3b82f6" dot={false} name="音量" isAnimationActive={false} />
            <Line yAxisId="pitch" type="monotone" dataKey="pitch" stroke="#f59e0b" dot={false} name="ピッチ" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
