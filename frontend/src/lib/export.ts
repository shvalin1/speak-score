// 分析結果のエクスポート（Markdown / JSON のクライアント生成 + ダウンロード）。
// 動画は1日でGCSから削除されるため対象外。テキスト/結果のみ出力する。
// 依存を増やさないため PDF はブラウザ印刷（window.print）で代替する。

import type { AnalysisResult, Dimensions } from "../types/interview";

const DIMENSION_LABELS: Record<keyof Dimensions, string> = {
  content: "内容",
  structure: "構成",
  delivery: "話し方",
  confidence: "自信",
};

const SOURCE_LABELS: Record<string, string> = {
  computed: "自動算出",
  llm: "AI採点",
};

function downloadBlob(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** ファイル名に使う安全なスラッグ（ラベル + 日時）。 */
function slug(label?: string): string {
  const base = (label ?? "speakscore").replace(/[^\w-]+/g, "_").replace(/^_+|_+$/g, "");
  return base || "speakscore";
}

/** AnalysisResult を読みやすい Markdown に整形する。 */
export function resultToMarkdown(result: AnalysisResult, label?: string): string {
  const { dimensions: d, audio_metrics: m, transcript } = result;
  const lines: string[] = [];

  lines.push(`# SpeakScore 分析結果${label ? `（${label}）` : ""}`);
  lines.push("");
  lines.push(`**総合スコア: ${result.overall_score} / 100**`);
  lines.push("");

  lines.push("## 評価軸");
  lines.push("");
  lines.push("| 軸 | スコア | 種別 | コメント |");
  lines.push("| --- | --- | --- | --- |");
  (Object.keys(DIMENSION_LABELS) as (keyof Dimensions)[]).forEach((key) => {
    const dim = d[key];
    const comment = dim.comment.replace(/\n/g, " ");
    lines.push(
      `| ${DIMENSION_LABELS[key]} | ${dim.score} | ${SOURCE_LABELS[dim.source] ?? dim.source} | ${comment} |`,
    );
  });
  lines.push("");

  lines.push("## 音声メトリクス");
  lines.push("");
  lines.push(`- 話速: ${Math.round(m.speech_rate_cpm)} 字/分`);
  lines.push(`- フィラー: ${m.filler_count} 回（${m.filler_rate} 回/分）`);
  lines.push(`- 沈黙率: ${Math.round(m.silence_ratio * 100)} %`);
  lines.push(`- ピッチ: 平均 ${m.pitch_mean} Hz / 標準偏差 ${m.pitch_std}`);
  lines.push(`- 音量変動係数: ${m.volume_cv}`);
  lines.push("");

  lines.push("## 良かった点");
  lines.push("");
  result.strengths.forEach((s) => lines.push(`- ${s}`));
  lines.push("");

  lines.push("## 改善点");
  lines.push("");
  result.improvements.forEach((s) => lines.push(`- ${s}`));
  lines.push("");

  lines.push("## 文字起こし");
  lines.push("");
  lines.push(transcript.full_text);
  lines.push("");

  return lines.join("\n");
}

/** Markdown としてダウンロードする。 */
export function exportResultMarkdown(result: AnalysisResult, label?: string): void {
  downloadBlob(`${slug(label)}.md`, resultToMarkdown(result, label), "text/markdown;charset=utf-8");
}

/** 生の AnalysisResult を JSON としてダウンロードする（再利用/検証用）。 */
export function exportResultJson(result: AnalysisResult, label?: string): void {
  downloadBlob(
    `${slug(label)}.json`,
    JSON.stringify(result, null, 2),
    "application/json;charset=utf-8",
  );
}
