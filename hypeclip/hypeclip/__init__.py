"""HypeClip package bootstrap.

YouTube bot-check auto-retry for yt-dlp (v5).

v5: after a full failed retry chain, a 15-minute cooldown blocks further
full chains (hammering YouTube deepens the IP/account flag), and the
final error honestly reports whether auth or formats were the blocker.
Order otherwise unchanged: Data\\cookies.txt, cookies+player clients,
cookieless clients, installed browsers only, relaxed-format fallback.
"""
from __future__ import annotations

import os
import sys
import time

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
_COOLDOWN_S = 900.0
_GOOD: dict = {"extra": None}
_FAIL: dict = {"t": 0.0, "kind": ""}


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
    return "requested format is not available" in str(exc).lower()


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
            # cooldown after a recently failed full chain
            left = _COOLDOWN_S - (time.time() - _FAIL["t"])
            if _FAIL["t"] > 0 and left > 0:
                mins = int(left // 60) + 1
                raise type(first)(
                    "HypeClip: YouTube bot-check cooldown active - "
                    "retrying now would deepen the flag on your IP. "
                    "Try again in ~%d min, switch to a phone hotspot, "
                    "or use a Twitch VOD meanwhile." % mins)
            cf = _manual_cookiefile()
            print("[hypeclip] YouTube bot-check hit. cookies.txt: %s"
                  % (cf or "NOT FOUND"), flush=True)
            last = first
            n_bot = n_fmt = 0
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
                                  + ": auth OK, relaxing format...",
                                  flush=True)
                            opts["format"] = _FMT_RELAXED
                            opts.setdefault("merge_output_format", "mp4")
                        with yt_dlp.YoutubeDL(opts) as y2:
                            r = orig(y2, url, *args, **kwargs)
                        _GOOD["extra"] = extra
                        print("[hypeclip] method worked"
                              + (" (relaxed format)" if mode == "relaxed"
                                 else "") + ": " + label, flush=True)
                        _FAIL["t"] = 0.0
                        return r
                    except Exception as e2:
                        last = e2
                        if _is_bot_error(e2):
                            n_bot += 1
                            print("[hypeclip]   " + label
                                  + ": auth rejected", flush=True)
                            break
                        if _is_format_error(e2):
                            n_fmt += 1
                            if mode == "app-format":
                                continue
                            print("[hypeclip]   " + label
                                  + ": still no formats", flush=True)
                            break
                        print("[hypeclip]   " + label + ": "
                              + _short(e2), flush=True)
                        break
            _FAIL["t"] = time.time()
            _FAIL["kind"] = "auth" if n_bot >= n_fmt else "format"
            if _FAIL["kind"] == "auth":
                tip = (" | HypeClip: YouTube rejected every login method - "
                       "your IP/account is flagged. Wait ~24h, or test on "
                       "a phone hotspot, or clip from Twitch meanwhile "
                       "(no bot-check there).")
            else:
                tip = (" | HypeClip: login works but no client served "
                       "downloadable formats (PO-token enforcement). "
                       "Switch network (phone hotspot) or update yt-dlp.")
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
