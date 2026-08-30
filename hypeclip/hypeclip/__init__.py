"""HypeClip package bootstrap.

Installs a YouTube bot-check auto-retry for yt-dlp: when YouTube replies
"Sign in to confirm you're not a bot", downloads transparently retry with
Data\\cookies.txt (if present), the android_vr player client, then cookies
from browsers installed on this PC (Chrome, Edge, Firefox, Brave, Opera,
Vivaldi). Everything is optional and fully guarded - if anything fails the
app behaves exactly like before.
"""

from __future__ import annotations

import os
import sys

_BOT_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "use --cookies",
    "log in to",
    "login required",
    "please sign in",
)
_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")


def _data_dir() -> str:
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(base, "Data")
        return p if os.path.isdir(p) else ""
    except Exception:
        return ""


def _manual_cookiefile() -> str:
    d = _data_dir()
    if not d:
        return ""
    p = os.path.join(d, "cookies.txt")
    return p if os.path.isfile(p) else ""


def _is_bot_error(exc: BaseException) -> bool:
    try:
        s = str(exc).lower()
        return any(m in s for m in _BOT_MARKERS)
    except Exception:
        return False


def _install_ytdlp_fix() -> None:
    try:
        import yt_dlp
    except Exception:
        return
    if getattr(yt_dlp, "_hypeclip_cookiefix", False):
        return
    try:
        orig = yt_dlp.YoutubeDL.extract_info
    except Exception:
        return

    def extract_info(self, url, *args, **kwargs):
        try:
            return orig(self, url, *args, **kwargs)
        except Exception as first:
            if not _is_bot_error(first):
                raise
            attempts = []
            cf = _manual_cookiefile()
            if cf:
                attempts.append(("Data cookies.txt", {"cookiefile": cf}))
            attempts.append(("android_vr client (no login)",
                             {"extractor_args": {"youtube": {
                                 "player_client": ["android_vr"]}}}))
            attempts += [(b + " cookies",
                          {"cookiesfrombrowser": (b, None, None, None)})
                         for b in _BROWSERS]
            last = first
            for label, extra in attempts:
                try:
                    self.to_screen("[hypeclip] YouTube bot-check - "
                                   "retrying with " + label + " ...")
                except Exception:
                    pass
                saved = dict(self.params or {})
                try:
                    self.params.update(extra)
                    ok_params = True
                except Exception:
                    ok_params = False
                try:
                    return orig(self, url, *args, **kwargs)
                except Exception as e2:
                    last = e2
                    continue
                finally:
                    if ok_params:
                        try:
                            self.params.clear()
                            self.params.update(saved)
                        except Exception:
                            pass
            tip = (" | HypeClip tip: sign in to youtube.com in Chrome, "
                   "Edge or Firefox on this PC and retry, or put an "
                   "exported cookies.txt into the Data folder.")
            try:
                raise type(last)(str(last) + tip)
            except Exception:
                raise last

    try:
        yt_dlp.YoutubeDL.extract_info = extract_info
        yt_dlp._hypeclip_cookiefix = True
    except Exception:
        pass


try:
    _install_ytdlp_fix()
except Exception:
    pass
