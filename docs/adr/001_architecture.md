# ADR 001 — アーキテクチャ確定（Arch 1 / Cloud Tasks 非同期）

- **状態**: 確定（2026-06-16）
- **決定**: API中心の Arch 1。署名URL直アップロード（ブラウザ→GCS）＋ Cloud Tasks worker 非同期。
  scale-to-zero と本物の非同期＋進捗ポーリングを両立できるのは Cloud Tasks のみ。
- **却下**: Arch 2（Firebaseイベント駆動・軽いバック廃止）は複雑性をフロントに移すだけで、
  加藤（Firebase未経験）には不適。BackgroundTasks は scale-to-zero 下で殺される。
- **根拠の全文**: docs Vault `design_review_and_frontback.md` §1, §2 / `qa_log.md`。
