"""LLM評価スパイク（Step2 llm_evaluation の試作・src には入れない）。

目的: gpt-4o structured outputs で content/structure 採点＋strengths/improvements を
JSON 強制する「プロンプトとスキーマ」をローカルで詰める。プロンプト全文・スキーマを
表示し、OPENAI_API_KEY があれば実呼び出しして生レスポンス＋パース結果も見る。

使い方:
  # プロンプトとスキーマだけ確認（API 呼ばない）
  uv run python _ai/spike/llm_eval.py --dry-run

  # 実呼び出し（OPENAI_API_KEY を env か backend/.env に置く）
  uv run python _ai/spike/llm_eval.py
  uv run python _ai/spike/llm_eval.py --transcript-file /path/to/transcript.txt

設計メモ: 算出系(delivery/confidence)は scoring.py の決定論。ここは意味判断が要る
content/structure の2軸＋自由記述のみ。audio_metrics は文脈として渡す（話速やフィラー率を
コメントに反映させるため）が、点数化はさせない。temperature=0・strict schema。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MODEL = "gpt-4o-2024-08-06"

# --- サンプル入力（--transcript-file で上書き可） ---
SAMPLE_TRANSCRIPT = (
    "本日はよろしくお願いします。えー、私は前職で3年間、Webアプリの開発を担当していました。"
    "特に、あのー、決済基盤のリプレイスでは、チームのリーダーとして要件定義から関わりました。"
    "課題は、レガシーなコードで障害が多かったことです。そこで、まあ、段階的に移行する方針を立てて、"
    "テストを整備しながら進めました。結果として、障害件数を前年比で6割削減できました。"
    "御社では、この経験を活かして、品質と開発速度の両立に貢献したいと考えています。"
)

SAMPLE_METRICS = {
    "speech_rate_cpm": 340.0,
    "filler_count": 3,
    "filler_rate": 5.2,
    "silence_ratio": 0.18,
    "pitch_mean": 132.0,
    "pitch_std": 22.0,
    "volume_cv": 0.42,
}

SYSTEM_PROMPT = (
    "あなたは日本語の面接スピーチを評価する採点者です。応募者の回答（文字起こし）と"
    "音声メトリクスを読み、内容(content)と構成(structure)の2軸を0-100で採点します。\n"
    "- content: 主張の具体性・説得力・質問への適合。具体例や数値の有無を重視。\n"
    "- structure: 論理の流れ。PREP法(結論→理由→具体例→結論)の観点。結論が先か。\n"
    "話速・フィラー・抑揚などの delivery 面は別系統で採点するため、ここでは点数化しないこと"
    "（ただしコメントで言及してよい）。\n"
    "採点は甘すぎず辛すぎず、根拠を comment に1-2文で日本語で書く。"
    "strengths/improvements は各2-3個、実行可能な粒度で。必ず指定の JSON スキーマで返す。"
)

# strict structured outputs 用 JSON スキーマ
JSON_SCHEMA = {
    "name": "interview_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "content": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "score": {"type": "integer", "description": "0-100の整数"},
                    "comment": {"type": "string"},
                },
                "required": ["score", "comment"],
            },
            "structure": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "score": {"type": "integer", "description": "0-100の整数"},
                    "comment": {"type": "string"},
                },
                "required": ["score", "comment"],
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "improvements": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content", "structure", "strengths", "improvements"],
    },
}


def build_user_prompt(transcript: str, metrics: dict) -> str:
    return (
        "# 応募者の回答（文字起こし）\n"
        f"{transcript}\n\n"
        "# 音声メトリクス（参考・点数化しない）\n"
        f"{json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
        "上記を評価し、JSON スキーマに従って返してください。"
    )


def load_api_key() -> str | None:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    # backend/.env から拾う（gitignore 配下・簡易パース）
    env = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="API を呼ばずプロンプト/スキーマだけ表示")
    ap.add_argument("--transcript-file", help="文字起こしテキスト（未指定はサンプル）")
    args = ap.parse_args()

    transcript = SAMPLE_TRANSCRIPT
    if args.transcript_file:
        transcript = Path(args.transcript_file).read_text().strip()
    user_prompt = build_user_prompt(transcript, SAMPLE_METRICS)

    print("=" * 70)
    print("MODEL:", MODEL, "  temperature=0  response_format=json_schema(strict)")
    print("=" * 70)
    print("\n----- SYSTEM PROMPT -----\n")
    print(SYSTEM_PROMPT)
    print("\n----- USER PROMPT -----\n")
    print(user_prompt)
    print("\n----- JSON SCHEMA -----\n")
    print(json.dumps(JSON_SCHEMA, ensure_ascii=False, indent=2))

    key = load_api_key()
    if args.dry_run or not key:
        if not key and not args.dry_run:
            print("\n[!] OPENAI_API_KEY 未設定のため dry-run。env か backend/.env に設定して再実行。",
                  file=sys.stderr)
        return 0

    print("\n" + "=" * 70)
    print("CALLING OpenAI ...")
    print("=" * 70)
    from openai import OpenAI

    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
    )
    raw = resp.choices[0].message.content
    print("\n----- RAW RESPONSE -----\n")
    print(raw)
    print("\n----- PARSED -----\n")
    print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
    usage = resp.usage
    print("\n----- USAGE -----")
    print(f"prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
