// 分析進捗・結果・エラーの表示（加藤）。job のステータスから表示を導出する。
// 設計根拠: Issue #8（React Router v7導入）、design_review_and_frontback.md §6.2, §6.3

import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useInterviewJob } from "../hooks/useInterviewJob";
import { AnalysisProgress } from "../components/AnalysisProgress";
import { ResultPage } from "../components/ResultPage";

// job.error（バックエンド内部のエラーメッセージ）を日本語のユーザー向けメッセージに変換する。
// TODO(加藤/石川): バックエンドのエラーコードが正式に決まったら、文字列マッチではなく
// コードベースの分岐に置き換える（Issue #9）。
function formatJobError(error: string | null | undefined): string {
  if (!error) return "処理に失敗しました。もう一度お試しください。";
  const lower = error.toLowerCase();
  if (lower.includes("size") || lower.includes("large")) {
    return "ファイルサイズが大きすぎます。200MB以下の動画でお試しください。";
  }
  if (lower.includes("format") || lower.includes("codec") || lower.includes("extension")) {
    return "対応していないファイル形式です。mp4 / mov / webm / m4a / wav のいずれかでお試しください。";
  }
  return "サーバーでエラーが発生しました。時間をおいて再度お試しください。";
}

export function JobPage() {
  const { jobId = "" } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { job } = useInterviewJob(jobId);
  const reset = () => navigate("/");

  if (job?.status === "completed" && job.result) {
    const initialTab = searchParams.get("tab") === "video" ? "video" : "score";
    return <ResultPage result={job.result} onReset={reset} initialTab={initialTab} />;
  }

  if (job?.status === "failed") {
    return (
      <Card className="mx-auto max-w-md border-destructive/40">
        <CardContent className="flex flex-col items-center gap-4 text-center">
          <CircleAlert className="size-10 text-destructive" />
          <p className="text-sm text-muted-foreground">{formatJobError(job.error)}</p>
          <Button type="button" size="lg" onClick={reset}>
            もう一度試す
          </Button>
        </CardContent>
      </Card>
    );
  }

  return <AnalysisProgress job={job} />;
}
