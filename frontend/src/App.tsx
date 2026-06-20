// アプリの骨組み（石川）: 認証ゲート + view切替。
// view は idle → processing → result/error を job の status から導出する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3

import { useEffect, useState } from "react";
import { listInterviews, uploadInterview } from "./services/api";
import { useInterviewJob } from "./hooks/useInterviewJob";
import { AuthGate } from "./components/AuthGate";
import { UploadZone } from "./components/UploadZone";
import { AnalysisProgress } from "./components/AnalysisProgress";
import { Dashboard } from "./components/Dashboard";
import { HistoryList } from "./components/HistoryList";
import type { InterviewSummary } from "./types/interview";
import "./App.css";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [history, setHistory] = useState<InterviewSummary[]>([]);
  const { job } = useInterviewJob(jobId);

  // 履歴一覧は初回表示時、および job のステータスが変わるたび（完了時など）に取り直す。
  useEffect(() => {
    listInterviews()
      .then(setHistory)
      .catch((err) => console.error("履歴一覧の取得に失敗しました", err));
  }, [job?.status]);

  const handleUpload = async (file: File) => {
    setUploadPct(0);
    try {
      const id = await uploadInterview(file, setUploadPct);
      setJobId(id);
    } finally {
      setUploadPct(null);
    }
  };

  const reset = () => {
    setJobId(null);
    setUploadPct(null);
  };

  return (
    <AuthGate>
      <header className="app-header">
        <h1>SpeakScore</h1>
        <p className="tagline">運に頼らず、実力で内定を掴む</p>
      </header>

      <main className="app-main">
        {!jobId && (
          <div className="flex flex-col gap-4">
            <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />
            <HistoryList items={history} />
          </div>
        )}

        {jobId && job?.status === "completed" && job.result && (
          <Dashboard result={job.result} onReset={reset} />
        )}

        {jobId && job?.status === "failed" && (
          <div className="error-view">
            <p>{job.error ?? "処理に失敗しました。"}</p>
            <button type="button" onClick={reset}>
              もう一度試す
            </button>
          </div>
        )}

        {jobId && (!job || job.status === "processing") && (
          <AnalysisProgress job={job} />
        )}
      </main>
    </AuthGate>
  );
}
