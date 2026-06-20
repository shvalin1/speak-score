# Step2 実装 詳細計画（実 pipeline ＋ 繰り越しバックログ）

> **ステータス（2026-06-20）**: これが Step2 実装の正本（tracked）。**暫定実装で前進する方針**に確定。
> 文字起こし/フィラーの**精度改善（disfluency 検出・分離）は加藤(@hiroki428)へ委譲**（[issue #21](https://github.com/shvalin1/speak-score/issues/21)）。
> 文字起こし方針と disfluency の扱いは [ADR 004](../adr/004_verbatim_transcription_and_disfluency.md) を参照。

対象: ダミー pipeline（Walking Skeleton）を実処理に差し替え、面接動画から実スコアを算出する。
前提: Step1b 実機 E2E 完了済み（署名URL→GCS→/start→Cloud Tasks OIDC→worker→Firestore→poll）。
インフラは準備済み（Dockerfile に ffmpeg+libsndfile1＋audio/llm extras、Cloud Run timeout=1800s、dispatch_deadline=1800s）。

---

## 0. 現状の事実（コード確認済み 2026-06-20）

- `services/pipeline.py`: orchestration は配線済み。各サービスはダミー値。`flac_path = ""`（抽出未実装）。
- `services/transcription.py` / `audio_analysis.py` / `llm_evaluation.py`: **全てダミー**。`TODO(石川/Step2)` 明記。
- `services/scoring.py`: **実装済み**（決定論。定数は暫定ルーブリック＝実測チューニング前提）。
- `api/tasks.py`(worker): リース→pipeline→complete/fail、`RecoverableError`→503 再試行 の枠は完成。
- `api/interviews.py` `/start`: GCS メタデータ確認は**コメントアウト**（2-2 の対象）。
- **ギャップ（要対応）**: `repo.create(job_id, owner_uid, expire_at)` は **content_type/filename を保存していない**。
  抽出（拡張子→`{job_id}/source.{ext}`）も 2-2 メタデータ確認も content_type が必須 → **前提タスク化**。
- `pipeline.run_pipeline(job_id, repo, worker_id)` は job を読まない → 抽出のため `repo.get` で content_type 取得が要る。
- `analyze_audio` は同期 CPU 処理を async pipeline 内で直接呼んでいる → librosa 実装後は `asyncio.to_thread` 必須。

## 役割分担・確定事項（2026-06-20）

- **担当はデプロイ単位で分担**（[ADR 005](../adr/005_evaluation_layer_ownership.md)・epic [#22](https://github.com/shvalin1/speak-score/issues/22)）:
  **評価品質レイヤ `services/*`（Phase 4・5）＝加藤(@hiroki428)**／**インフラ・配線・デプロイ（Phase 0–3,6,7）＝石川**。
  境界＝backend イメージで出荷できる範囲（terraform 不要）が Kato。CI 自動デプロイは当面作らず手動（石川）。
- **プロバイダは OpenAI 1本**: 文字起こし=Whisper、評価=gpt-4o structured outputs。`config.llm_provider=openai`。
  鍵は **OPENAI_API_KEY のみ**（Anthropic キー不要）。`whisper_api_key` は openai_api_key と同一でよい。
- scoring の定数チューニング（Phase 5）は実データが流れてから。

---

## レビュー反映：Phase 4 着手前に確定する設計（gpt/gemini クロスレビュー 2026-06-20）

> 査定は Opus。HIGH は「最も高コストな実処理の後段で初めて失敗が露出し丸ごと手戻り」を防ぐため Phase 4 前に設計確定。

- **[HIGH] リトライ枯渇時のジョブ滞留**（GPT）: Cloud Tasks が `max_attempts=3` で task を破棄すると worker は再呼出されず、
  `job.status` が `processing` のまま永久固着→ユーザー無限ポーリング。**対策**: worker 冒頭で `attempt_count`（lease で
  既にカウント）が上限超なら `repo.fail` に倒す。`RecoverableError` を返す経路は必ず「最終的に fatal へ落ちる」設計とセット。
- **[HIGH] Firestore 1MiB ドキュメント上限**（GPT。`FirestoreJobRepo` docstring に既出 NOTE）: 実 transcript 全文＋
  Whisper segments＋`volume_timeline`/`pitch_timeline` で `repo.complete` が最後に落ちうる。**対策（採用）**: タイムラインを
  一定点数に間引き（例: 等間隔 ≤200点）＋transcript 全文に上限（超過は要約/切詰め）。GCS オフロードは Step2 では過剰、間引きで回避。
- **[HIGH] 入力フォーマットは WAV mono16k**（Gemini、Opus 裏取り済み）: 現行 transcription API（gpt-4o-transcribe 含む）の
  対応は mp3/mp4/m4a/wav/webm 等で **FLAC は非対応**。**WAV mono 16kHz** に確定（300s で ≈9.6MB＜25MB・1500s 制限内）。
- **[HIGH] Cloud Run concurrency / 並列度**（GPT）: ffmpeg+librosa+`/tmp`(最大200MB) が多重実行でメモリ/ディスク/コスト同時跳ね。
  **対策**: `containerConcurrency=1`（CPU bound として妥当）、queue の `max_concurrent_dispatches` を抑制、mem/cpu(現2Gi/2CPU)で妥当性確認。
- **[MED] 外部呼び出しの明示 timeout＋soft_timeout 配線**（GPT）: `soft_timeout_seconds`(840) は定義のみで未使用。各 OpenAI 呼出に
  per-call timeout を設定し、全体が soft_timeout 超なら打ち切り→`RecoverableError`/`fail`。直列(ffmpeg→Whisper→librosa→gpt-4o)が
  1800s 張り付くのを防ぐ。
- **[MED] エラー分類の粒度**（GPT）: `429`→`RecoverableError`、`no_speech`/サイズ超過→fatal、**JSON schema 不一致は1回だけ
  リトライ→継続失敗は fatal**（実装バグで 3 回課金を焼かない）。
- **[MED] lease owner 検証（CAS）**（GPT）: `complete`/`fail` を lease-owner 条件付き書込みにし、長引いて lease 失効→別 worker 起動時の
  上書きを防ぐ（安価な堅牢化）。
- **[MED] 観測性を Step2 必須に格上げ**（GPT/Gemini）: `job_id`/stage/attempt/duration/input size/recoverable-or-fatal の
  構造化ログ。実機1周の原因切り分けが段違いに楽。
- **[LOW] プライバシー/データ保持**（Gemini）: 面接音声・transcript を OpenAI に送る。学習オプトアウト/保持方針（ZDR 要否）を
  事業要件として確認（実装ブロッカーではないが要確認事項として記録）。
- **[LOW] `llm_provider` 既定**: 現状 `anthropic`。OpenAI 1本確定なので env 設定漏れで Anthropic 経路に落ちないよう既定を
  `openai` に変更 or 起動時アサート。

---

## フェーズ構成（依存順）

### Phase 0 — 前提（こちら / 小・先行必須）
- [ ] **job レコードに content_type を永続化**: `repo.create` に `content_type` 引数追加 → Firestore/インメモリ両実装に保存。
      `create_interview` は既に `req.content_type` を持つので渡すだけ（作業は軽い）。
- [ ] **取得は内部メソッドで**（GPT #9）: `repo.get_content_type(job_id)` を新設。`InterviewJob`（GET レスポンススキーマ）に
      内部用 content_type を載せない＝契約汚染回避。`pipeline`/`/start` はこの内部メソッドを使う。
- [ ] filename は表示不要なら必須でないが、デバッグ用に内部フィールド保存は任意で可。
- 単体テストはインメモリ repo で完結（GCS/外部API 不要）。

### Phase 1 — 音声抽出（こちら / 中）
- [ ] `pipeline.py` の音声パス実装: `storage.download_to_tmp(...)` → ffmpeg で **WAV mono 16kHz**（`-ac 1 -ar 16000 -vn`）に変換。
      （FLAC は transcription API 非対応のため不採用。WAV16k/300s ≈9.6MB で 25MB 内）。`ffmpeg-python` or subprocess。
- [ ] **動画長チェック**: ffprobe で duration 取得し `max_video_seconds`(300) 超は **致命的 fail**（再試行しない）。
- [ ] **変換後サイズ assert**（GPT #7）: WAV が 25MB を超えないことを確認（超えたら fatal）。長尺分割は Step2 では作らない。
- [ ] **/tmp クリーンアップ**: Cloud Run インスタンス再利用でディスクが溜まらないよう `finally` で削除。
- [ ] 抽出失敗（壊れた動画 = 4xx 相当）は致命的 fail、一時的 I/O 失敗は `RecoverableError`。
- テスト: ローカルにサンプル mp4 を置き ffmpeg 抽出を検証（GCS DL はモック）。`experiments/disfluency/audio_metrics.py` で先行実験済み。

### Phase 2 — 2-2 /start の GCS メタデータ確認（こちら / 小、Phase 0 依存）
- [ ] `/start` で `storage.get_metadata(job_id, content_type)` を呼び、未アップロードなら **409**（or 422）で弾く。
- [ ] サイズ上限 `max_upload_bytes`(200MB) 超過も弾く（A: 署名URLに `x-goog-content-length-range` 付与も検討）。
- [ ] **content-type 整合チェック**（GPT #10）: 実アップロードの content-type が発行時と不一致なら弾く。
      後段の拡張子推定→ffmpeg が壊れる前に検出しエラー分類を綺麗にする。
- [ ] ローカル（GCS 未配線）は従来どおりスキップ（`gcs_bucket` 空で短絡）。
- 効果: §3-3 の PUT を省いても completed まで進む「過大評価」フットガンの解消。

### Phase 3 — 2-3 Secret Manager 結線（中、Phase 4 前に必須）
- [ ] 実キー登録: `gcloud secrets versions add OPENAI_API_KEY --data-file=-`（**OpenAI 1本**）。
- [ ] `run.tf` の backend env を `value_source.secret_key_ref` で結線（secrets.tf は箱だけ作成済み）。
      `OPENAI_API_KEY` と `WHISPER_API_KEY`（同値）を結線。`config.llm_provider=openai` を env で設定。
- [ ] run SA に `roles/secretmanager.secretAccessor`（iam.tf 確認、無ければ付与）。
- 注意: バージョン未登録のまま secret_key_ref を張ると **Cloud Run 起動失敗** → 登録を先に。

### Phase 4 — 実サービス実装（大・3サブに細分化）【加藤(@hiroki428) 所有・epic #22】

Gemini 指摘で「文字起こし/音声分析/LLM の3結合を1フェーズに詰めすぎ」→ サブフェーズ化し各々で単体テスト＆スパイク検証。
共通: 各 OpenAI 呼出に **per-call timeout** 設定（横断の soft_timeout と連動）。OpenAI クライアントは1つ（鍵1本）。
各サービスは **モック可能な境界**（クライアント注入 or 関数差し替え）でネットワーク非依存テスト。

- **Phase 4a 文字起こし**（`transcription.py`）: gpt-4o-transcribe（or whisper-1）。WAV mono16k を送る。タイムスタンプ付き
  セグメント、`no_speech_prob` で異常区間除去。`429`/timeout/5xx→`RecoverableError`、壊れ音声/サイズ超過(4xx)→致命的。
  - **【設計判断・確定】評価は「音声直渡し」でなく Whisper 文字起こしテキストを gpt-4o に渡す**。理由: 音声を gpt-4o に
    直接入れるとフィラー/言い淀みを除いて理解しがちで、フィラー込みの話し方評価が制御できない。テキスト経由なら
    delivery 採点を `scoring.py`＋メトリクスに分離できる。
  - **【スパイク実証 2026-06-20】Whisper も既定でフィラーを全消しする**: 同一音声(kato_test.m4a)で誘導なし=フィラー0件・
    `--prompt`(フィラー例文)誘導あり=11件。よって「テキスト経由にする」だけでは保持目的を達成できず、**prompt 誘導が必須**。
  - **【訂正・重要】誘導版は劣化でなく忠実**: 当初「漁師、漁師…」を精度劣化と誤認したが、話者は実際にそう言い淀んでおり、
    むしろ**誘導なし①が Whisper の補完/正規化（言い淀みを綺麗な内容語に書き換え）を起こしていた**。→ **verbatim（誘導あり）を
    source of truth に採用**。`temperature=0` 明示で誘導時の暴走を抑える。
  - **【暫定実装（今・石川）】**: verbatim 文字起こし（フィラー保持 prompt＋`temperature=0`）＋**簡易フィラー検出**
    （語彙マッチ or 軽い形態素）でフィラー率を算出し pipeline を通す。content/structure 評価には verbatim を渡しつつ
    「言い淀みは内容点に響かせず delivery 側で見る」とプロンプト指示。完璧でなくても E2E を通すことを優先。
  - **【精度改善＝加藤(@hiroki428)へ委譲（[issue #21](https://github.com/shvalin1/speak-score/issues/21)）】**: verbatim から (a) 語彙的フィラー / (b) 繰り返し・言い直し を
    分離・型別定量化。推奨は **形態素＋UniDic「感動詞-フィラー」（fugashi+unidic-lite or SudachiPy）で決定論ベースライン ＋
    LLM で (b) と機能語（その/あの/まあ/なんか）の曖昧性解消**。詳細・ガードレール（LLM に内容を捏造させない＝削除のみ）は
    [ADR 004](../adr/004_verbatim_transcription_and_disfluency.md)。調査: `docs/research/step2_filler_annotation_research.md`。
  - 実験台: `experiments/disfluency/transcribe.py`（`--prompt` 追加済み）/ `audio_metrics.py` / `run_chain.py`（kato_test.m4a で実証済み）。
- **Phase 4b 音声分析**（`audio_analysis.py`）: soundfile ロード→librosa。silence(`effects.split` top_db＝実データで要チューニング)、
  pitch(`yin`)、volume(`feature.rms`)、speech_rate_cpm（漢字/かな比でブレる参考値）、filler_rate。**`asyncio.to_thread` で実行**（CPU bound）。
  → `experiments/disfluency/audio_metrics.py` で先行実験（top_db・帯の感度確認）。**filler_rate の精緻化（disfluency 型別）は加藤へ委譲**（Phase 4a 参照）。
- **Phase 4c LLM評価**（`llm_evaluation.py`）: gpt-4o structured outputs（`response_format=json_schema`・strict）で
  content/structure 採点＋strengths/improvements を JSON 強制・temperature=0。**注意: strict schema は `minimum`/`maximum`
  非対応**→範囲制約は description に記述（スパイクで確認済み）。**schema 不一致は1回だけリトライ→継続失敗は fatal**（実装バグで
  3回課金しない）、`429`/timeout→`RecoverableError`。`config.llm_provider=openai`。→ `experiments/disfluency/llm_eval.py` で先行実験。

### Phase 5 — scoring チューニング（加藤 所有・epic #22 / 実データ後）
- [ ] 実音声で speech_rate/filler/silence/pitch/volume の分布を見て penalty 帯・slope・weight を調整。
- 暫定定数のまま Step2 は通せる（後追いで可）。

### Phase 6 — 2-1 run SA 最小権限化（こちら / 検証窓のついで）
- [ ] `storage.objectAdmin` → `objectViewer`（worker DL）＋ `objectCreator`（署名PUT URL は署名 SA の権限で動くため必須）。
  - **objectViewer だけに落とすと署名PUT URL が 403 でアップロード破綻** → objectCreator を必ず併せる。
- [ ] apply 後、`auth_disabled=true` の検証窓を再度開けて upload→/start→完了を再確認してから閉じる。

### Phase 7 — 実機再検証 ＆ 後始末（こちら）
- [ ] 実短尺動画（〜30秒）で E2E 一周。実スコア・transcript・metrics が妥当か目視。
- [ ] OpenAI（文字起こし＋gpt-4o）のレイテンシが soft_timeout/1800s 内か確認。
- [ ] `auth_disabled=false` 復帰・トラフィック 100% 確認（Step1b と同手順）。
- [ ] `cors_origins` を frontend 実オリジンへ（frontend 結線時）。

---

## 横断事項

- **エラー分類（重要）**: 一時的（`429`・API timeout/5xx・I/O）→ `RecoverableError`（503→Cloud Tasks 再試行・max_attempts=3）。
  恒久的（壊れ動画・長すぎ・サイズ超過・スキーマ不一致が継続）→ `repo.fail`（ユーザー向けメッセージ）。lease で二重処理は防止済み。
  **重要（上記 HIGH）**: 再試行が枯渇しても worker が呼ばれなくなるだけで `fail` は走らないため、`attempt_count` 上限検知で
  明示 fail に倒す経路を必ず持つ（`processing` 永久滞留の回避）。
- **部分失敗の再実行コスト**（GPT #11）: LLM だけ失敗でも再 enqueue で ffmpeg→Whisper→librosa から全やり直し。Step2 では
  **許容**（ステージ別キャッシュは作らない）。代わりにステージ別構造化ログで切り分け可能にする。
- **テスト戦略**: ①単体（API/GCS をモック・ネットワーク非依存、現行18本に追加）②サンプル音声での結合（`experiments/disfluency/` で先行・手動）
  ③実機 E2E（検証窓を開けて実動画1本）。
- **コスト/レイテンシ**: OpenAI（文字起こし＋gpt-4o）の従量課金。dispatch_deadline=1800s 済み。min_instances=0 はコールドスタート許容。
  concurrency=1（HIGH）でインスタンス単位の同時コストを抑制。
- **観測性（Step2 必須に格上げ）**: `job_id`/stage/attempt/duration/input size/recoverable-or-fatal を構造化ログに。
  失敗が外部API/変換/サイズ/Firestore に分散するため、実機1周の原因切り分けに必須。Sentry MCP は別途。
- **依存確認**（GPT #6）: `pyproject` の extras に `librosa`/`soundfile`/`ffmpeg-python`/`openai` 在ること確認済み（2026-06-20 `uv sync` 成功）。
- **プライバシー**（Gemini）: 面接音声・transcript の OpenAI 送信に関する学習オプトアウト/データ保持（ZDR 要否）を事業要件として要確認。

## 着手順（推奨）

Phase 0 → 1 → 2（配線、実機キー不要で先行可）
→ Phase 3（secrets: OpenAI キー登録）→ Phase 4（実サービス：Whisper＋gpt-4o）→ Phase 5（チューニング）
→ Phase 6（SA最小権限）＋ Phase 7（実機再検証）をまとめて検証窓で。

## 決定済み（2026-06-20）

1. **プロバイダ**: OpenAI 1本（文字起こし gpt-4o-transcribe ＋ 評価 gpt-4o structured outputs）。鍵は OPENAI_API_KEY のみ。
2. **担当**: 全 Phase をこちらで実施（依頼者＝石川）。
3. **入力フォーマット**: WAV mono16k（FLAC は transcription API 非対応・裏取り済み）。
4. **クロスレビュー反映済み**: gpt/gemini の HIGH/MED を上記「レビュー反映」節・各 Phase・横断事項に織り込み（Opus 査定）。
   GPT/Gemini が割れた高リスク点は FLAC 可否のみ→Opus が公式仕様で裏取りし WAV に確定（gpt-reviewer 配給 tie-breaker は不要だった）。
5. **ローカル実験台**: `experiments/disfluency/audio_metrics.py`（librosa・合成/実音声）と `experiments/disfluency/llm_eval.py`（gpt-4o 構造化出力・dry-run/実呼出）作成済み。
6. **今回**: 計画確定のみ。実装は次セッション。

## レビュー全文（参照）
- gemini: `_ai/step2/step2_plan_gemini_review.md`
- gpt: 本セッションのレビュー出力（要点は上記「レビュー反映」に集約済み）。
