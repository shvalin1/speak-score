// 文字起こし全文 + フィラー語ハイライト（加藤）。
// fillers の start_char/end_char で full_text を分割して色付け。
// 設計根拠: design_review_and_frontback.md §6.3

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Transcript } from "../types/interview";

export function TranscriptView({ transcript }: { transcript: Transcript }) {
  const { full_text, fillers } = transcript;

  // 文字オフセットで分割し、フィラー区間を <mark> で囲む
  const sorted = [...fillers].sort((a, b) => a.start_char - b.start_char);
  const parts: { text: string; filler: boolean }[] = [];
  let cursor = 0;
  for (const f of sorted) {
    if (f.start_char > cursor) {
      parts.push({ text: full_text.slice(cursor, f.start_char), filler: false });
    }
    parts.push({ text: full_text.slice(f.start_char, f.end_char), filler: true });
    cursor = f.end_char;
  }
  if (cursor < full_text.length) {
    parts.push({ text: full_text.slice(cursor), filler: false });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>文字起こし</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed whitespace-pre-wrap">
          {parts.map((p, i) =>
            p.filler ? (
              <mark
                key={i}
                className="rounded bg-amber-300/80 px-0.5 text-slate-900"
              >
                {p.text}
              </mark>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
      </CardContent>
    </Card>
  );
}
