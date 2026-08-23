from __future__ import annotations
import concurrent.futures as cf
import glob
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from . import audiohype, beats, captions, downloader, fx, sfx, scan, sources, youtube
from .captionstyle import CaptionStyle
from .config import Settings
from .utils import fmt_ts, probe_dims, probe_duration, safe_name, which_ffmpeg


class Reporter:
    def log(self, msg): print(msg, flush=True)
    def stage(self, name): pass
    def progress(self, fraction): pass
    def progress_scan(self, fraction): pass
    def moment(self, m): pass
    def set_series(self, s): pass
    def clip(self, c): pass
    def media_ready(self, key, fname, dur): pass
    def review(self, moments, series): pass
    def wait_selection(self): return {"mode": "audio", "rect": None}
    def wait_command(self): return ("confirm", None)


def run(url: str, settings: Settings, r: Reporter, stop: threading.Event | None = None):
    which_ffmpeg()
    settings.ensure_dirs()
    sfx.ensure_defaults(settings.sfx_dir, r)
    r.stage("resolve")

    plat = sources.detect(url)
    r.log(f"source platform: {plat['platform']}")
    info = youtube.video_info(url, settings)
    r.log(f"{info['title']}  -  {info['channel'] or '?'}"
          + ("  [LIVE]" if info["is_live"] else f"  [{fmt_ts(info['duration'])}]"))

    if info["is_live"]:
        if plat["platform"] == "tiktok":
            raise ValueError("TikTok LIVE isn't supported - paste a posted "
                             "TikTok video instead.")
        return _live(url, info, settings, r, stop)
    return _vod(url, info, plat, settings, r, stop)


def _analyze(analyzer, settings, r, total=None):
    r.stage("scan")
    moments, series = analyzer.detect(total)
    r.set_series(series)
    if not moments:
        raise RuntimeError("No hype found - try lower sensitivity, or redraw "
                           "the rectangle exactly over the moving chat.")
    for m in moments:
        r.log(f"HYPE @ {fmt_ts(m.peak)}  score={m.score:.1f}  "
              f"{fmt_ts(m.start)} -> {fmt_ts(m.end)}")
        r.moment({"start": round(m.start, 1), "end": round(m.end, 1),
                  "peak": round(m.peak, 1), "score": round(m.score, 1)})
    return moments


def _dims_for(aspect, src_h):
    if aspect == "9:16":
        return int(round(src_h * 9 / 16)) // 2 * 2, src_h
    if aspect == "1:1":
        return src_h, src_h
    return int(round(src_h * 16 / 9)) // 2 * 2, src_h


def _finish_clip(ctx, start, dur, idx, title, score, settings, r):
    work, src = ctx["work"], ctx["media"]
    wav = os.path
