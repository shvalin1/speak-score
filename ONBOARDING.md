# ONBOARDING（加藤向け・フロントエンド）

ようこそ！このドキュメントは **加藤がフロントエンド開発に着手するための道案内** です。
バックエンドやインフラ・Firebase・署名URL・Cloud Tasks などは **石川が全部隠蔽済み** なので、
加藤は **「型に従って React コンポーネントを書く」ことだけ** に集中できます。

> 困ったら遠慮なく石川に聞いてOK。詰まったら「担当を `UploadZone` と `FeedbackPanel` の2つに絞る」
> という撤退ラインも用意してあります（設計の合意事項）。まずは気楽に動かしてみましょう。

---

## 0. このプロダクトは何？（30秒）

**SpeakScore** = 就活の面接動画をアップロードすると、AIが文字起こし・音声分析・評価・改善点を返すツール。
加藤の担当は **「結果を画面に出すところ（フロントエンド）」** です。

画面の流れはこの3ステップだけ：

```
①アップロード画面  →  ②処理中（進捗表示）  →  ③結果ダッシュボード
  UploadZone           AnalysisProgress         Dashboard（＋子コンポーネント）
```

---

## 1. 環境準備（最初の1回だけ）

必要なのは **Node.js 20系** と **npm** だけ（バックエンドのPython/Dockerは触らなくてOK）。

```bash
# Node のバージョン確認（v20 系ならOK）
node -v
npm -v

# リポジトリを取得（まだなら）
git clone <speak-score の GitHub URL>
cd speak-score

# フロントの依存をインストール
cd frontend
npm install
```

> WSL で作業している場合も上記そのままでOK。

---

## 2. まず動かす（モックモード）⭐ ここが一番大事

**バックエンドが無くても、フロントだけで全画面が動きます。**
`VITE_USE_MOCK=1` を付けると、`api.ts` が「本物のサーバーの代わりに、時間経過で
`アップロード → 処理中（各stage）→ 完了` を返すニセAPI」に切り替わります。

```bash
cd frontend
VITE_USE_MOCK=1 npm run dev
# → http://localhost:5173 が開く
```

毎回打つのが面倒なら、`frontend/.env` を作って中身を1行：

```
VITE_USE_MOCK=1
```

（`frontend/.env.example` をコピーすればOK。`.env` は git に上げない設定済み。）

**やってみよう**: 画面でファイルを選ぶと、進捗バー → ステップ表示が進み、約10秒で
`shared/mock_data/sample_result.json` の内容がダッシュボードに表示されます。
これが「完成形のデータの形」です。

---

## 3. 加藤がいじるファイル

`frontend/src/` の中だけ見ればOKです。

```
frontend/src/
├── App.tsx                      ← 画面の切り替え（石川管理。基本いじらない）
├── types/interview.ts           ← データの「型」。石川が定義。【絶対に勝手に変えない】
├── services/
│   ├── api.ts                   ← サーバー通信＋モック（石川管理。呼ぶだけ）
│   └── auth.ts                  ← ログイン（石川管理。触らない）
├── hooks/
│   └── useInterviewJob.ts       ← 進捗ポーリング（石川管理。呼ぶだけ）
└── components/                  ← ★加藤のメイン作業場所★
    ├── AuthGate.tsx             （石川）ログインの囲い
    ├── UploadZone.tsx           ★ファイル選択（D&D）
    ├── AnalysisProgress.tsx     ★処理中の進捗表示
    ├── Dashboard.tsx            ★結果の全体レイアウト
    ├── ScoreSummary.tsx         ★総合スコア＋各評価軸
    ├── ScoreRadar.tsx           ★レーダーチャート（recharts）
    ├── FeedbackPanel.tsx        ★強み・改善点リスト
    ├── TranscriptView.tsx       ★文字起こし＋フィラー色付け
    └── AudioTimeline.tsx        ★音量・ピッチの折れ線グラフ（recharts）
```

各コンポーネントには **動く最小実装がすでに入っています**（中身は素朴）。
加藤の仕事は **これを見た目・使い勝手の面でちゃんと作り込む** ことです。ゼロからではありません。

---

## 4. 一番大事なルール：「型」に従う

データの形（型）は `frontend/src/types/interview.ts` に全部書いてあり、**石川が定義・管理** します。
加藤はこの型を **読んで従うだけ**。**このファイルを勝手に書き換えないでください**
（バックエンドの `backend/src/schemas/interview.py` と1対1で対応しているため、ズレると壊れます）。

例：結果データ `AnalysisResult` の形

```ts
interface AnalysisResult {
  overall_score: number;        // 総合点 0-100
  dimensions: {                 // 4つの評価軸
    content: Dimension;         // 内容（AI採点）
    structure: Dimension;       // 構成（AI採点）
    delivery: Dimension;        // 話し方（音声解析で算出）
    confidence: Dimension;      // 自信（音声解析で算出）
  };
  audio_metrics: AudioMetrics;  // 話速・フィラー・ピッチ・音量の時系列など
  transcript: Transcript;       // 文字起こし全文＋フィラー位置
  strengths: string[];          // 強み
  improvements: string[];       // 改善点
}
// Dimension = { score: number; comment: string; source: "computed" | "llm" }
```

VSCode なら、変数に `.` を打てば型が補完されます。**「どんなデータが来るか」は型を見ればわかる** ので、
`sample_result.json` を開きながら型と見比べると理解が早いです。

---

## 5. コンポーネントの受け取るデータ（props 早見表）

App から各コンポーネントへ、すでに正しいデータが渡るよう配線済みです。
加藤は **「この props を受け取って、いい感じに表示する」** だけ。

| コンポーネント | 受け取る props | やること |
|----------------|----------------|----------|
| `UploadZone` | `onUpload(file)`, `uploadPct` | ファイルを選んで `onUpload(file)` を呼ぶ。D&Dの見た目を作る |
| `AnalysisProgress` | `job`（現在の進捗） | `job.stage` を見てステップ表示。アニメ等を作り込む |
| `Dashboard` | `result`, `onReset()` | 下の子コンポーネントを並べる。全体レイアウト |
| `ScoreSummary` | `result` | 総合点＋4軸の点数を表示 |
| `ScoreRadar` | `dimensions` | recharts でレーダーチャート |
| `FeedbackPanel` | `strengths`, `improvements` | 2つのリスト表示 |
| `TranscriptView` | `transcript` | 全文表示＋フィラー語を色付け（`fillers` の位置を使う） |
| `AudioTimeline` | `metrics` | recharts で音量・ピッチの折れ線 |

> 「サーバーにどう送るか」「ログイントークンは？」「いつ完了するの？」は **全部 App と api.ts が裏でやっています**。
> 加藤は props を信じて表示に集中してください。

---

## 6. recharts（グラフ）について

`ScoreRadar` と `AudioTimeline` で使います。すでにインストール済み・動く状態です。
公式ドキュメント（https://recharts.org/）の例をそのまま真似ればOK。
まずは既存の実装を動かして、色やサイズを変えるところから慣れていきましょう。

---

## 7. 開発中によく使うコマンド

```bash
cd frontend

VITE_USE_MOCK=1 npm run dev   # 開発サーバー起動（ホットリロード）
npm run typecheck             # 型エラーのチェック（コミット前に通す）
npm run lint                  # コードスタイルのチェック
npm run build                 # 本番ビルドが通るか確認
```

**コミット前に最低限 `npm run typecheck` が通る**ようにしてください（CIでも自動チェックされます）。

---

## 8. コーディングのお約束（軽く）

- **関数コンポーネント**で書く（`function Xxx() { ... }`）。クラスは使わない。
- **`any` を使わない**（型は `types/interview.ts` から import して使う）。
- `types/interview.ts` / `api.ts` / `auth.ts` / `useInterviewJob.ts` は **石川の領域**。基本いじらない。
  「ここを変えたい／型が足りない」と思ったら石川に相談 → 石川が型を直して渡します。
- コミットメッセージは `feat: アップロード画面のD&D見た目を実装` のように（`feat`/`fix`/`docs` など）。

---

## 9. おすすめの進め方（順番）

設計で決めた順番です。**いきなり全部やらない**。1つずつ動かして確認しながら進めます。

1. **`UploadZone`** … ファイルを選べる／D&Dできる見た目を作る（一番とっつきやすい）
2. **`AnalysisProgress`** … 進捗ステップの表示を作り込む
3. **`Dashboard` まわり** … `ScoreSummary` → `FeedbackPanel` → `ScoreRadar` →
   `TranscriptView` → `AudioTimeline` の順で1個ずつ
4. 余裕が出たら見た目（CSS）の全体調整。CSSで溺れそうなら UIライブラリ（Mantine 等）を入れてOK

> モックモードなら何度でも「アップロード→結果表示」を試せます。`sample_result.json` の数値を
> いじれば、いろんなデータでの見え方も確認できます（このファイルは編集して試してOK）。

---

## 10. 困ったときは

- **画面が真っ白／エラー**: ブラウザの開発者ツール（F12）の Console を見る → エラー文を石川に共有
- **型が合わない**: `npm run typecheck` のエラー文をそのまま石川に共有
- **そもそも動かない**: `node -v` が v20 か、`npm install` が成功しているか確認
- 詰まったら早めに声をかける。**1人で長く悩まないのが最優先**（時間が限られているので）

リポジトリ全体のルールは [`AGENTS.md`](./AGENTS.md)、プロダクトの全体像は [`README.md`](./README.md) を参照。

頑張りましょう！🚀
