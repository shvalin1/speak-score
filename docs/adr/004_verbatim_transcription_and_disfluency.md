# ADR 004 — verbatim 文字起こしと非流暢性(disfluency)の分離方針

- **状態**: 確定（2026-06-20）。disfluency 検出の**精度改善は加藤(@hiroki428)へ委譲**（[issue #21](https://github.com/shvalin1/speak-score/issues/21)）。
- **決定**:
  1. **評価は「音声直渡し」でなく Whisper 文字起こしテキストを LLM(gpt-4o) に渡す**。音声を gpt-4o に直接入れると
     フィラー/言い淀みを除いて理解しがちで、フィラー込みの話し方評価が制御できないため。テキスト経由なら delivery 採点を
     決定論（`services/scoring.py` ＋ librosa メトリクス）に分離できる（[ADR 003] と整合）。
  2. **文字起こしは verbatim（忠実）を source of truth にする**。Whisper は既定でフィラーを除去・正規化（補完）するため、
     **フィラー保持を誘導する prompt＋`temperature=0`** で取得する。
  3. **非流暢性は2層で扱う**: (a) 語彙的フィラー（えー/えーと/あのー/うーん 等）と (b) 繰り返し・言い直し
     （例「漁師、漁師、漁師なんとか」）。**暫定実装**は (a) を簡易検出してフィラー率を出すに留め、(a)/(b) の精緻な
     検出・分離・型別定量化は**加藤へ委譲**（下記）。
- **背景・実証（2026-06-20 スパイク）**:
  - 同一音声(kato_test.m4a)で、誘導なし文字起こし=フィラー0件／フィラー誘導 prompt あり=11件。「テキスト経由にする」だけでは
    保持目的を達成できず **prompt 誘導が必須**と判明。
  - 当初「誘導版は精度劣化」と誤認したが、話者は実際に言い淀んでおり、**誘導なし版こそ Whisper が言い淀みを内容語に
    書き換える補完/正規化を起こしていた**（verbatim が忠実）。
- **ガードレール（重要）**: disfluency 除去で `clean_text` を LLM に生成させる場合は **削除のみ（語の置換・追加は禁止）**。
  Whisper 補完（"漁師なんとか"→"シミュレーション"）も LLM の clean 生成（"量子シミュレーション"を捏造）も、いずれも
  **内容の捏造**になりうる。verbatim を真実とし、内容評価は「印の付いた言い淀みを内容点に響かせない」指示で行う。
- **委譲スコープ（加藤 / issue）**: disfluency 検出精度の改善。推奨は **決定論（形態素＋UniDic「感動詞-フィラー」: fugashi+unidic-lite
  or SudachiPy）でベースライン ＋ LLM で繰り返し/言い直し・機能語（その/あの/まあ/なんか）の曖昧性解消・型別抽出** の二段構え。
  BERT 系列ラベリングの自己ホストは保守コスト高で非推奨。
- **指標の注意**: 話速 CPM（文字/分）は漢字/かな比でブレる参考値。分母の頑健化（モーラ/文節等）は Phase 5 で要検討。
- **根拠/資産**: 実装計画 [docs/plans/002_step2_real_pipeline.md]、調査 `docs/research/step2_filler_annotation_research.md`、
  ディープリサーチ用プロンプト `docs/research/step2_disfluency_deepresearch_prompt.md`、実験台 `experiments/disfluency/`
  （`transcribe.py --prompt` / `audio_metrics.py` / `run_chain.py`）。

[ADR 003]: ./003_scoring_split.md
[docs/plans/002_step2_real_pipeline.md]: ../plans/002_step2_real_pipeline.md
