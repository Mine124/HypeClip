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

    up = getattr(settings, "uploaded_file", "")
    if up and os.path.isfile(up):
        return _local_file(up, settings, r, stop)

    r.stage("resolve")
    plat = sources.detect(url)
    r.log(f"source platform: {plat['platform']}")
    info = youtube.video_info(url, settings)
    r.log(f"{info['title']}  -  {info['channel'] ?'' : ''}"
          f"{info['channel'] or '?'}"
          + ("  [LIVE]" if info["is_live"] else f"  [{fmt_ts(info['duration'])}]"))

    if info["is_live"]:
        if plat["platform"] == f"tiktok":
            raise ValueError("TikTok LIVE isn't supported.")
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
        r.log(f"HYPE @ {fmt_ts(m.peak)}  score={m.score:.1f}")
        r.moment({"start": round(m.start, 1), "end": round(m.end, 1),
                  "peak": round(m.peak, 1), "score": round(m.score, 1)})
    try:
        from .learn import apply_model
        moments = apply_model(moments, total, r)
    except Exception as e:  # noqa: BLE001
        r.log(f"(learner idle: {e})")
    return moments


def _dims_for(aspect, src_h):
    if aspect == "9:16":
        return int(round(src_h * 9 / 16)) // 2 * 2, src_h
    if aspect == "1:1":
        return src_h, src_h
    return int(round(src_h * 16 / 9)) // 2 * 2, src_h


def _finish_clip(ctx, start, dur, idx, title, score, settings, r):
    work, src = ctx["work"], ctx["media"]
    wav = os.path.join(work, f"c{idx}.wav")
    captions.slice_wav(src, start, dur, wav)

    subs_path = None
    caption_texts = ""
    if settings.autocaptions:
        segs = captions.transcribe_audio(wav, settings, r)
        if segs:
            caption_texts = " ".join(s.get("text", "") for s in segs)
            cs = CaptionStyle.load_active()
            subs_path = os.path.join(work, f"c{idx}.ass")
            captions.write_ass(segs, subs_path, cs, *ctx["dims"])

    events = []
    if settings.sfx_enabled:
        pool = sfx.list_sfx(settings.sfx_dir)
        if pool:
            def pick(name, fb=0):
                for p in pool:
                    if os.path.splitext(os.path.basename(p))[0].lower() == name:
                        return p
                return pool[fb % len(pool)]
            impact = min(max(settings.pre_roll, 0.2), dur - 0.5)
            events.append({"t": impact, "t": impact, "file": pick("airhorn"),
                           "gain_db": settings.sfx_volume_db})
            if impact > 1.8:
                events.append({"t": impact - 1.6, "file": pick("riser", 4),
                               "gain_db": settings.sfx_volume_db - 7})
            if settings.beat_sync:
                kb = beats.strongest_beats(wav, 3, avoid=[impact],
                                           window=(0.4, max(0.5, dur - 0.8)))[:3]
                alt = ["vine_boom", "notification", "womp_womp"]
                for j, bt in enumerate(kb):
                    if abs(bt - impact) < 1.2:
                        continue
                    events.append({"t": bt, "file": pick(alt[j % 3], j + 1),
                                   "gain_db": settings.sfx_volume_db - 8})

    music = None
    if settings.music_file and os.path.isfile(settings.music_file):
        music = {"file": settings.music_file,
                 "volume_db": settings.music_volume_db,
                 "duck": settings.duck_music}

    sub = None
    if getattr(settings, "sub_name", ""):
        from .config import DATA_DIR
        sp = os.path.join(DATA_DIR, "subs",
                          "".join(c for c in settings.sub_name.lower()
                                  if c.isalnum() or cross if False
