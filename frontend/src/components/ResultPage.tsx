// 結果詳細ページ（Variation B: 2カラム動画タブ + セグメントサブタブ）。"/jobs/:jobId" の本体。
// 「成績」タブ = 既存 Dashboard をそのまま表示（中身は変更しない）。
// 「動画」タブ = 左に動画プレイヤー、右にスクロール可能な文字起こし。
//   再生位置（timeupdate）に応じて、今話しているセグメントをハイライト＆自動スクロール。
//   文をクリックするとその位置へシークする。

import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { GraduationCap, Video } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Dashboard } from "./Dashboard";
import type { AnalysisResult, TranscriptSegment } from "../types/interview";

type Tab = "score" | "video";

interface Props {
  result: AnalysisResult;
  /** アップロード済み動画の再生URL。未指定ならプレースホルダを表示。 */
  videoUrl?: string;
  /** パンくず末尾の表示（例: "6/18 14:30 の分析"）。 */
  createdLabel?: string;
  /** 履歴ボタンの「成績確認 / 動画確認」に応じて初期タブを切り替える。 */
  initialTab?: Tab;
  /** Dashboard 内「別の動画を分析する」用。 */
  onReset: () => void;
}

const SUBTABS: { key: Tab; label: string; icon: typeof GraduationCap }[] = [
  { key: "score", label: "成績", icon: GraduationCap },
  { key: "video", label: "動画", icon: Video },
];

export function ResultPage({
  result,
  videoUrl,
  createdLabel = "分析結果",
  initialTab = "score",
  onReset,
}: Props) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>(initialTab);

  return (
    <div className="flex flex-col gap-4">
      {/* パンくず + サブタブ（セグメント） */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <button
            type="button"
            onClick={() => navigate("/history")}
            className="outline-none hover:text-foreground hover:underline"
          >
            履歴
          </button>
          <span>/</span>
          <button
            type="button"
            onClick={() => setTab("score")}
            className="text-foreground/80 outline-none hover:text-foreground hover:underline"
          >
            {createdLabel}
          </button>
        </div>

        <div className="flex rounded-[10px] bg-muted p-0.5">
          {SUBTABS.map((s) => {
            const Icon = s.icon;
            const on = tab === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setTab(s.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-all outline-none",
                  on
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 中身 */}
      {tab === "score" ? (
        <Dashboard result={result} onReset={onReset} />
      ) : (
        <VideoTab result={result} videoUrl={videoUrl} />
      )}
    </div>
  );
}

/* ───────────────────────── 動画タブ ───────────────────────── */

function VideoTab({ result, videoUrl }: { result: AnalysisResult; videoUrl?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const segments = result.transcript.segments;
  const m = result.audio_metrics;

  const activeIdx = useMemo(
    () => segments.findIndex((s) => currentTime >= s.start && currentTime < s.end),
    [segments, currentTime],
  );

  // 現在のセグメントが変わったらパネル内で中央付近へスクロール（scrollIntoView は使わない）。
  useEffect(() => {
    const panel = panelRef.current;
    const el = activeRef.current;
    if (!panel || !el) return;
    panel.scrollTo({
      top: el.offsetTop - panel.clientHeight / 2 + el.clientHeight / 2,
      behavior: "smooth",
    });
  }, [activeIdx]);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setCurrentTime(t);
  };

  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1.1fr_1fr]">
      {/* 左: 動画 + サマリ指標 */}
      <div className="flex flex-col gap-3">
        <div className="aspect-video overflow-hidden rounded-xl bg-black ring-1 ring-foreground/10">
          {videoUrl ? (
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              className="size-full"
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
            />
          ) : (
            <div className="flex size-full items-center justify-center bg-[repeating-linear-gradient(135deg,#161616_0,#161616_12px,#0f0f0f_12px,#0f0f0f_24px)]">
              <span className="font-mono text-xs text-neutral-500">面接動画（未取得）</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-2.5">
          <Metric label="話速" value={Math.round(m.speech_rate_cpm)} unit="字/分" />
          <Metric label="フィラー" value={m.filler_count} unit="回" />
          <Metric label="沈黙率" value={Math.round(m.silence_ratio * 100)} unit="%" />
        </div>
      </div>

      {/* 右: 文字起こし（スクロール + ハイライト） */}
      <div className="flex max-h-[440px] flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
        <div className="flex items-center justify-between border-b border-border bg-muted/50 px-4 py-2.5">
          <span className="text-sm font-semibold">文字起こし</span>
          <span className="text-xs text-muted-foreground">クリックでシーク</span>
        </div>
        <div ref={panelRef} className="flex flex-col gap-0.5 overflow-y-auto p-2">
          {segments.map((seg, i) => (
            <TranscriptLine
              key={i}
              ref={i === activeIdx ? activeRef : undefined}
              seg={seg}
              active={i === activeIdx}
              onSeek={() => seek(seg.start)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="rounded-[10px] border border-border px-3 py-2.5">
      <div className="mb-0.5 text-xs text-muted-foreground">{label}</div>
      <div className="text-[15px] font-bold">
        {value}
        <span className="text-xs font-medium text-muted-foreground"> {unit}</span>
      </div>
    </div>
  );
}

/* 1行ぶんの文字起こし。active は ref を受け取れるよう forwardRef にする。 */
const TranscriptLine = forwardRef<
  HTMLButtonElement,
  { seg: TranscriptSegment; active: boolean; onSeek: () => void }
>(function TranscriptLine({ seg, active, onSeek }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      data-active={active}
      onClick={onSeek}
      className={cn(
        "flex gap-3 rounded-lg px-3 py-2 text-left transition-colors outline-none",
        active ? "bg-primary/5" : "hover:bg-muted/60",
      )}
    >
      <span className="min-w-8 pt-0.5 font-mono text-xs tabular-nums text-muted-foreground/70">
        {fmt(seg.start)}
      </span>
      <span
        className={cn(
          "border-l-2 pl-3 text-sm leading-relaxed",
          active
            ? "border-primary font-semibold text-foreground"
            : "border-transparent text-muted-foreground",
        )}
      >
        {seg.text}
      </span>
    </button>
  );
});

function fmt(sec: number): string {
  const s = Math.floor(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
