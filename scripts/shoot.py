"""Dev helper: open SpaceHound on a folder and save the README screenshots (needs Pillow).

    python scripts/make_demo.py D:\\SpaceHound-Demo
    python scripts/shoot.py D:\\SpaceHound-Demo

Drives the real window through pywebview's evaluate_js and grabs it with capture.py.
"""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from spacehound import APP_NAME, winapi  # noqa: E402
from spacehound.api import Api  # noqa: E402
from spacehound.util import data_dir, resource_path  # noqa: E402

SONAR_PATH = "C:\\Windows"   # big enough to keep the sonar screen up for a moment
SHOTS = [  # name, javascript, seconds to settle
    ("overview", "App.go('overview')", 3),
    ("explorer", "App.go('explorer')", 2),
    ("treemap", "App.go('map'); setTimeout(() => document.querySelector('[data-v=treemap]').click(), 300)", 3),
    ("sunburst", "document.querySelector('[data-v=sunburst]').click()", 3),
    ("bubbles", "document.querySelector('[data-v=bubbles]').click()", 3.5),
    ("devjunk", "App.go('devjunk')", 3),
    ("duplicates", "App.go('duplicates'); setTimeout(() => { const b = document.querySelector('#go'); if (b) b.click(); }, 700)", 8),
    ("cleanup", "App.go('cleanup')", 10),
]


def wait_for(window, expr, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if window.evaluate_js(expr):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    raise SystemExit(f"timed out waiting for {expr}")


def capture(name):
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "capture.py"), name], check=True)


def drive(window, folder):
    window.events.loaded.wait()
    wait_for(window, "typeof App !== 'undefined' && !!(App.info && App.drives)")
    time.sleep(1.5)
    window.evaluate_js(f"App.startScan([{json.dumps(SONAR_PATH)}])")
    time.sleep(2.6)
    capture("sonar")
    window.evaluate_js(f"App.startScan([{json.dumps(folder)}])")  # cancels the sonar scan first
    wait_for(window, f"!!(App.summary && App.summary.roots.join() === {json.dumps(folder)} && !document.getElementById('sonar'))")
    for name, js, settle in SHOTS:
        window.evaluate_js(js)
        time.sleep(settle)
        window.evaluate_js("document.querySelectorAll('.toast').forEach((t) => t.remove())")
        time.sleep(0.4)
        capture(name)
    window.destroy()


def main(folder):
    width, height = 1460, 930
    area = winapi.work_area()
    if area:
        width = max(1000, min(width, int(area[0] * 0.92)))
        height = max(640, min(height, int(area[1] * 0.92)))
    window = webview.create_window(APP_NAME, url=resource_path("ui", "index.html"), js_api=(api := Api(mode="webview")),
                                   width=width, height=height, min_size=(1000, 640), background_color="#120e0b")
    api._set_window(window)
    webview.start(drive, (window, folder), http_server=True, private_mode=False,
                  storage_path=os.path.join(data_dir(), "webview"))


if __name__ == "__main__":
    main(sys.argv[1])
