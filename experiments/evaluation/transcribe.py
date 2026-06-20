"""Whisper 文字起こしスパイク（Step2 transcription の試作・src には入れない）。

目的: 実音声を OpenAI で文字起こしし、タイムスタンプ付きセグメント・no_speech_prob・
フィラー検出をローカルで確認する。出力を llm_eval.py の --transcript-file に渡せば
「文字起こし→評価」のチェーンを手で回せる。

使い方:
  uv run python _ai/spike/transcribe.py --audio /path/to/speech.wav
  uv run python _ai/spike/transcribe.py --audio sample.m4a --out /tmp/transcript.txt
  # 続けて:
  uv run python _ai/spike/llm_eval.py --transcript-file /tmp/transcript.txt

メモ: タイムスタンプ付き segment と no_speech_prob は whisper-1 の verbose_json で取れる。
gpt-4o-transcribe は segment/no_speech_prob の粒度が異なるため、計画 Phase 4a の
「異常区間除去」を試すならまず whisper-1 で挙動を見る。対応フォーマット: mp3/mp4/m4a/wav/webm 等
（FLAC は非対応 → 本番は WAV mono16k）。サイズ上限 25MB。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 日本語フィラーの簡易パターン（Step2 で精緻化）
FILLER_PATTERNS = ["えーと", "えー", "あのー", "あの", "そのー", "その", "まあ", "なんか", "ええと"]


def load_api_key() -> str | None:
    import os

    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    env = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def find_fillers(text: str) -> list[dict]:
    hits = []
    for pat in FILLER_PATTERNS:
        start = 0
        while True:
            i = text.find(pat, start)
            if i == -1:
                break
            hits.append({"text": pat, "start_char": i, "end_char": i + len(pat)})
            start = i + len(pat)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="音声/動画パス（wav/m4a/mp3/mp4/webm、≤25MB）")
    ap.add_argument("--model", default="whisper-1", help="whisper-1（segment/no_speech_prob）/ gpt-4o-transcribe")
    ap.add_argument("--prompt", help="Whisper のスタイル誘導プロンプト（フィラー保持の検証用）")
    ap.add_argument("--out", help="full_text の書き出し先（llm_eval --transcript-file 用）")
    args = ap.parse_args()

    path = Path(args.audio)
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 1
    size_mb = path.stat().st_size / 1024 / 1024
    if size_mb > 25:
        print(f"[!] {size_mb:.1f}MB > 25MB 上限。WAV mono16k 等に縮小して再実行。", file=sys.stderr)
        return 1

    key = load_api_key()
    if not key:
        print("OPENAI_API_KEY 未設定（env か backend/.env）。", file=sys.stderr)
        return 1

    from openai import OpenAI

    client = OpenAI(api_key=key)
    print(f"[transcribe] model={args.model} size={size_mb:.2f}MB ...", file=sys.stderr)

    kwargs = {"model": args.model, "file": path.open("rb"), "language": "ja"}
    if args.prompt:
        kwargs["prompt"] = args.prompt
    if args.model == "whisper-1":
        kwargs["response_format"] = "verbose_json"
        kwargs["timestamp_granularities"] = ["segment"]
    resp = client.audio.transcriptions.create(**kwargs)

    full_text = resp.text
    print("\n----- FULL TEXT -----\n")
    print(full_text)

    segments = getattr(resp, "segments", None)
    if segments:
        print("\n----- SEGMENTS（start/end/no_speech_prob/text）-----\n")
        for s in segments:
            nsp = getattr(s, "no_speech_prob", None)
            flag = " ⚠no_speech" if (nsp is not None and nsp > 0.5) else ""
            print(f"[{s.start:6.2f}-{s.end:6.2f}] nsp={nsp:.2f}{flag}  {s.text}")

    fillers = find_fillers(full_text)
    print(f"\n----- FILLERS（{len(fillers)}件）-----\n")
    print(", ".join(f"{h['text']}@{h['start_char']}" for h in fillers) or "(なし)")
    print(f"\n[chars={len(full_text)}]")

    if args.out:
        Path(args.out).write_text(full_text)
        print(f"[out] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
