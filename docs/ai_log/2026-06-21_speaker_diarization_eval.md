# 2026-06-21 話者分離（diarization）手法比較とSTT組み合わせ評価

担当: @hiroki428（加藤） / 関連: epic [#22](https://github.com/shvalin1/speak-score/issues/22)・子 [#21](https://github.com/shvalin1/speak-score/issues/21) /
[ADR 004](../adr/004_verbatim_transcription_and_disfluency.md)・[ADR 005](../adr/005_evaluation_layer_ownership.md) /
対象ノートブック: [experiments/evaluation/diarization_compare.ipynb](../../experiments/evaluation/diarization_compare.ipynb)

## 依頼内容

評価品質レイヤ（Step2）の前段として、面接動画から「応募者の発話だけ」を取り出すための話者分離手法を比較。
石川の実面接動画（2話者・面接官Q&A、218秒）を `InputData/` に入れて `diarization_compare.ipynb` を実走し、採用候補を見極める。
※ 入力音声は PII のためコミット禁止。

## やったこと

1. **実面接サンプルでノートブックを実走**し、3候補（A: Gladia / B: sherpa-onnx / C: VADのみ）の出力を確認。
2. **Gladia「うん」連発の再現性を検証**（`_gladia_recheck.py`、2回実行）。
3. **sherpa の CPU時間・ピークメモリを実測**（`_sherpa_bench.py`、スレッド数 × num_clusters）。
4. **話者分離 × STT を組み替えた4方式のフェア比較**（`_compare_all.py`）を実施し、
   「応募者テキストへの面接官混入」「固有語STT精度」「フィラー保持」で評価。
5. 検証コードと実測結果を **ノートブックに追記**（cell-14 直後に解説/コード/結果の3セル＋サマリ cell-15 を更新）。

## 主要な発見（石川面接サンプルでの実測）

| 方式 | speakers | 応募者chars | fillers | 面接官の混入 | 固有語STT | 速度 |
|---|---|---|---|---|---|---|
| Whisper全文(基準) | — | — | 1 (`その`) | — | ◎ | 〜15s |
| A. Gladia STT置換 | 2 | 923 | **3** (`あの`×2,`その`) | ⚠️冒頭に混入 | △ `サーマー`/`PTM` | 〜17s |
| B. Gladia分離+Whisper | 2 | 984 | 1 | ⚠️末尾に混入 | ◎ | 〜32s |
| C. sherpa(num=2)+Whisper | 2 | 915 | 1 | ✅なし | ◎ | 〜56s |
| D. sherpa(auto)+Whisper | 6 | 915 | 1 | ✅なし | ◎ | 〜56s |

- **応募者の切り出しは C（sherpa num=2）が最良**。Gladia は話者数2は当てるが境界の帰属が甘く、面接官発話が混入する（A=冒頭、B=末尾）。
- **diarization は「境界検知(segmentation)」と「同一話者帰属(clustering)」の2軸**。sherpa は segmentation が正確で、auto時の過分割(6話者)は clustering 段の問題に過ぎず、**抽出品質には無害**（C と D は応募者テキストが完全一致）。`num_clusters=2`（面接=2人既知）は保険。
- **Gladia「うん」連発は一過性エラーではなく決定論的に再現**（2回同一）。末尾の長尺セグメントを1発話に丸めたSTTハルシネーション。後処理（短い反復ループの除去）で対処は可能。
- **ハイブリッド B は両者の悪いとこ取り**（Gladiaのキー/課金を払いつつ境界混入を引き継ぎ、filler は Whisper の1に戻る）→ 候補から除外。
- **sherpa のリソース実測**: GPU不要（ONNX Runtime CPU）。2スレッドで RTF 0.19（218s音声→約41s）、ピークRSS 約460MB、モデル計40MB弱 → **Cloud Run CPU 2GiB に余裕で収まる**。
- **filler 指標は現状ほぼ機能していない**。3.5分の自発発話で 1〜3 は実態と乖離。原因は (1) `whisper-1` が言い淀みを正規化で除去、(2) 検出器が9パターン部分一致のみで伸ばし/言い直し/`うん`/`えっと` 非対応。**話者分離の選択では filler は動かず、#21 の本丸は STT 強化＋検出器再設計**。

## 決まったこと / ペンディング

- **候補は実質 A（Gladia全部）vs C（sherpa num=2 + Whisper）の二択**に絞られた。
  - 評価の純度・運用の軽さ（CPU/2GiB完結・外部依存ゼロ）重視 → **C**。
  - filler信号＋速度重視で課金許容 → A（ただし境界混入・固有語誤り・幻聴後処理が宿題）。
- **Gladia採用可否（新規外部依存＋課金＋本番シークレット管理）は石川(infra)判断**。`.env` の既存キーは実験用としては有効。
- **#21 の主戦場は STT（verbatim強化・gpt-4o-transcribe検討）と disfluency 検出器**であることが明確化。

## 追補：フィラー検出は Whisper の prompt 次第（1 → 33）／結論が C に固まる

- main の `backend/src/services/transcription.py` は**まだダミー**（Whisper未実装）。「20〜30個検出」はスパイク `transcribe.py` 由来。
- 同一音声・同一 `find_fillers` で **Whisper の prompt 内容だけ**で個数が激変（実測）:
  - prompt無し（transcribe.py既定）= **1** / verbatim指示文（NB現状）= **1** / フィラー語の羅列プロンプト = **33**（`あの`×30,`その`×3）。
  - 「省略せず書き起こす」指示は効かず、**フィラー語を列挙したプロンプトがWhisperをフィラー保持モードにする**（スタイルプライミング）。
- 帰結: **filler 信号は STT のプロンプト設計が本体**で、話者分離の選択では動かない。`whisper-1`＋フィラー語プロンプトは 33個 ≫ Gladia 3個。
- → **Gladia を選ぶ最後の理由（filler保持）が消滅**。純度・固有語精度・所有境界に加え filler でも Whisper+sherpa が優位。**推奨は C（Whisper + sherpa num=2）に確定的**（Gladia が勝るのは速度のみ）。
- 注意: フィラー語羅列プロンプトは過剰プライミングで実発話以上に拾う恐れあり。保持率の妥当性検証は #21 の課題。

## 次アクション候補

- #22 に結論（**C 採用、Gladia は速度のみ優位で不採用方向**）と #21（Whisperプロンプト設計＋検出器再設計）の論点を起票。
- `experiments/evaluation/.gitignore` に `_*.py` / `_diar_tmp.wav` / `InputData/` を追加（PII・一時物の混入防止）。
- 検証用スクリプト（`_gladia_recheck.py` / `_sherpa_bench.py` / `_compare_all.py` / `_whisper_prompt_test.py`）は一時物。残すなら gitignore 配下、不要なら削除。

## 生成物

- `diarization_compare.ipynb`: 4方式比較＋話者ラベル付き突き合わせ＋prompt→filler検証＋サマリを追記。
- 一時検証スクリプト（コミット非対象）: `_gladia_recheck.py` / `_sherpa_bench.py` / `_compare_all.py` / `_whisper_prompt_test.py`。
