from __future__ import annotations
import glob
import os
import re
import time


def _clean(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", str(s))


def _remux_for_browser(path: str, reporter) -> str:
    from .utils import resolve_bin, run
    out = os.path.splitext(path)[0] + "_web.mp4"
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    reporter.log("preparing video for preview...")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error", "-i", path,
         "-c", "copy", "-movflags", "+faststart", out])
    return out


def _bundled_ffmpeg_dir() -> str | None:
    try:
        from .utils import resolve_bin
        return os.path.dirname(resolve_bin("ffmpeg"))
    except Exception:
        return None


def _extract(url: str, opts: dict, reporter):
    import yt_dlp
    last = None
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl.prepare_filename(info)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            last = e
            locky = ("WinError 32" in msg
                     or "being used by another process" in msg
                     or "Unable to rename" in msg)
            if locky and attempt < 2:
                reporter.log(f"Windows locked a file mid-download - "
                             f"retrying ({attempt + 2}/3)...")
                time.sleep(5)
                continue
            raise
    raise last  # pragma: no cover


def _base_opts(settings) -> dict:
    o = {"merge_output_format": "mp4", "noplaylist": True, "quiet": True,
         "no_warnings": True, "retries": 8, "fragment_retries": 8,
         "concurrent_fragment_downloads": 2,
         "nopart": True, "continuedl": False}
    ffd = _bundled_ffmpeg_dir()
    if ffd:
        o["ffmpeg_location"] = ffd
    if settings.cookies_browser:
        o["cookiesfrombrowser"] = (settings.cookies_browser,)
    return o


def _fmt_hd(h: int) -> str:
    return (f"bv*[vcodec^=avc1][height<={h}]+ba[acodec^=mp4a]/"
            f"b[vcodec^=avc1][height<={h}]/"
            f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b")


def _pick_file(prepared: str) -> str:
    base = os.path.splitext(prepared)[0]
    hits = sorted(glob.glob(base + ".*") + glob.glob(base),
                  key=os.path.getsize, reverse=True)
    hits = [p for p in hits if os.path.isfile(p)
            and not p.endswith((".part", ".ytdl"))]
    if not hits:
        raise RuntimeError("download finished but output file not found")
    return hits[0]


def _clean_junk(out_dir: str):
    for junk in (glob.glob(os.path.join(out_dir, "*.part"))
                 + glob.glob(os.path.join(out_dir, "*.ytdl"))):
        try:
            os.remove(junk)
        except OSError:
            pass


# ------------------------------------------------------------------ proxy
def download_proxy(url: str, out_dir: str, settings, reporter,
                   progress_cb=None):
    """Fast lightweight pass (480p) used for preview/scan/tracking."""
    import yt_dlp
    os.makedirs(out_dir, exist_ok=True)
    _clean_junk(out_dir)
    last = [-1]

    def hook(d):
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate")
            got = d.get("downloaded_bytes") or 0
            if tot:
                pct = int(got / tot * 100)
                if pct != last[0] and pct % 10 == 0:
                    last[0] = pct
                    reporter.log(f"P {pct:3d}%  (lightweight pass)")
                if progress_cb:
                    progress_cb(got / tot)

    opts = _base_opts(settings)
    opts.update({
        "format": ("bv*[height<=480][vcodec^=avc1]+ba[acodec^=mp4a]/"
                   "b[height<=480]/bv*+ba/b"),
        "outtmpl": os.path.join(out_dir, "%(id)s_proxy.%(ext)s"),
        "concurrent_fragment_downloads": 8,
        "progress_hooks": [hook],
    })
    info, prepared = _extract(url, opts, reporter)
    path = _pick_file(prepared)
    try:
        path = _remux_for_browser(path, reporter)
    except Exception as e:  # noqa: BLE001
        reporter.log(f"preview-prep skipped ({e})")
    return path, info


# ------------------------------------------------------------- HD segment
def download_segment(url: str, start: float, end: float, out_dir: str,
                     settings, reporter, idx: int = 0) -> str:
    """Downloads ONLY [start,end] in full quality."""
    import yt_dlp
    os.makedirs(out_dir, exist_ok=True)
    _clean_junk(out_dir)
    opts = _base_opts(settings)
    opts.update({
        "format": _fmt_hd(settings.max_height),
        "outtmpl": os.path.join(out_dir, f"hdseg{idx}.%(ext)s"),
        "download_ranges": lambda info, ydl: [
            {"start_time": max(0.0, start), "end_time": max(end, start + 5)}],
        "force_keyframes_at_cuts": True,
        "progress_hooks": [],
    })
    reporter.log(f"fetching HD segment {idx + 1} "
                 f"({end - start:.0f}s, full quality)...")
    info, prepared = _extract(url, opts, reporter)
    return _pick_file(prepared)


# ------------------------------------------------------- legacy full VOD
def download_vod(url: str, out_dir: str, settings, reporter,
                 progress_cb=None):
    """Full-quality full-length download (fallback / forced mode)."""
    import yt_dlp
    os.makedirs(out_dir, exist_ok=True)
    _clean_junk(out_dir)
    last = [-1]

    def hook(d):
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate")
            got = d.get("downloaded_bytes") or 0
            if tot:
                pct = int(got / tot * 100)
                if pct != last[0] and pct % 5 == 0:
                    last[0] = pct
                    reporter.log(f"D  {pct:3d}%  "
                                 f"ETA {_clean(d.get('_eta_str', '')).strip()}")
                if progress_cb:
                    progress_cb(got / tot)

    opts = _base_opts(settings)
    opts.update({"format": _fmt_hd(settings.max_height),
                 "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
                 "concurrent_fragment_downloads": 2,
                 "progress_hooks": [hook]})
    info, prepared = _extract(url, opts, reporter)
    path = _pick_file(prepared)
    try:
        path = _remux_for_browser(path, reporter)
    except Exception as e:  # noqa: BLE001
        reporter.log(f"preview-prep skipped ({e})")
    return path, info
