"""Runs inside GUI Blender: executes scripts dropped into bridge/inbox/ on the main thread.
Output (stdout + traceback) goes to bridge/outbox/<name>.log"""
import contextlib
import io
import os
import traceback

import bpy

ROOT = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(ROOT, "bridge", "inbox")
OUTBOX = os.path.join(ROOT, "bridge", "outbox")
os.makedirs(INBOX, exist_ok=True)
os.makedirs(OUTBOX, exist_ok=True)

bpy.context.preferences.view.show_splash = False


def close_splash():
    # Splash may already be open on first launch: dismiss it by moving the mouse-less way
    for win in bpy.context.window_manager.windows:
        with bpy.context.temp_override(window=win):
            try:
                bpy.ops.wm.splash_close()
            except Exception:
                pass
    return None


def poll():
    for name in sorted(os.listdir(INBOX)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(INBOX, name)
        src = open(path).read()
        os.remove(path)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                exec(compile(src, name, "exec"), {"__name__": "__bridge__", "ROOT": ROOT})
                buf.write("\n[OK]\n")
            except Exception:
                buf.write(traceback.format_exc() + "\n[ERROR]\n")
        with open(os.path.join(OUTBOX, name[:-3] + ".log"), "w") as f:
            f.write(buf.getvalue())
    return 0.3


bpy.app.timers.register(close_splash, first_interval=1.0)
bpy.app.timers.register(poll, first_interval=1.5, persistent=True)
print("bridge ready:", INBOX)
