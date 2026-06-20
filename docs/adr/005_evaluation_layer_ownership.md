# ADR 005 — 評価品質レイヤの所有境界（デプロイ単位で分担）

- **状態**: 確定（2026-06-20）。
- **決定**: 担当を**デプロイ単位（出荷方法）**で分ける。
  - **アプリ層（＝backend イメージ再ビルド → 新リビジョンで出荷。`terraform apply` 不要）＝加藤(@hiroki428)**:
    `backend/src/services/*`（`transcription` / `audio_analysis` / `llm_evaluation` / `scoring`）＋プロンプト＋
    ルーブリック定数＋それに要る `backend/Dockerfile` / `pyproject` の依存追加。**評価の品質はここで完結**。
  - **インフラ層（＝`terraform apply` で出荷）＝石川**: Cloud Run の CPU/mem/timeout/concurrency、Cloud Tasks、GCS、
    IAM、Secret Manager、pipeline オーケストレーション/lease 等の配線（Phase 0–3,6,7）。
- **根拠**: 「改善後に（Kato 自身が）デプロイを変更できる範囲」を境界にすると、品質改善のイテレーションが
  terraform を介さず回る。自然な継ぎ目＝**コンテナイメージ**。
- **継ぎ目（品質改善に見えてインフラ変更が要る＝石川へハンドオフ）**:
  - モデル変更でメモリ/CPU/timeout 不足 → Cloud Run リソース。
  - 新しい外部プロバイダのキー → Secret Manager＋`secretAccessor`。
  - 並列度・キュー調整 → Cloud Tasks。
  - 新しい GCP API 有効化。
- **デプロイ運用（現時点）**: backend CI 自動デプロイは**当面作らない**（手動 `gcloud builds submit` ＋ 新リビジョン展開を
  石川が回す）。将来 CI（main マージ→イメージ build＆展開）を入れれば Kato が terraform を触らず自走できる＝この境界が
  実運用で完成する（後日検討）。
- **関連**: [ADR 003] スコアリング2系統分離（決定論/LLM）、[ADR 004] verbatim 文字起こしと disfluency。
  epic [issue #22](https://github.com/shvalin1/speak-score/issues/22)（評価品質レイヤ委譲）と子
  [issue #21](https://github.com/shvalin1/speak-score/issues/21)（disfluency 精度改善）。実装計画 [docs/plans/002]。

[ADR 003]: ./003_scoring_split.md
[ADR 004]: ./004_verbatim_transcription_and_disfluency.md
[docs/plans/002]: ../plans/002_step2_real_pipeline.md
