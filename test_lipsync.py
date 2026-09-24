"""Headless end-to-end check: click play for real, the audio clock must advance and the mouth must move.
usage: test_lipsync.py [url]"""
import sys

from playwright.sync_api import sync_playwright

import json
url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
lang = "2" if "song=2" in url else "1"
L = json.load(open(f"web/lipsync_{lang}.json"))
first = next(i / L["fps"] for i, f in enumerate(L["frames"]) if f[0] >= 0.06)  # the voice actually starts
with sync_playwright() as p:
    b = p.chromium.launch(channel="chromium", args=["--use-gl=angle", "--use-angle=swiftshader",
                                                    "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 700, "height": 820})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url, wait_until="networkidle")
    pg.wait_for_timeout(1500)
    pg.click("#card")
    pg.wait_for_timeout(300)
    pg.wait_for_function(f"document.getElementById('song').currentTime > {first + 0.3}", timeout=60000)  # first sung syllable
    rows = []
    for _ in range(25):
        pg.wait_for_timeout(120)
        rows.append(pg.evaluate("""(() => { const r = window.__rig, d = r.morph, inf = r.face.morphTargetInfluences;
          const s = document.getElementById('song');
          return [+s.currentTime.toFixed(2), s.paused, ...['jawOpen','pucker','mbp','upperUp'].map(k => +inf[d[k]].toFixed(2))]; })()"""))
    for r in rows[::4]:
        print(r)
    clock = rows[-1][0] - rows[0][0]
    moving = len({tuple(r[2:]) for r in rows}) > 3
    print(f"audio clock advanced {clock:.2f}s;", "MOUTH MOVES" if moving else "MOUTH STUCK", errs or "")
    b.close()
