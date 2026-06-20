# SpeakScore — 中間発表 素材（3分・技術審査向け）

> **目的**: アロカップ2026 中間発表（持ち時間3分・エンジニア審査）の発表素材。
> **構成**: 1章＝スライド1枚を意識。各章は「スライド用サマリー（箇条書き）」→「詳細・出典」→「決め台詞」の順。
> **出典表記**: 事実はファイル名＋該当箇所を明記。推測は「（推測）」を付す。事実と意見を混ぜない。
> **作成日**: 2026-06-20
> **一次ソース**: `context.md` / `product_spec.md` / `qa_log.md` / `_maintenance/design_review_and_frontback.md`（設計v2）/ `Projects/P2_Internship_Eatas/context.md`

---

## 0. プロダクト一行説明（つかみ）

> 就活の面接動画をアップロードすると、AIが**文字起こし・音声分析・評価・改善点**を返すフィードバックツール。
> テーマ「**運**（うん）に頼らず、実力で内定を掴む」。
> 出典: `context.md` L21-27 / `product_spec.md` L10-11, L4

---

## 1. ハッカソンの軸／テーマ

### スライド用サマリー
- イベントテーマは「うん」（≒雲・運・運用、ほぼ自由）。約40名の学生ハッカソン。
- 審査配点は **完成度50 > 技術30 > 技術の無駄遣い10 = Topa'z記事10**。→「概念の新しさ」より「実装の質・完走」で勝つ設計に最適化。
- テーマ接続: 「**運**に頼らず、実力で内定を掴む」。面接の不確実性（運ゲー）を、定量フィードバックで実力勝負に変える。
- コードはGitHub公開が審査前提（`speak-score` リポジトリ）。
- **裏テーマ＝2人の成長**: 「勝つ」と同時に、チーム2人がそれぞれ未経験領域を踏むことを最上位目的に置く（優先順位①＝加藤の学習・戦力化）。加藤はGitHub開発フロー＆フロント自己決定を体感、石川は立ち上げ/設計/デプロイ/AI駆動開発/PMを実践。

### 詳細・出典
- イベント概要・テーマ「うん」・参加約40名・泊まりがけ: `context.md` L5-12
- 審査基準「技術レベル(30) + 完成度(50) + 技術の無駄遣い(10) + Topa'z記事(10)」: `context.md` L11
- 「審査は完成度50>技術30で実装の質を評価 → 概念の新しさより実装深度」: `qa_log.md` L90-92（2026-06-09 最終方向転換時の判断）
- テーマ接続「運（うん）に頼らず、実力で内定を掴む」: `context.md` L26-27 / `product_spec.md` L4
- GitHub公開が審査対象: `context.md` L12, L128

### チームの軸（裏テーマ：2人が同時に成長する）
このハッカソンは「入賞」だけでなく、**チーム2人がそれぞれ未経験領域を踏む**ことを最上位の目的に置いている（優先順位①＝加藤の学習・戦力化が②入賞より上）。

- **加藤（開発初心者・ハッカソン初心者）に体験してほしいこと**:
  - **GitHubを使った開発フロー**（issue → branch → push → PR → レビュー → 再実装）の一周を体感する
  - 技術にキャッチアップしながら、**フロント分野を自分で考えて決定していく**流れを経験する
- **石川（発表者）が積みたい経験**:
  - 企業インターン経験はあるが、**プロダクトをゼロから立ち上げる／コード・インフラを自分で設計する／自分でデプロイする**通し経験は少ない → それを一周する
  - **AIをバンバン使う開発フロー（AI駆動開発）**の実践
  - **PMとして振る舞う**経験（設計・タスク分解・API契約凍結でチームを動かす）
- だから設計判断も「**難所はバック（石川）に集約し、フロントは`/api`叩きに絞る**」形にしている＝加藤がフロントに集中して学べるようにする意図（§4 Arch 1採用理由と直結）。

**出典**
- 優先順位①加藤の学習・戦力化 ＞ ②入賞 ＞ ③開発環境習得 ＞ ④ポートフォリオ: `context.md` L82-88 / `qa_log.md` L11-14
- 加藤=開発初心者でGitHubフロー体感・フロント自己決定 / 石川=立ち上げ・設計・デプロイ・AI駆動開発・PM経験を積む: 発表者談（一次ソース）
- Arch 1が加藤の学習#1に資する（難所をバックに集約・フロントは/api叩き）: `qa_log.md` L264, L267 / 設計書 §1表

> 一言（テーマ軸）: 「テーマは『うん』。僕らは"面接という運ゲー"を、実力で勝てる土俵に変えます。」
> 一言（チーム軸）: 「これは2人の成長装置でもあります。彼にはGitHubでの開発を一周、僕には設計からデプロイまでとPMを——だから難所は僕が引き受け、フロントは彼に任せる設計にしました。」

---

## 2. 目的

### スライド用サマリー
- **誰の**: 面接を受ける側＝就活生（一次ターゲットを決め打ち）。
- **どんな課題**: 面接の良し悪しがフィードバックされず、自分の「話し方」が客観視できない。録画を手作業で文字起こし→LLMに投げる運用は重く、しかも**音声情報が抜け落ちる**。
- **どう解決**: 動画1本アップロードで、文字起こし＋音声特徴量＋構造化スコア＋改善点を自動で返す。
- **差別化（"ただのGPTラッパー"との違い）**: ①音声特徴量を**自前DSP計算**（librosa）②スコアを**算出系/LLM系に2分割**し算出系は決定論的③**非同期パイプライン**設計で進捗まで見せる。

### 詳細・出典
- ターゲットを就活生に決め打ち: `qa_log.md` L163-164, L166 / `product_spec.md` L25
- 差別化3点（自前音声特徴量・構造化スコア可視化・非同期パイプライン）: `context.md` L34-38 / `qa_log.md` L89-92, L95
- 「テキスト内容の評価はLLMに丸投げすれば済む → 差別化にならない → LLM以外の技術を重視」: `qa_log.md` L162 / `product_spec.md` L256, L268-271
- 算出系（delivery/confidence）は音声特徴量から**決定論的に算出**、LLM系（content/structure）はLLM採点という2分割が「一貫性の核」: `context.md` L36, L132 / `product_spec.md` L121-125 / 設計書 §4
- 競合は激戦区（カチメン！/ steach / RECOMEN 等）でコンセプト新規性はゼロ→だからこそ実装深度で差をつける: `qa_log.md` L88-90

> 一言: 「GPTに投げるだけなら誰でもできる。僕らは"声"を数式で測る。点数の半分はLLMを通さず、同じ動画なら必ず同じ点が出ます。」

---

## 3. 開発に至った経緯（ナラティブ）★最重視

### スライド用サマリー
- **原体験（2つ）**: ①発表者自身の就活 — 面接を録画→LLMで文字起こし→LLMに議事録を作らせて手動管理。**管理が大変**で、しかも一度テキストに落とすので**話し方（話速・間・抑揚）の情報が消える**。②インターン先 Eatas でも、管理栄養士の面談を文字起こし→評価する同じ課題を抱えていた。
- **テーマ自由ゆえの迷走**: 当初は加藤の専門（感染シミュレーション×NSGA-II）を活かす遺伝的アルゴリズム案を検討。
- **制約による転換①**: 論文ABMはスパコンで数時間級→デプロイ・生デモに乗らない。シミュ路線を断念。
- **制約による転換②**: テーマ自由で「実装の質」を競う審査と、加藤の学習目標（Webフロント/バック/APIを全部触る）に最も合うものとして、**就活面接フィードバックツールに決定**。
- 以後、設計を4回のAIクロスレビューで叩いて確定（§4へ）。

### 詳細・出典
**原体験（発表者の就活 ＋ Eatas）**
- 「石川自身が就活で面接動画を録画→文字起こし→Claudeに投げてフィードバックを得ていた実体験。この手動プロセスをプロダクト化する」: `product_spec.md` L13-14
- 「インターン先（食事指導アプリ）で面談の品質評価に取り組んでいた経験」が元ネタ: `product_spec.md` L14, L28-32
- Eatas側の課題: 管理栄養士とユーザーの**面談を文字起こし→評価・要約**するシステムを検討中。話者分離・タイムスタンプ・感情解析（音声）が要件: `Projects/P2_Internship_Eatas/context.md` L4-5, L10-11
- 「ハッカソンの成果物をEatasに逆輸入する前提（特に話者分離・音声特徴量）」: `context.md` L130 / `product_spec.md` L28-32, L137
- 「一度テキストに起こすと話し方の情報が加味されない」という問題意識は、差別化方針「音声・インタラクションの評価は自前計算」と整合（発表者の口頭談に基づく原体験。文書上の直接記述は原体験の要約 `product_spec.md` L13-14 まで）

**方向性の迷走と転換（時系列）**
- 6/09: 加藤の技術シーズ（GA/インタラクティブGA）案を検討: `qa_log.md` L30-39
- 6/09: 感染シミュレーション(SIR)直接転用は却下、動的政策最適化の骨格は保持: `qa_log.md` L43-53
- 6/09: 欲求ダイナミクス系（スマホ断ち/カップル/バズ）に絞る方向へ: `qa_log.md` L57-68
- 6/09 22:39: 「論文コードはスパコンで数時間 → デプロイ不可」を確認し**シミュレーション路線を断念**: `qa_log.md` L72-81
- 6/09 22:46: **就活面接フィードバックツールに最終決定**。実用的・インターンに転用可・加藤の学習#1（フロント/バック/API全部）に最も合致: `qa_log.md` L84-99
- 6/11: 要件定義MTGで加藤が方向性に合意・担当決定（加藤=フロント React/TS）: `qa_log.md` L115-141
- 6/15: ターゲットを就活生に決め打ち、MVP（文字起こし→LLM評価）から積み上げる方針を確定: `qa_log.md` L155-171

> 一言: 「これは自分が就活でやっていた手作業そのものです。録画して、文字起こして、AIに講評させる——でも文字に起こした瞬間、"どう話したか"が消える。そこを埋めたくて作りました。」

---

## 4. 設計判断の記録（採用 / 却下の決定表）★エンジニア審査の山場

### スライド用サマリー
- 設計は **AIクロスレビューを4回**（GPT-5.5×2回／Claude独立／Gemini 3.1 Pro）通して確定（v2）。
- 主要判断はすべて **scale-to-zero（コスト0維持）と「本物の非同期＋進捗表示」の両立**という1本の軸で説明できる。
- 「点数は機械的、コメントはLLM」という当初原則が content/structure（意味判断）で**破綻**→2系統に分離して解消。
- ハッカソンでは**完成度50点を最優先**し、GKE/GPU/WIF/pyannote は「Walking Skeleton緑化後の技術点アップグレード枠」に格下げ。

### 決定表（論点 / 採用 / 却下した代替案 / 却下理由・trade-off）

| 論点 | 採用 | 却下した代替案 | 却下理由 / trade-off |
|------|------|----------------|----------------------|
| 非同期処理 | **Cloud Tasks worker**（即job_id返却→enqueue→worker→stage逐次更新→ポーリング） | FastAPI `BackgroundTasks` | scale-to-zero下のCloud Runは**リクエスト処理中しかインスタンス生存を保証しない**→idleでタスクが殺される。「scale-to-zero＋本物の非同期」を両立できるのはCloud Tasksのみ |
| 状態/結果ストア | **Firestore (Nativeモード)** | Cloud SQL PostgreSQL (db-f1-micro) / SQLite / Supabase | Cloud SQLは**$7/月＋warm-up**でscale-to-zero思想と矛盾。SQLiteはCloud Runで非永続。SupabaseはGCP統一を崩す。FirestoreはKVモデル最適・サーバーレス・warm-up不要 |
| アップロード経路 | **署名URL直アップロード**（ブラウザ→GCS直PUT、backendを通さない） | backend経由のmultipartアップロード | backendが動画本体を受けると**body-size/タイムアウト/Nginx 60秒504**が全部リスク化。署名URLにすると原理的に消滅。trade-off=GCS CORS・SignBlob権限・Content-Type一致の配線が増える |
| 動画/音声の一時保存 | **GCS必須**（lifecycle 1日で自動削除） | Cloud Run `/tmp` を共有 | uploadインスタンスとworkerインスタンスは**別**で`/tmp`共有不可。かつ`/tmp`はtmpfs（メモリ）で**OOMリスク**。GCS化で両方解消 |
| スコアリング方式 | **2系統に分離**: delivery/confidence=算出系（決定論）、content/structure=LLM系 | 「点数は機械的・コメントはLLM」の単純原則 | content/structureは**意味判断でLLMしか採点不可**→単純原則が破綻。各Dimensionに`source`を持たせ算出根拠を透明化。一貫性の売りは算出系（決定論）に置く |
| 認証 | **Firebase Authentication**（MVPは匿名認証）。IDトークンをAPI認証の土台に | 自前認証 / 無認証 | 自前認証を作る工数を排除。無認証だと**一覧GETでプライバシー漏洩・アップロードAPI悪用**。`owner_uid`スコープ化で「自分の分のみ」返す。Arch 1なのでFirestore Security Rules不要（認可はFastAPIでuid照合） |
| アーキ全体 | **Arch 1（API中心 / Cloud Tasks）** | Arch 2（軽いバック廃止・Firebaseイベント駆動） | Arch 2は工数削減でなく**複雑性の移動**（フロントにFirebase SDK/Rules/Eventarc/onSnapshotが乗り全部クリティカルパス化）。加藤はFirebase未経験・実装経験自体なし→難所はバック（石川）に集約しフロントは/api叩きに絞る方が完走率＆学習#1の両面で有利 |
| 音声フォーマット | **単一FLAC**（16kHz mono・ロスレス、Whisper/librosa両用途で共用） | wav/Whisper分岐 → mp3統一 → FLAC | 非圧縮wavはWhisper 25MB上限に抵触。mp3は**量子化ノイズで無音判定(`librosa.effects.split`)が破綻**＝差別化の核が壊れる。FLACはロスレスで無音/ピッチ保持＋soundfileで高速ロード＋16kHz mono≈1MB/分で25MB余裕 |
| フロントホスティング | **Cloud Run + Nginx**（/apiリバースproxyでCORS不要化） | GCS + CDN（Cloud Load Balancing） | GCS+CDNはLBが**$18/月**。Cloud Run+Nginxは実質$0でGCP統一、リバースproxyで本番のCORSが原理的に不要 |
| 話者分離 | **ハッカソンは話者分離API or VAD簡易分離** | pyannote（自前モデル） | pyannoteは**GPU前提でCPU Cloud RunではOOM/激遅**。pyannoteはPhase3（GKE+GPU）に後送り |
| Terraform環境 | **単一環境のみ** | dev + prod の2環境 | 2環境はハッカソンに過剰（時間予算を溶かす） |
| リージョン | **全リソース us-central1** | asia-northeast1（東京） | Firestore/GCSの**無料枠がUSリージョン限定**。処理は分単位でレイテンシ非依存なので東京である必要がない |
| 技術点アップグレード（GKE/GPU/WIF/api・worker分離） | **Walking Skeleton緑化後に後送り** | 最初から実装 | 審査配点が**完成度50>技術30**。完走を最優先し、技術点は緑化後の上積みに回す |

### worker堅牢化（at-least-once対策、レビューで作り込んだ核）
- Cloud Tasksは at-least-once → 二重処理・二重課金リスク。当初の「completedチェックのみ」では競合で二重実行。
- → worker冒頭で **Firestore transactionによるリース取得**（`lease_owner`/`lease_expires_at`/`attempt_count`）。取得条件は`status==processing`かつリース失効。各stageでリース更新、クラッシュ時は**自然失効で再取得**してスタックジョブを回避。
- task名は `job_id+uuid` の一意接尾辞で**tombstone**（同名再利用不可）を回避、dedupは/start transactionに一本化。
- 出典: 設計書 §1.1c, §1.1d, §5.1 / `qa_log.md` L299-318, L322-342

### この章の出典（まとめ）
- 方針変更の差分表（非同期/ストア/GCS/Terraform/フロント/話者分離/スコアリング/認証/音声）: 設計書 §1 表 L12-23
- 各レビューの実害と反映: 設計書 §1.1（GPT）, §1.1b（Claude+GPT 2回目）, §1.1c（Gemini）, §1.1d（GPT 4回目）
- BackgroundTasksがscale-to-zeroで殺される根拠: `qa_log.md` L244 / `product_spec.md` L130 / 設計書 §1表
- Firestore採用とCloud SQL/SQLite/Supabase却下: `qa_log.md` L222 / 設計書 §1表 / `product_spec.md` L131
- 署名URL直アップロード採用: `qa_log.md` L260-272 / 設計書 §1.1（最終行）, §5.2
- スコアリング2分割: `qa_log.md` L218, L225 / 設計書 §4 / `product_spec.md` L121-125
- 認証 Firebase Auth: `qa_log.md` L280-293 / 設計書 §10
- Arch 1採用 vs Arch 2却下: `qa_log.md` L260-267
- 音声フォーマットFLAC: `qa_log.md` L299-306 / 設計書 §1表, §5.1
- フロントCloud Run+Nginx（LB$18却下）: 設計書 §1表 L18, §9
- リージョンus-central1: `qa_log.md` L308 / 設計書 §8 L581
- 技術点アップグレード後送り: 設計書 §1表 L23, §2.1 / `qa_log.md` L227

> 一言: 「全部の判断が"$0を保ったまま本物の非同期を出す"という一本の軸でつながっています。だから却下理由が一言で言える。例えばCloud SQLは——idleで金が出るので落としました。」

---

## 5. アーキテクチャパターンの要点

### スライド用サマリー（1案=1行）
- **API中心（Arch 1）**: 難所はバックに集約、フロントは`/api`を叩くだけ。
- **署名URL直アップロード**: 動画はブラウザ→GCS直PUT、backendは一切通さない。
- **非同期worker（Cloud Tasks）**: 即job_id返却→enqueue→OIDCでworker起動→Firestoreにstage逐次書込→フロントが5秒ポーリング。
- **フルサーバーレス＋scale-to-zero**: Cloud Run / Cloud Tasks / Firestore / GCS、min-instances=0でidleコスト0。
- **決定論×LLMのハイブリッド採点**: delivery/confidenceは音声特徴量から決定論、content/structureはLLM。

### 設計原則
- **API契約をDay 0で凍結**（最重要成果物）: Pydantic（backend）⇄ TS型（frontend）のミラー＋モックを先にpush→加藤が全UIをモックで先行構築、石川はパイプラインに集中、後でAPIで合流。出典: 設計書 §3 L134-136, §7 順序0 / `qa_log.md` L229, L351
- **IaC徹底**: 全GCPリソースをTerraformでコード管理（単一環境）。出典: `context.md` L59 / 設計書 §8
- **クリティカルパスを最小ダミーで先に一周**: 「本番Cloud Run経路で upload→enqueue→worker→Firestore→poll が一周するか」をダミー結果で最初に通し、重い処理は後で中身を流し込む（Step1b）。出典: 設計書 §7 L549, 順序1b / `qa_log.md` L250, L362
- **モックファースト**: 静的JSONでなく`api.ts`にdelay＋状態遷移マシンのモック非同期関数まで用意し`VITE_USE_MOCK`で切替。出典: 設計書 §6.5 / `qa_log.md` L313
- **べき等性をリース＋dedupで担保**（§4 worker堅牢化）。

### 構成図のためのコンポーネント間フロー（言語化・別リポジトリで作図用）
番号は設計書 §2 / `product_spec.md` §3 に準拠。

1. `[ブラウザ React+TS]` →（同一オリジン）→ `[Cloud Run: frontend (Nginx)]`。Nginxが `location /api/` をbackendへリバースproxy（CORS不要化）。
2. **(1) POST /api/interviews**（Firebase認証）: backendがトークン検証→uid取得、`validate(filename, content_type, size)`、`job_id=uuid4`、Firestoreにjob作成（`status=awaiting_upload, owner_uid, expire_at`）、**GCS V4署名URL（PUT・期限15分・content-type一致）を発行**して返す。動画は送らない。
3. **(2) PUT <upload_url>**: ブラウザが動画を `storage.googleapis.com` へ**直接PUT**（backendを通らない）。GCS uploadsバケットにCORS設定（フロントoriginからのPUT許可・responseHeaderにContent-Type）。
4. **(3) POST /api/interviews/{job_id}/start**（Firebase認証）: owner_uid照合・GCSオブジェクト存在＋サイズ確認、Firestore transactionで `awaiting_upload→processing` を一度だけ許可（二重enqueue防止）、Cloud Tasksへenqueue、202返却。
5. `[Cloud Tasks queue]` →（OIDC・SA）→ `[Cloud Run: backend] POST /api/tasks/process`。**Nginxを通らずbackendの.run.appを直叩き**（timeout=900s, concurrency=1, memory=2Gi）。workerはOIDC検証→Firestore transactionでリース取得→GCSから動画DL→ffprobe検証。
6. **worker内パイプライン**（各stepで `repo.update_stage()`）: `extracting_audio`（ffmpeg→単一FLAC 16kHz mono）→ `transcribing`（Whisper API＋フィラー抽出＋ハルシネーション除去）→ `analyzing_audio`（librosa: 話速/フィラー/沈黙/ピッチ/音量）→ `evaluating`（scoring.py=delivery/confidence決定論 ＋ LLM=content/structure採点）。完了で `repo.complete(job_id, result)`、失敗で `repo.fail`。
7. `[ブラウザ]` **GET /api/interviews/{job_id}**（5秒ポーリング・Firebase認証）→ Nginx /api → backend → Firestore読取。`status`/`stage`で進捗表示、`completed`で`result`描画（ScoreRadar/FeedbackPanel/TranscriptView/AudioTimeline）。
- スコープ: 動画一時はGCS（1日自動削除）、状態/結果はFirestore、全リソース us-central1、認証は全`/api`にFirebase IDトークン、worker経路のみCloud Tasks OIDC。
- 出典: 設計書 §2 L78-131 / `product_spec.md` §3 L50-138 / `context.md` L29-32

> 一言: 「動画はバックエンドを1バイトも通りません。ブラウザから直接ストレージへ。だからサーバーは常にゼロまで縮み、財布も痛まない。」

---

## 中間発表時点のステータス（口頭補足用）

### スライド用サマリー
- **API契約を凍結済み**（Pydantic⇄TSミラー＋モック）→加藤がフロントのモックUIを先行構築中。
- backend雛形は検証green（ruff/pytest 5件pass、scoring.py決定論を完全実装、worker→pipeline→scoringのin-memory E2Eで有効な`AnalysisResult`組立を確認）。
- パイプライン中身（ffmpeg/Whisper/librosa/LLM）はダミー返却スタブ（`TODO(Step2)`）。
- **デモ可能範囲**: フロントのモックUIまで。インフラは本番経路を一周させる **Step1b 進行中**（GCS+CORS / Cloud Tasks / OIDC / FirestoreJobRepo / Whisper FLAC受理を実GCPでスパイク）。

### 詳細・出典
- Step0/Step1 scaffold完了・検証green・スタブ状況: `qa_log.md` L346-360（2026-06-17 実装開始ログ）
- Step1b（次フェーズ＝本番経路一周）の内容: `qa_log.md` L362 / 設計書 §7 順序1b
- 中間発表のデモ範囲「フロントのモックUIまで／インフラはStep1b進行中」: 本タスク前提（発表者指定）

> 一言: 「今日お見せできるのはモックUIまで。でも"見えていない方"——本番のCloud Run経路一周——を今まさに通しているところです。」

---

## 読んだファイル一覧

| ファイル | 役割 |
|----------|------|
| `Projects/P6_MiniProjects/topics/hackathon_allocup_2026/context.md` | プロジェクト全体像・技術スタック・役割分担・マイルストーン |
| `.../product_spec.md` | プロダクト仕様書（原体験・画面・パイプライン・API・フェーズ） |
| `.../qa_log.md` | 意思決定ログ（方向転換のナラティブ・レビュー反映の全履歴）★最重要 |
| `.../_maintenance/design_review_and_frontback.md` | 設計v2（採用/却下の根拠・API契約・モジュール設計・Terraform）★最重要 |
| `Projects/P2_Internship_Eatas/context.md` | 元ネタ（Eatas面談文字起こし→評価システムの課題・要件） |
| （一覧把握のみ）`tasks.md` / `meeting_minutes/20260611_要件定義MTG.md` / `chat_raw/*` / `_maintenance/implementation_plan_speakscore.md` / `_maintenance/gemini_review_20260616.md` | 補助。決定の根拠は上記4ファイルに集約済みのため本素材では深掘り未実施 |

---

## 未確認点（情報が薄かった／見つからなかった項目）

1. **発表者の就活原体験の「話し方情報が消える」具体記述**: 文書上は `product_spec.md` L13-14 の原体験要約までで、「テキストに起こすと話速・間・抑揚が抜ける」という痛点の明文記述は無い（発表者の口頭談が一次ソース）。本素材では発表者談として扱い、差別化方針（音声=自前計算）との整合で補強した。
2. **加藤の可処分時間**: `qa_log.md` L15, L126 で「要確認」のまま。中間発表時点の実働状況は文書に明記なし。
3. **実機スパイクの結果**: Whisper APIがFLACを受けるか、署名URLサイズ制約の実効性、FLACの`top_db`無音判定チューニング等（設計書 §7 #6 / `qa_log.md` L337-339）は「Day0確認」のまま、結果ログは未発見（Step1bで検証中＝発表時点で未確定の可能性）。
4. **デモの具体的中身**（どの動画を使うか・min-instances=1のwarm-up運用）: 撤退ライン（`context.md` L95）には記載があるが、中間発表での実演内容は文書に確定記述なし。
5. **Topa'z記事の進捗**: 審査配点10点だが、記事の着手状況は文書に記載なし。
6. **competitorsの詳細比較**: `qa_log.md` L88 に競合名（カチメン！/steach/RECOMEN）はあるが、各社との機能差分の精査ドキュメントは本トピック内に見当たらず（推測: 差別化はコンセプトでなく実装深度で取る方針のため、競合機能比較は意図的に深掘りしていない）。
