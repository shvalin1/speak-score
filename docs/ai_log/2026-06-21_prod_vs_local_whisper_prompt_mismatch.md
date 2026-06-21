# 2026-06-21 本番とノートブックの文字起こし差分 → verbatimプロンプト文字列の不一致が原因

担当: @hiroki428（加藤） / 関連: [ADR 004](../adr/004_verbatim_transcription_and_disfluency.md) / issue [#21](https://github.com/shvalin1/speak-score/issues/21)・[#22](https://github.com/shvalin1/speak-score/issues/22) /
対象: [backend/src/services/transcription.py](../../backend/src/services/transcription.py) / [experiments/evaluation/diarization_compare.ipynb](../../experiments/evaluation/diarization_compare.ipynb)

## 発端

本番（remote URL）で文字起こしした結果と、`diarization_compare.ipynb` で同じ音声（`InputData/TestInterview.mp4`、石川の実面接サンプル）を
ローカルでwhisper-1にかけた結果が大きく異なっていた。

- ノートブック（②verbatimプロンプト）: fillers=1, chars=1282。クリーンな書き起こし。
- 本番: 「あの」が30回以上挿入され、「へー」「うんうん」のような相手（面接官）の相槌まで混入。chars=1439超。

## 調査

最初に GPU/Whisper API側の非決定性を疑ったが、的外れだった。本番ページを再読み込みしても同じ結果が出るのは
Firestore に保存済みのジョブ結果を表示しているだけで、Whisperを再実行しているわけではない。

本当の原因はもっと単純で、**ノートブックの `VERBATIM_PROMPT` と backend 本番の `_VERBATIM_PROMPT` の文字列が違う**こと。

- backend本番（[transcription.py:26-28](../../backend/src/services/transcription.py#L26-L28)）:
  `"えーと、あのー、まあ、なんか、その、といったフィラーも省略せずそのまま書き起こす。"`
- ノートブック旧版（`diarization_compare.ipynb` cell `ce0696f2`）:
  `"えーと、あのー、まあ、なんか。フィラーや言い淀みも省略せず書き起こす。"`

ノートブック自身がすでに示していた通り（プロンプト文言だけでfillers 1→33に変動する実験）、この文言差が
出力の暴れ幅に直結していた。

## 検証（再現実験）

同一音声（`InputData/TestInterview.mp4` → ffmpeg `-ac 1 -ar 16000 -vn` でWAV化）に対し、backend本番と完全に同じ
プロンプト文字列・パラメータ（`model=whisper-1, language=ja, temperature=0, response_format=verbose_json,
timestamp_granularities=["segment"]`）で3回連続呼び出した。

```
run 1: fillers=28, chars=1439
run 2: fillers=28, chars=1439
run 3: fillers=28, chars=1439
```

3回とも**完全に同一の出力**（全文一致）。つまり：

- **whisper-1 は `temperature=0` でこの音声に対して決定論的**（呼び出し間のランダム性は無い）。
- 本番の「あの」多発・相槌混入は、ハルシネーションでも非決定性でもなく、**verbatimプロンプトの文言が誘発する再現可能な挙動**。
- ノートブックは本番と違うプロンプト文字列でテストしていたため、本番の実際の挙動を正しく評価できていなかった。

## 結論 / 次のアクション

- [ ] `diarization_compare.ipynb` の `VERBATIM_PROMPT` を backend の `_VERBATIM_PROMPT`
      （`transcription.py` から import、または文字列を完全一致させる）に揃えて、本番を正しく再現した状態で
      モデル評価（フィラー検出・話者分離との組み合わせ）をやり直す。
- プロンプト文言のわずかな違いがfillers検出数を1→28まで動かす、という事実は ADR 004 のverbatim方針の脆さを示す。
  `#21` のdisfluency検出器再設計を急ぐ理由がここでも補強された。
- 相槌（「うん」「へー」等）の混入自体は今回は許容方針（応募者発話の純度より優先度を下げる）。

## 追記: フィラー検出器をパターンマッチ→ハイブリッド（形態素解析併用）に書き換え（同日）

上記で本番を正しく再現できたテキストを使い、`diarization_compare.ipynb` 末尾に
パターンマッチ / 形態素解析のみ / ハイブリッドの精度比較セルを追加（API再呼び出しなし）。

実測（本番再現テキスト、29件のあの/その）:
- A. パターンマッチ（既存）: 29件
- B. 形態素解析のみ（fugashi+unidic-lite, POS=感動詞-フィラー）: **0件**（再現率0%。
  unidic-lite は短い「あの/その」をほぼ全て連体詞＝真の指示詞用法と判定し、フィラーPOSが付くのは
  「あのー」等の伸ばし形のみ。単独導入は不可）。
- C. ハイブリッド（B + 連体詞「あの/その」の直後トークン判定。読点/文末ならフィラー、名詞が続けば除外）: 28件。
  Aと同等の再現率を保ったまま、「その中でも結構その、えっと…」の**真の連体詞「その」を正しく除外**できた。

この結果を `backend/src/services/transcription.py` の `find_fillers` に反映:
- パターンマッチを土台に維持し、「あの/その」のみ形態素解析の文脈判定（`_ambiguous_determiner_spans`）で
  誤検出を除外するハイブリッド方式に変更。まあ/なんか/えーと等は曖昧性が低く、unidic-liteのPOSタグも
  不安定（「なんか」は代名詞+助詞に分割、「えっと」は文脈次第でフィラーPOS/分割タグが揺れる）なため
  対象外（パターンマッチのみ）。
- `FILLER_PATTERNS` に欠けていた `"えっと"` を追加（本番テキストに2箇所登場していたが旧実装では検出不可だった既知ギャップ）。
- 依存追加: `backend/pyproject.toml` の `audio` extra に `fugashi` / `unidic-lite`（軽量・モデル同梱）。
- 本番再現テキストで新実装を実行 → 30件検出（あの27・えっと2[新規]・その1[27→1減=誤検出除外]）、
  既存テスト40件 (`uv run pytest`) は全てパス。

残課題: 「えっと」は形態素解析の分割が不安定（文脈により1トークン or 2トークンに割れる）なため、
パターンマッチのみで担保している。形態素解析だけで完結する設計には未到達 — ハイブリッドの土台は
依然パターンマッチであることを明記しておく。

### 追記2: 単体テスト追加時に判明した unidic-lite の POSタグの揺れ

`test_find_fillers_excludes_true_determiner_usage`（「あの人に会った」が誤検出されないことを確認するテスト）を
追加した際、最初の実装（`連体詞`タグの時だけ次トークンを見る）が落ちた。原因は **unidic-lite が「あの人」の
「あの」を `連体詞` ではなく `感動詞-フィラー` に品詞付けすることがある**ため（文頭という位置だけで統計的に
揺れる・決定的ではない）。

→ 判定基準を「品詞タグが何か」ではなく「直後トークンが補助記号(読点)か文末か」のみに一本化（`_ambiguous_determiner_spans`）。
POSタグはトークン境界を得るためだけに使い、フィラー/連体詞の判定そのものには使わない。テスト4件（既存1+新規3）で
固定化済み（`backend/tests/test_services.py`）。
unidic-lite の品詞タグは曖昧語の用法判定には単独で頼れない、という前項の知見をさらに補強する結果。
