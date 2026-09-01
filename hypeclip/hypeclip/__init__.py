"""HypeClip package bootstrap - v6.7.

Boot stamp + universal yt-dlp retry engine + data-403 recovery +
universal ffmpeg_location injection.

- Auth walls (bot-check/login/private/429): cookies.txt -> YouTube player
  clients -> browser cookies, 15-min per-platform cooldown after failure.
- Data walls (HTTP 403/410/503 on video bytes = stale signed URL):
  re-resolve fresh URLs up to 3x, then cookies.txt, 2-min soft cooldown.
- ffmpeg: EVERY YoutubeDL instance gets ffmpeg_location from Data\\bin
  (or PATH) injected at creation, so VRE downloads, per-clip HD segment
  fetches, and live recording can always find the bundled ffmpeg.
"""
from __future__ import annotations

print("[hypeclip] __init__ v6.7 ACTIVE", flush=True)

import os
import shutil
import sys
import threading
import time

_AUTH_MARKERS = (
    "sign in to confirm", "not a bot", "confirm you", "use --cookies",
    "log in to", "login required", "please sign in", "requires login",
    "requires authentication", "private video", "this video is private",
    "login required to view", "account is private",
    "too many requests", "http error 429", "rate limit", "rate-limited",
    "rate limited",
)
_FLAG_MARKERS = (
    "sign in to confirm", "not a bot", "confirm you",
    "too many requests", "http error 429",
)
_DATA_MARKERS = (
    "unable to download video data",
    "http error 403", "http error 410", "http error 503",
)
_FMT_RELAXED = "bestvideo*+bestaudio/best"
_CLIENTS = ("tv", "tv_simply", "web_safari", "mweb", "ios", "android_vr")
_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")
_COOLDOWN_S = 900.0
_DATA_COOLDOWN_S = 120.0
_GOOD_X: dict = {}
_FAIL_T: dict = {}
_DATA_FAIL_T: dict = {}


# ------------------------------------------------- data dir + ffmpeg
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


def _ffmpeg_bin_dir() -> str:
    d = _data_dir()
    if d and os.path.isfile(os.path.join(d, "bin", "ffmpeg.exe")):
        return os.path.join(d, "bin")
    return ""


def _locate_ffmpeg() -> str:
    d = _ffmpeg_bin_dir()
    if d:
        return d
    w = shutil.which("ffmpeg")
    if w:
        return os.path.dirname(os.path.abspath(w))
    try:
        from .utils import resolve_bin
        return os.path.dirname(os.path.abspath(resolve_bin("ffmpeg")))
    except Exception:
        return ""


# put bundled tools on PATH before anything probes for them
try:
    _bd = _ffmpeg_bin_dir()
    if _bd and _bd not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _bd + os.pathsep + os.environ.get("PATH", "")
        print("[hypeclip] bundled bin prepended to PATH: " + _bd, flush=True)
except Exception:
    pass


def _manual_cookiefile() -> str:
    d = _data_dir()
    if not d:
        return ""
    p = os.path.join(d, "cookies.txt")
    return p if os.path.isfile(p) else ""


def _platform_hint(url) -> str:
    u = str(url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "twitch.tv" in u:
        return "twitch"
    if "instagram.com" in u:
        return "instagram"
    if "facebook.com" in u or "fb.watch" in u:
        return "facebook"
    return "other"


def _is_auth_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return any(m in s for m in _AUTH_MARKERS)


def _is_flag_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return any(m in s for m in _FLAG_MARKERS)


def _is_data_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return any(m in s for m in _DATA_MARKERS)


def _errcode(e: BaseException) -> str:
    import re
    m = re.search(r"HTTP Error (\d{3})", str(e))
    return m.group(1) if m else "data error"


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


def _attempts(url) -> list:
    platform = _platform_hint(url)
    cf = _manual_cookiefile()
    out = []
    if cf:
        out.append(("Data/cookies.txt", {"cookiefile": cf}))
    if platform == "youtube":
        for cl in _CLIENTS:
            label = ("Data/cookies.txt + " if cf else "") + cl + " client"
            extra = {"extractor_args": {"youtube": {"player_client": [cl]}}}
            if cf:
                extra["cookiefile"] = cf
            out.append((label, extra))
    for b in _BROWSERS:
        if _browser_installed(b):
            out.append((b + " browser cookies",
                        {"cookiesfrombrowser": (b,)}))
    return out


def _final_tip(platform: str, flagged: bool) -> str:
    if flagged:
        if platform == "youtube":
            return (" | HypeClip: YouTube is flagging this IP/account - "
                    "wait ~24h, test on a phone hotspot, or clip from "
                    "Twitch meanwhile (no bot-check there).")
        return (" | HypeClip: " + platform + " is rate-limiting this IP - "
                "log in to " + platform + ".com in any browser on this PC, "
                "wait a while, or use a different network.")
    return (" | HypeClip: this content seems to need a login that has "
            "access to it - sign in on " + platform +
            ".com in any browser on this PC, or re-export "
            "Data\\cookies.txt while on that site.")


def _short(e: BaseException) -> str:
    s = " ".join(str(e).split())
    return s[:100] + ("..." if len(s) > 100 else "")


def _install_ffmpeg_default() -> None:
    """Inject ffmpeg_location into EVERY YoutubeDL at construction."""
    try:
        import yt_dlp
    except Exception:
        return
    if getattr(yt_dlp.YoutubeDL, "_hc_ffloc", False):
        return
    try:
        orig_init = yt_dlp.YoutubeDL.__init__
    except Exception:
        return

    def init(self, *a, **k):
        orig_init(self, *a, **k)
        try:
            if not self.params.get("ffmpeg_location"):
                loc = _locate_ffmpeg()
                if loc:
                    self.params["ffmpeg_location"] = loc
        except Exception:
            pass

    try:
        yt_dlp.YoutubeDL.__init__ = init
        yt_dlp.YoutubeDL._hc_ffloc = True
        print("[hypeclip] ffmpeg_location auto-injection installed",
              flush=True)
    except Exception:
        pass


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
            if _is_auth_error(first):
                return _auth_chain(self, url, args, kwargs, first)
            if _is_data_error(first):
                return _data_chain(self, url, args, kwargs, first)
            raise

    def _auth_chain(self, url, args, kwargs, first):
        import yt_dlp as _y
        platform = _platform_hint(url)
        left = _COOLDOWN_S - (time.time() - _FAIL_T.get(platform, 0.0))
        if _FAIL_T.get(platform, 0.0) > 0 and left > 0:
            raise type(first)(
                "HypeClip: %s retry cooldown active - retrying now "
                "would deepen the flag. Try again in ~%d min."
                % (platform, int(left // 60) + 1))
        cf = _manual_cookiefile()
        print("[hypeclip] %s login/bot wall hit. cookies.txt: %s"
              % (platform, cf or "NOT FOUND"), flush=True)
        last = first
        n_flag = n_other = 0
        good = _GOOD_X.get(platform)
        if good is not None:
            try:
                print("[hypeclip] retrying with known-good method...",
                      flush=True)
                opts = dict(self.params or {})
                opts.update(good)
                with _y.YoutubeDL(opts) as y2:
                    return orig(y2, url, *args, **kwargs)
            except Exception as e:
                last = e
                if not (_is_auth_error(e) or _is_format_error(e)):
                    raise
        for label, extra in _attempts(url):
            for mode in ("app-format", "relaxed"):
                try:
                    opts = dict(self.params or {})
                    opts.update(extra)
                    if mode == "relaxed":
                        print("[hypeclip]   " + label
                              + ": auth OK, relaxing format...", flush=True)
                        opts["format"] = _FMT_RELAXED
                        opts.setdefault("merge_output_format", "mp4")
                    with _y.YoutubeDL(opts) as y2:
                        r = orig(y2, url, *args, **kwargs)
                    _GOOD_X[platform] = extra
                    print("[hypeclip] method worked"
                          + (" (relaxed format)" if mode == "relaxed"
                             else "") + ": " + label, flush=True)
                    _FAIL_T.pop(platform, None)
                    return r
                except Exception as e2:
                    last = e2
                    if _is_flag_error(e2):
                        n_flag += 1
                        print("[hypeclip]   " + label + ": auth rejected",
                              flush=True)
                        break
                    if _is_auth_error(e2):
                        n_other += 1
                        print("[hypeclip]   " + label
                              + ": needs the right login", flush=True)
                        break
                    if _is_format_error(e2):
                        if mode == "app-format":
                            continue
                        print("[hypeclip]   " + label
                              + ": still no formats", flush=True)
                        break
                    print("[hypeclip]   " + label + ": "
                          + _short(e2), flush=True)
                    break
        flagged = n_flag >= 1 and n_flag >= n_other
        if flagged:
            _FAIL_T[platform] = time.time()
        raise type(first)(str(last) + _final_tip(platform, flagged))

    def _data_chain(self, url, args, kwargs, first):
        import yt_dlp as _y
        platform = _platform_hint(url)
        left = _DATA_COOLDOWN_S - (time.time()
                                   - _DATA_FAIL_T.get(platform, 0.0))
        if _DATA_FAIL_T.get(platform, 0.0) > 0 and left > 0:
            raise type(first)(
                str(first)
                + " | HypeClip: repeated stream-data failures on %s - "
                  "wait ~%d min, then retry (a fresh run re-resolves new "
                  "signed URLs). Check VPN/proxy, and for Twitch "
                  "subscriber-only VODs log in to twitch.tv in a browser "
                  "on this PC." % (platform, int(left // 60) + 1))
        last = first
        total = 3
        for i in range(total - 1):
            delay = 2.0 * (i + 1)
            print("[hypeclip] stream data rejected (%s) - re-resolving "
                  "fresh URLs in %.0fs (attempt %d/%d)..."
                  % (_errcode(first), delay, i + 2, total), flush=True)
            time.sleep(delay)
            try:
                opts = dict(self.params or {})
                with _y.YoutubeDL(opts) as y2:
                    return orig(y2, url, *args, **kwargs)
            except Exception as e:
                last = e
                if not _is_data_error(e):
                    raise
        cf = _manual_cookiefile()
        if cf:
            print("[hypeclip] final attempt with Data/cookies.txt...",
                  flush=True)
            try:
                opts = dict(self.params or {})
                opts["cookiefile"] = cf
                with _y.YoutubeDL(opts) as y2:
                    r = orig(y2, url, *args, **kwargs)
                _DATA_FAIL_T.pop(platform, None)
                return r
            except Exception as e:
                last = e
                if not _is_data_error(e):
                    raise
        _DATA_FAIL_T[platform] = time.time()
        raise type(last)(
            str(last)
            + " | HypeClip: the platform kept refusing the video data. "
              "This is usually a stale signed URL - retrying the job "
              "re-resolves fresh URLs. If it persists: check VPN/proxy "
              "is OFF, and for subscriber-only Twitch VODs sign in to "
              "twitch.tv in a browser on this PC.")

    try:
        yt_dlp.YoutubeDL.extract_info = extract_info
        yt_dlp._hypeclip_cookiefix = True
    except Exception:
        pass


try:
    _install_ffmpeg_default()
except Exception:
    pass

try:
    _install_ytdlp_fix()
except Exception:
    pass
