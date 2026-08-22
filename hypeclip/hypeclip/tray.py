from __future__ import annotations
import os
import re
import threading
import webbrowser

import pystray
import requests
from PIL import Image, ImageDraw

YT_RE = re.compile(r"(?:v=|youtu\.be/|live/|shorts/)([\w-]{11})|^([\w-]{11})$")


def _icon_image() -> Image.Image:
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gp = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            gp[x, y] = (int(109 - 75 * t), int(92 + 119 * t), int(246 - 8 * t), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([2, 2, S - 2, S - 2], radius=14, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, S - 6, S - 6], radius=10, fill=(10, 11, 18, 255))
    bolt = [(38, 8), (19, 36), (30, 36), (26, 56), (45, 27), (33, 27), (41, 8)]
    d.polygon(bolt, fill=(255, 255, 255, 255))
    return img


class Tray:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.icon = pystray.Icon(
            "HypeClip", _icon_image(), "HypeClip Studio",
            menu=pystray.Menu(
                pystray.MenuItem("Open Dashboard", self._open, default=True),
                pystray.MenuItem("New clip from clipboard", self._clipboard),
                pystray.MenuItem("Output folder", self._folder),
                pystray.MenuItem("Check for updates", self._check_updates),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ))

    def _notify(self, msg: str, title="HypeClip"):
        try:
            self.icon.notify(msg, title)
            threading.Timer(6, self.icon.remove_notification).start()
        except Exception:
            pass

    def _post(self, path: str, payload: dict) -> dict:
        r = requests.post(self.base + path, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    def _open(self, *_a):
        webbrowser.open(self.base)

    def _clipboard(self, *_a):
        def go():
            try:
                import pyperclip
                text = (pyperclip.paste() or "").strip()
                if not YT_RE.search(text):
                    return self._notify("No YouTube link in clipboard.", "Info")
                self._post("/api/jobs", {"url": text, "options": {}, "use_last": True})
                self._notify("Job started with your last settings.")
            except Exception as e:
                self._notify(str(e)[:180], "Clipboard clip failed")
        threading.Thread(target=go, daemon=True).start()

    def _folder(self, *_a):
        def go():
            try:
                meta = requests.get(self.base + "/api/meta", timeout=10).json()
                requests.post(self.base + "/api/reveal",
                              json={"path": meta["out_dir"]}, timeout=10)
            except Exception as e:
                self._notify(str(e)[:180], "Error")
        threading.Thread(target=go, daemon=True).start()

    def _check_updates(self, *_a):
        def go():
            try:
                res = self._post("/api/update/check", {})
                if res.get("error"):
                    self._notify(res["error"], "Update check")
                elif res.get("update_available"):
                    self._notify(f"v{res['latest']} available - see Updates.",
                                 "Update available")
                else:
                    self._notify(f"Latest version (v{res['current']}).", "Up to date")
            except Exception as e:
                self._notify(str(e)[:180], "Update check failed")
        threading.Thread(target=go, daemon=True).start()

    def _quit(self, *_a):
        self.icon.stop()
        os._exit(0)

    def run(self):
        self.icon.run()


def start_async(base_url: str):
    try:
        tray = Tray(base_url)
    except Exception:
        return None
    threading.Thread(target=tray.run, daemon=True).start()
    return tray