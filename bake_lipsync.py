"""Bake lip sync from an isolated vocal track -> web/lipsync.json

usage: bake_lipsync.py audio/song.mp3 [--english [lyrics.txt]]
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
bpm = 60 * 100 / lag
phase = np.argmax([onset[p::lag].sum() for p in range(lag)])

# phonemes -> mouth shapes with Rhubarb (needs 16 kHz mono PCM)
import torch  # noqa: E402
import torchaudio  # noqa: E402
v16 = torchaudio.functional.resample(torch.tensor(voc, dtype=torch.float32), sr, 16000).numpy()
wav16 = f"audio/{name}_vocals16k.wav"
sf.write(wav16, v16, 16000, subtype="PCM_16")
rhubarb = os.path.expanduser("~/opt/Rhubarb-Lip-Sync-1.14.0-Linux/rhubarb")
cmd = [rhubarb, "-f", "tsv", "--extendedShapes", "GHX", "-q", wav16]
if "--english" in sys.argv:
    i = sys.argv.index("--english")
    cmd += ["-r", "pocketSphinx"]
    if i + 1 < len(sys.argv):
        cmd += ["-d", sys.argv[i + 1]]
else:
    cmd += ["-r", "phonetic"]
tsv = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
cues = [[round(float(t), 3), sh] for t, sh in (ln.split("\t") for ln in tsv.strip().splitlines())]

out = {"fps": FPS, "cues": cues, "bpm": round(float(bpm), 2), "beat0": round(phase / 100, 3), "frames": frames}
json.dump(out, open("web/lipsync.json", "w"), separators=(",", ":"))
print(f"{n} frames, bpm {bpm:.1f}, beat0 {phase / 100:.2f}s, voiced {voiced.mean():.0%}")
