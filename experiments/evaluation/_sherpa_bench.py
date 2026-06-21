"""sherpa-onnx の CPU時間・ピークメモリ実測。GPU不要の確認用。"""
import time, resource, threading
from pathlib import Path
import soundfile as sf
import sherpa_onnx

EVAL = Path(__file__).resolve().parent
MODELS = EVAL / "diar_models"
WAV = EVAL / "_diar_tmp.wav"

audio, sr = sf.read(WAV, dtype="float32")
DUR = len(audio) / sr


def make_sd(num, threshold, threads):
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.int8.onnx")),
            num_threads=threads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(MODELS / "3dspeaker_eres2net_base_16k.onnx"), num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    return sherpa_onnx.OfflineSpeakerDiarization(cfg)


def peak_rss_mb():
    # macOS は bytes, Linux は KB を返す
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    import sys
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


print(f"audio {DUR:.1f}s sr={sr}")
for threads in (1, 2):
    for num in (-1, 2):
        sd = make_sd(num=num, threshold=0.7, threads=threads)
        t0 = time.time()
        cpu0 = time.process_time()
        res = sd.process(audio).sort_by_start_time()
        wall = time.time() - t0
        cpu = time.process_time() - cpu0
        spk = len(set(r.speaker for r in res))
        print(f"threads={threads} num={num:>2}  wall={wall:5.1f}s "
              f"RTF={wall/DUR:.3f}  cpu_time={cpu:5.1f}s  speakers={spk}  peakRSS={peak_rss_mb():.0f}MB")
