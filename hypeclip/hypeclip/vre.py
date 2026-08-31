"""Viral Reverse Engineering Engine (VRE).

Paste a viral video URL -> VRE deconstructs HOW it is edited (cut rhythm,
punch-ins, flashes, caption coverage, SFX cadence, energy curve, hook
shape) and distills it into an abstract EDITING BLUEPRINT - numeric style
metrics only, never copied assets. A blueprint can be activated so the
next clipping job adopts that style via HypeClip's existing settings.

Self-contained (numpy + opencv + bundled ffmpeg), fully guarded: any
failure degrades to "no blueprint", never a crashed pipeline.
"""
from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import threading
import uuid

import numpy as np

try:
    from .config import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "Data")

BP_DIR = os.path.join(DATA_DIR, "vre")
WORK_DIR = os.path.join(DATA_DIR, "work", "vre")
ACTIVE_PATH = os.path.join(BP_DIR, "_active.json")
_MAX_ANALYZE_S = 480.0  # cap: analyze at most the first 8 minutes

_STATE = {"state": "idle", "frac": 0.0, "error": None,
          "blueprint": None, "log": []}


def _log(m):
    _STATE["log"] = (_STATE["log"] + [str(m)])[-60:]
    print("[vre] " + str(m), flush=True)


def _ensure_dirs():
    for d in (BP_DIR, WORK_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def _bin(name):
    try:
        from .utils import resolve_bin
        return resolve_bin(name)
    except Exception:
        return name


# ---------------------------------------------------------------- storage
def _bp_path(bid: str) -> str:
    return os.path.join(BP_DIR, "bp_" + bid + ".json")


def list_blueprints() -> list:
    _ensure_dirs()
    out = []
    for f in sorted(glob.glob(os.path.join(BP_DIR, "bp_*.json")),
                    key=os.path.getmtime, reverse=True):
        try:
            bp = json.load(open(f, encoding="utf-8"))
            out.append({"id": bp.get("id"), "name": bp.get("name"),
                        "source_url": bp.get("source_url", ""),
                        "title": bp.get("title", ""),
                        "profile": bp.get("profile", {}),
                        "created": bp.get("created", "")})
        except Exception:
            pass
    return out


def get_blueprint(bid: str):
    try:
        return json.load(open(_bp_path(os.path.basename(bid)),
                              encoding="utf-8"))
    except Exception:
        return None


def delete_blueprint(bid: str) -> bool:
    try:
        p = _bp_path(os.path.basename(bid))
        if os.path.isfile(p):
            os.remove(p)
        act = active_id()
        if act == bid:
            deactivate()
        return True
    except Exception:
        return False


def active_id():
    try:
        return json.load(open(ACTIVE_PATH, encoding="utf-8")).get("id")
    except Exception:
        return None


def activate(bid) -> bool:
    bp = get_blueprint(bid or "")
    if not bp:
        return False
    _ensure_dirs()
    json.dump({"id": bp["id"], "name": bp["name"]},
              open(ACTIVE_PATH, "w", encoding="utf-8"))
    _log("style activated: " + bp["name"])
    return True


def deactivate():
    try:
        os.remove(ACTIVE_PATH)
    except Exception:
        pass


def active_blueprint():
    bid = active_id()
    return get_blueprint(bid) if bid else None


def status() -> dict:
    return dict(_STATE)


# ------------------------------------------------------------- download
def _download(url, progress=None):
    import yt_dlp
    _ensure_dirs()
    opts = {
        "outtmpl": os.path.join(WORK_DIR, "%(id)s.%(ext)s"),
        "format": ("bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]/"
                   "bv*[height<=720]+ba/b[height<=720]/b"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True, "no_warnings": True,
        "progress_hooks": ([lambda p: progress and progress(
            min(1.0, (p.get("downloaded_bytes") or 0)
                / max(1, p.get("total_bytes") or 1)))]
           if progress else []),
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        title = str(info.get("title") or "reference")
        vid = str(info.get("id") or "")
    best, best_sz = "", 0
    for f in glob.glob(os.path.join(WORK_DIR, vid + ".*")):
        if f.lower().endswith((".part", ".jpg", ".webp", ".json")):
            continue
        sz = os.path.getsize(f)
        if sz > best_sz:
            best, best_sz = f, sz
    if not best:
        raise RuntimeError("downloaded file not found")
    return best, title


# ------------------------------------------------------------- analysis
def _probe(path):
    try:
        out = subprocess.run(
            [_bin("ffprobe"), "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height,avg_frame_rate:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, errors="replace", timeout=60)
        d = json.loads(out.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        dur = float((d.get("format") or {}).get("duration") or 0)
        fps = 30.0
        try:
            n, de = str(st.get("avg_frame_rate") or "30/1").split("/")
            fps = float(n) / float(de or 1) or 30.0
        except Exception:
            pass
        return dur, int(st.get("width") or 0), int(st.get("height") or 0), fps
    except Exception:
        return 0.0, 0, 0, 30.0


def _audio_rms(path, step=0.1):
    n = 8000
    try:
        cmd = [_bin("ffmpeg"), "-v", "error", "-i", path, "-map", "a:0",
               "-af", ("aresample=8000,asetnsamples=n=%d:p=0,"
                       "astats=metadata=1:reset=1,"
                       "ametadata=print:key=lavfi.astats.Overall.RMS_level:"
                       "file=-" % n),
               "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             errors="replace", timeout=300)
        vals = []
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("lavfi.astats.Overall.RMS_level="):
                try:
                    v = float(line.split("=", 1)[1])
                    vals.append(v if math.isfinite(v) else -90.0)
                except Exception:
                    pass
        return vals
    except Exception:
        return []


def _norm(x):
    a = np.asarray(x, dtype=np.float32)
    if a.size < 2:
        return np.zeros(max(1, a.size), dtype=np.float32)
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    if hi - lo < 1e-3:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def _video_track(path, dur, progress=None):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / 5.0)))
    dt = step / float(fps)
    max_frames = int(fps * min(_MAX_ANALYZE_S, max(dur, 1.0)))
    total = max(1, max_frames)
    prev = None
    cols = {"diff": [], "lum": [], "ef": [], "eb": [], "ce": [], "be": []}
    n = 0
    try:
        while True:
            if not cap.grab():
                break
            if n % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                g = cv2.resize(g, (160, 90)).astype(np.float32)
                cols["diff"].append(
                    0.0 if prev is None else float(np.abs(g - prev).mean()))
                cols["lum"].append(float(g.mean()))
                sx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
                sy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
                mag = np.sqrt(sx * sx + sy * sy)
                cols["ef"].append(float(mag.mean()))
                cols["eb"].append(float(mag[66:, 16:144].mean()))
                cols["ce"].append(float(g[27:63, 48:112].var()))
                ring = np.concatenate([g[:20].ravel(), g[70:].ravel(),
                                       g[:, :24].ravel(),
                                       g[:, 136:].ravel()])
                cols["be"].append(float(ring.var()))
                prev = g
                if progress and len(cols["diff"]) % 25 == 0:
                    progress(min(1.0, n / total))
            n += 1
            if n > max_frames:
                break
    finally:
        cap.release()
    if len(cols["diff"]) < 8:
        return None
    return {k: np.asarray(v, dtype=np.float32) for k, v in cols.items()}, dt


def _events(v, dur):
    diff, lum = v["diff"], v["lum"]
    dt = float(np.linspace(0, dur, len(diff))[1] - np.linspace(0, dur, len(diff))[0]) \
        if len(diff) > 1 else 0.2
    ts = np.arange(len(diff)) * dt

    # scene cuts (adaptive threshold + refractory)
    thr = max(18.0, float(np.percentile(diff, 92) * 1.9))
    cuts, last = [], -9.0
    for i in range(1, len(diff)):
        if diff[i] > thr and ts[i] - last >= 0.3:
            cuts.append(float(ts[i]))
            last = ts[i]

    # punch-ins: sustained center-vs-border energy growth
    zs = v["ce"] / (v["be"] + 1e-3)
    zooms, last = [], -9.0
    for i in range(3, len(zs)):
        ref = float(zs[max(0, i - 8):i - 1].mean()) + 1e-3
        if (zs[i] > 1.25 * ref and zs[i] > zs[i - 1] > zs[i - 2]
                and ts[i] - last >= 1.0):
            zooms.append(float(ts[i]))
            last = ts[i]

    # white flashes: spike then return
    flashes = []
    for i in range(1, len(lum) - 1):
        if abs(lum[i] - lum[i - 1]) > 30 \
                and abs(lum[i + 1] - lum[i - 1]) < 12:
            if not flashes or ts[i] - flashes[-1] >= 0.5:
                flashes.append(float(ts[i]))

    # shake: jitter of the jitter, normalized
    d2 = np.abs(np.diff(diff))[1:]
    shake = float(d2.mean() / (float(diff.mean()) + 1e-3))

    # caption coverage: texty edge density in the bottom band
    frame_ref = float(np.median(v["ef"])) + 1e-3
    cap_mask = v["eb"] > np.maximum(16.0, 1.8 * frame_ref)
    caption_cov = float(cap_mask.mean()) if len(cap_mask) else 0.0

    return cuts, zooms, flashes, shake, caption_cov, ts


def _audio_events(rms, dur):
    if len(rms) < 10:
        return [], 100.0
    a = np.asarray(rms, dtype=np.float32)
    ats = np.arange(len(a)) * 0.1
    ats = np.clip(ats, 0, dur)
    sigma = float(np.std(np.diff(a))) + 1e-3
    onsets, last = [], -9.0
    for i in range(1, len(a)):
        if (a[i] - a[i - 1] > 2.5 * sigma and a[i] > -38.0
                and ats[i] - last >= 0.25):
            onsets.append(float(ats[i]))
            last = ats[i]
    silence_pct = float((a < -45.0).mean() * 100.0)
    return onsets, silence_pct


def _deep_hook(path):
    """Optional: transcribe the first 60s for a verbal-hook read."""
    try:
        from faster_whisper import WhisperModel
        wav = os.path.join(WORK_DIR, "_vre_hook.wav")
        subprocess.run(
            [_bin("ffmpeg"), "-y", "-v", "error", "-t", "60", "-i", path,
             "-vn", "-ac", "1", "-ar", "16000", wav],
            capture_output=True, timeout=120)
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(wav, beam_size=1, vad_filter=True,
                                   language=None)
        first, wps0, words, t_end = None, 0.0, 0, 0.0
        for s in segs:
            if first is None:
                first = float(s.start)
            if s.start < 8.0:
                words += len(s.text.split())
                t_end = max(t_end, float(s.end))
        try:
            os.remove(wav)
        except Exception:
            pass
        return {"first_speech": first,
                "words_per_sec_open": (words / t_end) if t_end > 0.5 else 0.0}
    except Exception:
        return {}


def _why(m, hook, pace):
    out = []
    asl = m.get("avg_shot", 0)
    if asl and asl <= 2.0:
        out.append("Average shot is %.1fs - visual changes arrive faster "
                   "than the swipe reflex, the core retention trick."
                   % asl)
    elif asl >= 5.0:
        out.append("Long %.1fs shots build immersion - it earns attention "
                   "with content instead of cuts." % asl)
    if m.get("zooms_per_min", 0) >= 2:
        out.append("%.1f punch-ins/minute re-anchor the eye exactly when "
                   "energy spikes." % m["zooms_per_min"])
    if m.get("flashes_per_min", 0) >= 2:
        out.append("Frequent flashes (~%.0f/min) act as pattern interrupts "
                   "and reset passive viewing." % m["flashes_per_min"])
    cov = m.get("caption_coverage", 0.0)
    if cov >= 0.5:
        out.append("Captions cover ~%.0f%% of runtime - silent scrollers "
                   "stay without unmuting." % (cov * 100))
    elif 0 < cov <= 0.15:
        out.append("Almost no captions - it bets on raw audio, demanding "
                   "sound-on viewers.")
    spm = m.get("sfx_per_min", 0.0)
    if spm >= 3:
        out.append("Audio is layered (~%.0f hits/min): every cut lands "
                   "with a sound, doubling perceived production value."
                   % spm)
    if m.get("beat_alignment", 0.0) >= 0.35:
        out.append("Cuts land on audio transients (beat-aligned) - the "
                   "edit feels intentional, not assembled.")
    if hook.get("open_with") == "visual":
        out.append("Cold-opens on action at %.1fs - the first frame "
                   "already asks a question." % hook.get("first_event", 0))
    elif hook.get("open_with") == "speech":
        out.append("Opens straight into speech at %.1fs - the hook is "
                   "verbal." % hook.get("first_event", 0))
    sil = m.get("silence_pct", 100.0)
    if sil <= 8:
        out.append("Wall-to-wall audio (%.0f%% silence) - no dead second "
                   "for the thumb to swipe in." % sil)
    return out[:6] or ["Balanced, moderate editing - it works on clarity "
                       "rather than stimulation."]


def analyze_file(path, title="", url="", progress=None, deep=False):
    dur, w, h, fps = _probe(path)
    if dur <= 0.5:
        raise RuntimeError("could not read video")
    if progress:
        progress(0.05)
    v = _video_track(path, dur, progress)
    if not v:
        raise RuntimeError("could not decode frames")
    (cols, dt), = [v]
    cuts, zooms, flashes, shake, cap_cov, ts = _events(cols, dur)
    if progress:
        progress(0.7)
    rms = _audio_rms(path)
    onsets, sil = _audio_events(rms, dur)
    if progress:
        progress(0.9)

    n = 64
    grid = np.linspace(0, dur, n)
    motion = _norm(cols["diff"])
    energy = 0.6 * np.interp(grid, ts, motion)
    if len(rms) >= 4:
        a = np.asarray(rms, dtype=np.float32)
        a = np.clip((a + 50.0) / 45.0, 0.0, 1.0)
        ats = np.arange(len(a)) * 0.1
        energy = energy + 0.4 * np.interp(grid, np.clip(ats, 0, dur), a)
    energy = np.clip(energy, 0, 1)

    shots = len(cuts) + 1
    avg_shot = dur / shots
    cps = len(cuts) / max(0.1, dur / 10.0)
    beat_hits = sum(1 for c in cuts
                    if any(abs(c - o) <= 0.15 for o in onsets))
    beat_align = beat_hits / len(cuts) if cuts else 0.0

    first_cut = cuts[0] if cuts else dur
    hook = {"first_event": round(min(first_cut,
                                     onsets[0] if onsets else dur), 2)}
    if deep:
        dh = _deep_hook(path)
        hook.update(dh)
    hook["open_with"] = ("speech" if hook.get("first_speech") is not None
                         and hook["first_speech"] < 1.5
                         else ("visual" if hook["first_event"] < 1.2
                               else "none"))

    m = {
        "duration": round(dur, 2),
        "resolution": "%dx%d" % (w, h),
        "shots": shots,
        "avg_shot": round(avg_shot, 2),
        "cuts_per_10s": round(cps, 2),
        "zooms_per_min": round(len(zooms) / max(0.1, dur / 60.0), 2),
        "zoom_strength": round(float(min(1.0, shake * 0.5 + 0.25)), 2),
        "flashes_per_min": round(len(flashes) / max(0.1, dur / 60.0), 2),
        "shake_score": round(min(1.0, shake), 2),
        "caption_coverage": round(cap_cov, 2),
        "sfx_per_min": round(len(onsets) / max(0.1, dur / 60.0), 2),
        "silence_pct": round(sil, 1),
        "beat_alignment": round(beat_align, 2),
        "energy_curve": [[round(float(t), 2), round(float(e), 3)]
                         for t, e in zip(grid, energy)],
    }
    pace = ("fast" if cps >= 4 else "medium" if cps >= 1.5 else "slow")
    profile = {
        "pace": pace,
        "camera": ("aggressive" if m["zooms_per_min"] >= 3
                   else "active" if m["zooms_per_min"] >= 1.5 else "calm"),
        "captions": ("heavy" if cap_cov >= 0.5
                     else "light" if cap_cov >= 0.2 else "none"),
        "sfx": ("dense" if m["sfx_per_min"] >= 4
                else "moderate" if m["sfx_per_min"] >= 1.5 else "sparse"),
        "audio": ("wall-to-wall" if sil <= 10 else
                  "with breathing room" if sil <= 30 else "sparse"),
    }
    bp = {
        "id": uuid.uuid4().hex[:10],
        "name": (title or "reference")[:42].strip() + " blueprint",
        "title": title, "source_url": url,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "analyzed_seconds": round(min(dur, _MAX_ANALYZE_S), 1),
        "metrics": m, "profile": profile, "hook": hook,
        "why": _why(m, hook, pace),
        "note": ("Abstract style metrics only - no frames, audio, or "
                 "assets are copied from the reference video."),
    }
    _ensure_dirs()
    json.dump(bp, open(_bp_path(bp["id"]), "w", encoding="utf-8"),
              indent=1)
    return bp


import time  # noqa: E402  (used in blueprint timestamps)


# --------------------------------------------------- blueprint -> settings
def blueprint_overrides(bp):
    """Map blueprint metrics onto existing HypeClip settings."""
    m = bp.get("metrics", {})
    cps = m.get("cuts_per_10s", 2.0)
    zpm = m.get("zooms_per_min", 1.0)
    fpm = m.get("flashes_per_min", 0.0)
    spm = m.get("sfx_per_min", 1.0)
    cov = m.get("caption_coverage", 0.0)
    sil = m.get("silence_pct", 50.0)
    beat = m.get("beat_alignment", 0.0)
    zs = m.get("zoom_strength", 0.3)
    hook = bp.get("hook") or {}

    if cps >= 4:
        pace, dur, zst = "fast", 35, 26 + int(10 * zs)
    elif cps >= 1.5:
        pace, dur, zst = "medium", 60, 16 + int(8 * zs)
    else:
        pace, dur, zst = "slow", 90, 10 + int(6 * zs)

    ov = {
        "clip_duration": int(dur),
        "zoom_strength": int(min(45, zst)),
        "zoom_punch": bool(zpm >= 2.0 and pace != "slow"),
        "flash_intro": bool(fpm >= 2.0),
        "beat_sync": bool(beat >= 0.35),
        "sfx_enabled": bool(spm >= 1.0),
        "sfx_volume_db": -8 if spm < 2 else (-4 if spm < 5 else 0),
        "duck_music": bool(sil < 15.0),
        "hype_threshold": 3.0 if pace == "fast" else (
            3.5 if pace == "medium" else 4.0),
        "pre_roll": 1.0 if hook.get("open_with") == "visual" else 1.5,
    }
    hints = {"size": 52 if cov >= 0.6 else 44, "bold": True}
    return ov, hints


# ------------------------------------------------------- background job
def start_analysis(url, deep=False):
    if not str(url or "").strip():
        return False, "missing url"
    if _STATE["state"] == "running":
        return False, "analysis already running"
    threading.Thread(target=_analyze_job, args=(str(url).strip(),
                                                bool(deep)),
                     daemon=True).start()
    return True, ""


def _analyze_job(url, deep):
    _STATE.update(state="running", frac=0.0, error=None, blueprint=None)
    try:
        _log("downloading reference: " + url)

        def dprog(f):
            _STATE.update(frac=round(0.45 * f, 3))

        path, title = _download(url, dprog)
        _log("deconstructing " + os.path.basename(path) + " ...")

        def aprog(f):
            _STATE.update(frac=round(0.45 + 0.5 * f, 3))

        bp = analyze_file(path, title=title, url=url, progress=aprog,
                          deep=deep)
        _STATE.update(frac=1.0, state="done", blueprint=bp)
        _log("blueprint ready: " + bp["name"])
    except Exception as e:
        _STATE.update(state="error", error=str(e))
        _log("error: " + str(e))
