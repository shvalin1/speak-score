"""3候補フェア比較（PII・コミット禁止）。Whisper / Gladia(STT) / Gladia-diar+Whisper / sherpa(num=2)+Whisper。
_diar_tmp.wav を再利用。Whisper と Gladia は各1回ずつ叩く。"""
import os, re, time
from pathlib import Path
from collections import defaultdict
import httpx
import soundfile as sf

EVAL = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EVAL))
from transcribe import find_fillers, load_api_key

MODELS = EVAL / "diar_models"
WAV = EVAL / "_diar_tmp.wav"
ENV = EVAL.parents[1] / "backend" / ".env"
audio, sr = sf.read(WAV, dtype="float32")
DUR = len(audio) / sr

# ---------- helpers ----------
def n_speakers(turns):
    return len(set(s for _, _, s in turns))

def assign_speakers(segments, turns):
    out = []
    for s, e, txt in segments:
        tally = defaultdict(float)
        for ts, te, spk in turns:
            ov = max(0.0, min(e, te) - max(s, ts))
            if ov > 0:
                tally[spk] += ov
        out.append((s, e, txt, max(tally, key=tally.get) if tally else None))
    return out

def pick_applicant(turns):
    tot = defaultdict(float)
    for s, e, spk in turns:
        tot[spk] += e - s
    return max(tot, key=tot.get) if tot else None

REP = re.compile(r"(.{1,3}?)\1{5,}")  # 短い単位の6回以上連続＝幻聴ループ

def is_halluc(text):
    m = REP.search(text)
    return bool(m) and len(m.group(0)) >= max(10, 0.5 * len(text))

def collapse_rep(text):
    return REP.sub(lambda m: m.group(1), text)

# ---------- Gladia ----------
def load_gladia_key():
    for n in ("GRADIA_API_KEY", "GLADIA_API_KEY"):
        if os.environ.get(n):
            return os.environ[n]
    for line in ENV.read_text().splitlines():
        line = line.strip()
        for n in ("GRADIA_API_KEY", "GLADIA_API_KEY"):
            if line.startswith(n + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def gladia(wav, key):
    h = {"x-gladia-key": key}
    with open(wav, "rb") as f:
        up = httpx.post("https://api.gladia.io/v2/upload", headers=h,
                        files={"audio": (wav.name, f, "audio/wav")}, timeout=180).json()
    body = {"audio_url": up["audio_url"], "model": "solaria-1",
            "language_config": {"languages": ["ja"]}, "diarization": True,
            "diarization_config": {"min_speakers": 2, "max_speakers": 2}}  # 面接=2人固定
    job = httpx.post("https://api.gladia.io/v2/pre-recorded", headers=h, json=body, timeout=60).json()
    url = job.get("result_url") or f"https://api.gladia.io/v2/pre-recorded/{job['id']}"
    for _ in range(150):
        r = httpx.get(url, headers=h, timeout=60).json()
        if r.get("status") == "done":
            break
        if r.get("status") == "error":
            raise RuntimeError(r)
        time.sleep(2)
    tr = r["result"]["transcription"]
    return [(u["start"], u["end"], u.get("speaker", 0), u["text"]) for u in tr.get("utterances", [])]

# ---------- Whisper ----------
def whisper(wav):
    from openai import OpenAI
    oai = OpenAI(api_key=load_api_key())
    r = oai.audio.transcriptions.create(
        model="whisper-1", file=open(wav, "rb"), language="ja", temperature=0,
        prompt="えーと、あのー、まあ、なんか。フィラーや言い淀みも省略せず書き起こす。",
        response_format="verbose_json", timestamp_granularities=["segment"])
    segs = [(s.start, s.end, s.text) for s in (getattr(r, "segments", None) or [])]
    return r.text, segs

# ---------- sherpa ----------
def sherpa(num):
    import sherpa_onnx
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.int8.onnx")),
            num_threads=2),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(MODELS / "3dspeaker_eres2net_base_16k.onnx"), num_threads=2),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num, threshold=0.7),
        min_duration_on=0.3, min_duration_off=0.5)
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    res = sd.process(audio).sort_by_start_time()
    return [(r.start, r.end, r.speaker) for r in res]

def applicant_text(turns, segs):
    app = pick_applicant(turns)
    lab = assign_speakers(segs, turns)
    return "".join(t for _, _, t, spk in lab if spk == app), app

# ================= 実行 =================
from collections import Counter
def fb(txt):
    return dict(Counter(h["text"] for h in find_fillers(txt)))

print("=== Whisper verbatim (全文・両話者) ===")
t0 = time.time()
w_text, w_segs = whisper(WAV)
print(f"  {time.time()-t0:.1f}s  segs={len(w_segs)}  fillers={len(find_fillers(w_text))}  内訳={fb(w_text)}")

print("\n=== Gladia (2人固定) ===")
gk = load_gladia_key()
t0 = time.time()
g_utts = gladia(WAV, gk)
g_dt = time.time() - t0
g_turns = [(s, e, spk) for s, e, spk, _ in g_utts]
g_raw = "".join(t for *_, t in g_utts)
g_clean = "".join(("" if is_halluc(t) else collapse_rep(t)) for *_, t in g_utts)
n_drop = sum(1 for *_, t in g_utts if is_halluc(t))
print(f"  {g_dt:.1f}s  speakers={n_speakers(g_turns)}  幻聴判定で除外した発話={n_drop}")
print(f"  fillers: raw={len(find_fillers(g_raw))}  幻聴除去後={len(find_fillers(g_clean))}  (Whisper基準={len(find_fillers(w_text))})")

print("\n=== 応募者テキスト：4方式を横並べ ===")
# A: Gladia STT そのまま（応募者発話のみ・幻聴除去）
g_app = pick_applicant(g_turns)
a_text = "".join(("" if is_halluc(t) else collapse_rep(t)) for s, e, spk, t in g_utts if spk == g_app)
# B: Gladia diar + Whisper STT
b_text, b_app = applicant_text(g_turns, w_segs)
# C: sherpa(num=2) + Whisper STT
s_turns = sherpa(2)
c_text, c_app = applicant_text(s_turns, w_segs)
# D: sherpa(auto) + Whisper STT（参考）
s_auto = sherpa(-1)
d_text, d_app = applicant_text(s_auto, w_segs)

def filler_breakdown(txt):
    from collections import Counter
    c = Counter(h["text"] for h in find_fillers(txt))
    return dict(c)

def stat(label, txt):
    print(f"\n--- {label} ---")
    print(f"  chars={len(txt)}  fillers={len(find_fillers(txt))}  内訳={filler_breakdown(txt)}")
    print("  " + (txt[:240] + ("…" if len(txt) > 240 else "")))
    print("  …" + txt[-120:] if len(txt) > 360 else "")

stat("A. Gladia STT（応募者・幻聴除去）", a_text)
stat("B. Gladia diar + Whisper STT", b_text)
stat(f"C. sherpa(num=2) + Whisper STT  [speakers={n_speakers(s_turns)}]", c_text)
stat(f"D. sherpa(auto) + Whisper STT   [speakers={n_speakers(s_auto)}]", d_text)
