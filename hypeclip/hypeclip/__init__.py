"""HypeClip package bootstrap.

Installs a YouTube bot-check auto-retry for yt-dlp. When YouTube replies
"Sign in to confirm you're not a bot", the request is retried with, in
order: Data\\cookies.txt (if present), alternate player clients
(android_vr, tv, ios), then cookies from browsers installed on this PC.

v2 fix: yt-dlp only reads cookie options at YoutubeDL construction, so
mutating an existing instance's params silently runs cookie-less. Each
retry now builds a FRESH YoutubeDL with merged options. Every attempt is
printed to the debug console so the working method is visible.
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
_CLIENTS = ("android_vr", "tv", "ios")
_GOOD: dict = {"extra": None}  # first retry method that works, reused


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


def _attempts() -> list:
    out = []
    cf = _manual_cookiefile()
    if cf:
        out.append(("Data/cookies.txt", {"cookiefile": cf}))
    for cl in _CLIENTS:
        out.append((cl + " player client",
                    {"extractor_args": {"youtube": {"player_client": [cl]}}}))
    for b in _BROWSERS:
        out.append((b + " browser cookies",
                    {"cookiesfrombrowser": (b,)}))
    return out


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
            last = first
            cf = _manual_cookiefile()
            print("[hypeclip] YouTube bot-check hit. cookies.txt: %s"
                  % (cf or "NOT FOUND"), flush=True)
            # fast path: a method that already worked this session
            if _GOOD["extra"] is not None:
                try:
                    print("[hypeclip] retrying with known-good method...",
                          flush=True)
                    opts = dict(self.params or {})
                    opts.update(_GOOD["extra"])
                    with yt_dlp.YoutubeDL(opts) as y2:
                        r = orig(y2, url, *args, **kwargs)
                        return r
                except Exception as e:
                    last = e
            # full chain, fresh YoutubeDL per attempt (the actual fix)
            for label, extra in _attempts():
                try:
                    print("[hypeclip] YouTube bot-check - retrying with "
                          + label + " ...", flush=True)
                    opts = dict(self.params or {})
                    opts.update(extra)
                    with yt_dlp.YoutubeDL(opts) as y2:
                        r = orig(y2, url, *args, **kwargs)
                        _GOOD["extra"] = extra
                        print("[hypeclip] method worked: " + label,
                              flush=True)
                        return r
                except Exception as e2:
                    last = e2
                    continue
            tip = (" | HypeClip tip: export cookies from youtube.com while "
                   "signed in and save as Data\\cookies.txt, or try a "
                   "different network (phone hotspot).")
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
