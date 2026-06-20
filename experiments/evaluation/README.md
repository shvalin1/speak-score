# 評価品質レイヤ 実験スパイク

Step2 の音声→文字起こし→評価パイプライン（`backend/src/services/*` = transcription / audio_analysis /
llm_evaluation / scoring）を、本番コードに入れる前にローカルで試すための実験台。**本番ではない**（src への移植前の検証用）。

関連: epic [#22](https://github.com/shvalin1/speak-score/issues/22)（評価品質レイヤ委譲・担当 @hiroki428）/
子 [#21](https://github.com/shvalin1/speak-score/issues/21)（disfluency 精度改善）/
[ADR 004](../../docs/adr/004_verbatim_transcription_and_disfluency.md) ・ [ADR 005](../../docs/adr/005_evaluation_layer_ownership.md) /
[実装計画 002](../../docs/plans/002_step2_real_pipeline.md)

## 準備

- `backend/.env` に `OPENAI_API_KEY=...` を置く（スクリプトが自動で拾う。環境変数でも可）。
- ffmpeg をローカルに入れる（`sudo apt-get install -y ffmpeg`。動画→音声変換と m4a 読込に必要）。
- 依存は backend の extras: `cd backend && uv sync --extra audio --extra llm`。
- **サンプル音声は各自用意**（wav/m4a/mp3/mp4、≤25MB）。本人の自己紹介を10〜30秒録るのが手軽。
  ※ 個人音声は PII のためリポジトリには含めない。

## スクリプト

| ファイル | 役割 |
|---|---|
| `transcribe.py` | Whisper 文字起こし。`--prompt` でフィラー保持を誘導、`--out` でテキスト書出し |
| `audio_metrics.py` | librosa で話速/無音/ピッチ/音量。`--gen-sample` で合成音声、`--audio`/`--video` で実ファイル |
| `llm_eval.py` | gpt-4o structured outputs で content/structure 採点。`--dry-run` でプロンプト/スキーマ確認 |
| `run_chain.py` | 上記を一気通貫（変換→文字起こし→メトリクス→評価）。結果を `out/<日時>_<名前>.{json,md}` に保存 |

## 実行例

```sh
# 一気通貫
uv run --project backend python experiments/evaluation/run_chain.py --audio /path/to/speech.m4a

# 個別: フィラー保持の誘導あり/なし比較
uv run --project backend python experiments/evaluation/transcribe.py --audio speech.m4a
uv run --project backend python experiments/evaluation/transcribe.py --audio speech.m4a \
  --prompt "えーと、あのー、まあ、なんか。フィラーや言い淀みも省略せず書き起こす。"
```

## 既知の知見（ADR 004 / issue #21 参照）

- Whisper は既定でフィラーを除去・正規化（補completion）する。verbatim には `--prompt` 誘導＋`temperature=0` が要る。
- 強い誘導は内容語の精度に影響しうる。LLM に clean text を作らせる場合は **削除のみ（語の置換・追加禁止）**。
- 話速 CPM は漢字/かな比でブレる参考値。`--top-db` で無音検出感度を要チューニング。
