"""Step2 実サービスのユニットテスト（OpenAI 非依存・librosa は合成音声で実行）。

network を踏むのは Whisper/gpt-4o の HTTP 呼び出しのみ。ここではそれをモックし、
純ロジック（フィラー検出・話速/無音などの librosa 算出・LLM 出力のパース/リトライ）を固定する。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from src.core.errors import FatalError, RecoverableError
from src.schemas.interview import (
    AudioMetrics,
    TimePoint,
    Transcript,
    TranscriptSegment,
)
from src.services import (
    applicant_id,
    audio_analysis,
    diarization,
    llm_evaluation,
    qa_formatting,
    transcription,
)
from src.services.diarization import SpeakerTurn
from src.services.transcription import Word


def test_find_fillers_longest_match_no_overlap() -> None:
    # 「えーと」は「えー」+「と」に二重計上せず、最長一致で1件になる
    hits = transcription.find_fillers("えーと、あのこれは、なんか難しい。")
    texts = [h.text for h in hits]
    assert "えーと" in texts
    assert texts.count("えー") == 0  # 「えーと」に飲み込まれる
    # オフセットは full_text の実位置
    for h in hits:
        assert "えーと、あのこれは、なんか難しい。"[h.start_char:h.end_char] == h.text


def test_find_fillers_excludes_true_determiner_usage() -> None:
    # 「あの人」「その中で」は真の連体詞用法（直後に名詞）なのでフィラーとして誤検出しない
    hits = transcription.find_fillers("あの人に会った。その中でも結構大きい。")
    texts = [h.text for h in hits]
    assert "あの" not in texts
    assert "その" not in texts


def test_find_fillers_keeps_filler_usage_of_ano_sono() -> None:
    # 直後が読点・文末の「あの/その」はフィラーとして検出する
    hits = transcription.find_fillers("あの、それでですね。その、つまり。")
    texts = [h.text for h in hits]
    assert texts.count("あの") == 1
    assert texts.count("その") == 1


def test_find_fillers_detects_etto() -> None:
    # 旧パターンリストに無かった「えっと」を検出できる
    hits = transcription.find_fillers("えっと、それは難しいですね。")
    texts = [h.text for h in hits]
    assert "えっと" in texts


def _write_wav(path: str, seconds: float = 6.0, sr: int = 16000) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    voiced = 0.25 * np.sin(2 * np.pi * 130 * t)
    env = np.zeros_like(t)
    for s, e in [(0.3, 2.5), (3.2, 5.5)]:  # 2 フレーズ + 間の無音
        env[(t >= s) & (t < e)] = 1.0
    sf.write(path, (voiced * env).astype(np.float32), sr)


def test_audio_analysis_real_metrics(tmp_path) -> None:
    wav = str(tmp_path / "s.wav")
    _write_wav(wav)
    transcript = Transcript(
        full_text="これはテストの発話です。" * 10, duration_sec=6.0, segments=[], fillers=[]
    )

    m = audio_analysis.analyze_audio(wav, transcript)

    assert isinstance(m, AudioMetrics)
    assert m.speech_rate_cpm > 0          # 文字数/発話秒 から算出される
    assert 0.0 <= m.silence_ratio <= 1.0
    assert m.silence_segments              # 無音区間が検出される
    assert m.pitch_mean > 0
    assert m.volume_timeline and m.pitch_timeline  # timeline がサンプリングされる


def _valid_llm_json() -> str:
    return json.dumps({
        "content": {"score": 150, "comment": "良い"},   # 範囲外 → clamp 確認
        "structure": {"score": 60, "comment": "普通"},
        "strengths": ["具体例"],
        "improvements": ["結論先出し"],
    })


def test_llm_evaluation_parses_and_clamps(monkeypatch) -> None:
    monkeypatch.setattr(llm_evaluation, "_call_llm", lambda _p: _valid_llm_json())
    t = Transcript(full_text="本日はよろしくお願いします。", duration_sec=5.0, segments=[], fillers=[])  # noqa: E501
    m = AudioMetrics(
        speech_rate_cpm=300.0, filler_count=0, filler_rate=0.0, silence_ratio=0.1,
        silence_segments=[], pitch_mean=140.0, pitch_std=25.0, volume_mean=0.05,
        volume_cv=0.4, volume_timeline=[], pitch_timeline=[],
    )

    result = asyncio.run(llm_evaluation.evaluate(t, m))

    assert result.content.score == 100  # 150 → 0-100 に丸め
    assert result.structure.score == 60
    assert result.strengths == ["具体例"]


def test_llm_evaluation_retries_then_recoverable(monkeypatch) -> None:
    calls = {"n": 0}

    def bad(_p: str) -> str:
        calls["n"] += 1
        return "not json{"

    monkeypatch.setattr(llm_evaluation, "_call_llm", bad)
    t = Transcript(full_text="x", duration_sec=1.0, segments=[], fillers=[])
    m = AudioMetrics(
        speech_rate_cpm=0.0, filler_count=0, filler_rate=0.0, silence_ratio=0.0,
        silence_segments=[], pitch_mean=0.0, pitch_std=0.0, volume_mean=0.0,
        volume_cv=0.0, volume_timeline=[], pitch_timeline=[],
    )

    with pytest.raises(RecoverableError):
        asyncio.run(llm_evaluation.evaluate(t, m))
    assert calls["n"] == 2  # 初回 + 1リトライ


def test_llm_evaluation_refusal_is_fatal_not_retried(monkeypatch) -> None:
    # refusal/空content は FatalError（恒久）→ リトライせず即送出
    calls = {"n": 0}

    def refuse(_p: str) -> str:
        calls["n"] += 1
        raise FatalError("LLM が評価を拒否")

    monkeypatch.setattr(llm_evaluation, "_call_llm", refuse)
    t = Transcript(full_text="x", duration_sec=1.0, segments=[], fillers=[])
    m = AudioMetrics(
        speech_rate_cpm=0.0, filler_count=0, filler_rate=0.0, silence_ratio=0.0,
        silence_segments=[], pitch_mean=0.0, pitch_std=0.0, volume_mean=0.0,
        volume_cv=0.0, volume_timeline=[], pitch_timeline=[],
    )

    with pytest.raises(FatalError):
        asyncio.run(llm_evaluation.evaluate(t, m))
    assert calls["n"] == 1  # リトライされない


# --- qa_formatting（議事録④ + 設問別問答⑤）------------------------------------

def _metrics_with_pitch(pitch_timeline: list[TimePoint]) -> AudioMetrics:
    return AudioMetrics(
        speech_rate_cpm=0.0, filler_count=0, filler_rate=0.0, silence_ratio=0.0,
        silence_segments=[], pitch_mean=0.0, pitch_std=0.0, volume_mean=0.0,
        volume_cv=0.0, volume_timeline=[], pitch_timeline=pitch_timeline,
    )


def _valid_qa_json() -> str:
    return json.dumps({
        "minutes": {
            "summary": "山田さんの自己紹介と志望動機。",
            "topics": ["自己紹介", "志望動機"],
            "key_points": ["具体例あり"],
        },
        "qa_segments": [{
            "question": "自己紹介をお願いします。",
            "answer": "えっと、私は山田です。",   # フィラー「えっと」を含む
            "start": 0.0,
            "end": 4.0,
            "score": 120,                          # 範囲外 → clamp 確認
            "comment": "具体性あり",
            "intent": "self_intro",
            "is_reverse_question": False,
            "question_inferred": False,
        }],
    })


def test_qa_formatting_parses_and_attaches_audio(monkeypatch) -> None:
    monkeypatch.setattr(qa_formatting, "_call_llm", lambda _p: _valid_qa_json())
    # [0,4] 内のピッチ点だけ集計され、t=10 は除外される
    pitch = [TimePoint(t=1.0, value=120.0), TimePoint(t=2.0, value=140.0),
             TimePoint(t=10.0, value=200.0)]
    segs = [
        TranscriptSegment(start=0.0, end=4.0, text="自己紹介をお願いします。", speaker="0"),
        TranscriptSegment(start=4.0, end=8.0, text="えっと、私は山田です。", speaker="1"),
    ]

    out = asyncio.run(qa_formatting.format_qa(segs, _metrics_with_pitch(pitch), "1"))

    assert out.minutes.summary.startswith("山田さん")
    assert out.minutes.topics == ["自己紹介", "志望動機"]
    assert len(out.qa_segments) == 1
    qa = out.qa_segments[0]
    assert qa.index == 0
    assert qa.score == 100                # 120 → clamp
    assert qa.intent.value == "self_intro"
    # QaAudio は LLM ではなく決定論で後付けされる
    assert qa.audio is not None
    assert qa.audio.pitch_mean == 130.0   # (120+140)/2、t=10 は区間外で除外
    assert qa.audio.filler_count == 1     # 「えっと」を answer から検出


def test_qa_formatting_preprocess_merges_and_drops_backchannel() -> None:
    segs = [
        TranscriptSegment(start=0.0, end=5.0, text="長い回答前半", speaker="1"),
        TranscriptSegment(start=5.0, end=5.4, text="はい", speaker="0"),  # 0.4s 相槌
        TranscriptSegment(start=5.4, end=10.0, text="長い回答後半", speaker="1"),
    ]

    out = qa_formatting._preprocess_segments(segs)

    # 相槌が落ち、前後の同一話者が結合されて1セグメントになる
    assert len(out) == 1
    assert out[0].speaker == "1"
    assert out[0].start == 0.0 and out[0].end == 10.0
    assert out[0].text == "長い回答前半 長い回答後半"


def test_qa_formatting_retries_then_recoverable(monkeypatch) -> None:
    calls = {"n": 0}

    def bad(_p: str) -> str:
        calls["n"] += 1
        return "not json{"

    monkeypatch.setattr(qa_formatting, "_call_llm", bad)
    segs = [TranscriptSegment(start=0.0, end=2.0, text="x", speaker="1")]

    with pytest.raises(RecoverableError):
        asyncio.run(qa_formatting.format_qa(segs, _metrics_with_pitch([]), "1"))
    assert calls["n"] == 2  # 初回 + 1リトライ


# --- diarization（話者帰属）---------------------------------------------------

def test_attribute_speakers_by_words_splits_at_boundary() -> None:
    # 1つの Whisper segment が話者境界をまたぐケース。word 粒度で分割・帰属される。
    words = [
        Word(start=0.0, end=1.0, text="質問"),
        Word(start=1.0, end=2.0, text="です"),
        Word(start=2.0, end=3.0, text="回答"),
        Word(start=3.0, end=4.0, text="します"),
    ]
    turns = [SpeakerTurn(0.0, 2.0, "0"), SpeakerTurn(2.0, 4.0, "1")]
    segs = [TranscriptSegment(start=0.0, end=4.0, text="質問です回答します")]

    out = diarization.attribute_speakers(segs, words, turns)

    assert [s.speaker for s in out] == ["0", "1"]
    assert out[0].text == "質問です" and out[1].text == "回答します"
    assert out[0].start == 0.0 and out[1].end == 4.0


def test_attribute_speakers_zero_duration_word_uses_nearest() -> None:
    # ゼロ長 word / turn 間ギャップの word は None で分断せず、最近傍話者に吸収される
    words = [
        Word(start=0.0, end=1.0, text="本題に"),
        Word(start=1.0, end=1.0, text="入"),       # ゼロ長 → 最近傍(speaker0)へ
        Word(start=1.0, end=2.0, text="る前に"),
    ]
    turns = [SpeakerTurn(0.0, 2.0, "0"), SpeakerTurn(2.0, 4.0, "1")]

    out = diarization.attribute_speakers([], words, turns)

    # 全 word が speaker0 に帰属し、1セグメントに結合される（None で分断しない）
    assert len(out) == 1
    assert out[0].speaker == "0"
    assert out[0].text == "本題に入る前に"


def test_attribute_speakers_segment_fallback_when_no_words() -> None:
    # word が無ければ segment 丸帰属（最大重なり）にフォールバックする
    turns = [SpeakerTurn(0.0, 1.0, "0"), SpeakerTurn(1.0, 5.0, "1")]
    segs = [TranscriptSegment(start=0.0, end=5.0, text="まるごと")]

    out = diarization.attribute_speakers(segs, [], turns)

    assert len(out) == 1
    assert out[0].speaker == "1"  # 重なりの大きい "1"


def test_attribute_speakers_no_turns_passthrough() -> None:
    # turns 空（diarization スキップ）なら speaker=None のまま素通り
    segs = [TranscriptSegment(start=0.0, end=2.0, text="x", speaker=None)]
    out = diarization.attribute_speakers(segs, [], [])
    assert out is segs and out[0].speaker is None


def test_diarize_gladia_mock_transport_with_429_retry(tmp_path, monkeypatch) -> None:
    # backoff/poll の sleep を潰してテストを速くする
    monkeypatch.setattr(diarization.time, "sleep", lambda _s: None)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    state = {"poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/upload"):
            return httpx.Response(200, json={"audio_url": "https://x/a.wav"})
        if url.endswith("/pre-recorded"):
            return httpx.Response(200, json={"id": "j1", "result_url": "https://api.gladia.io/v2/pre-recorded/j1"})  # noqa: E501
        state["poll"] += 1
        if state["poll"] == 1:
            return httpx.Response(429)  # 一時的 → backoff リトライ
        if state["poll"] == 2:
            return httpx.Response(200, json={"status": "processing"})
        done = {"status": "done", "result": {"transcription": {"utterances": [
            {"start": 0.0, "end": 2.0, "speaker": 0, "text": "q"},
            {"start": 2.0, "end": 5.0, "speaker": 1, "text": "a"},
        ]}}}
        return httpx.Response(200, json=done)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    turns = diarization.diarize_gladia(str(wav), "key", client=client)

    assert diarization.n_speakers(turns) == 2
    assert [(t.start, t.end, t.speaker) for t in turns] == [(0.0, 2.0, "0"), (2.0, 5.0, "1")]


# --- applicant_id（LLM#0・応募者判定）-----------------------------------------

def _two_speaker_segs() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=3.0, text="自己紹介をお願いします？", speaker="0"),
        TranscriptSegment(start=3.0, end=10.0, text="はい、私は山田と申します。", speaker="1"),
    ]


def test_identify_applicant_single_speaker_degrades(monkeypatch) -> None:
    # 話者1名 → LLM を呼ばず縮退
    called = {"n": 0}
    monkeypatch.setattr(applicant_id, "_call_llm", lambda *_a: called.__setitem__("n", 1))
    segs = [TranscriptSegment(start=0.0, end=5.0, text="x", speaker="0")]

    r = applicant_id.identify_applicant(segs)

    assert r.speaker is None and r.degraded is True
    assert called["n"] == 0  # LLM 未呼び出し


def test_identify_applicant_llm_success(monkeypatch) -> None:
    monkeypatch.setattr(
        applicant_id, "_call_llm",
        lambda *_a: json.dumps({"applicant_speaker": "1", "confidence": 0.9, "reason": "自己紹介"}),
    )
    r = applicant_id.identify_applicant(_two_speaker_segs())
    assert r.speaker == "1" and r.degraded is False


def test_identify_applicant_low_confidence_degrades(monkeypatch) -> None:
    monkeypatch.setattr(
        applicant_id, "_call_llm",
        lambda *_a: json.dumps({"applicant_speaker": "1", "confidence": 0.3, "reason": "曖昧"}),
    )
    r = applicant_id.identify_applicant(_two_speaker_segs())
    assert r.speaker == "1" and r.degraded is True  # 推定は返すが degraded


def test_identify_applicant_llm_failure_degrades(monkeypatch) -> None:
    def boom(*_a):
        raise ValueError("LLM down")

    monkeypatch.setattr(applicant_id, "_call_llm", boom)
    r = applicant_id.identify_applicant(_two_speaker_segs())
    assert r.speaker is None and r.degraded is True  # 例外を上げずに縮退


# --- llm_evaluation: 応募者発話の選別と degraded 注記（Phase3）-------------------

def test_select_applicant_text_uses_applicant_only() -> None:
    segs = [
        TranscriptSegment(start=0.0, end=2.0, text="質問です", speaker="0"),
        TranscriptSegment(start=2.0, end=8.0, text="応募者の回答", speaker="1"),
    ]
    text, degraded = llm_evaluation.select_applicant_text(segs, "1", applicant_degraded=False)
    assert text == "応募者の回答" and degraded is False


def test_select_applicant_text_soft_prior_when_unknown() -> None:
    # 未確定だが2話者 → 最長発話(speaker1)を soft prior、degraded True
    segs = [
        TranscriptSegment(start=0.0, end=2.0, text="短い", speaker="0"),
        TranscriptSegment(start=2.0, end=10.0, text="長い回答", speaker="1"),
    ]
    text, degraded = llm_evaluation.select_applicant_text(segs, None, applicant_degraded=True)
    assert text == "長い回答" and degraded is True


def test_select_applicant_text_no_diarization_returns_full_text() -> None:
    # 話者分離なし（<2話者）→ None（全文で評価）・degraded False
    segs = [TranscriptSegment(start=0.0, end=5.0, text="全文", speaker=None)]
    text, degraded = llm_evaluation.select_applicant_text(segs, None, applicant_degraded=True)
    assert text is None and degraded is False


def test_llm_evaluation_degraded_appends_note(monkeypatch) -> None:
    monkeypatch.setattr(llm_evaluation, "_call_llm", lambda _p: _valid_llm_json())
    t = Transcript(full_text="x", duration_sec=1.0, segments=[], fillers=[])
    m = AudioMetrics(
        speech_rate_cpm=300.0, filler_count=0, filler_rate=0.0, silence_ratio=0.1,
        silence_segments=[], pitch_mean=140.0, pitch_std=25.0, volume_mean=0.05,
        volume_cv=0.4, volume_timeline=[], pitch_timeline=[],
    )

    result = asyncio.run(
        llm_evaluation.evaluate(t, m, applicant_text="応募者のみ", degraded=True)
    )

    assert "話者特定が不確実" in result.content.comment
    assert "話者特定が不確実" in result.structure.comment
