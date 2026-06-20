// アップロード専用画面（加藤）。履歴は/historyに分離（Issue #8拡張）。

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CircleCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { uploadInterview } from "../services/api";
import { UploadZone } from "../components/UploadZone";
import { useActiveJob } from "../hooks/useActiveJob";

export function HomePage() {
  const navigate = useNavigate();
  const { setActiveJobId } = useActiveJob();
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadedJobId, setUploadedJobId] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setUploadPct(0);
    try {
      const jobId = await uploadInterview(file, setUploadPct);
      setActiveJobId(jobId);
      setUploadedJobId(jobId);
    } finally {
      setUploadPct(null);
    }
  };

  if (uploadedJobId) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card p-12 text-center">
        <CircleCheck className="size-10 text-emerald-500" />
        <p className="text-base font-semibold">アップロード成功！</p>
        <p className="mb-4 text-sm text-muted-foreground">
          分析が完了するまで、他のページに移動しても進捗を確認できます。
        </p>
        <div className="flex gap-3">
          <Button type="button" onClick={() => navigate(`/jobs/${uploadedJobId}`)}>
            分析ページに移動
          </Button>
          <Button type="button" variant="outline" onClick={() => setUploadedJobId(null)}>
            ホームに戻る
          </Button>
        </div>
      </div>
    );
  }

  return <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />;
}
