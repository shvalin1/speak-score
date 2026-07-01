// アップロード専用画面（加藤）。履歴は/historyに分離（Issue #8拡張）。

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CircleCheck, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { uploadInterview } from "../services/api";
import { UploadZone } from "../components/UploadZone";
import { useActiveJob } from "../hooks/useActiveJob";
import { useMe } from "../hooks/useMe";

export function HomePage() {
  const navigate = useNavigate();
  const { setActiveJobId } = useActiveJob();
  const { me, loading: meLoading } = useMe();
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

  // reader（匿名・未許可 Google）はアップロード不可。閲覧のみの案内を出す。
  // 判定が取れるまでは案内もアップロードUIも出さない（ちらつき防止）。
  if (meLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
        読み込み中…
      </div>
    );
  }
  // me が取れない（未writer or /me 取得失敗）ときは安全側=read-only に倒す。
  // 書込は結局 backend の require_writer が弾くが、UI もコメント通り reader 側へ寄せる。
  if (!me || !me.is_writer) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card p-12 text-center">
        <Eye className="size-10 text-muted-foreground" />
        <p className="text-base font-semibold">閲覧のみモードです</p>
        <p className="max-w-md text-sm text-muted-foreground">
          動画のアップロードと解析は許可されたアカウントのみ利用できます。
          履歴・設問別のデモ結果はそのままご覧いただけます。
        </p>
        <Button type="button" variant="outline" className="mt-2" onClick={() => navigate("/history")}>
          デモ結果を見る
        </Button>
      </div>
    );
  }

  return <UploadZone onUpload={handleUpload} uploadPct={uploadPct} />;
}
