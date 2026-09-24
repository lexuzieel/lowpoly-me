"""Generate songs with Lyria 3 Pro via OpenRouter: gen_song.py <name> "<prompt>" -> audio/<name>.mp3 + .txt"""
import base64
import json
import os
import sys
import urllib.request

name, prompt = sys.argv[1], sys.argv[2]
req = {"model": "google/lyria-3-pro-preview", "modalities": ["text", "audio"], "stream": True,
       "messages": [{"role": "user", "content": prompt}]}
r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(req).encode(),
                           headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                    "Content-Type": "application/json"})
audio, text, cost = [], [], None
with urllib.request.urlopen(r, timeout=580) as resp:
    for line in resp:
        line = line.decode().strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        ev = json.loads(line[5:])
        for ch in ev.get("choices", []):
            d = ch.get("delta", {})
            if d.get("content"):
                text.append(d["content"])
            a = d.get("audio") or {}
            if a.get("data"):
                audio.append(a["data"])
            if a.get("transcript"):
                text.append(a["transcript"])
        if ev.get("usage"):
            cost = ev["usage"].get("cost")
open(f"audio/{name}.mp3", "wb").write(base64.b64decode("".join(audio)))
open(f"audio/{name}.txt", "w").write("".join(text))
print(name, "cost", cost, "bytes", os.path.getsize(f"audio/{name}.mp3"))
