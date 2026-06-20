// 分析進捗・結果・エラーの表示（加藤）。job のステータスから表示を導出する。
// 設計根拠: Issue #8（React Router v7導入）、design_review_and_frontback.md §6.2, §6.3

import { useNavigate, useParams } from "react-router-dom";
import { useInterviewJob } from "../hooks/useInterviewJob";
import { AnalysisProgress } from "../components/AnalysisProgress";
import { Dashboard } from "../components/Dashboard";

export function JobPage() {
  const { jobId = "" } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { job } = useInterviewJob(jobId);
  const reset = () => navigate("/");

  if (job?.status === "completed" && job.result) {
    return <Dashboard result={job.result} onReset={reset} />;
  }

  if (job?.status === "failed") {
    return (
      <div className="error-view">
        <p>{job.error ?? "処理に失敗しました。"}</p>
        <button type="button" onClick={reset}>
          もう一度試す
        </button>
      </div>
    );
  }

  return <AnalysisProgress job={job} />;
}
