"""HypeClip package bootstrap.

YouTube bot-check auto-retry for yt-dlp (v3).

Order of attempts when YouTube says "Sign in to confirm you're not a bot":
  1. Data\\cookies.txt
  2. Data\\cookies.txt + tv / tv_simply / web_safari / mweb / ios clients
  3. cookieless player clients
  4. cookies from installed browsers only (uninstalled browsers are skipped)

v3 fixes:
  - cookies + alternate player client combos (the known-good bypass)
  - browsers without a cookie database are skipped silently
  - the ORIGINAL bot-check error is reported when all attempts fail,
    instead of the last attempt's unrelated error
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
_CLIENTS = ("tv", "tv_simply", "web_safari", "mweb", "ios", "android_vr")
_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")
_GOOD: dict = {"extra": None}


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


def _browser_installed(b: str) -> bool:
    la = os.environ.get("LOCALAPPDATA", "")
    ra = os.environ.get("APPDATA", "")
    paths = {
        "chrome": os.path.join(la, "Google", "Chrome", "User Data"),
        "edge": os.path.join(la, "Microsoft", "Edge", "User Data"),
        "firefox": os.path.join(ra, "Mozilla", "Firefox", "Profiles"),
        "brave": os.path.join(la, "BraveSoftware", "Brave-Browser",
                              "User Data"),
        "opera": os.path.join(ra, "Opera Software"),
        "vivaldi": os.path.join(la, "Vivaldi", "User Data"),
    }
    p = paths.get(b, "")
    return bool(p) and os.path.isdir(p)


def _attempts() -> list:
    cf = _manual_cookiefile()
    out = []
    if cf:
        out.append(("Data/cookies.txt", {"cookiefile": cf}))
        for cl in _CLIENTS:
            out.append(("Data/cookies.txt + " + cl + " client",
                        {"cookiefile": cf,
                         "extractor_args": {"youtube": {
                             "player_client": [cl]}}}))
    else:
        for cl in _CLIENTS:
            out.append((cl + " player client (no cookies)",
                        {"extractor_args": {"youtube": {
                            "player_client": [cl]}}}))
    for b in _BROWSERS:
        if not _browser_installed(b):
            continue
        out.append((b + " browser cookies",
                    {"cookiesfrombrowser": (b,)}))
    return out


def _short(e: BaseException) -> str:
    s = " ".join(str(e).split())
    return s[:110] + ("..." if len(s) > 110 else "")


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
            for label, extra in _attempts():
                try:
                    print("[hypeclip] YouTube bot-check - trying "
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
                    print("[hypeclip]   failed: " + _short(e2), flush=True)
                    continue
            tip = (" | HypeClip: your IP is likely flagged - connect the PC "
                   "to a phone hotspot and retry, or wait a day. Cookies "
                   "were valid but the media endpoint demands a PO token "
                   "from this network.")
            try:
                raise type(first)(str(first) + tip)
            except Exception:
                raise first

    try:
        yt_dlp.YoutubeDL.extract_info = extract_info
        yt_dlp._hypeclip_cookiefix = True
    except Exception:
        pass


try:
    _install_ytdlp_fix()
except Exception:
    pass
