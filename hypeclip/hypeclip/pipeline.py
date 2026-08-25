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

from . import audiohype, beats, captions, decide, downloader, fx, sfx
from . import scan, sources, youtube
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


def run(url: str, settings: Settings, r: Reporter,
        stop: threading.Event | None = None):
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
    r.log(f"{info['title']}  -  {info['channel'] or '?'}"
          + ("  [LIVE]" if info["is_live"]
             else f"  [{fmt_ts(info['duration'])}]"))

    if info["is_live"]:
        if plat["platform"] == "tiktok":
            raise ValueError("TikTok LIVE isn't supported - paste a posted "
                             "TikTok video or upload the file yourself.")
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

    # ---- preliminary category (drives punch/SFX taste) ----
    pre_cat = "highlight"
    try:
        from . import intel
        if caption_texts:
            pre_cat, _tags = intel.classify(caption_texts)
    except Exception:
        pass

    # ---- decision-engine SFX (taste + restraint) ----
    events: list = []
    if settings.sfx_enabled:
        pool = sfx.list_sfx(settings.sfx_dir)
        if pool:
            try:
                events, notes = decide.sfx_plan(
                    wav, caption_texts, settings, r, pool)
                for nt in notes:
                    r.log("🧭 " + nt)
            except Exception as e:  # noqa: BLE001
                r.log(f"(sfx engine fallback: {e})")
                pool = [p for p in pool]
                if pool:
                    impact = min(max(settings.pre_roll, 0.2), dur - 0.5)
                    events = [{"t": impact, "file": pool[0],
                               "gain_db": settings.sfx_volume_db}]
    if settings.beat_sync:
        try:
            kb = beats.strongest_beats(wav, 3, avoid=[],
                                       window=(0.4, max(0.5, dur - 0.8)))[:3]
            alt = ["vine_boom", "notification", "womp_womp"]
            pool = sfx.list_sfx(settings.sfx_dir)
            for j, bt in enumerate(kb):
                p = pool[j + 1] if len(pool) > j + 1 else (pool[0] if pool
                                                           else None)
                if p:
                    events.append({"t": bt, "file": p,
                                   "gain_db": settings.sfx_volume_db - 8})
        except Exception:
            pass

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
                                  if c.isalnum() or c in "-_ ")[:32] + ".png")
        if os.path.isfile(sp):
            sub = {"file": sp, "dur": settings.sub_dur,
                   "pos": settings.sub_pos,
                   "t0": 0.5 if settings.sub_when == "start"
                        else max(0.3, dur - settings.sub_dur - 0.3)}

    wm = settings.watermark_file if settings.watermark_file and \
        os.path.isfile(settings.watermark_file) else None

    # ---- decision-engine punch-in ----
    do_punch, amp, zreason = decide.punch_decision(
        pre_cat, int(_clamp(score, 0, 99)))
    zoom_on = settings.zoom_punch or do_punch
    zoom_str = max(settings.zoom_strength, amp) if do_punch \
        else settings.zoom_strength
    if do_punch:
        r.log(f"🧭 punch-in: {zreason} ({int(amp * 100)}%)")

    plan = {
        "src": src, "dest": os.path.join(work, f"c{idx}_fin.mp4"),
        "start": start, "dur": dur, "fps": settings.fps,
        "encoder_mode": settings.gpu, "aspect": settings.aspect,
        "smart_reframe": settings.smart_reframe,
        "sendcmd": os.path.join(work, f"c{idx}_cmd.txt"),
        "W": ctx["dims"][0], "H": ctx["dims"][1],
        "enhance": bool(getattr(settings, "enhance", False)),
        "enhance_mode": getattr(settings, "enhance_mode", "light"),
        "look": settings.fx_look, "bloom": settings.bloom,
        "grain": settings.grain, "vignette": settings.vignette,
        "zoom_punch": zoom_on, "zoom_strength": zoom_str,
        "shake": settings.shake,
        "impact_t": min(settings.pre_roll, dur * 0.6),
        "beat_sync": settings.beat_sync,
        "flash_intro": settings.flash_intro,
        "title": settings.title_text.replace("{score}", str(int(score))),
        "progress_bar": settings.progress_bar, "watermark": wm,
        "subscribe": sub,
        "subs": subs_path, "sfx_events": events, "music": music,
        "wav": wav,
    }

    trk = (ctx.get("tracks_by_index") or {}).get(idx)
    if trk:
        plan["track_cmd"] = trk["cmd_file"]

    fx.render_clip(plan, r)

    fname = f"{safe_name(title)}_{idx + 1:02d}_{int(start)}s.mp4"
    dest = os.path.join(settings.out_dir, fname)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(
            settings.out_dir,
            f"{safe_name(title)}_{idx + 1:02d}_{int(start)}s-{n}.mp4")
        n += 1
    shutil.move(plan["dest"], dest)

    clip = {"file": os.path.basename(dest),
            "url": "/clips/" + urllib.parse.quote(os.path.basename(dest)),
            "duration": round(probe_duration(dest), 1),
            "score": round(score, 1), "start": round(start, 1)}

    try:
        from . import intel
        stem = os.path.splitext(os.path.basename(dest))[0]
        info_i = intel.finalize(
            wav=wav, texts=caption_texts, src_title=title,
            peak_score=score, start=start, dur=dur,
            video=dest, impact_t=min(plan["impact_t"], dur - 0.5),
            out_dir=settings.out_dir, stem=stem)
        clip.update(info_i)
        r.log(f"clip verdict: [{info_i['category']}] "
              f"viral={info_i['viral']}/100 "
              f"({' · '.join(info_i['reasons'])})")
        if info_i["meta"].get("title"):
            r.log(f"suggested title: {info_i['meta']['title']} "
                  f"{info_i['meta']['hashtags']}")
    except Exception as e:  # noqa: BLE001
        r.log(f"(intelligence pass skipped: {e})")

    # ---- retention prediction ----
    try:
        db = intel.audio_db(wav)
        feats = decide.features_from_db(db, 0.0, dur, score, caption_texts)
        clip["retention"] = decide.predict(feats)
        rt = clip["retention"]
        r.log(f"📈 predicted: watch {rt['avg_watch_pct']}% · "
              f"complete {rt['completion']}% · swipe {rt['swipe_prob']}%"
              + (" · calibrated on your history" if rt["calibrated"] else ""))
    except Exception as e:  # noqa: BLE001
        r.log(f"(prediction skipped: {e})")

    r.clip(clip)
    r.log(f"saved {fname}")
    return clip


def _clamp(v, a, b):
    return max(a, min(b, v))


def _local_file(path, settings, r, stop):
    r.stage("resolve")
    title = os.path.splitext(os.path.basename(path))[0]
    r.log(f"local file: {title}  [{fmt_ts(probe_duration(path))}]")
    dur = probe_duration(path)
    key = safe_name(title) or "upload"
    work = os.path.join(settings.work_dir, key)
    os.makedirs(work, exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".mp4"
    dest = os.path.join(work, key + ext)
    if os.path.abspath(dest) != os.path.abspath(path):
        shutil.copyfile(path, dest)
    r.media_ready(key, os.path.basename(dest), dur)
    return _scan_and_render(dest, dur, title, settings, r, stop, url=None)


def _vod(url, info, plat, settings, r, stop):
    key = info.get("id") or safe_name(info.get("title") or "media")
    work = os.path.join(settings.work_dir, key)
    os.makedirs(work, exist_ok=True)

    if os.getenv("HYPECLIP_FULL_DOWNLOAD") == "1":
        r.log("full-download mode (HYPECLIP_FULL_DOWNLOAD=1)")
        path, _ = downloader.download_vod(
            url, work, settings, r,
            progress_cb=lambda f: r.progress(0.02 + 0.43 * (f or 0)))
        dur = probe_duration(path)
        r.media_ready(key, os.path.basename(path), dur)
        return _scan_and_render(path, dur, info["title"],
                                settings, r, stop, url=None)

    r.log("fast pass: lightweight preview first - HD is fetched per-clip")
    path, _ = downloader.download_proxy(
        url, work, settings, r,
        progress_cb=lambda f: r.progress(0.02 + 0.38 * (f or 0)))
    dur = probe_duration(path)
    r.media_ready(key, os.path.basename(path), dur)
    return _scan_and_render(path, dur, info["title"],
                            settings, r, stop, url=url)


def _scan_and_render(media_path, dur, title, settings, r, stop,
                     url=None, media_is_proxy=False):
    """select -> scan -> intelligence -> [review unless autopilot] ->
    per-clip HD fetch -> decision-driven render."""
    src_h = min(settings.max_height, probe_dims(media_path)[1])
    ctx = {"work": os.path.dirname(media_path), "media": media_path,
           "dims": _dims_for(settings.aspect, src_h)}
    proxy = media_is_proxy
    track_point = None

    moments = []
    while True:
        sel = r.wait_selection()
        if stop is not None and stop.is_set():
            return []
        track_point = sel.get("point") \
            if sel.get("mode") == "track" else None
        r.stage("scan")
        r.progress(0.44)
        if sel.get("mode") == "audio":
            analyzer = audiohype.AudioHypeAnalyzer(settings, media_path)
            moments = _analyze(analyzer, settings, r, dur)
        else:
            rc = sel.get("rect") or {}
            analyzer = scan.ScrollScanner(
                settings, media_path,
                (rc.get("x", 0.6), rc.get("y", 0),
                 rc.get("w", 0.4), rc.get("h", 1.0)),
                r, sample_fps=float(getattr(settings, "scan_fps", 6)))
            moments = _analyze(analyzer, settings, r, dur)

        try:
            from . import intel
            intel.adjust_boundaries(moments, media_path, settings, r)
        except Exception as e:  # noqa: BLE001
            r.log(f"(boundaries default: {e})")

        # decision-engine micro-revision: try tight vs loose ending,
        # keep whichever predicts better retention
        try:
            from . import intel
            db = intel.audio_db(media_path)
            for m in moments[:int(settings.max_clips)]:
                feats_a = decide.features_from_db(db, m.start,
                                                  m.end - m.start, m.score)
                alt_end = m.end - min(6.0, (m.end - m.start) * 0.18)
                if alt_end - m.start > 15:
                    feats_b = decide.features_from_db(
                        db, m.start, alt_end - m.start, m.score)
                    if decide.predict(feats_b)["score"] > \
                            decide.predict(feats_a)["score"] + 2:
                        m.end = round(alt_end, 1)
                        r.log(f"🧭 tightened ending @ {fmt_ts(m.end)} "
                              f"(predicts better retention)")
        except Exception as e:  # noqa: BLE001
            r.log(f"(boundary revision skipped: {e})")
        r.progress(0.50)

        r.review([{"start": round(m.start, 1), "end": round(m.end, 1),
                   "peak": round(m.peak, 1), "score": round(m.score, 1)}
                  for m in moments],
                 getattr(r, "last_series", None))

        if getattr(settings, "auto_render", False):
            r.log("autopilot: peaks locked in - rendering now")
            break

        cmd = r.wait_command()
        if cmd[0] == "rescan":
            settings.hype_threshold = float(cmd[1])
            continue
        break

    r.stage("clip")
    ordered = sorted(moments, key=lambda m: m.start)[:int(settings.max_clips)]

    # ---- per-clip HD segments (proxy mode only) ----
    hd: dict = {}
    if url and proxy:
        r.stage("fetch-hd")
        for i, m in enumerate(ordered):
            try:
                hd[i] = downloader.download_segment(
                    url, max(0.0, m.start), m.end,
                    ctx["work"], settings, r, idx=i)
                r.progress(0.50 + 0.08 * (i + 1) / max(1, len(ordered)))
            except Exception as e:  # noqa: BLE001
                r.log(f"(HD segment {i + 1} failed: {e}) "
                      f"- rendering from preview quality")
    elif url:
        r.log("(proxy off - rendering from the full download)")

    clips: list = [None] * len(ordered)

    def job(im):
        i, m = im
        seg = hd.get(i)
        if seg:
            sdur = min(probe_duration(seg), m.end - m.start + 0.5)
            c = {"work": os.path.dirname(seg), "media": seg,
                 "dims": _dims_for(settings.aspect,
                                   min(settings.max_height,
                                       probe_dims(seg)[1]))}
            s, d = 0.0, min(sdur, m.end - m.start)
        else:
            c = ctx
            s, d = m.start, m.end - m.start

        # Eagle-Eye camera follow (built on the actual render source)
        if track_point:
            try:
                from . import tracker
                outp = os.path.join(c["work"], f"trk_{i}.txt")
                trk = tracker.build_track(
                    c["media"], s, d,
                    (float(track_point.get("x", 0.5)),
                     float(track_point.get("y", 0.5))),
                    settings.aspect, outp)
                if trk:
                    c["tracks_by_index"] = {i: trk}
                    r.log(f"Eagle-Eye: clip {i + 1} camera follow ready"
                          + (" (AI)" if trk["ai"]
                             else " (motion-fallback)"))
            except Exception as e:  # noqa: BLE001
                r.log(f"(tracking skipped for clip {i + 1}: {e})")

        return i, _finish_clip(c, s, d, i, title, m.score, settings, r)

    workers = max(1, min(int(settings.workers), 3))
    if workers > 1 and len(ordered) > 1:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for done, (i, c) in enumerate(ex.map(job, enumerate(ordered))):
                clips[i] = c
                r.progress(0.58 + 0.40 * (done + 1) / len(ordered))
    else:
        for i, m in enumerate(ordered):
            r.progress(0.58 + 0.40 * i / max(1, len(ordered)))
            _, clips[i] = job((i, m))

    r.stage("done")
    r.progress(1.0)
    return [cl for cl in clips if cl]


def _spawn_recorder(url, work, settings):
    cmd = [sys.executable, "-m", "yt_dlp", url,
           "-f", f"bv*[height<={settings.max_height}]+ba/"
                 f"b[height<={settings.max_height}]/b",
           "--hls-use-mpegts", "-o", os.path.join(work, "rec.%(ext)s"),
           "--retries", "infinite", "--fragment-retries", "infinite",
           "--concurrent-fragments", "4", "-q"]
    if settings.cookies_browser:
        cmd += ["--cookies-from-browser", settings.cookies_browser]
    return subprocess.Popen(cmd)


def _find_recording(work):
    hits = [p for p in glob.glob(os.path.join(work, "rec.*"))
            if os.path.isfile(p)]
    return max(hits, key=os.path.getmtime) if hits else None


def _live(url, info, settings, r, stop):
    work = os.path.join(settings.work_dir, f"live_{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    r.stage("record")
    rec_proc = _spawn_recorder(url, work, settings)
    chat = youtube.LiveChatThread(url, info.get("start_epoch"))
    chat.start()

    from . import hype
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
                        all(abs(pk - f) > settings.cooldown
                            for f in fired):
                    fired.add(pk)
                    pending.append(
                        {"start": max(0, pk - settings.pre_roll),
                         "end": pk - settings.pre_roll
                                + settings.clip_duration,
                         "score": m.score})
                    r.log(f"LIVE HYPE @ {fmt_ts(m.peak)} - queued")

            ready = [p for p in pending if rec_dur >= p["end"] + 2]
            for p in sorted(ready, key=lambda x: x["start"]):
                pending.remove(p)
                ctx = {"work": work, "media": rec_file,
                       "dims": _dims_for(settings.aspect,
                                         settings.max_height)}
                clips.append(_finish_clip(ctx, p["start"],
                                          p["end"] - p["start"],
                                          idx, info["title"], p["score"],
                                          settings, r))
                idx += 1

            if chat.dead and chat.q.empty() \
                    and rec_proc.poll() is not None:
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
