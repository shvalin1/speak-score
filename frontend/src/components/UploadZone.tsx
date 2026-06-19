// 動画のドラッグ&ドロップ + バリデーション → onUpload(file)（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3
// TODO(加藤): D&Dの見た目・エラーメッセージ表示・対応形式の案内を作り込む。

import { useRef, useState } from "react";
import { CircleAlert, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

const ALLOWED_EXTENSIONS = ["mp4", "mov", "webm", "m4a", "wav"];
const MAX_BYTES = 200 * 1024 * 1024; // 申告サイズ上限の目安（実効はサーバ側で担保）

interface Props {
  onUpload: (file: File) => void;
  uploadPct: number | null;
}

export function UploadZone({ onUpload, uploadPct }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const validateAndUpload = (file: File) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !ALLOWED_EXTENSIONS.includes(extension)) {
      setError(`対応していない形式です（.${extension}）`);
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("ファイルが大きすぎます（最大200MB）。");
      return;
    }
    setError(null);
    onUpload(file);
  };

  if (uploadPct !== null) {
    return (
      <div className="rounded-xl border border-border bg-card p-12 text-center">
        <p className="mb-4 text-sm text-muted-foreground">
          アップロード中… {uploadPct}%
        </p>
        <Progress value={uploadPct} className="mx-auto max-w-xs" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border bg-card p-12 text-center transition-colors cursor-pointer",
        dragging && "border-primary bg-accent",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) validateAndUpload(file);
      }}
      onClick={() => inputRef.current?.click()}
    >
      <UploadCloud className="size-12 text-muted-foreground" />

      <p className="text-sm">面接動画をドラッグ&ドロップ、またはクリックして選択</p>
      <p className="text-xs text-muted-foreground">
        対応形式: {ALLOWED_EXTENSIONS.join(" / ")}（最大200MB）
      </p>

      <Button type="button" size="sm">
        ファイルを選択
      </Button>

      {error && (
        <p className="flex items-center gap-1.5 text-sm text-destructive">
          <CircleAlert className="size-4" />
          {error}
        </p>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(",")}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) validateAndUpload(file);
        }}
      />
    </div>
  );
}
