"""Record a few seconds of the card while the song plays (real audio clock) -> out/clip.webm
usage: record.py [url] [seconds]"""
import glob
import json
import os
import shutil
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 6
L = json.load(open(f"web/lipsync_{'2' if 'song=2' in url else '1'}.json"))
start = next(i / L["fps"] for i, f in enumerate(L["frames"]) if f[0] >= 0.06)
shutil.rmtree("out/video", ignore_errors=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chromium", args=["--use-gl=angle", "--use-angle=swiftshader",
                                                    "--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 540, "height": 720}, record_video_dir="out/video",
                        record_video_size={"width": 540, "height": 720})
    import time
    pg = ctx.new_page()
    t_video0 = time.monotonic()  # the recording starts with the page
    pg.goto(url, wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.mouse.move(330, 300)
    pg.click("#card")
    pg.wait_for_function("document.getElementById('song').currentTime > 0.05")
    song_at = time.monotonic() - t_video0 - pg.evaluate("document.getElementById('song').currentTime")
    pg.wait_for_function(f"document.getElementById('song').currentTime > {start - 1}", timeout=60000)
    head = []
    for _ in range(int(secs * 10)):
        pg.wait_for_timeout(100)
        head.append(pg.evaluate("(() => { const S = window.__three.S; return [S.head[0].x, S.head[2].x, S.hand.x]; })()"))
    ctx.close()
    b.close()
vid = glob.glob("out/video/*.webm")[0]
shutil.move(vid, "out/clip.webm")
mx = [max(abs(h[i]) for h in head) for i in range(3)]
print("max |head nod|, |head tilt|, |hand|:", [round(v, 3) for v in mx])
# mux the song in at the moment it started in the recording; drop the silent page-load part
import subprocess  # noqa: E402
song_file = f"web/song_{'2' if 'song=2' in url else '1'}.mp3"
cut = max(0.0, start - 1.5 + song_at)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{cut:.3f}", "-i", "out/clip.webm",
                "-ss", f"{max(0.0, cut - song_at):.3f}", "-i", song_file,
                "-map", "0:v", "-map", "1:a", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", "out/clip.mp4"], check=True)
print(f"out/clip.mp4 (song started {song_at:.2f}s into the recording)")
