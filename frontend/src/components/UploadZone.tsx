// 動画のドラッグ&ドロップ + バリデーション → onUpload(file)（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3
// TODO(加藤): D&Dの見た目・エラーメッセージ表示・対応形式の案内を作り込む。

import { useRef, useState } from "react";

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
    const extension = file.name.split('.').pop()?.toLowerCase();
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
      <div className="upload-zone uploading">
        <p>アップロード中… {uploadPct}%</p>
        <progress value={uploadPct} max={100} />
      </div>
    );
  }

  return (
    <div
      className={`upload-zone${dragging ? " dragging" : ""}`}
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
      <div style={{ fontSize: "4rem", marginBottom: "2rem", textAlign: "center" }}>📥</div>

      <p>面接動画をドラッグ&ドロップ、またはクリックして選択</p>
      <small>対応形式 : {ALLOWED_EXTENSIONS.join(" / ")} ( 最大200MB)</small>
      {error && <p className="error">⚠️ {error}</p>}

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
