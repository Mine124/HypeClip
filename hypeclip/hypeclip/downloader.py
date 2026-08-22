from __future__ import annotations
import glob
import os


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

    fmt = f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"
    opts = {
        "format": fmt,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    }
    if settings.cookies_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared = ydl.prepare_filename(info)

    base = os.path.splitext(prepared)[0]
    hits = sorted(glob.glob(base + ".*") + glob.glob(base),
                  key=os.path.getsize, reverse=True)
    hits = [p for p in hits if os.path.isfile(p) and not p.endswith((".part", ".ytdl"))]
    if not hits:
        raise RuntimeError("Download finished but output file not found.")
    return hits[0], info