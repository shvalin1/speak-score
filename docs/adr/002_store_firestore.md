# ADR 002 — ストアは Firestore (Native)

- **状態**: 確定（2026-06-16）
- **決定**: ジョブ/結果ストアは Firestore (Nativeモード)。KVモデルに最適・サーバーレス・scale-to-zero一致。
- **却下**: Cloud SQL（warm-up/$7・scale-to-zero思想と矛盾）、SQLite（Cloud Runで非永続）、Supabase（GCP統一を崩す）。
- **注意**: 1MiBドキュメント上限。timeline はダウンサンプル、肥大時は result を GCS に逃がす（design §10）。
- **根拠**: `design_review_and_frontback.md` §1。
