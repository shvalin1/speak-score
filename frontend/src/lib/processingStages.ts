// 処理ステージのラベル定義。AnalysisProgress / FloatingProgressWidget で共有する。

import type { ProcessingStage } from "../types/interview";

export const STAGES: { key: ProcessingStage | "queued"; label: string }[] = [
  { key: "queued", label: "待機中" },
  { key: "extracting_audio", label: "音声を抽出中" },
  { key: "transcribing", label: "文字起こし中" },
  { key: "analyzing_audio", label: "音声を分析中" },
  { key: "evaluating", label: "AIが評価中" },
];
