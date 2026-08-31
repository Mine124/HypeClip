"""HypeClip package bootstrap.

Universal download-retry engine for yt-dlp (v6.2).

Applies to EVERY platform the app accepts - YouTube, TikTok, Twitch,
Instagram, Facebook, and any other link yt-dlp understands:

  - login walls       -> retry with Data\\cookies.txt, then cookies from
                         installed browsers. yt-dlp sends each site only
                         its own cookies, so one jar never leaks across.
  - YouTube only      -> alternate player clients (tv, tv_simply, ...)
  - format walls      -> "Requested format is not available" relaxes the
                         selector to best-available, merged to mp4
  - hammering guard   -> after a failed bot-flag chain, a 15-minute
                         cooldown engages for THAT platform only

v6.2: the safe-blank sentinel sweep now covers EVERY hypeclip module
(via pkgutil) instead of a hand-picked list, so the numeric-zero
hardening lands no matter which module defines the class.
"""
from __future__ import annotations

import os
import sys
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


# ----------------------------------------------------- sentinel hardening
def _patch_blank_sentinels() -> None:
    """Make any _SafeBlank-style sentinel behave as numeric zero.

    Sweeps every hypeclip submodule (except side-effecty ones like the
    tray) so the patch lands regardless of which module owns the class.
    """
    import importlib
    import pkgutil

    def _sb_float(self):
        return 0.0

    def _sb_int(self):
        return 0

    def _sb_bool(self):
        return False

    def _sb_add(self, o):
        try:
            return 0.0 + float(o)
        except Exception:
            return NotImplemented

    def _sb_radd(self, o):
        try:
            return float(o) + 0.0
        except Exception:
            return NotImplemented

    def _harden(cls) -> bool:
        if not isinstance(cls, type):
            return False
        changed = False
        for name, fn in (("__float__", _sb_float), ("__int__", _sb_int),
                         ("__bool__", _sb_bool), ("__add__", _sb_add),
                         ("__radd__", _sb_radd)):
            if not hasattr(cls, name):
                try:
                    setattr(cls, name, fn)
                    changed = True
                except Exception:
                    pass
        return changed

    try:
        pkg = importlib.import_module(__package__)
        paths = list(getattr(pkg, "__path__", []))
    except Exception:
        return
    skip = {"tray", "main", "__main__"}
    try:
        mod_names = [mi.name for mi in pkgutil.iter_modules(paths)]
    except Exception:
        return
    for mname in mod_names:
        if mname in skip:
            continue
        try:
            mod = importlib.import_module("." + mname, __package__)
        except Exception:
            continue
        try:
            names = list(vars(mod).keys())
        except Exception:
            continue
        for attr in names:
            if "SafeBlank" in attr:
                try:
                    if _harden(getattr(mod, attr)):
                        print("[hypeclip] hardened numeric sentinel: "
                              + mname + "." + attr, flush=True)
                except Exception:
                    pass


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
    _patch_blank_sentinels()
except Exception:
    pass

try:
    _install_ytdlp_fix()
except Exception:
    pass
