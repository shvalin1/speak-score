// アプリの骨組み（石川）: 認証ゲート + view切替。
// view は idle → processing → result/error を job の status から導出する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3

import { useState } from "react";
import { uploadInterview } from "./services/api";
import { useInterviewJob } from "./hooks/useInterviewJob";
import { AuthGate } from "./components/AuthGate";
import { UploadZone } from "./components/UploadZone";
import { AnalysisProgress } from "./components/AnalysisProgress";
import { Dashboard } from "./components/Dashboard";
import "./App.css";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const { job } = useInterviewJob(jobId);

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
        {!jobId && <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />}

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
