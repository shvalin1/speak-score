"""話者分離（Gladia API・B方式）と話者帰属。

B方式: Gladia で話者ターン境界 turns:[(start,end,speaker)] を得て、Whisper の word/segment に
最大時間重なりで話者を充填する。面接=面接官＋応募者の2人固定（min=max=2）。

設計（docs/plans/005 §2/§7/§12/§13）:
  - レート制限 429/5xx は即縮退せず **指数バックオフ＋ジッター**でリトライしてから諦める
    （スケール時に正常リクエストが一斉に「偽の単一話者」になるのを防ぐ）。
  - word 粒度で話者境界に分割してから帰属し、segment 丸帰属（末尾境界の面接官混入）を緩和する。
    word が無い場合は segment 丸帰属にフォールバック。
  - Gladia 障害/キー未設定/話者1名時は呼び出し側で diarization をスキップ（単一話者に縮退）。
  - キー名は正規 `GLADIA_API_KEY` のみ（実験コードの typo 互換は持ち込まない・§12.10）。

実験出典: experiments/evaluation/_compare_all.py の gladia()/assign_speakers()。
PII: 面接音声を Gladia(仏) へ送る。デモ前提で許容（本番化時に ZDR/法務・§7/§13(B)）。
"""

from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass

import httpx

from ..schemas.interview import TranscriptSegment
from .transcription import Word

log = logging.getLogger(__name__)

_UPLOAD_URL = "https://api.gladia.io/v2/upload"
_PRERECORDED_URL = "https://api.gladia.io/v2/pre-recorded"
_MODEL = "solaria-1"

_MAX_POLLS = 150          # ×_POLL_INTERVAL = 最大 ~300s（実測 17–32s）
_POLL_INTERVAL = 2.0
_HTTP_TIMEOUT = 60.0
_UPLOAD_TIMEOUT = 180.0

# 指数バックオフ（429/5xx/タイムアウト用）。
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_BACKOFF_RETRIES = 5
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 30.0
_BACKOFF_JITTER = 0.5


class GladiaError(RuntimeError):
    """Gladia 呼び出しの回復不能な失敗（呼び出し側は diarization をスキップして縮退する）。"""


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


def _sleep_backoff(attempt: int) -> None:
    delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP) + random.uniform(0, _BACKOFF_JITTER)
    time.sleep(delay)


def _request_with_backoff(
    client: httpx.Client, method: str, url: str, **kwargs
) -> httpx.Response:
    """429/5xx/タイムアウトは指数バックオフでリトライ。その他 4xx は即送出。"""
    last: Exception | None = None
    for attempt in range(_MAX_BACKOFF_RETRIES):
        try:
            resp = client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            log.warning("Gladia %s 一時的失敗（attempt=%d）: %s", method, attempt + 1, e)
        else:
            if resp.status_code in _TRANSIENT_STATUS:
                last = GladiaError(f"transient HTTP {resp.status_code}")
                log.warning(
                    "Gladia %s %d（attempt=%d）→ backoff", method, resp.status_code, attempt + 1
                )
            else:
                resp.raise_for_status()  # 恒久 4xx は HTTPStatusError で送出（縮退に倒す）
                return resp
        _sleep_backoff(attempt)
    raise GladiaError(f"Gladia request failed after {_MAX_BACKOFF_RETRIES} retries: {last}")


def _parse_turns(result: dict) -> list[SpeakerTurn]:
    tr = result.get("result", {}).get("transcription", {})
    turns = [
        SpeakerTurn(start=float(u["start"]), end=float(u["end"]), speaker=str(u.get("speaker", 0)))
        for u in tr.get("utterances", [])
    ]
    turns.sort(key=lambda t: t.start)
    return turns


def diarize_gladia(
    wav_path: str, key: str, *, client: httpx.Client | None = None
) -> list[SpeakerTurn]:
    """Gladia に WAV を渡し話者ターンを得る（2人固定）。失敗時は GladiaError。"""
    headers = {"x-gladia-key": key}
    own_client = client is None
    client = client or httpx.Client(timeout=_HTTP_TIMEOUT)
    try:
        with open(wav_path, "rb") as f:
            up = _request_with_backoff(
                client, "POST", _UPLOAD_URL, headers=headers,
                files={"audio": (wav_path.rsplit("/", 1)[-1], f, "audio/wav")},
                timeout=_UPLOAD_TIMEOUT,
            ).json()

        body = {
            "audio_url": up["audio_url"],
            "model": _MODEL,
            "language_config": {"languages": ["ja"]},
            "diarization": True,
            "diarization_config": {"min_speakers": 2, "max_speakers": 2},  # 面接=2人固定
        }
        job = _request_with_backoff(
            client, "POST", _PRERECORDED_URL, headers=headers, json=body
        ).json()
        result_url = job.get("result_url") or f"{_PRERECORDED_URL}/{job['id']}"

        for _ in range(_MAX_POLLS):
            r = _request_with_backoff(client, "GET", result_url, headers=headers).json()
            status = r.get("status")
            if status == "done":
                return _parse_turns(r)
            if status == "error":
                raise GladiaError(f"Gladia ジョブがエラー終了: {r.get('error') or r.get('status')}")
            time.sleep(_POLL_INTERVAL)
        raise GladiaError(f"Gladia ジョブがタイムアウト（{_MAX_POLLS} polls 経過）")
    finally:
        if own_client:
            client.close()


def n_speakers(turns: list[SpeakerTurn]) -> int:
    return len({t.speaker for t in turns})


def _max_overlap_speaker(start: float, end: float, turns: list[SpeakerTurn]) -> str | None:
    tally: dict[str, float] = defaultdict(float)
    for t in turns:
        ov = max(0.0, min(end, t.end) - max(start, t.start))
        if ov > 0:
            tally[t.speaker] += ov
    return max(tally, key=tally.get) if tally else None


def _attribute_by_words(words: list[Word], turns: list[SpeakerTurn]) -> list[TranscriptSegment]:
    """各 word を最大重なりで話者帰属し、連続同一話者を結合して segment 化する。

    segment 丸帰属では末尾境界で面接官発話が応募者に混入するため、word 境界で分割する（§12.3）。
    """
    out: list[TranscriptSegment] = []
    for w in words:
        spk = _max_overlap_speaker(w.start, w.end, turns)
        if out and out[-1].speaker == spk:
            last = out[-1]
            out[-1] = TranscriptSegment(
                start=last.start, end=w.end, text=last.text + w.text, speaker=spk
            )
        else:
            out.append(TranscriptSegment(start=w.start, end=w.end, text=w.text, speaker=spk))
    return out


def _attribute_by_segments(
    segments: list[TranscriptSegment], turns: list[SpeakerTurn]
) -> list[TranscriptSegment]:
    """word 粒度が無いときのフォールバック（segment 丸帰属・実験 assign_speakers 相当）。"""
    return [
        TranscriptSegment(
            start=s.start, end=s.end, text=s.text,
            speaker=_max_overlap_speaker(s.start, s.end, turns),
        )
        for s in segments
    ]


def attribute_speakers(
    segments: list[TranscriptSegment],
    words: list[Word],
    turns: list[SpeakerTurn],
) -> list[TranscriptSegment]:
    """Whisper の segment/word に Gladia の話者ターンを帰属する。

    turns 空（diarization スキップ）なら speaker=None のまま返す。
    word があれば word 境界分割、無ければ segment 丸帰属。
    """
    if not turns:
        return segments
    if words:
        return _attribute_by_words(words, turns)
    return _attribute_by_segments(segments, turns)
