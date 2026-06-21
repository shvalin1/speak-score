# ユーザー提案機能の実装計画（共有デモユーザー / 動画シンクロ / 声連動 / エクスポート）

> **ステータス（2026-06-21）**: 石川提案の6案（①〜⑥）をコード精査した結果と、
> そのうち**実装する①②③⑥**の計画＋実装結果。④⑤は本計画では着手しない（⑤は別エピックで設計から）。
> 契約変更は AGENTS.md のルール（`schemas/interview.py`↔`types/interview.ts` 両側同期）に従う。

## 実装状況（2026-06-21・状態復元ポイント）

意図したブランチは `feature/user-features-video-export`。①②③⑥**実装完了**（検証済み）。

| # | 内容 | 主な変更ファイル | 検証 |
|---|---|---|---|
| ① | 匿名→共有 demo_uid / Google→個人 | `core/config.py`(demo_uid)・`core/auth.py`(provider分岐)・`tests/test_auth.py`(新規4) | pytest 4件 ✓ |
| ② | 署名GET URL＋video-urlエンドポイント＋フロント結線 | `core/storage.py`(signed_get_url)・`api/interviews.py`(GET /video-url＋VideoUrlResponse)・`tests/test_interviews.py`(+4)・`services/api.ts`(getVideoUrl)・`pages/JobPage.tsx`(配線) | pytest +4 / typecheck ✓ |
| ③ | 声タイムラインに再生ヘッド＋クリックでシーク | `components/AudioTimeline.tsx`(currentTime/onSeek)・`components/ResultPage.tsx`(VideoTabに組込) | typecheck/lint ✓ |
| ⑥ | Markdown/JSON エクスポート | `lib/export.ts`(新規)・`components/Dashboard.tsx`(ボタン)・`ResultPage.tsx`(label配線) | typecheck/lint/build ✓ |

**全体検証**: backend `pytest` 48 passed / `ruff` クリーン。frontend `typecheck`/`build` 成功、変更ファイルは `eslint` クリーン
（既存4件の lint エラーは AnalysisProgress/badge/button/useInterviewJob のベースライン issue で本変更とは無関係）。

**残・未着手**:
- 未コミット（コミットは依頼待ち）。`DEMO_UID` の `run.tf` env 追加は任意（既定値 `"demo-shared"` で動作）。
- 実機E2E未実施（②の署名GET URLは本番GCSでのみ実URLを返す。ローカル/モックは null でプレースホルダ）。
- デモ用プリシード（匿名共有プールに評価済み結果を仕込む）は別途。

## 精査サマリ（コード確認済み 2026-06-21）

| # | 案 | 判定 | 既存実装 | 主なギャップ |
|---|---|---|---|---|
| ① | 共有デモユーザー（匿名=共有 / Google=個人） | 実装する・小 | `auth.py:get_uid` は uid 直返し | provider 判定で匿名を固定 uid に寄せる |
| ② | 動画シンクロ（クリック→シーク / 再生→ハイライト） | 実装する・中 | **同期UI完成**（`ResultPage.tsx` VideoTab） | `videoUrl` 未供給。署名GET URL〜配線 |
| ③ | ピッチ/音量を文字起こしと時刻連動 | 実装する・小 | timeline 描画済み（`AudioTimeline.tsx`） | 再生位置との連動（純フロント） |
| ④ | 議事録作成 | 見送り | なし | ⑤に内包される下位互換 |
| ⑤ | 問答形式＋設問別採点＋横断管理 | 別エピック | なし | 入力モデル（面接官音声の有無）の設計判断が前提 |
| ⑥ | エクスポート（文字起こし/結果） | 実装する・小〜中 | `AnalysisResult` に全データ | 出力生成（フロント）。動画出力のみ保持に依存 |

### 精査の根拠（ファイル:行）

- **①**: `backend/src/core/auth.py` が `decoded["uid"]` を直返し。Firebase 匿名は**セッション毎に別 uid**
  （`frontend/src/services/api.ts` のコメントも「匿名再ログインで owner_uid が変わり履歴は空になる」前提）。
- **②**: `frontend/src/components/ResultPage.tsx`（VideoTab）が再生位置→セグメントハイライト＆自動スクロール、
  クリック→`seek(seg.start)` を**実装済み**。データも `transcription.py` が whisper-1 verbose_json から
  **実 timestamp 付き segments** を生成。欠けは `JobPage.tsx` が `videoUrl` を渡さない点。
- **③**: `frontend/src/components/AudioTimeline.tsx` が pitch/volume の `TimePoint{t,value}` を時系列描画済み。
  `audio_analysis.py` の `_sample_timeline` が両 timeline を充填（確認済み）。transcript segments も同一時間軸。
- **⑥**: `schemas/interview.py` の `AnalysisResult` に transcript全文・dimensions・metrics・strengths/improvements。

---

## 実装スコープと設計判断（実装済み）

### ① 共有デモユーザー（backend のみ・契約変更なし）
- `auth.py:get_uid` で `verify_id_token` の戻り `decoded["firebase"]["sign_in_provider"]` を見る。
  `"anonymous"` の場合のみ **固定 `DEMO_UID`** を返し、それ以外（google.com 等）は従来どおり `decoded["uid"]`。
  provider 不明なトークンは従来どおり uid フォールバック。
- `DEMO_UID` は `config.Settings.demo_uid`（env `DEMO_UID`、既定 `"demo-shared"`）。
- **リスク明示**: 匿名は相互に閲覧可。「デモは共有・本利用は Google 推奨」を UI 文言で誘導（別タスク・任意）。

### ② 動画シンクロ（backend 配線 + frontend 結線・契約は汚さない）
- **署名GET URL**: `core/storage.py:signed_get_url(job_id, content_type) -> str | None`
  （V4・method=GET・TTL=30分。PUT と同じ IAM SignBlob 経路）。`gcs_bucket` 空 or オブジェクト不在なら `None`。
- **エンドポイント**: `GET /interviews/{job_id}/video-url` → `{ "video_url": str | None }`（`VideoUrlResponse` を
  interviews.py にローカル定義し凍結契約を汚さない）。owner スコープ検証必須。動画削除済みなら `null`。
- **frontend**: `api.getVideoUrl(jobId)`（モックは null）→ `JobPage` の useEffect で完了後に取得し `ResultPage` の
  既存 `videoUrl` prop に渡す。期限切れ等は null → プレースホルダ表示にフォールバック。
- **GCS 保持方針**: 現状の1日保持のまま。新規アップロード直後（<24h）はシンクロ、古い履歴は「未取得」表示で degrade。

### ③ 声（ピッチ/音量）と文字起こしの時刻連動（純フロント・契約変更なし）
- `AudioTimeline` に任意 `currentTime`（recharts `ReferenceLine` の赤い再生ヘッド・最近傍点にスナップ）と
  `onSeek`（グラフクリック→`activeLabel` の t へシーク）を追加。Dashboard 利用は props 省略で後方互換。
- VideoTab に `<AudioTimeline metrics currentTime={currentTime} onSeek={seek} />` を組込。

### ⑥ エクスポート（frontend 中心・契約変更なし）
- `lib/export.ts`: `AnalysisResult` から **Markdown**（総合/4軸表/メトリクス/強み弱み/transcript全文）と **JSON** を
  クライアント生成し `Blob`+`a[download]` でダウンロード。dimension ラベルは既存（内容/構成/話し方/自信）に統一。
- PDF は初版では未対応（必要時はブラウザ印刷）。動画ファイルのエクスポートは1日削除のため対象外。
- 置き場: Dashboard（成績タブ）に「Markdown で保存 / JSON で保存」ボタン。`exportLabel`=createdLabel。

## 横断事項

- **契約不変**: ①②③⑥いずれも `AnalysisResult` を変更していない。②の video-url は別エンドポイント、③⑥は既存データの再利用。
- **owner スコープ**: ②の新エンドポイントは `get_owner` で job 所有者照合（他人の動画 URL を取らせない）。
- **共通ブロッカー（GCS 1日削除）**: ②（履歴再生）と⑥（動画出力）に影響。保持延長せず degrade 容認。
- **デプロイ**: ①②は backend イメージ更新（CD 自動・main push）。`DEMO_UID` env は任意で `run.tf` に追加可。

## 本計画でやらないこと

- ④ 議事録（⑤に内包）／⑤ 問答形式・設問別採点（入力モデルの設計スパイクから別エピック）。
- GCS 保持期間の延長、PDF 専用ライブラリ導入、デモ用プリシード。
