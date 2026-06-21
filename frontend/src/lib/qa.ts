// 設問カテゴリ(QuestionIntent)の表示ラベルと小ヘルパ。ResultPage / QaListPage で共用。

import type { QuestionIntent } from "../types/interview";

export const INTENT_LABELS: Record<QuestionIntent, string> = {
  self_intro: "自己紹介",
  motivation: "志望動機",
  strength: "強み",
  weakness: "弱み",
  experience: "経験",
  reverse: "逆質問",
  other: "その他",
};

export function intentLabel(intent: QuestionIntent): string {
  return INTENT_LABELS[intent] ?? INTENT_LABELS.other;
}

/** 秒を m:ss に整形。 */
export function fmtTime(sec: number): string {
  const s = Math.floor(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** スコアに応じた配色（横断比較で一目で良し悪しが分かるように）。 */
export function scoreClass(score: number): string {
  if (score >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 60) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}
