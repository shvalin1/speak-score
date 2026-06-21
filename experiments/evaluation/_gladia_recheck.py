"""Gladia 再現性チェック（PII・コミット禁止）。_diar_tmp.wav を再利用して2回叩く。"""
import os, time, json
from pathlib import Path
import httpx

EVAL = Path(__file__).resolve().parent
WAV = EVAL / "_diar_tmp.wav"
ENV = EVAL.parents[1] / "backend" / ".env"


def load_gladia_key():
    for name in ("GRADIA_API_KEY", "GLADIA_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    for line in ENV.read_text().splitlines():
        line = line.strip()
        for name in ("GRADIA_API_KEY", "GLADIA_API_KEY"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def gladia(wav, key):
    h = {"x-gladia-key": key}
    with open(wav, "rb") as f:
        up = httpx.post("https://api.gladia.io/v2/upload", headers=h,
                        files={"audio": (wav.name, f, "audio/wav")}, timeout=180).json()
    body = {
        "audio_url": up["audio_url"],
        "model": "solaria-1",
        "language_config": {"languages": ["ja"]},
        "diarization": True,
        "diarization_config": {"min_speakers": 1, "max_speakers": 3},
    }
    job = httpx.post("https://api.gladia.io/v2/pre-recorded", headers=h, json=body, timeout=60).json()
    result_url = job.get("result_url") or f"https://api.gladia.io/v2/pre-recorded/{job['id']}"
    for _ in range(150):
        r = httpx.get(result_url, headers=h, timeout=60).json()
        st = r.get("status")
        if st == "done":
            break
        if st == "error":
            raise RuntimeError(f"Gladia error: {r}")
        time.sleep(2)
    tr = r["result"]["transcription"]
    utts = [(u["start"], u["end"], u.get("speaker", 0), u["text"]) for u in tr.get("utterances", [])]
    return utts


def repeat_ratio(text):
    """最頻トークン(空白区切り)の占有率で繰り返し度を測る簡易指標。"""
    toks = text.split()
    if not toks:
        return 0.0, "", 0
    from collections import Counter
    c = Counter(toks)
    tok, n = c.most_common(1)[0]
    return n / len(toks), tok, len(toks)


key = load_gladia_key()
assert key, "GRADIA_API_KEY なし"

for run in (1, 2):
    print(f"\n========== RUN {run} ==========")
    t0 = time.time()
    utts = gladia(WAV, key)
    spk = sorted(set(s for _, _, s, _ in utts))
    print(f"{time.time()-t0:.1f}s  utterances={len(utts)}  speakers={len(spk)} {spk}")
    # 末尾5発話を話者付きで
    print("--- 末尾6発話 ---")
    for s, e, sp, t in utts[-6:]:
        disp = t if len(t) <= 60 else t[:57] + "…"
        print(f"  [{s:6.1f}-{e:6.1f}] spk{sp}  {disp}")
    # 繰り返し度（うん幻聴の検出）
    for sp in spk:
        txt = "".join(t for _, _, s, t in utts if s == sp)
        # 文字レベルで「うん」の連続を測る
        un = txt.count("うんうん")
        print(f"  spk{sp}: chars={len(txt)}  'うんうん'出現={un}")
