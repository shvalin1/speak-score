// アップロード + 履歴一覧（加藤）。
// 設計根拠: Issue #8（React Router v7導入）

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listInterviews, uploadInterview } from "../services/api";
import { UploadZone } from "../components/UploadZone";
import { HistoryList } from "../components/HistoryList";
import type { InterviewSummary } from "../types/interview";

export function HomePage() {
  const navigate = useNavigate();
  const [history, setHistory] = useState<InterviewSummary[]>([]);
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  useEffect(() => {
    listInterviews()
      .then(setHistory)
      .catch((err) => console.error("履歴一覧の取得に失敗しました", err));
  }, []);

  const handleUpload = async (file: File) => {
    setUploadPct(0);
    try {
      const jobId = await uploadInterview(file, setUploadPct);
      navigate(`/jobs/${jobId}`);
    } finally {
      setUploadPct(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />
      <HistoryList items={history} onSelect={(jobId) => navigate(`/jobs/${jobId}`)} />
    </div>
  );
}
