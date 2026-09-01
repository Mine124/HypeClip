from __future__ import annotations
import concurrent.futures as cf
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from . import audiohype, audit, beats, captions, decide, downloader, fx, sfx
from . import scan, sources, youtube
from .captionstyle import CaptionStyle
from .config import Settings
from .utils import (fmt_ts, probe_dims, probe_duration, resolve_bin,
                    safe_name, which_ffmpeg)


# ------------------------------------------------------------------
# Settings coercion helpers. The sources layer can hand back "_SafeBlank"
# placeholders for unset values; raw int()/float()/str ops on them crash
# the pipeline. Every Settings read below goes through these helpers,
# which fall back to the documented defaults instead.
# ------------------------------------------------------------------
def _num(v, default):
    if isinstance(v, bool):
        return float(default)
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else float(default)
    try:
        f = float(str(v).strip())
        return f if f == f else float(default)
    except Exception:
        return float(default)


def _int(v, default):
    return int(round(_num(v, default)))


def _bool(v, default):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return bool(default)


def _str(v, default):
    return v if isinstance(v, str) else default


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
    if isinstance(up, str) and up and os.path.isfile(up):
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
    if not isinstance(aspect, str):
        aspect = "9:16"
    if aspect == "9:16":
        return int(round(src_h * 9 / 16)) // 2 * 2, src_h
    if aspect == "1:1":
        return src_h, src_h
    return int(round(src_h * 16 / 9)) // 2 * 2, src_h


def _finish_clip(ctx, start, dur, idx, title, score, settings, r):
    work, src = ctx["work"], ctx["media"]

    # hardened locals (blank-proof)
    pre_roll = _num(settings.pre_roll, 1.5)
    fps_out = _int(settings.fps, 60)
    zoom_strength = _int(settings.zoom_strength, 20)
    shake_setting = _num(settings.shake, 0.3)
    autocap = _bool(settings.autocaptions, True)
    ttext = _str(getattr(settings, "title_text", ""), "")
    score_n = _num(score, 5.0)

    # ================= HOOK PASS =================
    probe_wav = os.path.join(work, f"c{idx}_probe.wav")
    captions.slice_wav(src, start, dur, probe_wav)
    hook_delta, hook_why = 0.0, "n/a"
    segs = []
    if autocap:
        segs = captions.transcribe_audio(probe_wav, settings, r)
        try:
            from . import hooks
            hook_delta, hook_why = hooks.best_trim(segs, cur_dur=dur)
        except Exception as e:  # noqa: BLE001
            hook_why = f"skipped ({e})"
    if hook_delta >= 0.6:
        start += hook_delta
        dur -= hook_delta
        captions.slice_wav(src, start, dur, probe_wav)
        segs = [s for s in segs if s["end"] > hook_delta]
        for s in segs:
            s["start"] = max(0.0, s["start"] - hook_delta)
            s["end"] = max(0.05, s["end"] - hook_delta)
            if s.get("words"):
                s["words"] = [w for w in s["words"]
                              if w.get("e", 0) > hook_delta]
                for w in s["words"]:
                    w["s"] -= hook_delta; w["e"] -= hook_delta
        r.log(f"🪝 hook trim -{hook_delta:.1f}s ({hook_why})")
    elif autocap:
        r.log(f"🪝 hook kept as-is ({hook_why})")

    wav = os.path.join(work, f"c{idx}.wav")
    shutil.copyfile(probe_wav, wav)

    subs_path = None
    caption_texts = ""
    if autocap and segs:
        caption_texts = " ".join(s.get("text", "") for s in segs)
    pre_cat = "highlight"
    if caption_texts:
        try:
            from . import intel
            pre_cat, _tags = intel.classify(caption_texts)
        except Exception:
            pass

    # ================= DEAD-AIR SURGEON (with protection) =================
    mapping = None
    if dur >= 30:
        try:
            prot = decide.find_protected_pauses(wav)
            if prot:
                r.log(f"🛡 protecting {len(prot)} comedic/suspense "
                      f"pause(s) from the surgeon")
            pauses = decide.find_dead_air(wav, protected=prot)
            removable = sum(b - a for a, b in pauses)
            if 0.8 <= removable <= dur * 0.30:
                prep = os.path.join(work, f"c{idx}_prep.mp4")
                built, mapping = decide.build_trimmed(
                    src, prep, start, dur, pauses, protected=prot)
                if built:
                    r.log(f"✂ removed {removable:.0f}s of dead air "
                          f"({len(pauses)} pauses)")
                    dur = mapping["new_dur"]
                    start = 0.0
                    src = built
                    if segs:
                        for s in segs:
                            s["start"] = decide.remap(s["start"], mapping)
                            s["end"] = decide.remap(s["end"], mapping)
                            if s.get("words"):
                                for w in s["words"]:
                                    w["s"] = decide.remap(w["s"], mapping)
                                    w["e"] = decide.remap(w["e"], mapping)
                        segs = [s for s in segs if s["end"] > 0.1]
        except Exception as e:  # noqa: BLE001
            r.log(f"(dead-air surgery skipped: {e})")

    # ---- captions ----
    if autocap and segs:
        cs = CaptionStyle.load_active()
        if pre_cat == "reaction":
            cs.d["effect"] = "fade"
            r.log("🧭 captions calmed (fade) - emotional tone")
        subs_path = os.path.join(work, f"c{idx}.ass")
        captions.write_ass(segs, subs_path, cs, *ctx["dims"])

    # ---- SFX taste engine (transient-aligned) ----
    events: list = []
    if _bool(settings.sfx_enabled, True):
        pool = sfx.list_sfx(settings.sfx_dir)
        if pool:
            try:
                events, notes = decide.sfx_plan(
                    wav, caption_texts, settings, r, pool,
                    protected=decide.find_protected_pauses(wav))
                for nt in notes:
                    r.log("🧭 " + nt)
            except Exception as e:  # noqa: BLE001
                r.log(f"(sfx engine fallback: {e})")
                pool = pool
                impact_fb = min(max(pre_roll, 0.2), dur - 0.5)
                if pool:
                    events = [{"t": impact_fb, "file": pool[0],
                               "gain_db": _num(settings.sfx_volume_db, -6)}]

    music = None
    music_file = getattr(settings, "music_file", "")
    if isinstance(music_file, str) and music_file \
            and os.path.isfile(music_file):
        music = {"file": music_file,
                 "volume_db": _num(settings.music_volume_db, -18),
                 "duck": _bool(settings.duck_music, True)}

    sub = None
    sub_name = getattr(settings, "sub_name", "")
    if isinstance(sub_name, str) and sub_name:
        from .config import DATA_DIR
        sp = os.path.join(DATA_DIR, "subs",
                          "".join(c for c in sub_name.lower()
                                  if c.isalnum() or c in "-_ ")[:32] + ".png")
        if os.path.isfile(sp):
            sub_dur = _num(settings.sub_dur, 3.0)
            sub = {"file": sp, "dur": sub_dur,
                   "pos": _str(settings.sub_pos, "bottom-right"),
                   "t0": 0.5 if _str(settings.sub_when, "start") == "start"
                        else max(0.3, dur - sub_dur - 0.3)}

    wm_file = getattr(settings, "watermark_file", "")
    wm = wm_file if isinstance(wm_file, str) and wm_file \
        and os.path.isfile(wm_file) else None

    # ---- PACING DOCTRINE (continuous intensity) ----
    doc = decide.pacing_plan(pre_cat, 70)
    r.log(f"🧭 doctrine[{pre_cat}] ({doc.get('intensity', 0.5)}): "
          f"{doc['note']}")
    zoom_on = _bool(settings.zoom_punch, True) and doc["zoom"]
    do_punch, amp, zreason = decide.punch_decision(
        pre_cat, int(_clamp(score_n, 0, 99)), doc.get("intensity", 0.5))
    if do_punch and doc["zoom"]:
        zoom_on = True
        r.log(f"🧭 punch-in: {zreason} ({int(amp * 100)}%)")
    shake_v = shake_setting if doc["shake"] else 0.0
    flash_v = _bool(settings.flash_intro, False) and doc["flash"]
    bloom_v = _bool(settings.bloom, False) and doc["bloom"]
    grain_v = _bool(settings.grain, False) and doc["grain"]
    vig_v = _bool(settings.vignette, False) and doc["vignette"]
    beat_v = _bool(settings.beat_sync, True) and doc["beat"]

    plan = {
        "src": src, "dest": os.path.join(work, f"c{idx}_fin.mp4"),
        "start": start, "dur": dur, "fps": fps_out,
        "encoder_mode": _bool(settings.gpu, True),
        "aspect": _str(settings.aspect, "9:16"),
        "smart_reframe": (not ctx.get("no_reframe"))
        and _bool(settings.smart_reframe, True),
        "sendcmd": os.path.join(work, f"c{idx}_cmd.txt"),
        "W": ctx["dims"][0], "H": ctx["dims"][1],
        "enhance": _bool(getattr(settings, "enhance", False), False),
        "enhance_mode": _str(getattr(settings, "enhance_mode", "light"),
                             "light"),
        "look": _str(settings.fx_look, "clean"), "bloom": bloom_v,
        "grain": grain_v, "vignette": vig_v,
        "zoom_punch": zoom_on, "zoom_strength": zoom_strength,
        "shake": shake_v,
        "impact_t": min(pre_roll, dur * 0.6),
        "beat_sync": beat_v, "flash_intro": flash_v,
        "title": ttext.replace("{score}", str(int(_clamp(score_n, 0, 99)))),
        "progress_bar": _bool(settings.progress_bar, True),
        "watermark": wm,
        "subscribe": sub,
        "subs": subs_path, "sfx_events": events, "music": music,
        "wav": wav,
    }

    # ---- persist the full render plan (powers the effect toggle panel) ----
    plan_file = ""
    try:
        plan_file = os.path.join(work, f"c{idx}_plan.json")
        json.dump(plan, open(plan_file, "w", encoding="utf-8"), default=str)
    except Exception:
        plan_file = ""

    trk = (ctx.get("tracks_by_index") or {}).get(idx)
    if trk and not mapping and not ctx.get("no_reframe"):
        plan["track_cmd"] = trk["cmd_file"]
    elif trk and mapping:
        r.log("(eagle-eye skipped on this clip: timeline was surgically "
              "edited)")

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

    # ---- clean reference (no effects, for side-by-side review) ----
    clean_url, clean_name = "", ""
    try:
        stem = os.path.splitext(os.path.basename(dest))[0]
        clean_name = stem + "_clean.mp4"
        clean_dest = os.path.join(settings.out_dir, clean_name)
        clean_src = ctx.get("clean_src")
        if clean_src and os.path.isfile(clean_src):
            shutil.copyfile(clean_src, clean_dest)
        else:
            W, H = ctx["dims"]
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H}")
            cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error",
                   "-ss", f"{float(start):.3f}", "-t", f"{float(dur):.3f}",
                   "-i", src, "-vf", vf,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                   "-movflags", "+faststart", clean_dest]
            p = subprocess.run(cmd, capture_output=True, text=True,
                               errors="replace", timeout=900)
            if p.returncode != 0 or not os.path.isfile(clean_dest):
                raise RuntimeError((p.stderr or "")[-200:])
        clean_url = "/clips/" + urllib.parse.quote(clean_name)
    except Exception as e:  # noqa: BLE001
        r.log(f"(clean reference skipped: {e})")

    clip = {"file": os.path.basename(dest),
            "url": "/clips/" + urllib.parse.quote(os.path.basename(dest)),
            "duration": round(probe_duration(dest), 1),
            "score": round(score_n, 1), "start": round(start, 1)}

    if clean_url:
        clip["clean"] = clean_url
        clip["clean_file"] = clean_name
    clip["hook"] = (f"-{hook_delta:.1f}s trimmed ({hook_why})"
                    if hook_delta >= 0.6 else f"kept as-is ({hook_why})")
    clip["created"] = time.strftime("%H:%M")
    if plan_file:
        clip["plan_file"] = plan_file

    # ---- intelligence pass ----
    try:
        from . import intel
        stem = os.path.splitext(os.path.basename(dest))[0]
        info_i = intel.finalize(
            wav=wav, texts=caption_texts, src_title=title,
            peak_score=score_n, start=start, dur=dur,
            video=dest, impact_t=min(plan["impact_t"], dur - 0.5),
            out_dir=settings.out_dir, stem=stem)
        clip.update(info_i)
        r.log(f"clip verdict: [{info_i['category']}] "
              f"viral={info_i['viral']}/100 "
              f"({' · '.join(info_i['reasons'])})")
    except Exception as e:  # noqa: BLE001
        r.log(f"(intelligence pass skipped: {e})")

    # ---- retention prediction + critic ----
    try:
        db = intel.audio_db(wav)
        feats = decide.features_from_db(db, 0.0, dur, score_n, caption_texts)
        rt = decide.predict(feats)
        clip["retention"] = rt
        issues = decide.critique(
            feats, rt,
            [k for k, on in (("zoom", zoom_on), ("shake", shake_v > 0),
                             ("flash", flash_v), ("bloom", bloom_v),
                             ("grain", grain_v)) if on],
            pre_cat)
        if issues:
            r.log("🔍 critic: " + " · ".join(issues))
        r.log(f"📈 predicted: watch {rt['avg_watch_pct']}% · "
              f"complete {rt['completion']}% · swipe {rt['swipe_prob']}%"
              + (" · calibrated" if rt["calibrated"] else ""))
    except Exception as e:  # noqa: BLE001
        r.log(f"(prediction skipped: {e})")

    # ================= RENDER AUDIT + QUARANTINE GATE =================
    try:
        rep_a = audit.audit_clip(dest, expected_dur=dur)
        clip["audit"] = rep_a
        if rep_a["issues"]:
            r.log("🔍 audit: " + " · ".join(rep_a["issues"]))
        if rep_a["quarantine"]:
            qp = audit.quarantine_move(
                dest, "; ".join(rep_a["issues"]) or "low quality score")
            r.log(f"🚫 quarantined -> Data\\quarantine\\"
                  f"{os.path.basename(qp)} (quality gate failed)")
            clip["quarantined"] = True
        else:
            r.log("🔍 audit passed")
    except Exception as e:  # noqa: BLE001
        r.log(f"(audit skipped: {e})")

    r.clip(clip)
    r.log(f"saved {os.path.basename(clip['file'])}")
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
    r.log("fast pass: lightweight preview first - HD fetched per-clip")
    path, _ = downloader.download_proxy(
        url, work, settings, r,
        progress_cb=lambda f: r.progress(0.02 + 0.38 * (f or 0)))
    dur = probe_duration(path)
    r.media_ready(key, os.path.basename(path), dur)
    # FIX: mark the media as a proxy so the per-clip HD fetch actually
    # runs below (previously dead code - clips rendered from the
    # low-res preview even though HD was promised).
    return _scan_and_render(path, dur, info["title"],
                            settings, r, stop, url=url,
                            media_is_proxy=True)


def _scan_and_render(media_path, dur, title, settings, r, stop,
                     url=None, media_is_proxy=False):
    """select -> scan -> intelligence -> [review unless autopilot] ->
    per-clip HD fetch -> face layout -> render -> audit."""
    src_h = min(_int(settings.max_height, 1080), probe_dims(media_path)[1])
    ctx = {"work": os.path.dirname(media_path), "media": media_path,
           "dims": _dims_for(settings.aspect, src_h)}
    proxy = media_is_proxy
    track_point = None

    # ---- user-guided face layout (set via the FACE REGION picker) ----
    face_rect = getattr(r, "face_rect", None)
    try:
        if isinstance(face_rect, (list, tuple)) and len(face_rect) == 4:
            face_rect = tuple(float(v) for v in face_rect)
        else:
            face_rect = None
    except Exception:
        face_rect = None
    if face_rect:
        r.log("👤 face layout ON - facecam top band, gameplay bottom band")

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
                r, sample_fps=_num(getattr(settings, "scan_fps", 6), 6.0))
            moments = _analyze(analyzer, settings, r, dur)

        # ---- smart boundaries + hooks ----
        try:
            from . import intel
            intel.adjust_boundaries(moments, media_path, settings, r)
        except Exception as e:  # noqa: BLE001
            r.log(f"(boundaries default: {e})")

        # ---- retention-guided ending tightening ----
        try:
            from . import intel
            dbx = intel.audio_db(media_path)
            for m in moments[:_int(settings.max_clips, 20)]:
                fa = decide.features_from_db(dbx, m.start,
                                             m.end - m.start, m.score)
                alt_end = m.end - min(6.0, (m.end - m.start) * 0.18)
                if alt_end - m.start > 15:
                    fb = decide.features_from_db(dbx, m.start,
                                                 alt_end - m.start, m.score)
                    if decide.predict(fb)["score"] > \
                            decide.predict(fa)["score"] + 2:
                        m.end = round(alt_end, 1)
                        r.log(f"🧭 tightened ending @ {fmt_ts(m.end)}")
        except Exception as e:  # noqa: BLE001
            r.log(f"(boundary revision skipped: {e})")
        r.progress(0.50)

        # ---- Eagle-Eye camera follow ----
        if sel.get("mode") == "track" and sel.get("point"):
            try:
                from . import tracker
                pt = sel["point"]
                ordered_m = sorted(
                    moments,
                    key=lambda x: x.start)[:_int(settings.max_clips, 20)]
                tracks = {}
                for i, m in enumerate(ordered_m):
                    outp = os.path.join(ctx["work"], f"trk_{i}.txt")
                    trk = tracker.build_track(
                        media_path, m.start, m.end - m.start,
                        (float(pt.get("x", 0.5)),
                         float(pt.get("y", 0.5))),
                        _str(settings.aspect, "9:16"), outp)
                    if trk:
                        tracks[i] = trk
                ctx["tracks_by_index"] = tracks
                ai_used = any(t.get("ai") for t in tracks.values())
                r.log(f"Eagle-Eye: camera follow built for "
                      f"{len(tracks)}/{len(ordered_m)} clips"
                      + (" (AI)" if ai_used else " (motion-fallback)"))
            except Exception as e:  # noqa: BLE001
                r.log(f"(tracking skipped: {e})")

        r.review([{"start": round(m.start, 1), "end": round(m.end, 1),
                   "peak": round(m.peak, 1), "score": round(m.score, 1)}
                  for m in moments],
                 getattr(r, "last_series", None))

        if getattr(settings, "auto_render", False):
            r.log("autopilot: peaks locked in - rendering now")
            break
        cmd = r.wait_command()
        if cmd[0] == "rescan":
            settings.hype_threshold = _num(cmd[1], 3.5)
            continue
        break

    r.stage("clip")
    ordered = sorted(moments,
                     key=lambda m: m.start)[:_int(settings.max_clips, 20)]
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
                r.log(f"(HD segment {i + 1} failed: {e}) - "
                      f"rendering from preview quality")

    clips: list = [None] * len(ordered)
    used_layout: dict = {}

    def job(im):
        i, m = im
        seg = hd.get(i)
        if seg:
            sdur = min(probe_duration(seg), m.end - m.start + 0.5)
            c = {"work": os.path.dirname(seg), "media": seg,
                 "dims": _dims_for(settings.aspect,
                                   min(_int(settings.max_height, 1080),
                                       probe_dims(seg)[1]))}
            s, d = 0.0, min(sdur, m.end - m.start)
        else:
            c = ctx
            s, d = m.start, m.end - m.start
        if face_rect:
            try:
                from . import layout
                comp = os.path.join(c["work"], f"c{i}_comp.mp4")
                made = layout.build_composite(c["media"], s, d,
                                              face_rect, comp, r)
                if made:
                    cw, ch = probe_dims(made)
                    c = {"work": c["work"], "media": made,
                         "dims": (cw, ch), "clean_src": made,
                         "no_reframe": True}
                    s, d = 0.0, probe_duration(made)
                    used_layout[i] = True
                    r.log(f"👤 clip {i + 1}: face-top layout composited")
            except Exception as e:  # noqa: BLE001
                r.log(f"(face layout skipped on clip {i + 1}: {e})")
        return i, _finish_clip(c, s, d, i, title, m.score, settings, r)

    workers = max(1, min(_int(settings.workers, 3), 3))
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
    mh = _int(settings.max_height, 1080)
    cmd = [sys.executable, "-m", "yt_dlp", url,
           "-f", f"bv*[height<={mh}]+ba/b[height<={mh}]/b",
           "--hls-use-mpegts", "-o", os.path.join(work, "rec.%(ext)s"),
           "--retries", "infinite", "--fragment-retries", "infinite",
           "--concurrent-fragments", "4", "-q"]
    cb = getattr(settings, "cookies_browser", "")
    if isinstance(cb, str) and cb:
        cmd += ["--cookies-from-browser", cb]
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
    live_cd = _num(settings.cooldown, 8.0)
    live_pre = _num(settings.pre_roll, 1.5)
    live_dur = _num(settings.clip_duration, 90.0)
    live_h = _int(settings.max_height, 1080)

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
                        all(abs(pk - f) > live_cd for f in fired):
                    fired.add(pk)
                    pending.append(
                        {"start": max(0, pk - live_pre),
                         "end": pk - live_pre + live_dur,
                         "score": m.score})
                    r.log(f"LIVE HYPE @ {fmt_ts(m.peak)} - queued")

            ready = [p for p in pending if rec_dur >= p["end"] + 2]
            for p in sorted(ready, key=lambda x: x["start"]):
                pending.remove(p)
                ctx = {"work": work, "media": rec_file,
                       "dims": _dims_for(_str(settings.aspect, "9:16"),
                                         live_h)}
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

    if not _bool(getattr(settings, "keep_temp", False), False):
        shutil.rmtree(work, ignore_errors=True)
    r.stage("done")
    r.progress(1.0)
    return clips
