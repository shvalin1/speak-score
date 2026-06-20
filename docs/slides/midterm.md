---
marp: true
theme: default
paginate: true
size: 16:9
math: false
header: 'SpeakScore — アロカップ2026 中間発表'
style: |
  :root {
    --indigo: #4f46e5;
    --violet: #7c3aed;
    --cyan:   #0891b2;
    --amber:  #ca8a04;
    --ink:    #1e1b4b;
    --muted:  #64748b;
  }
  section {
    font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif;
    font-size: 24px;
    color: #0f172a;
    padding: 48px 56px;
  }
  h1 { color: var(--ink); font-size: 44px; }
  h2 { color: var(--indigo); font-size: 32px; border-bottom: 3px solid #e0e7ff; padding-bottom: 6px; }
  h3 { color: var(--violet); font-size: 24px; margin-bottom: 4px; }
  strong { color: var(--indigo); }
  header { color: var(--muted); font-size: 14px; }
  table { font-size: 19px; }
  th { background: #eef2ff; color: var(--ink); }
  blockquote {
    border-left: 5px solid var(--violet);
    background: #faf5ff; color: #4c1d95;
    padding: 10px 18px; font-style: normal; font-size: 21px;
  }
  .lead { font-size: 30px; line-height: 1.5; }
  .small { font-size: 18px; color: var(--muted); }
  .pill { display:inline-block; background:#eef2ff; color:var(--indigo);
          border:1px solid #c7d2fe; border-radius:999px; padding:2px 12px; font-size:17px; margin:2px; }

  /* ---- アーキテクチャ構成図（CSS / Mermaid非依存・ネット不要） ---- */
  .arch { display:flex; gap:18px; align-items:stretch; margin-top:10px; }
  .col { flex:1; display:flex; flex-direction:column; gap:10px; }
  .col.gcp { flex:2.2; border:2px dashed #cbd5e1; border-radius:12px; padding:10px; background:#f8fafc; }
  .ltitle { font-size:15px; color:var(--muted); font-weight:700; letter-spacing:.04em; }
  .grow { display:flex; gap:10px; }
  .grow .node { flex:1; }
  .node { border-radius:10px; padding:10px 12px; font-size:16px; line-height:1.35;
          border:2px solid; background:#fff; position:relative; }
  .node .b { display:block; font-weight:700; font-size:17px; }
  .node small { color:var(--muted); font-size:13px; }
  .browser { border-color:var(--indigo); background:#eef2ff; }
  .run { border-color:var(--violet); background:#f5f3ff; }
  .store { border-color:var(--cyan); background:#ecfeff; }
  .sec { border-color:var(--amber); background:#fef9c3; }
  .badge { position:absolute; top:-10px; left:-10px; width:24px; height:24px; border-radius:50%;
           background:var(--violet); color:#fff; font-size:14px; font-weight:700;
           display:flex; align-items:center; justify-content:center; box-shadow:0 1px 3px rgba(0,0,0,.3); }
  .flowlist { font-size:16px; line-height:1.5; margin-top:14px; column-count:2; column-gap:32px; }
  .flowlist b { color:var(--violet); }
  /* カラム分割（原体験・チームのテーマ）を大きめに見せる */
  .exp .node { font-size:21px; line-height:1.5; padding:16px 18px; }
  .exp .node .b { font-size:24px; margin-bottom:6px; }
  .exp .node small { font-size:17px; }
---

<!-- _paginate: false -->
<!-- _header: '' -->

# SpeakScore

## 面接を、<span style="color:var(--cyan)">“雲”（クラウド）</span> で管理する

<br>

就活の面接動画をアップロードすると、AIが
**文字起こし・音声分析・評価・改善点** を返すフィードバックツール

<br>

<span class="small">アロカップ2026 / 中間発表 — 石川（バックエンド・インフラ・設計）／加藤（フロントエンド）</span>

<!--
つかみ。15秒。
「テーマは『うん』——雲・運・運用。僕らは面接の"運"を、"雲"＝クラウドで管理します（フルサーバーレス）。」
プロダクトは1文で説明しきる。詳細は次から。
-->


---

## チームのテーマ ① — 加藤の成長（フロントエンド）

このチームの優先順位は **①メンバーが未経験領域を踏む ＞ ②入賞**。
その筆頭が、開発初心者・ハッカソン初心者である **加藤の戦力化**。

<div class="grow exp">
<div class="node run" style="flex:1">
<span class="b">踏む領域 ①：GitHub 開発フロー</span>
<small>issue → branch → push → PR → レビュー → 再実装 の一周を、体で覚える</small>
</div>
<div class="node run" style="flex:1">
<span class="b">踏む領域 ②：フロントを自分で決める</span>
<small>React / TS をキャッチアップしながら、UI・コンポーネント設計を自分で考えて決定していく</small>
</div>
</div>

<br>

- だから設計を **「難所はバックが隠蔽し、フロントは `/api` 叩き＋モックに集中」** に寄せた
  （API契約凍結・モックファースト）→ 加藤が *学びながら手を動かせる* 構造をアーキ側から用意

> 勝ちにいくと同時に、彼がこの1本で "開発の一周" を体験しきれるように——それを設計の制約に落とし込みました。

<!--
25秒。技術審査が重心なので軽く。ポイントは「学習目標がアーキ判断(Arch1=難所をバックに集約)と直結している」こと。
ここを後の設計判断①の伏線にできる。優先順位①加藤＞②入賞、を一度だけ明言。
-->

---

## チームのテーマ ② — 石川の成長（設計・インフラ・PM）

インターンでの実装経験はあるが、**0→1 を通しでやり切った経験は少ない**。
このハッカソンを、その "通し経験" の場にしている。

<div class="grow exp">
<div class="node store" style="flex:1">
<span class="b">立ち上げ→設計→デプロイを一周</span>
<small>プロダクトをゼロから／コードもインフラも自分で設計／自分でデプロイ する通し経験</small>
</div>
<div class="node store" style="flex:1">
<span class="b">AI駆動開発 ＆ PM</span>
<small>AIをフルに使う開発フロー／設計・タスク分解・API契約凍結でチームを動かす</small>
</div>
</div>

<br>

- **アーキテクチャ・Terraform** は、その *自分で全部設計する* 実践そのもの
- API契約を凍結して2人を並行で走らせたのは、**PMとしての振る舞い** の練習でもある

> 設計からデプロイ、そしてチームを動かすところまで——"自分で全部やる" を一周することが、僕個人の目標です。

<!--
25秒。発表者(石川)自身の成長軸。後半のアーキ/Terraform/worker堅牢化スライドが"この実践の成果物"だと位置づけられる。
「API契約凍結＝PM実践」で、加藤スライドと石川スライドが1本の線（並行開発を可能にした設計）で繋がる。
-->

---

## 目的 — "ただのGPTラッパー" との違い

**誰の・何を**：就活生の「自分の話し方が客観視できない」を解消。
手作業の録画→文字起こし→LLM運用は重く、しかも **音声情報が抜け落ちる**。

| | 差別化ポイント | 中身 |
|--|--|--|
| ① | **音声特徴量を自前DSP計算** | librosa で話速・フィラー率・無音分布・ピッチ変動を抽出 |
| ② | **スコアを2系統に分離** | delivery/confidence=**決定論算出** ／ content/structure=LLM採点 |
| ③ | **非同期パイプライン** | Cloud Tasks worker で進捗まで可視化（scale-to-zero両立） |

> GPTに投げるだけなら誰でもできる。僕らは "声" を数式で測る。
> 点数の半分はLLMを通さず、**同じ動画なら必ず同じ点** が出ます。

<!--
45秒。ここで技術の主張を先出しして"GPTラッパーではない"を宣言。
②の「決定論」が一貫性の核＝差別化の核。後の設計判断スライドに繋ぐ。
-->

---

## 開発に至った経緯 — 原体験

<div class="grow exp">
<div class="node browser" style="flex:1.4">
<span class="b">自分の就活そのものが出発点</span>
面接を録画 → 文字起こし → Claude に講評させて、手で管理していた。
<small>運用が重く、しかも一度テキストに起こすと "どう話したか"（話速・間・抑揚）が消える</small>
</div>
<div class="node store" style="flex:1">
<span class="b">インターン先でも同じ課題</span>
食事指導アプリで **面談を文字起こし→評価** する仕組みを検討中。
<small>ハッカソンの成果をそのまま逆輸入できる</small>
</div>
</div>

<br>

- ねらいは *手作業を自動化し、消えていた音声情報まで取り戻す* こと → 差別化（自前の音声特徴量）の動機そのもの

> これは自分が就活でやっていた手作業そのもの。文字に起こした瞬間 "どう話したか" が消える——そこを埋めたくて作りました。

<!--
35秒。原体験に絞る。"自分の就活の手作業そのもの"＋"テキスト化で音声情報が消える"痛点が、
差別化(自前音声特徴量)の動機に直結することだけ言い切る。迷走/転換のくだりは尺短縮のため今回カット。聞かれたら口頭で。
-->

---

## 設計判断 ① — コストを0に保ちつつ、ちゃんと非同期にする

**使っていない間はコスト0（scale-to-zero）に保ちつつ、本物の非同期処理＋進捗表示を出す**。

| 論点 | 採用 | 不採用にしたものと理由 |
|--|--|--|
| 非同期 | **Cloud Tasks worker** | `BackgroundTasks` は待機中にインスタンスが落とされ処理が消える |
| ストア | **Firestore (Native)** | Cloud SQL は使っていない間も課金／SQLiteは消える |
| アップロード | **署名URL直PUT** | backend経由は容量制限・タイムアウトが全部リスクに。動画を通さない |
| ホスティング | **Cloud Run+Nginx** | GCS+CDN は固定費 $18/月。proxyにすればCORSも不要 |
| 音声形式 | **単一FLAC** | mp3は圧縮ノイズで無音判定が壊れる＝差別化の核が崩れる |

<!--
私用メモ（50秒・山場①）。
言い方：最初に「判断の狙いはどれも同じです」と言ってから表を見せる。すると各行が同じ狙いの帰結に見え、納得されやすい。
全部は読まない。Cloud Tasks（非同期）と署名URL（動画を通さない）の2つだけ口頭で深掘り、残りは「これも同じ"使ってない間はコスト0"の判断です」で流す。
補足したい用語：
- scale-to-zero =「アクセスが無い待機中はインスタンス0台＝料金が発生しない」。ここが全判断の前提。
- 署名URL =「ブラウザがGCSへ直接アップロードするための、期限付きの許可証つきURL」。動画がbackendを通らないので容量制限/タイムアウトが消える。
-->

---

## アーキテクチャ構成図

![Architecture Diagram](./assets/arch.png)


---

## 設計を支える原則 ＆ 現在地

<div class="grow">
<div style="flex:1">

### 設計原則
- **API契約を Day0 で凍結**（Pydantic ⇄ TS のミラー＋モック）
  → 加藤はモックUIを先行構築、石川はパイプラインに集中、後でAPI合流
- **IaC徹底** — 全GCPリソースを Terraform（単一環境）
- **クリティカルパスを最小ダミーで先に一周**（Walking Skeleton）

</div>
<div style="flex:1">

### 中間発表時点の現在地
- ✅ API契約 凍結済み・backend骨格 green（ruff/pytest）
- ✅ **フロントのモックUIが動く**（本日のデモ範囲）
- 🔄 **デプロイStep1b 進行中**：本番Cloud Run経路を一周
  （GCS+CORS / Cloud Tasks / OIDC / Firestore）
- ⏭ Step2：ffmpeg→Whisper→librosa→LLM を流し込む

</div>
</div>

<!--
35秒。締め。原則（API契約凍結・IaC・Walking Skeleton）で"設計をやり切っている"印象を残しつつ、
中間らしく「ここまで出来て、次はここ」を明示。デモ（モックUI）はこのスライドで or 直後に短く。
時間が押したらデモは口頭スキップ可能な位置。
-->
