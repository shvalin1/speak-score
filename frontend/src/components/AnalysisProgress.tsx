// 処理中の進捗表示（加藤）。App がポーリングした job を受け取り stage を表示する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3
// TODO(加藤): ステップのアニメーション・推定残り時間などを作り込む。

import { useState, useEffect } from "react";
import type { InterviewJob, ProcessingStage } from "../types/interview";

const STAGES: { key: ProcessingStage | "queued"; label: string }[] = [
  { key: "queued", label: "待機中" },
  { key: "extracting_audio", label: "音声を抽出中" },
  { key: "transcribing", label: "文字起こし中" },
  { key: "analyzing_audio", label: "音声を分析中" },
  { key: "evaluating", label: "AIが評価中" },
];

export function AnalysisProgress({ job }: { job: InterviewJob | null }) {
  const [isReady, setIsReady] = useState(false);
  useEffect(() => {
    setIsReady(true);
  }, []);

  const current = job?.stage ?? "queued";
  let currentIdx = STAGES.findIndex((s) => s.key === current);

  if (!isReady || currentIdx === -1) {
    currentIdx = 0;
  }

  return (
    <div className="analysis-progress">

      <style>{`
        .custom-loader {
          display: inline-block;
          width: 18px;
          height: 18px;
          position: relative;
          border: 3px solid #3b82f6; /* 青色に変更 */
          animation: loader 2s infinite ease;
        }
        .custom-loader-inner {
          vertical-align: top;
          display: inline-block;
          width: 100%;
          background-color: #3b82f6; /* 青色に変更 */
          animation: loader-inner 2s infinite ease-in;
        }
        @keyframes loader {
          0% { transform: rotate(0deg); }
          25% { transform: rotate(180deg); }
          50% { transform: rotate(180deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes loader-inner {
          0% { height: 0%; }
          25% { height: 0%; }
          50% { height: 100%; }
          75% { height: 100%; }
          100% { height: 0%; }
        }
      `}</style>

      <h2>分析しています…</h2>

      <p style={{ color: "#666", marginBottom: "1.5rem", fontSize: "1.1rem" }}>
        ⏱️ 完了まであと <strong>約1〜2分</strong> かかります（動画の長さによって前後します）
      </p>

      <ol className="stage-list">
        {STAGES.map((s, i) => {
          const isDone = i < currentIdx;
          const isActive = i === currentIdx;

          return (
            <li
              key={s.key}
              className={isDone ? "done" : isActive ? "active" : "pending"}
              style={{
                padding: "0.5rem 0",
                display: "flex",
                alignItems: "center",
                fontSize: isActive ? "1.3rem" : "1.1rem"
              }}
            >
              {/* ▼ アイコンの表示エリア */}
              <div style={{ marginRight: "13px", width: "24px", display: "flex", justifyContent: "center" }}>
                {isDone ? (
                  "" // 完了時はCSSチェックマークにお任せ
                ) : isActive ? (
                  /* ▼ ここに新しいローダーのHTMLを配置！ */
                  <span className="custom-loader">
                    <span className="custom-loader-inner"></span>
                  </span>
                ) : (
                  "⚪" // 待機中
                )}
              </div>

              <span style={{
                fontWeight: isActive ? "bold" : "bold",
                color: isActive ? "#3b82f6" : isDone ? "#10b981" : "#9ca3af"
              }}>
                {s.label}
                {isActive && " ..."}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
