// 強み・改善点のリスト表示（加藤）。
// 設計根拠: design_review_and_frontback.md §6.3

export function FeedbackPanel({
  strengths,
  improvements,
}: {
  strengths: string[];
  improvements: string[];
}) {
  return (
    <div className="feedback-panel">
      <div className="strengths">
        <h3>強み</h3>
        <ul>
          {strengths.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </div>
      <div className="improvements">
        <h3>改善点</h3>
        <ul>
          {improvements.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
