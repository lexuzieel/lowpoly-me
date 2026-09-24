"""Bake lip sync from an isolated vocal track -> web/lipsync.json

usage: bake_lipsync.py audio/song.mp3 [--english [lyrics.txt]] [--out web/lipsync.json]
  expects demucs output in audio/sep/htdemucs/<name>/
- cues: Rhubarb mouth shapes (A-H, X) with start times: the phonemes
- frames at FPS: [loudness-driven jaw, wide, pucker], used to scale the cues and as a fallback
- bpm and first beat, for pose timing and the glow pulse
Rhubarb's phonetic recognizer works for any language; --english uses its English model (better with lyrics)."""
import subprocess
import json
import os
import sys

import numpy as np
import soundfile as sf

FPS = 12
src = sys.argv[1] if len(sys.argv) > 1 else "audio/song.mp3"
name = os.path.splitext(os.path.basename(src))[0]
sep = f"audio/sep/htdemucs/{name}"


def mono(path):
    x, sr = sf.read(path, always_2d=True)
    return x.mean(1), sr


voc, sr = mono(f"{sep}/vocals.wav")
hop = sr // FPS
n = len(voc) // hop
win = np.hanning(hop * 2)
freqs = np.fft.rfftfreq(hop * 2, 1 / sr)
low = (freqs > 250) & (freqs < 900)      # F1 region: open vowels, "o/u" dominate
high = (freqs > 1600) & (freqs < 4000)   # F2 region: "i/e", teeth-showing vowels

frames = []
db = np.zeros(n)
ratio = np.zeros(n)
for i in range(n):
    seg = voc[i * hop: i * hop + hop * 2]
    if len(seg) < hop * 2:
        seg = np.pad(seg, (0, hop * 2 - len(seg)))
    spec = np.abs(np.fft.rfft(seg * win)) ** 2
    db[i] = 10 * np.log10(spec[low | high].sum() + 1e-12)
    ratio[i] = np.log10((spec[high].sum() + 1e-9) / (spec[low].sum() + 1e-9))

loud = np.percentile(db, 97)
floor = loud - 28
jaw = np.clip((db - floor) / (loud - floor), 0, 1) ** 1.3
voiced = jaw > 0.08
r_mid = np.median(ratio[voiced]) if voiced.any() else 0
r_spread = np.std(ratio[voiced]) + 1e-6 if voiced.any() else 1
tone = np.clip((ratio - r_mid) / (r_spread * 1.5), -1, 1)
wide = np.where(voiced, np.clip(tone, 0, 1) * 0.8, 0)
pucker = np.where(voiced, np.clip(-tone, 0, 1) * 0.7, 0)
# a closed mouth in wide vowels opens less
jaw = jaw * (1 - 0.35 * wide) * 0.9

for i in range(n):
    frames.append([round(float(jaw[i]), 2), round(float(wide[i]), 2), round(float(pucker[i]), 2)])

# tempo from the instrumental: onset envelope autocorrelation
inst, _ = mono(f"{sep}/no_vocals.wav")
ohop = sr // 100
env = np.array([np.sqrt(np.mean(inst[i * ohop:(i + 1) * ohop] ** 2)) for i in range(len(inst) // ohop)])
onset = np.maximum(0, np.diff(np.log(env + 1e-6)))
ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
lags = np.arange(len(ac))
bpm_range = (lags >= 100 * 60 / 160) & (lags <= 100 * 60 / 70)
lag = lags[bpm_range][np.argmax(ac[bpm_range])]
if "--bpm" in sys.argv:  # autocorrelation can lock onto 2/3 or 3/2 of the tempo; let the caller pin it
    lag = int(round(100 * 60 / float(sys.argv[sys.argv.index("--bpm") + 1])))
bpm = 60 * 100 / lag
phase = np.argmax([onset[p::lag].sum() for p in range(lag)])

# drum hits from the instrumental: kick (low band) and snare (noisy highs) onsets, peak-picked
def band_onsets(x, lo, hi, k, min_gap):
    hop_ = sr // 100
    win_ = np.hanning(hop_ * 4)
    f_ = np.fft.rfftfreq(hop_ * 4, 1 / sr)
    band = (f_ >= lo) & (f_ <= hi)
    n_ = (len(x) - hop_ * 4) // hop_
    e = np.array([np.log1p(np.abs(np.fft.rfft(x[i * hop_: i * hop_ + hop_ * 4] * win_))[band].sum()) for i in range(n_)])
    flux = np.maximum(0, np.diff(e, prepend=e[0]))
    thr = flux.mean() + k * flux.std()
    hits, last = [], -1e9
    for i in range(2, len(flux) - 2):
        if flux[i] > thr and flux[i] == flux[i - 2:i + 3].max() and i - last >= min_gap * 100:
            hits.append(round(i / 100, 3))
            last = i
    return hits


kicks = band_onsets(inst, 30, 150, 1.6, 0.18)
snares = band_onsets(inst, 1500, 5000, 1.8, 0.18)
print(f"kicks {len(kicks)}, snares {len(snares)}")

# phonemes -> mouth shapes with Rhubarb (needs 16 kHz mono PCM)
import torch  # noqa: E402
import torchaudio  # noqa: E402
v16 = torchaudio.functional.resample(torch.tensor(voc, dtype=torch.float32), sr, 16000).numpy()
wav16 = f"audio/{name}_vocals16k.wav"
sf.write(wav16, v16, 16000, subtype="PCM_16")
rhubarb = os.path.expanduser("~/opt/Rhubarb-Lip-Sync-1.14.0-Linux/rhubarb")
cues_path = f"audio/{name}_cues.tsv"
cmd = [rhubarb, "-f", "tsv", "--extendedShapes", "GHX", wav16, "-o", cues_path]
if "--english" in sys.argv:
    i = sys.argv.index("--english")
    cmd += ["-r", "pocketSphinx"]
    if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
        cmd += ["-d", sys.argv[i + 1]]
else:
    cmd += ["-r", "phonetic"]
subprocess.run(cmd, check=True, capture_output=True)  # writing to stdout fails with the English model
tsv = open(cues_path).read()
cues = [[round(float(t), 3), sh] for t, sh in (ln.split("\t") for ln in tsv.strip().splitlines())]

out = {"fps": FPS, "cues": cues, "kicks": kicks, "snares": snares, "bpm": round(float(bpm), 2), "beat0": round(phase / 100, 3), "frames": frames}
dst = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "web/lipsync.json"
json.dump(out, open(dst, "w"), separators=(",", ":"))
print(f"{n} frames, bpm {bpm:.1f}, beat0 {phase / 100:.2f}s, voiced {voiced.mean():.0%}")
