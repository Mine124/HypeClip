from __future__ import annotations
from .captionstyle import CaptionStyle
import concurrent.futures as cf
import glob
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from . import beats, captions, downloader, fx, hype, sfx, youtube
from .config import Settings
from .utils import fmt_ts, probe_dims, probe_duration, safe_name, which_ffmpeg


class Reporter:
    def log(self, msg): print(msg, flush=True)
    def stage(self, name): pass
    def progress(self, fraction): pass
    def moment(self, m: dict): pass
    def set_series(self, s: dict): pass
    def clip(self, c: dict): pass


def run(url: str, settings: Settings, r: Reporter, stop: threading.Event | None = None):
    which_ffmpeg()
    settings.ensure_dirs()
    sfx.ensure_defaults(settings.sfx_dir, r)
    r.stage("resolve")
    vid = youtube.parse_video_id(url)
    if not vid:
        raise ValueError("Couldn't find a video ID in that link.")
    info = youtube.video_info(url, settings)
    r.log(f"{info['title']}  -  {info['channel'] or '?'}"
          + ("  [LIVE]" if info["is_live"] else f"  [{fmt_ts(info['duration'])}]"))
    if info["is_live"] and settings.mode != "vod":
        return _live(url, info, settings, r, stop)
    return _vod(url, info, settings, r, stop)


def _analyze(analyzer, settings, r, total=None):
    r.stage("hype")
    moments, series = analyzer.detect(total)
    r.set_series(series)
    if not moments:
        raise RuntimeError("No hype peaks found - lower sensitivity or check chat data.")
    for m in moments:
        r.log(f"HYPE peak @ {fmt_ts(m.peak)}  score={m.score:.1f}  "
              f"clip {fmt_ts(m.start)} -> {fmt_ts(m.end)}")
        r.moment({"start": round(m.start, 1), "end": round(m.end, 1),
                  "peak": round(m.peak, 1), "score": round(m.score, 1)})
    return moments


def _dims_for(aspect: str, src_h_after_cap: int) -> tuple[int, int]:
    if aspect == "9:16":
        h = src_h_after_cap
        return int(round(h * 9 / 16)) // 2 * 2, h
    if aspect == "1:1":
        return src_h_after_cap, src_h_after_cap
    return int(round(src_h_after_cap * 16 / 9)) // 2 * 2, src_h_after_cap


def _finish_clip(ctx: dict, start: float, dur: float, idx: int,
                 title: str, score: float, settings: Settings, r: Reporter) -> dict:
    work = ctx["work"]
    src = ctx["media"]

    wav = os.path.join(work, f"c{idx}.wav")
    captions.slice_wav(src, start, dur, wav)

    subs_path = None
    if settings.autocaptions:
        karaoke = settings.caption_style == "karaoke"
        segs = captions.transcribe_audio(wav, settings, r, word_ts=karaoke)
        if segs:
            subs_path = os.path.join(work, f"c{idx}.ass")
            captions.write_ass(segs, subs_path, settings.caption_style,
                               *ctx["dims"])

    events = []
    if settings.sfx_enabled:
        pool = sfx.list_sfx(settings.sfx_dir)
        if pool:
            def pick(name, fb_idx=0):
                for p in pool:
                    if os.path.splitext(os.path.basename(p))[0].lower() == name:
                        return p
                return pool[fb_idx % len(pool)]
            impact = min(max(settings.pre_roll, 0.2), dur - 0.5)
            events.append({"t": impact, "file": pick("airhorn"),
                           "gain_db": settings.sfx_volume_db})
            if impact > 1.8:
                events.append({"t": impact - 1.6, "file": pick("riser", 4),
                               "gain_db": settings.sfx_volume_db - 7})
            if settings.beat_sync:
                kb = beats.strongest_beats(
                    wav, 3, avoid=[impact],
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

    wm = settings.watermark_file if settings.watermark_file and \
        os.path.isfile(settings.watermark_file) else None

    plan = {
        "src": src, "dest": os.path.join(work, f"c{idx}_fin.mp4"),
        "start": start, "dur": dur, "fps": settings.fps,
        "encoder_mode": settings.gpu,
        "aspect": settings.aspect, "smart_reframe": settings.smart_reframe,
        "sendcmd": os.path.join(work, f"c{idx}_cmd.txt"),
        "W": ctx["dims"][0], "H": ctx["dims"][1],
        "look": settings.fx_look, "bloom": settings.bloom,
        "grain": settings.grain, "vignette": settings.vignette,
        "zoom_punch": settings.zoom_punch,
        "zoom_strength": settings.zoom_strength,
        "shake": settings.shake, "impact_t": min(settings.pre_roll, dur * 0.6),
        "beat_sync": settings.beat_sync, "flash_intro": settings.flash_intro,
        "title": settings.title_text.replace("{score}", str(int(score))),
        "progress_bar": settings.progress_bar, "watermark": wm,
        "subs": subs_path, "sfx_events": events, "music": music, "wav": wav,
    }
    fx.render_clip(plan, r)

    fname = f"{safe_name(title)}_{idx + 1:02d}_{int(start)}s.mp4"
    dest = os.path.join(settings.out_dir, fname)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(settings.out_dir,
                            f"{safe_name(title)}_{idx + 1:02d}_{int(start)}s-{n}.mp4")
        n += 1
    shutil.move(plan["dest"], dest)

    clip = {"file": os.path.basename(dest),
            "url": "/clips/" + urllib.parse.quote(os.path.basename(dest)),
            "duration": round(probe_duration(dest), 1),
            "score": round(score, 1), "start": round(start, 1)}
    r.clip(clip)
    r.log(f"saved {fname}")
    return clip


def _vod(url, info, settings: Settings, r: Reporter, stop):
    r.stage("chat")
    msgs = youtube.fetch_chat_replay(
        url, settings, on_batch=lambda n: r.log(f"fetched {n} chat messages"))
    r.log(f"{len(msgs)} messages total")

    analyzer = hype.HypeAnalyzer(settings)
    for m in msgs:
        analyzer.add(m.t, m.text, m.money)
    total = info["duration"] or max(m.t for m in msgs)
    moments = _analyze(analyzer, settings, r, total)

    r.stage("download")
    work = os.path.join(settings.work_dir, info["id"])
    os.makedirs(work, exist_ok=True)
    path, _ = downloader.download_vod(
        url, work, settings, r,
        progress_cb=lambda f: r.progress(0.10 + 0.40 * (f or 0)))

    src_h = min(settings.max_height, probe_dims(path)[1])
    ctx = {"work": work, "media": path, "dims": _dims_for(settings.aspect, src_h)}

    r.stage("clip")
    ordered = sorted(moments, key=lambda x: x.start)
    clips: list = [None] * len(ordered)

    def job(i_m):
        i, m = i_m
        return i, _finish_clip(ctx, m.start, m.end - m.start, i,
                               info["title"], m.score, settings, r)

    workers = max(1, min(int(settings.workers), 3))
    if workers > 1 and len(ordered) > 1:
        r.log(f"rendering {len(ordered)} clips with {workers} workers")
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for done, (i, c) in enumerate(ex.map(job, enumerate(ordered))):
                clips[i] = c
                r.progress(0.52 + 0.46 * (done + 1) / len(ordered))
                if stop is not None and stop.is_set():
                    break
    else:
        for i, m in enumerate(ordered):
            if stop is not None and stop.is_set():
                break
            r.progress(0.52 + 0.46 * i / max(1, len(ordered)))
            _, clips[i] = job((i, m))

    if not settings.keep_temp:
        shutil.rmtree(work, ignore_errors=True)
    r.stage("done")
    r.progress(1.0)
    r.log(f"done - {len([c for c in clips if c])} clip(s)")
    return [c for c in clips if c]


def _spawn_recorder(url, work, settings):
    cmd = [sys.executable, "-m", "yt_dlp", url,
           "-f", f"bv*[height<={settings.max_height}]+ba/b[height<={settings.max_height}]/b",
           "--hls-use-mpegts", "-o", os.path.join(work, "rec.%(ext)s"),
           "--retries", "infinite", "--fragment-retries", "infinite",
           "--concurrent-fragments", "4", "-q"]
    if settings.cookies_browser:
        cmd += ["--cookies-from-browser", settings.cookies_browser]
    return subprocess.Popen(cmd)


def _find_recording(work):
    hits = [p for p in glob.glob(os.path.join(work, "rec.*")) if os.path.isfile(p)]
    return max(hits, key=os.path.getmtime) if hits else None


def _live(url, info, settings: Settings, r: Reporter, stop):
    work = os.path.join(settings.work_dir, f"live_{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    r.stage("record")
    r.log("recording live stream (mpeg-ts)...")
    rec_proc = _spawn_recorder(url, work, settings)
    chat = youtube.LiveChatThread(url, info.get("start_epoch"))
    chat.start()

    analyzer = hype.HypeAnalyzer(settings)
    fired: set = set()
    pending: list = []
    clips: list = []
    idx = 0
    t0 = time.time()

    try:
        while stop is None or not stop.is_set():
            time.sleep(1)
            while True:
                try:
                    m = chat.q.get_nowait()
                except Exception:
                    break
                if 0 <= m.t <= 86400 * 2:
                    analyzer.add(m.t, m.text, m.money)

            rec_file = _find_recording(work)
            if not rec_file:
                if time.time() - t0 > 120:
                    raise RuntimeError("Recorder produced no file.")
                continue
            rec_dur = probe_duration(rec_file)
            if rec_dur <= 0:
                continue

            moments, _ = analyzer.detect(total=rec_dur)
            for m in moments:
                pk = int(m.peak)
                if rec_dur - m.peak < 60 and pk not in fired and \
                        all(abs(pk - f) > settings.cooldown for f in fired):
                    fired.add(pk)
                    pending.append({"start": max(0, pk - settings.pre_roll),
                                    "end": pk - settings.pre_roll + settings.clip_duration,
                                    "score": m.score})
                    r.log(f"LIVE HYPE @ {fmt_ts(m.peak)} - queued")

            ready = [p for p in pending if rec_dur >= p["end"] + 2]
            for p in sorted(ready, key=lambda x: x["start"]):
                pending.remove(p)
                ctx = {"work": work, "media": rec_file,
                       "dims": _dims_for(settings.aspect, settings.max_height)}
                clips.append(_finish_clip(ctx, p["start"], p["end"] - p["start"],
                                          idx, info["title"], p["score"],
                                          settings, r))
                idx += 1

            if chat.dead and chat.q.empty() and rec_proc.poll() is not None:
                break
    finally:
        if rec_proc.poll() is None:
            rec_proc.terminate()
            try:
                rec_proc.wait(timeout=10)
            except Exception:
                rec_proc.kill()
        chat.stop()

    if not settings.keep_temp:
        shutil.rmtree(work, ignore_errors=True)
    r.stage("done")
    r.progress(1.0)
    return clips
