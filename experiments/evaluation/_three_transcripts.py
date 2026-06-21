"""3者の文字起こし全文を比較（PII・コミット禁止）。_diar_tmp.wav 再利用。
①whisper-1 prompt無し(main相当) ②whisper-1 verbatim(このスレッド) ③Gladia STT"""
import sys, time
from pathlib import Path
EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))
from transcribe import find_fillers, load_api_key
from openai import OpenAI
import httpx

WAV = EVAL / "_diar_tmp.wav"
ENV = EVAL.parents[1] / "backend" / ".env"
oai = OpenAI(api_key=load_api_key())

def load_gladia_key():
    for line in ENV.read_text().splitlines():
        line = line.strip()
        for n in ("GRADIA_API_KEY", "GLADIA_API_KEY"):
            if line.startswith(n + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def whisper(prompt):
    kw = dict(model="whisper-1", file=open(WAV, "rb"), language="ja", temperature=0,
              response_format="verbose_json", timestamp_granularities=["segment"])
    if prompt:
        kw["prompt"] = prompt
    return oai.audio.transcriptions.create(**kw).text

def gladia():
    key = load_gladia_key()
    h = {"x-gladia-key": key}
    with open(WAV, "rb") as f:
        up = httpx.post("https://api.gladia.io/v2/upload", headers=h,
                        files={"audio": (WAV.name, f, "audio/wav")}, timeout=180).json()
    body = {"audio_url": up["audio_url"], "model": "solaria-1",
            "language_config": {"languages": ["ja"]}, "diarization": True,
            "diarization_config": {"min_speakers": 1, "max_speakers": 3}}
    job = httpx.post("https://api.gladia.io/v2/pre-recorded", headers=h, json=body, timeout=60).json()
    url = job.get("result_url") or f"https://api.gladia.io/v2/pre-recorded/{job['id']}"
    for _ in range(150):
        r = httpx.get(url, headers=h, timeout=60).json()
        if r.get("status") == "done":
            break
        if r.get("status") == "error":
            raise RuntimeError(r)
        time.sleep(2)
    return r["result"]["transcription"].get("full_transcript", "")

def show(title, txt):
    print("=" * 80)
    print(f"{title}   fillers={len(find_fillers(txt))}  chars={len(txt)}")
    print("=" * 80)
    print(txt)
    print()

show("① whisper-1 prompt無し（main/transcribe.py 相当）", whisper(None))
show("② whisper-1 verbatimプロンプト（このスレッドの cell-6）",
     whisper("えーと、あのー、まあ、なんか。フィラーや言い淀みも省略せず書き起こす。"))
show("③ Gladia STT 全文", gladia())
