"""Screenshot the web card: shot.py [out.png] [--play] [--tilt x y]"""
import sys
from playwright.sync_api import sync_playwright

out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "out/web.png"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 700, "height": 820})
    errs = []
    pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    pg.goto(__import__("os").environ.get("URL", "http://localhost:8000/"), wait_until="networkidle")
    pg.wait_for_timeout(1500)
    if "--tilt" in sys.argv:
        i = sys.argv.index("--tilt")
        pg.mouse.move(float(sys.argv[i + 1]) * 700, float(sys.argv[i + 2]) * 820, steps=5)
        pg.wait_for_timeout(1500)
    if "--play" in sys.argv:
        pg.click("#card")
        pg.evaluate("document.getElementById('song').currentTime = 17.3")
        pg.wait_for_timeout(700)
    pg.screenshot(path=out)
    print("\n".join(errs) or "no console errors")
    b.close()
