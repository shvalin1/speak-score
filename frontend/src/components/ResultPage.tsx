// 結果詳細ページ（Variation B: 2カラム動画タブ + セグメントサブタブ）。"/jobs/:jobId" の本体。
// 「成績」タブ = 既存 Dashboard をそのまま表示（中身は変更しない）。
// 「動画」タブ = 左に動画プレイヤー、右にスクロール可能な文字起こし。
//   再生位置（timeupdate）に応じて、今話しているセグメントをハイライト＆自動スクロール。
//   文をクリックするとその位置へシークする。

import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { FileText, GraduationCap, MessagesSquare, Video } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { intentLabel, scoreClass } from "@/lib/qa";
import { Dashboard } from "./Dashboard";
import { AudioTimeline } from "./AudioTimeline";
import type { AnalysisResult, QaSegment, TranscriptSegment } from "../types/interview";

export type Tab = "score" | "video" | "minutes" | "qa";

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

const ALL_SUBTABS: { key: Tab; label: string; icon: typeof GraduationCap }[] = [
  { key: "score", label: "成績", icon: GraduationCap },
  { key: "video", label: "動画", icon: Video },
  { key: "minutes", label: "議事録", icon: FileText },
  { key: "qa", label: "問答", icon: MessagesSquare },
];

export function ResultPage({
  result,
  videoUrl,
  createdLabel = "分析結果",
  initialTab = "score",
  onReset,
}: Props) {
  const navigate = useNavigate();
  // 議事録/問答は話者分離エピック以降のデータのみ。旧データ（None/空）ではタブを出さない。
  const hasMinutes = result.minutes != null;
  const hasQa = (result.qa_segments?.length ?? 0) > 0;
  const subtabs = ALL_SUBTABS.filter(
    (s) => (s.key !== "minutes" || hasMinutes) && (s.key !== "qa" || hasQa),
  );
  const wanted = subtabs.some((s) => s.key === initialTab) ? initialTab : "score";
  const [tab, setTab] = useState<Tab>(wanted);

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
          {subtabs.map((s) => {
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
      {tab === "score" && (
        <Dashboard result={result} onReset={onReset} exportLabel={createdLabel} />
      )}
      {tab === "video" && <VideoTab result={result} videoUrl={videoUrl} />}
      {tab === "minutes" && result.minutes && <MinutesTab minutes={result.minutes} />}
      {tab === "qa" && (
        <QaTab segments={result.qa_segments ?? []} videoUrl={videoUrl} />
      )}
    </div>
  );
}

/* ───────────────────────── 議事録タブ ───────────────────────── */

function MinutesTab({ minutes }: { minutes: NonNullable<AnalysisResult["minutes"]> }) {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <h3 className="mb-2 text-sm font-semibold">要約</h3>
        <p className="text-sm leading-relaxed text-muted-foreground">{minutes.summary}</p>
      </section>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="mb-2 text-sm font-semibold">トピック</h3>
          <div className="flex flex-wrap gap-1.5">
            {minutes.topics.map((t, i) => (
              <span
                key={i}
                className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
              >
                {t}
              </span>
            ))}
          </div>
        </section>
        <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="mb-2 text-sm font-semibold">要点</h3>
          <ul className="flex flex-col gap-1.5">
            {minutes.key_points.map((k, i) => (
              <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                <span className="text-primary">・</span>
                {k}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

/* ───────────────────────── 問答タブ ───────────────────────── */

function QaTab({ segments, videoUrl }: { segments: QaSegment[]; videoUrl?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [openIdx, setOpenIdx] = useState<number | null>(segments.length ? 0 : null);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = t;
      void v.play().catch(() => {});
    }
  };

  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1.1fr_1fr]">
      {/* 左: 動画 */}
      <div className="aspect-video overflow-hidden rounded-xl bg-black ring-1 ring-foreground/10">
        {videoUrl ? (
          <video ref={videoRef} src={videoUrl} controls className="size-full" />
        ) : (
          <div className="flex size-full items-center justify-center bg-[repeating-linear-gradient(135deg,#161616_0,#161616_12px,#0f0f0f_12px,#0f0f0f_24px)]">
            <span className="font-mono text-xs text-neutral-500">面接動画（未取得）</span>
          </div>
        )}
      </div>

      {/* 右: 設問別 Q&A（クリックで該当箇所へシーク） */}
      <div className="flex flex-col gap-2">
        {segments.map((q) => (
          <QaCard
            key={q.index}
            q={q}
            open={openIdx === q.index}
            onToggle={() => setOpenIdx(openIdx === q.index ? null : q.index)}
            onSeek={() => seek(q.start)}
          />
        ))}
      </div>
    </div>
  );
}

function QaCard({
  q,
  open,
  onToggle,
  onSeek,
}: {
  q: QaSegment;
  open: boolean;
  onToggle: () => void;
  onSeek: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left outline-none hover:bg-muted/50"
      >
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {q.is_reverse_question ? "逆質問" : intentLabel(q.intent)}
        </span>
        <span className="flex-1 truncate text-sm font-medium">
          {q.question}
          {q.question_inferred && (
            <span className="ml-1 text-xs text-muted-foreground">(推定)</span>
          )}
        </span>
        <span className={cn("text-sm font-bold tabular-nums", scoreClass(q.score))}>
          {q.score}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          <p className="mb-2 text-sm leading-relaxed text-muted-foreground">{q.answer}</p>
          {q.audio && (
            <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>ピッチ {Math.round(q.audio.pitch_mean)}±{Math.round(q.audio.pitch_std)}Hz</span>
              <span>話速 {Math.round(q.audio.speech_rate_cpm)}字/分</span>
              <span>フィラー {q.audio.filler_count}回</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <p className="text-xs text-foreground/70">{q.comment}</p>
            <button
              type="button"
              onClick={onSeek}
              className="shrink-0 rounded-lg bg-primary/10 px-3 py-1 text-xs font-medium text-primary outline-none hover:bg-primary/20"
            >
              この箇所を再生
            </button>
          </div>
        </div>
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
    <div className="flex flex-col gap-4">
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

      {/* 声（音量・ピッチ）の時系列。再生位置に赤い再生ヘッド、クリックでシーク。 */}
      <AudioTimeline metrics={m} currentTime={currentTime} onSeek={seek} />
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
