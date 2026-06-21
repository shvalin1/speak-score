"""Whisper-1 の prompt がフィラー保持に与える影響を実測（PII・コミット禁止）。
同じ _diar_tmp.wav に対し prompt 条件を変えて filler 個数を比較。"""
import sys, time
from pathlib import Path
from collections import Counter
EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))
from transcribe import find_fillers, load_api_key
from openai import OpenAI

WAV = EVAL / "_diar_tmp.wav"
oai = OpenAI(api_key=load_api_key())

def fb(t):
    return dict(Counter(h["text"] for h in find_fillers(t)))

CONDITIONS = {
    "prompt無し（transcribe.py 既定 / main想定）": None,
    "verbatimプロンプト（ノートブック現状）": "えーと、あのー、まあ、なんか。フィラーや言い淀みも省略せず書き起こす。",
    "フィラー羅列のみのプロンプト": "えー、えーと、あのー、あの、その、まあ、なんか、ええと。",
}

for label, prompt in CONDITIONS.items():
    kwargs = dict(model="whisper-1", file=open(WAV, "rb"), language="ja",
                  temperature=0, response_format="verbose_json",
                  timestamp_granularities=["segment"])
    if prompt:
        kwargs["prompt"] = prompt
    t0 = time.time()
    r = oai.audio.transcriptions.create(**kwargs)
    txt = r.text
    print(f"\n===== {label} =====")
    print(f"  {time.time()-t0:.1f}s  chars={len(txt)}  fillers={len(find_fillers(txt))}  内訳={fb(txt)}")
    print(f"  冒頭: {txt[:140]}")
