# Topa'z 記事ドラフト — SpeakScore

> Topa'z 投稿用の下書き。`topaz.dev/projects/new` の各欄に流し込む想定で、固定項目（推し3点＋メタ）と本文に分けている。
> 中間発表は経緯・biz が主役だったので、この記事は技術の中身（なぜその構成にしたか・実装で詰めたところ）を中心に書く。
> 事実の出典は `docs/adr/*` / `design_review_and_frontback.md`(設計v2) / `docs/ai_log/2026-06-21_*`。

---

## ■ 固定項目（フォーム上部の短い欄）

**プロダクト名**: SpeakScore
**サブタイトル / キャッチ**: 面接という「運ゲー」を、実力勝負に変えるAIフィードバック
**リンク**: GitHub `https://github.com/shvalin1/speak-score` / デモ `https://speak-score-frontend-ps6252xwfa-uc.a.run.app/`
**タグ**: TypeScript / React / Python / FastAPI / GCP (Cloud Run・Cloud Tasks・Firestore・GCS) / Terraform / Whisper / librosa

### 推しアイデア
面接をテキストの文字起こしだけで採点すると、話速や間、抑揚といった「どう話したか」がまるごと抜ける。そこを音声から数値で拾って評価軸を足し、テキスト単体よりも面接を細かく見られるようにした。音声側のスコアは毎回同じ値が出るので、評価がブレないのもありがたい。

### 作った背景
自分が就活していたとき、面接を録画して文字起こしし、それをLLMに講評させていた。やってみて気づいたのは、テキストに落とした瞬間に肝心の話し方が消えること。声の情報こそ面接の良し悪しを分けるのに、と思ったのがそのまま動機になった。

### 推し技術
- 待機コストをゼロに保ったまま、ちゃんとした非同期処理を回す Cloud Tasks の worker パイプライン
- 音声特徴量（librosa）で測る軸とLLMで測る軸を分けたハイブリッド採点
- 動画はブラウザから署名URLでGCSへ直接アップロードし、バックエンドには一切通さない

---

## ■ 本文

### どんなプロダクトか

SpeakScore は、就活の面接動画を上げると文字起こし・音声分析・スコア・改善点を返すツールです。テーマは「運に頼らず、実力で内定を掴む」。

面接は相手やお題、その日の調子に左右されやすく、しかも終わったあとに何が良くて何が悪かったのかが返ってきません。録画を自分で文字起こししてLLMに投げる手もありますが、運用が重いうえ、テキストにした時点で話し方の情報が落ちます。SpeakScore は動画1本でその手間を肩代わりし、加えて音声そのものを数値で評価して返します。

正直、この領域には既にカチメン！や steach、RECOMEN といった競合がいて、コンセプト自体の新しさはありません。なので勝負どころは「概念の目新しさ」ではなく「実装の中身」に振りました。

### できること

動画を上げると、音声抽出・文字起こし・音声分析・評価がパイプラインで自動的に走ります。処理は数分かかるので、`extracting_audio → transcribing → analyzing_audio → evaluating` の各段階を画面に出して進捗が見えるようにしました。

結果は評価軸ごとのスコアをレーダーチャートやタイムラインで表示します。各スコアには `source`（computed=算出 / llm=LLM採点）を持たせていて、どうやって出した点なのかが分かるようにしてあります。改善点のコメントは、文字起こしやフィラー、無音区間と紐づけて返します。

### 技術構成と、その選び方

| レイヤ | 採用技術 |
|--------|----------|
| Frontend | React 19 + TypeScript + Vite / recharts / Firebase Auth（匿名） |
| Backend | FastAPI + Python 3.12 / ffmpeg + librosa + Whisper API + GPT/Claude API |
| 非同期 | Cloud Tasks worker（OIDC） |
| Store | Firestore (Native) / GCS（動画は1日で自動削除） |
| Infra | GCP Cloud Run ×2（frontend+Nginx / backend）/ Terraform（単一環境・全リソース `us-central1`） |
| Monorepo | Turborepo + uv / CI: GitHub Actions |

構成はAIに4回クロスレビューさせて固めました（GPT-5.5を2回、Claude単独、Gemini）。迷ったときは、だいたい「待機コストをゼロに保ったまま、ちゃんとした非同期を出す」に立ち返って決めていました。

非同期処理に FastAPI の `BackgroundTasks` を使わなかったのは、scale-to-zero の Cloud Run がリクエスト処理中しかインスタンスの生存を保証しないからです。idle で殺されるとタスクごと落ちる。待機ゼロと本物の非同期を両立できるのは Cloud Tasks くらいしかありませんでした。

ストアに Firestore を選んだのも同じ理由です。Cloud SQL は最小構成でも月7ドルかかり warm-up も要るので、待機ゼロの方針と噛み合いません。Firestore はサーバーレスで待機コストがかからない。

フロントを Cloud Run + Nginx にしたのは、GCS+CDN だと Load Balancer に月18ドル取られるからです。Cloud Run + Nginx なら実質ゼロで済むうえ、Nginx で `/api` をリバースproxyすれば本番のCORSがそもそも要らなくなります。

音声フォーマットは少し回り道をしました。最初は容量効率のいいロスレスFLACで設計していたのですが、実装してみると使っている文字起こしAPIがFLACを受け付けず、WAVに変えています。mp3のような非可逆圧縮は量子化ノイズで無音判定（`librosa.effects.split`）やピッチ解析が崩れるので使えません。最終的に WAV mono 16kHz（`-ac 1 -ar 16000 -vn`）に統一し、無音やピッチをロスレスで保ったまま Whisper と librosa の両方で使い回しています。

### 実装で詰めたところ

採点はハイブリッドにしています。テキストだけでは拾えない「どう話したか」を点数に反映させたかったからです。文字起こしだけでは測れない delivery / confidence（話速・フィラー率・無音分布・ピッチ変動）を librosa の音声特徴量から `scoring.py` で算出し、content / structure（話の中身と構成）は LLM に採点させています。

実は最初「点数は機械的に、コメントはLLMに」という素朴なルールで進めていたのですが、話の中身や構成は意味を読まないと採点できず、LLMに任せるしかなくてこのルールは破綻しました。そこで2系統に分けたという経緯です。音声側は毎回同じ値が出るので評価のブレが小さく、ローカルのsmokeテストと本番E2Eでoverallスコアが一致することも確認しています。

動画はバックエンドを通しません。ブラウザから `storage.googleapis.com` へ直接PUTします。署名URL（V4・期限15分・Content-Type一致）を使うと、バックエンドが動画本体を受けたときに付いて回るbody-size制限やタイムアウト、Nginxの60秒504といった問題を、そもそも踏まずに済みます。

worker は二重実行を前提に作りました。Cloud Tasks の配信は at-least-once なので、放っておくと二重実行で課金が二重になったり状態が壊れたりします。状態遷移をCAS（compare-and-swap）で冪等にして二重enqueue・二重実行を吸収し、`awaiting_upload → processing` の遷移は Firestore のトランザクションで一度きりに絞りました（dedupは/startに集約）。さらに attempt-cap、1MiBのバイトガード、soft-timeout でスタックや暴走を抑えています。

リトライの線引きも気を使ったところです。OpenAI呼び出しの一時的な障害（timeout / connection / 429 / 5xx）と、恒久的な障害（その他の4xx・キー欠如・refusal）をSDKの例外階層で分けました。前者は `RecoverableError` として Cloud Tasks に503を返して再試行させ、後者は `FatalError` で即落とす。回復できるジョブは落とさず、落とすべきものは粘らず落とす、という線引きを `services/_openai.py` にまとめています。

プロジェクトで一番に作ったのは、Pydantic（backend）と TypeScript 型（frontend）のミラー、それとモックでした。いわばAPI契約をDay 0で凍結したわけです。これを先に push したことで、フロント担当はモックUI（進捗表示まで）を先に組み、自分はパイプラインに集中し、最後にAPIで合流する、という二人並行の進め方ができました。

### つまずいたところ

一番手こずったのは画面が真っ白になる現象でした。コンソールに `Invalid hook call: more than one copy of React`。最初は `react-router-dom` が展開されていないせいかと疑って入れ直したのですが、これは誤診でした。本当の原因は、react-router-dom v7 がCJS依存で、Viteの依存事前バンドルがreactを別チャンクに二重バンドルしていたこと。`node_modules` が一つでも起きます。`vite.config.ts` に `resolve.dedupe` と `optimizeDeps.include` を足して、全依存が同じreact実体（同一の `?v=`）を見るように揃えて直しました。

インフラ側では、Secret Manager の「版0」で Cloud Run が起動しないのに引っかかりました。シークレットに版が一つもない状態で `version=latest` を注入すると、Run が解決できずに起動しません。apply前に版を追加して解決。鍵はstdinパイプでだけ流し込み、コマンド引数やログに値が出ないようにしています。

CORSの扱いも一手間でした。バックエンドは同一オリジン（Nginx proxy）前提なので `CORSMiddleware` をあえて入れていません。そのためローカルのフロントから直叩きすると弾かれます。バックにCORSを足すと本番構成が濁るので、Vite の dev proxy（`changeOrigin`）でブラウザに同一オリジンと見せて回避しました。

### アーキテクチャの流れ

```
[React+TS] ──同一オリジン──> [Cloud Run: frontend(Nginx)] ──/api proxy──> [Cloud Run: backend(FastAPI)]
   (1) POST /api/interviews          → job作成 + GCS V4署名URL発行（動画は送らない）
   (2) PUT <署名URL>                 → ブラウザ→GCSへ動画を直接PUT
   (3) POST /api/interviews/{id}/start → transactionで一度だけ processing 化 → Cloud Tasks enqueue
   [Cloud Tasks] ──OIDC──> backend /api/tasks/process（Nginxを通さず直叩き）
       worker: lease取得 → ffmpeg(WAV 16k mono) → Whisper → librosa → scoring(算出)＋LLM → Firestore逐次更新
   (4) GET /api/interviews/{id}（5秒ポーリング）→ 進捗・結果を描画
```

リソースはすべて `us-central1` に置いています。Firestore と GCS の無料枠がUSリージョン限定で、処理は分単位なのでレイテンシも気にならないからです。

### チーム

石川がバックエンドとインフラ、設計（立ち上げ・API契約凍結・デプロイ・PM）を担当。加藤がフロントエンド（React + TS）で、GitHubの開発フローを一周しながらフロントを自分で決めていく経験を積みました。

難所はバックに寄せて、フロントは `/api` を叩くことに絞る、という分け方は意図的です。完走しやすさと、フロント担当が学習に集中できることを両方取りにいきました。

### これから

評価品質はまだ伸ばせるので、LLM評価のプロンプトとルーブリックを詰めていきます。話者分離も今は簡易なので、いずれGKE+GPUでpyannoteに載せ替えたい。フロントのCloud Runデプロイとgoogleサインインも残っています。それと、もともとの発端だったインターン先（食事指導アプリ）の面談評価にも、音声特徴量や話者分離の資産を逆輸入していくつもりです。

---

> 投稿前チェック: ①スクショ（採点画面/レーダーチャート/進捗UI）を本文に挿入 ②GitHubを公開設定に ③デモURLの稼働確認
