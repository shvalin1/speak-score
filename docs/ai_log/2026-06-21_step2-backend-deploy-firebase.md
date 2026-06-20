# 2026-06-21 Step2 バックエンド実装〜本番デプロイ〜Firebase 導入の振り返り

担当: 石川 + Claude Code（Opus 4.8）
範囲: Step2 Phase4 暫定実評価（Whisper/librosa/gpt-4o）の実装、本番 GCP デプロイ、Firebase Auth(匿名) 有効化と通し E2E。
一次情報: 設計判断は `docs/adr/*` と `design_review_and_frontback.md`。本ファイルは「何で躓き・なぜ・何にこだわったか」の要約。詳細な試行錯誤は `_ai/`（gitignore）。

---

## 躓いたところ と 原因

### A. バックエンド実装（worker/パイプライン）

1. **重複ディスパッチによるジョブ喪失**
   - 症状: Cloud Tasks の重複配信／再試行で、処理中ジョブの状態が上書き・喪失しうる。
   - 原因: 状態遷移が冪等でなく、二重 enqueue / 二重実行を吸収できていなかった。
   - 対処: CAS(compare-and-swap)で状態遷移を冪等化、attempt-cap、1MiB のバイトガード、soft-timeout を追加（`876c509`, `eb4bcd9`）。

2. **OpenAI 呼び出しの一時障害と恒久障害の取り違え**
   - 症状: 一時的なネットワーク/レート制限まで即 fail にすると、リトライで回復できるジョブを落とす。
   - 原因: 例外を一律に扱っていた。
   - 対処: SDK 例外階層で分類。timeout/connection/429/5xx → `RecoverableError`（Cloud Tasks に 503 を返して再試行）、その他 4xx・キー欠如・refusal → `FatalError`（即 fail）。`services/_openai.py` に集約。

3. **CI: `ModuleNotFoundError: numpy`（実 worker サービスが import 不可）**
   - 症状: CI のテストで numpy/librosa/openai の import に失敗。
   - 原因: これらは pyproject の optional extras(`audio`/`llm`)。CI の `uv sync` が extras を入れていなかったが、実サービスは module-level で import する。
   - 対処: CI を `uv sync --extra audio --extra llm` に変更（`7013aad`）。

4. **CI が「そもそも回らない」**
   - 症状: workflow ファイルを変更した push で run が 0 件（Actions 有効・YAML 妥当・承認待ち無し）。
   - 原因: その push で `synchronize` イベントが発火しなかった（GitHub 側の取りこぼし）。
   - 対処: 空コミットを push して再発火 → 正常起動・成功（`df52077`）。

5. **ruff E501（行長）が日本語コメントで頻発**
   - 原因: ruff は CJK を表示幅(全角=2列)でカウントするため、日本語コメント/文字列が超過しやすい。
   - 対処: 文字列・シグネチャを分割、一部 `# noqa: E501`。

### B. インフラ / デプロイ

6. **Secret Manager の「版0」で Cloud Run 起動失敗**
   - 症状: `OPENAI_API_KEY` を `secret_key_ref(version="latest")` で注入したが Run が起動しない。
   - 原因: シークレットに版が1つも無い(版0)状態で apply すると Run が解決できず失敗。
   - 対処: apply 前に版を1つ追加。鍵は **stdin パイプ**で投入し、コマンド引数・出力に鍵値を一切出さない（`grep ... | gcloud secrets versions add --data-file=-`）。

7. **Run サービスアカウントの権限過多**
   - 原因: バケットアクセスが `objectAdmin` で広すぎた。
   - 対処: `objectViewer` + `objectCreator` に分割して最小権限化（`6a92d4c`）。署名 PUT は署名 SA の create 権限で成立する。

### C. フロント連携 / Firebase 導入（本番認証の有効化）

8. **CORS 未設定でローカル→本番バックが全滅**
   - 症状: ローカルフロントから本番バック API を直叩きすると全リクエストが弾かれる。
   - 原因: バックは **同一オリジン(Nginx proxy)前提で `CORSMiddleware` を意図的に入れていない**（`main.py` §9）。ローカル直叩きは別オリジンになる。
   - 対処: Vite dev proxy(`VITE_PROXY_TARGET` + `changeOrigin`)で `/api` を本番バックへ転送し、ブラウザには同一オリジンに見せる。バックに CORS を足して本番構成を汚すことは避けた。

9. **【最大の躓き】画面が真っ白（`Invalid hook call: more than one copy of React`）**
   - 症状: フロントを開くと白画面、コンソールに react-router-dom の `useRef` が null。
   - 初手の誤診: `react-router-dom` 未展開を `npm --prefix frontend install` で補ったが、これは npm workspaces の hoisting を崩し `frontend/package-lock.json` を誤生成しただけ。`npm ls` 上 React は 1 コピー(deduped)で、これは**真因ではなかった**。
   - 真因: `react-router-dom` v7 は CJS 依存で、Vite の dep pre-bundle が react を別チャンク(`react-qr-*`)に二重バンドルし、アプリの react と別実体になる。`node_modules` が単一でも起きる。
   - 切り分けの罠: `turbo run dev` は frontend を cwd に vite を動かすため、Vite キャッシュは `frontend/node_modules/.vite` に出る。ルートの `node_modules/.vite` を消しても空振りで、`?v=` ハッシュが変わらず「直っていない」ように見えた。
   - 対処: `vite.config.ts` に `resolve.dedupe: ['react','react-dom']` と `optimizeDeps.include: ['react','react-dom','react-dom/client','react/jsx-runtime','react-router-dom']` を追加し、全依存を単一実体(同一 `?v=`)に揃える（PR #26）。検証は `curl http://localhost:5173/src/main.tsx` で react / react-router-dom の `?v=` 一致を確認。

10. **Playwright で UI 自動検証ができない**
    - 原因: Chrome 配布が無く、`playwright install chrome` は sudo 必須(root 不可環境)で失敗。
    - 対処: ブラウザ自動化に固執せず、**Identity Toolkit REST で匿名 ID トークンを取得 → curl で本番バック API を検証**するルートに切替。コア（Firebase 認証＋バック検証）を確実に通した。UI の最終確認はユーザーのブラウザで実施。

11. **`firebase_admin` の project 解決**
    - 懸念: `verify_id_token` は audience(project_id) 照合に project を要し、`initialize_app()` 引数なしでは ADC 解決に依存する。
    - 対処: `run.tf` が注入する `FIREBASE_PROJECT` を `initialize_app(options={"projectId": ...})` に明示注入する保険を追加（未設定時は従来フォールバック）。実機検証では現行リビジョン(ADC)でも通っていたため、再デプロイは任意。

12. **アップロード 415（Unsupported Media Type）**
    - 原因: 許可 content_type は `video/mp4|quicktime|webm` と `audio/m4a|wav`。テストで使った `audio/mp4` は許可外。
    - 対処: `audio/m4a` で 201（ジョブ作成＋署名 URL 発行）まで確認。401 でなく 415 だったことが「認証は通過している」証跡にもなった。

13. **Firebase プロビジョニングの手段**
    - 当初 gcloud アクセストークン + Admin API(curl) で自動化を計画したが、ユーザー判断で **Firebase コンソール(GUI)で手動**に変更（その方が速く確実）。役割分担を切り、取得した firebaseConfig を受けて以降を自動化。

---

## こだわったところ

- **障害の分離とリトライ設計**: 一時/恒久エラーを明確に分け、Cloud Tasks の再試行を「回復可能なものだけ」に限定。落とすべきものは即落とす。
- **秘密情報の非露出**: API キーは stdin パイプ投入のみ、ログ/引数に出さない。エラーログは status_code・例外型のみで本文(PII)を出さない。`.env.local` は gitignore。
- **最小権限**: Run SA を objectViewer + objectCreator に限定。
- **決定論的な採点**: `temperature=0`、structured outputs(strict json_schema)、`scoring.py` の penalty_band で再現性を確保（ローカル smoke と本番 E2E で overall が一致することを確認）。
- **本番構成を汚さない検証**: CORS をバックに足さず Vite proxy で回避。認証検証は `auth_disabled` の検証窓パターンと REST トークン検証を使い分け。
- **暫定と改善の所有分離**: 暫定実装は石川、評価品質の改善は加藤(#22)という ADR 005 の境界を維持し、「まず本番で通す」ことを優先。
- **不要な再デプロイを避ける**: projectId 修正も「まず現行で試す→必要なら反映」の順序にし、現行で通ることを確認して再デプロイを保留。

---

## 最終状態
- 本番: Step2 パイプライン稼働、Firebase Auth(匿名) 有効化済み、アップロード→採点まで通し E2E 成功。
- PR: #25(Step2 パイプライン, merged) / #26(白画面修正 + projectId 保険, open)。
- 残: 評価品質の改善(#22, 加藤)、`auth.py` 保険のデプロイ反映(任意)、フロントの Cloud Run デプロイ・Google サインイン・承認済みドメイン登録(別途)。
