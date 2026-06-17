// 動画のドラッグ&ドロップ + バリデーション → onUpload(file)（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3
// TODO(加藤): D&Dの見た目・エラーメッセージ表示・対応形式の案内を作り込む。

import { useRef, useState } from "react";

const ACCEPTED = ["video/mp4", "video/quicktime", "video/webm", "audio/m4a", "audio/wav"];
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
    if (file.type && !ACCEPTED.includes(file.type)) {
      setError(`対応していない形式です: ${file.type}`);
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("ファイルが大きすぎます。");
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
      <p>面接動画をドラッグ&ドロップ、またはクリックして選択</p>
      <small>対応形式: mp4 / mov / webm / m4a / wav</small>
      {error && <p className="error">{error}</p>}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) validateAndUpload(file);
        }}
      />
    </div>
  );
}
