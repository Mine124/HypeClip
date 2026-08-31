"""HypeClip package bootstrap - v6.4.

Boot stamp + universal yt-dlp retry engine + lazy scan hardening.
The first line of output is always the boot stamp so we can verify
exactly which version of this file is running inside a build.
"""
from __future__ import annotations

print("[hypeclip] __init__ v6.4 ACTIVE", flush=True)

import os
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
_FMT_RELAXED = "bestvideo*+bestaudio/best"
_CLIENTS = ("tv", "tv_simply", "web_safari", "mweb", "ios", "android_vr")
_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")
_COOLDOWN_S = 900.0
_GOOD_X: dict = {}
_FAIL_T: dict = {}


# ---------------------------------------------- lazy scan hardening
def _harden_class(cls) -> bool:
    if not isinstance(cls, type):
        return False
    changed = False

    def _f(self):
        return 0.0

    def _i(self):
        return 0

    def _b(self):
        return False

    def _a(self, o):
        try:
            return 0.0 + float(o)
        except Exception:
            return NotImplemented

    def _ra(self, o):
        try:
            return float(o) + 0.0
        except Exception:
            return NotImplemented

    for name, fn in (("__float__", _f), ("__int__", _i), ("__bool__", _b),
                     ("__add__", _a), ("__radd__", _ra)):
        if not hasattr(cls, name):
            try:
                setattr(cls, name, fn)
                changed = True
            except Exception:
                pass
    return changed


def _gc_sweep() -> int:
    import gc
    n = 0
    try:
        objs = gc.get_objects()
    except Exception:
        return 0
    for o in objs:
        try:
            if isinstance(o, type) and "SafeBlank" in (o.__name__ or ""):
                if _harden_class(o):
                    n += 1
                    print("[hypeclip] hardened sentinel (gc): %s.%s"
                          % (getattr(o, "__module__", "?"), o.__name__),
                          flush=True)
        except Exception:
            continue
    return n


def _wrap_when_ready(timeout_s: float = 600.0) -> None:
    """Wait until hypeclip.scan exists in memory, then wrap detect().

    Works regardless of import order and regardless of HOW pipeline.py
    imported the function (module attr or from-import alias), because we
    rebind every alias in pipeline's namespace that points at the
    original function object.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        scan = sys.modules.get("hypeclip.scan")
        orig = getattr(scan, "detect", None) if scan else None
        if callable(orig) and not getattr(orig, "_hypeclip_hardened", False):
            def detect(*a, **k):
                try:
                    return orig(*a, **k)
                except TypeError as e:
                    if "_SafeBlank" in str(e):
                        print("[hypeclip] scan hit a blank sentinel - "
                              "hardening and retrying once...", flush=True)
                        _gc_sweep()
                        try:
                            r = orig(*a, **k)
                            print("[hypeclip] scan recovered after "
                                  "hardening", flush=True)
                            return r
                        except Exception as e2:
                            print("[hypeclip] scan retry failed: "
                                  + str(e2)[:200], flush=True)
                            raise
                    raise
            try:
                detect._hypeclip_hardened = True
            except Exception:
                pass
            scan.detect = detect
            rebound = 0
            pipe = sys.modules.get("hypeclip.pipeline")
            if pipe is not None:
                for aname, aval in list(vars(pipe).items()):
                    if aval is orig:
                        try:
                            setattr(pipe, aname, detect)
                            rebound += 1
                        except Exception:
                            pass
            print("[hypeclip] scan.detect wrapped (lazy); pipeline "
                  "aliases rebound: %d" % rebound, flush=True)
            return
        time.sleep(0.5)
    print("[hypeclip] scan wrapper timed out waiting for hypeclip.scan",
          flush=True)


threading.Thread(target=_wrap_when_ready, daemon=True).start()


# ------------------------------------------------------------- helpers
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
            if not _is_auth_error(first):
                raise
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
                    with yt_dlp.YoutubeDL(opts) as y2:
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
                                  + ": auth OK, relaxing format...",
                                  flush=True)
                            opts["format"] = _FMT_RELAXED
                            opts.setdefault("merge_output_format", "mp4")
                        with yt_dlp.YoutubeDL(opts) as y2:
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
                            print("[hypeclip]   " + label
                                  + ": auth rejected", flush=True)
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
                        n_other += 1
                        print("[hypeclip]   " + label + ": "
                              + _short(e2), flush=True)
                        break
            flagged = n_flag >= 1 and n_flag >= n_other
            if flagged:
                _FAIL_T[platform] = time.time()
            raise type(first)(str(last) + _final_tip(platform, flagged))

    try:
        yt_dlp.YoutubeDL.extract_info = extract_info
        yt_dlp._hypeclip_cookiefix = True
    except Exception:
        pass


try:
    _install_ytdlp_fix()
except Exception:
    pass
