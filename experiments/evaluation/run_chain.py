"""フルチェーン実行＋結果をタイムスタンプ付きファイルに書き出す（src には入れない）。

m4a/mp4 等 → wav(mono16k) 変換 → Whisper文字起こし → librosaメトリクス → gpt-4o評価 を一気通貫。
プロンプト/スキーマ/メトリクス処理は既存スパイク(llm_eval/audio_metrics/transcribe)を再利用。

出力: _ai/spike/out/YYYYMMDD_HHMMSS_<stem>.json（機械可読）と .md（目視用）

使い方:
  uv run python _ai/spike/run_chain.py --audio _ai/spike/kato_test.m4a
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import audio_metrics as A  # noqa: E402
import llm_eval as L  # noqa: E402
import transcribe as T  # noqa: E402


def to_wav(src: str, sr: int = 16000) -> str:
    """ffmpeg で wav mono16k に変換（本番 Phase 1 の抽出相当）。"""
    out = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", str(sr), "-vn", out],
        check=True,
        capture_output=True,
    )
    return out


def transcribe_openai(client, audio_path: str, model: str):
    kwargs = {"model": model, "file": Path(audio_path).open("rb"), "language": "ja"}
    if model == "whisper-1":
        kwargs["response_format"] = "verbose_json"
        kwargs["timestamp_granularities"] = ["segment"]
    return client.audio.transcriptions.create(**kwargs)


def render_md(r: dict) -> str:
    ev = r["evaluation"]
    m = r["metrics"]
    segs = "\n".join(
        f"- [{s['start']:.2f}-{s['end']:.2f}] nsp={s['no_speech_prob']:.2f}  {s['text']}"
        for s in r["transcript"]["segments"]
    )
    return f"""# スピーチ評価 実行結果

- 実行日時: {r["timestamp"]}
- 入力: `{r["audio"]}`
- 文字起こしモデル: {r["model"]} / 評価モデル: {L.MODEL}

## 文字起こし（{r["transcript"]["chars"]}字）

{r["transcript"]["full_text"]}

### セグメント
{segs}

### フィラー（{len(r["transcript"]["fillers"])}件）
{", ".join(h["text"] for h in r["transcript"]["fillers"]) or "(なし)"}

## 音声メトリクス（librosa, top_db={m["params"]["top_db"]}）

| 指標 | 値 |
|---|---|
| 総尺/発話秒 | {m["total_sec"]}s / {m["voiced_sec"]}s |
| 話速(cpm) | {m["speech_rate_cpm"]} |
| 無音率 | {m["silence_ratio"]} |
| ピッチ平均/標準偏差 | {m["pitch_mean"]} / {m["pitch_std"]} |
| 音量平均/CV | {m["volume_mean"]} / {m["volume_cv"]} |

## LLM 評価（gpt-4o structured outputs）

- **content {ev["content"]["score"]}**: {ev["content"]["comment"]}
- **structure {ev["structure"]["score"]}**: {ev["structure"]["comment"]}

**強み**
{chr(10).join("- " + s for s in ev["strengths"])}

**改善点**
{chr(10).join("- " + s for s in ev["improvements"])}

## トークン使用
prompt={r["usage"]["prompt"]} / completion={r["usage"]["completion"]} / total={r["usage"]["total"]}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--top-db", type=int, default=30)
    ap.add_argument("--model", default="whisper-1", help="whisper-1 / gpt-4o-transcribe")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        print(f"not found: {audio}", file=sys.stderr)
        return 1
    key = L.load_api_key()
    if not key:
        print("OPENAI_API_KEY 未設定（env か backend/.env）。", file=sys.stderr)
        return 1

    from openai import OpenAI

    client = OpenAI(api_key=key)

    print("[1/4] ffmpeg で wav(mono16k) 変換 ...", file=sys.stderr)
    wav = to_wav(str(audio))

    print("[2/4] Whisper 文字起こし ...", file=sys.stderr)
    tr = transcribe_openai(client, str(audio), args.model)
    full_text = tr.text
    segments = [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text,
            "no_speech_prob": float(getattr(s, "no_speech_prob", 0.0)),
        }
        for s in (getattr(tr, "segments", None) or [])
    ]
    fillers = T.find_fillers(full_text)
    chars = len(full_text)

    print("[3/4] librosa メトリクス ...", file=sys.stderr)
    metrics = A.analyze(wav, chars, args.top_db)

    print("[4/4] gpt-4o 評価 ...", file=sys.stderr)
    metrics_for_llm = {
        "speech_rate_cpm": metrics["speech_rate_cpm"],
        "filler_count": len(fillers),
        "silence_ratio": metrics["silence_ratio"],
        "pitch_mean": metrics["pitch_mean"],
        "pitch_std": metrics["pitch_std"],
        "volume_cv": metrics["volume_cv"],
    }
    user_prompt = L.build_user_prompt(full_text, metrics_for_llm)
    resp = client.chat.completions.create(
        model=L.MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": L.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": L.JSON_SCHEMA},
    )
    evaluation = json.loads(resp.choices[0].message.content)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "timestamp": ts,
        "audio": str(audio),
        "model": args.model,
        "transcript": {
            "full_text": full_text,
            "chars": chars,
            "segments": segments,
            "fillers": fillers,
        },
        "metrics": metrics,
        "metrics_sent_to_llm": metrics_for_llm,
        "evaluation": evaluation,
        "usage": {
            "prompt": resp.usage.prompt_tokens,
            "completion": resp.usage.completion_tokens,
            "total": resp.usage.total_tokens,
        },
    }

    outdir = HERE / "out"
    outdir.mkdir(exist_ok=True)
    base = outdir / f"{ts}_{audio.stem}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    md_path.write_text(render_md(result))

    print(f"\n[done] wrote:\n  {json_path}\n  {md_path}", file=sys.stderr)
    print(render_md(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
