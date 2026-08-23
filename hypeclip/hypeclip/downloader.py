from __future__ import annotations
import glob
import os


def _remux_for_browser(path: str, reporter) -> str:
    """Stream-copy remux so the file plays instantly in <video> tags:
    MP4 container + moov atom up front. Quality untouched, takes seconds."""
    from .utils import resolve_bin, run
    out = os.path.splitext(path)[0] + "_web.mp4"
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    reporter.log("preparing video for preview...")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error", "-i", path,
         "-c", "copy", "-movflags", "+faststart", out])
    return out


def _bundled_ffmpeg_dir() -> str | None:
    """Point yt-dlp at our bundled FFmpeg (it only searches PATH otherwise)."""
    try:
        from .utils import resolve_bin
        return os.path.dirname(resolve_bin("ffmpeg"))
    except Exception:
        return None


def download_vod(url: str, out_dir: str, settings, reporter, progress_cb=None):
    import yt_dlp
    os.makedirs(out_dir, exist_ok=True)
    h = settings.max_height
    last_pct = [-1]

    def hook(d):
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate")
            got = d.get("downloaded_bytes") or 0
            frac = (got / tot) if tot else None
            if frac is not None:
                pct = int(frac * 100)
                if pct != last_pct[0] and pct % 5 == 0:
                    last_pct[0] = pct
                    reporter.log(f"D  {pct:3d}%  ETA {d.get('_eta_str','').strip()}")
                if progress_cb:
                    progress_cb(frac)

    # prefer H.264/AAC (universally playable); fall back gracefully
    fmt = (
        f"bv*[vcodec^=avc1][height<={h}]+ba[acodec^=mp4a]/"
        f"b[vcodec^=avc1][height<={h}]/"
        f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"
    )
    opts = {
        "format": fmt,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 8,
        "fragment_retries": 8,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    }
    ffd = _bundled_ffmpeg_dir()
    if ffd:
        opts["ffmpeg_location"] = ffd
    if settings.cookies_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared = ydl.prepare_filename(info)

    base = os.path.splitext(prepared)[0]
    hits = sorted(glob.glob(base + ".*") + glob.glob(base),
                  key=os.path.getsize, reverse=True)
    hits = [p for p in hits if os.path.isfile(p)
            and not p.endswith((".part", ".ytdl"))]
    if not hits:
        raise RuntimeError("Download finished but output file not found.")
    path = hits[0]

    try:
        path = _remux_for_browser(path, reporter)
    except Exception as e:  # noqa: BLE001
        reporter.log(f"preview-prep skipped ({e}) - using raw download")
    return path, info
