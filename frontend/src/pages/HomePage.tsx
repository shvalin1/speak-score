// アップロード専用画面（加藤）。履歴は/historyに分離（Issue #8拡張）。

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadInterview } from "../services/api";
import { UploadZone } from "../components/UploadZone";

export function HomePage() {
  const navigate = useNavigate();
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  const handleUpload = async (file: File) => {
    setUploadPct(0);
    try {
      const jobId = await uploadInterview(file, setUploadPct);
      navigate(`/jobs/${jobId}`);
    } finally {
      setUploadPct(null);
    }
  };

  return <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />;
}
