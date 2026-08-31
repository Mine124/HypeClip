"""HypeClip package bootstrap.

YouTube bot-check auto-retry for yt-dlp (v4).

v4: a retry that returns "Requested format is not available" means the
AUTH SUCCEEDED (cookies worked) but the alternate client serves formats
that fail the app's strict selector. In that case the format selector is
relaxed to best-available and merged to mp4 by the bundled ffmpeg.
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
_FMT_RELAXED = "bestvideo*+bestaudio/best"
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


def _is_format_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "requested format is not available" in s


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
    return s[:100] + ("..." if len(s) > 100 else "")


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
            # fast path: method that already worked this session
            if _GOOD["extra"] is not None:
                try:
                    print("[hypeclip] retrying with known-good method...",
                          flush=True)
                    opts = dict(self.params or {})
                    opts.update(_GOOD["extra"])
                    with yt_dlp.YoutubeDL(opts) as y2:
                        return orig(y2, url, *args, **kwargs)
                except Exception as e:
                    last = e
                    if not (_is_bot_error(e) or _is_format_error(e)):
                        raise
            for label, extra in _attempts():
                for mode in ("app-format", "relaxed"):
                    try:
                        opts = dict(self.params or {})
                        opts.update(extra)
                        if mode == "relaxed":
                            print("[hypeclip]   " + label
                                  + ": auth OK, formats mismatch - "
                                    "relaxing format selector...",
                                  flush=True)
                            opts["format"] = _FMT_RELAXED
                            opts.setdefault("merge_output_format", "mp4")
                        with yt_dlp.YoutubeDL(opts) as y2:
                            r = orig(y2, url, *args, **kwargs)
                        _GOOD["extra"] = extra  # auth only, never format
                        print("[hypeclip] method worked"
                              + (" (relaxed format)" if mode == "relaxed"
                                 else "") + ": " + label, flush=True)
                        return r
                    except Exception as e2:
                        last = e2
                        if _is_bot_error(e2):
                            print("[hypeclip]   " + label
                                  + ": auth rejected", flush=True)
                            break  # try next combo
                        if _is_format_error(e2):
                            if mode == "app-format":
                                continue  # relax and retry same combo
                            print("[hypeclip]   " + label
                                  + ": still no formats", flush=True)
                            break
                        print("[hypeclip]   " + label + ": "
                              + _short(e2), flush=True)
                        break
            tip = (" | HypeClip: authentication is working but no client "
                   "served downloadable formats - connect the PC to a "
                   "phone hotspot and retry (flagged IP), or update "
                   "yt-dlp in requirements.txt.")
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
