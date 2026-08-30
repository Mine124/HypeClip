"""Retention Intelligence Engine.

Predicts how long viewers keep watching each clip, finds the exact spots
where they would swipe away, explains why, and can render an auto-improved
V2 of the clip. Self-contained: needs only stdlib + numpy + bundled
ffmpeg/ffprobe. Never raises into the pipeline - all entry points are
guarded and callers wrap them in try/except.

Report shape (attached to clip dicts as clip["retention"]):
    score        0-100 predicted average retention
    completion   0-100 predicted watch-through
    grade        S / A / B / C / D
    verdict      one-line explanation
    curve        [[t, retention], ...]
    risks        [{t0, t1, kind, severity, reason, fix}, ...]
    watch_time   estimated seconds watched
"""
from __future__ import annotations

import math
import os
import subprocess

import numpy as np

from .utils import resolve_bin

CURVE_STRIDE_TARGET = 160
SILENCE_DB = -42.0
LOW_INTEREST = 0.32


def _bin(name):
    try:
        return resolve_bin(name)
    except Exception:
        return name


def _probe_duration(path):
    try:
        out = subprocess.run(
            [_bin("ffprobe"), "-v", "error", "-show_entries",
             "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, errors="replace", timeout=60)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _audio_curve(path, step=0.1):
    """RMS (dB) per `step` seconds. Empty list if anything fails."""
    n = 8000  # samples per window at 8 kHz -> 0.1 s windows
    try:
        cmd = [_bin("ffmpeg"), "-v", "error", "-i", path, "-map", "a:0",
               "-af",
               ("aresample=8000,asetnsamples=n=%d:p=0,"
                "astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"
                % n),
               "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             errors="replace", timeout=180)
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


def _num(d, *names):
    for k in names:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except Exception:
                pass
    return None


def _moment_list(moments):
    out = []
    for m in moments or []:
        if not isinstance(m, dict):
            continue
        st = _num(m, "start", "t0", "t", "time", "at")
        en = _num(m, "end", "t1", "stop")
        sc = _num(m, "score", "hype", "value")
        if st is None:
            continue
        if en is None:
            en = st + 12.0
        out.append((float(st), float(en), float(sc if sc is not None else 5.0)))
    return out


def _series_arrays(series):
    ts, vs = [], []
    try:
        if isinstance(series, dict):
            ts = list(series.get("t") or [])
            vs = list(series.get("v") or series.get("y") or [])
        elif isinstance(series, list) and series:
            first = series[0]
            if isinstance(first, dict):
                for it in series:
                    t = _num(it, "t", "time", "x")
                    v = _num(it, "v", "y", "value", "intensity")
                    if t is not None and v is not None:
                        ts.append(t)
                        vs.append(v)
            else:
                for it in series:
                    if isinstance(it, (list, tuple)) and len(it) >= 2:
                        ts.append(float(it[0]))
                        vs.append(float(it[1]))
    except Exception:
        pass
    return ts, vs


def _interest_grid(duration, moments, series, audio_rms):
    n = max(4, int(duration / 0.5) + 1)
    ts = np.arange(n) * 0.5
    mm = _moment_list(moments)
    has_audio = bool(audio_rms)
    has_series = False

    mi = np.zeros(n)
    for (st, en, sc) in mm:
        s = max(0.0, st - 0.6)
        e = min(duration, en + 0.8)
        w = float(np.clip(sc / 10.0, 0.15, 1.0))
        for k in range(n):
            t = ts[k]
            if s <= t <= e:
                mi[k] = max(mi[k], w)

    tsr, vsr = _series_arrays(series)
    if len(tsr) >= 2:
        arr = np.asarray(vsr, dtype=float)
        ref = float(np.percentile(np.abs(arr), 90)) or 1.0
        ref = max(ref, 1e-6)
        si = np.clip(np.interp(ts, tsr, arr) / ref, 0.0, 1.0) * 0.85
        has_series = True
    else:
        si = np.zeros(n)

    if has_audio:
        ats = np.arange(len(audio_rms)) * step
        av = np.asarray(audio_rms, dtype=float)
        ai = np.clip((np.interp(ts, ats, av) + 38.0) / 28.0, 0.0, 1.0)
    else:
        ai = np.zeros(n)

    if not mm and not has_series and not has_audio:
        i = np.full(n, 0.5)
    else:
        base = np.full(n, 0.28)
        i = np.maximum(base, np.maximum(mi, np.maximum(si, ai * 0.9)))
        k3 = np.ones(3) / 3.0
        i = np.convolve(i, k3, mode="same")
        i[:2] = np.maximum(i[:2], mi[:2])
    return ts, np.clip(i, 0.0, 1.0), mm, ai


def _curve_from_interest(ts, i, mm):
    n = len(ts)
    r = np.empty(n)
    r[0] = 100.0
    strong = [(st, en) for (st, en, sc) in mm if sc >= 8.0]
    for k in range(1, n):
        t = ts[k - 1]
        dt = ts[k] - ts[k - 1]
        h = 0.010 * (1.0 - 0.85 * float(i[k - 1])) ** 1.5
        if t < 3.0:
            h *= 1.6
        elif t < 8.0:
            h *= 1.2
        for (st, en) in strong:
            if st - 0.4 <= t <= en:
                h *= 0.7
                break
        r[k] = r[k - 1] * (1.0 - min(h * dt, 0.25))
    return r


def _fmt_t(s):
    s = max(0, int(round(s)))
    return "%d:%02d" % (s // 60, s % 60)


def _find_risks(ts, i, ai, mm, duration):
    risks = []
    k0 = None
    for k in range(len(ts) + 1):
        low = k < len(ts) and i[k] < LOW_INTEREST
        if low and k0 is None:
            k0 = k
        if (not low or k == len(ts)) and k0 is not None:
            t0 = float(ts[k0])
            t1 = float(ts[min(k, len(ts) - 1)])
            dur = t1 - t0
            if dur >= 0.9:
                silent = False
                if len(ai):
                    a0 = max(0, int(t0 / 0.1))
                    a1 = min(len(ai), int(t1 / 0.1) + 1)
                    seg = ai[a0:a1]
                    if len(seg):
                        silent = float((seg < SILENCE_DB).mean()) >= 0.6
                sev = min(1.0, 0.35 + 0.12 * dur)
                if silent:
                    risks.append({"t0": round(t0, 2), "t1": round(t1, 2),
                                  "kind": "dead_air",
                                  "severity": round(sev, 2),
                                  "reason": "%.1fs of near-silence, no action"
                                            % dur,
                                  "fix": "Trim %.1fs at %s-%s"
                                         % (dur, _fmt_t(t0), _fmt_t(t1))})
                else:
                    risks.append({"t0": round(t0, 2), "t1": round(t1, 2),
                                  "kind": "pacing",
                                  "severity": round(sev * 0.7, 2),
                                  "reason": "%.1fs low-action stretch" % dur,
                                  "fix": "Tighten %s-%s (cut to next peak)"
                                         % (_fmt_t(t0), _fmt_t(t1))})
            k0 = None

    first_peak = None
    for (st, en, sc) in mm:
        if sc >= 6.0:
            first_peak = st
            break
    if first_peak is None:
        hot = np.where(i >= 0.6)[0]
        if len(hot):
            first_peak = float(ts[hot[0]])
    if first_peak and first_peak > 3.0:
        sev = min(1.0, 0.3 + 0.08 * (first_peak - 3.0))
        risks.append({"t0": 0.0, "t1": round(max(0.0, first_peak - 0.75), 2),
                      "kind": "hook", "severity": round(sev, 2),
                      "reason": "slow open - first real peak at %s"
                                % _fmt_t(first_peak),
                      "fix": "Start at %s and skip the warm-up"
                             % _fmt_t(max(0.0, first_peak - 0.5))})

    if duration >= 15.0:
        cut = int(duration * 0.8 / 0.5)
        if cut < len(i):
            tail = i[cut:]
            if float(tail.mean()) < 0.35:
                risks.append({"t0": round(duration * 0.8, 2),
                              "t1": round(duration, 2),
                              "kind": "ending", "severity": 0.45,
                              "reason": "final 20 percent trails off",
                              "fix": "End at %s where the payoff lands"
                                     % _fmt_t(duration * 0.8)})

    if len(mm) >= 4:
        starts = sorted(s for (s, e, sc) in mm)
        for a in range(len(starts) - 3):
            if starts[a + 3] - starts[a] <= 10.0:
                risks.append({"t0": round(starts[a], 2),
                              "t1": round(starts[a + 3], 2),
                              "kind": "density", "severity": 0.4,
                              "reason": "4+ hype beats stacked inside 10s",
                              "fix": "Let it breathe - do not stack effects"})
                break

    risks.sort(key=lambda r: -r["severity"])
    return risks[:6]


def _score_curve(ts, r, risks):
    T = float(ts[-1]) if len(ts) else 1.0

    def at(x):
        return float(np.interp(x, ts, r))

    s = (0.40 * at(3.0) + 0.30 * at(T / 3.0)
         + 0.20 * at(2.0 * T / 3.0) + 0.10 * at(T))
    top = sorted([x["severity"] for x in risks], reverse=True)[:3]
    s = max(1.0, min(99.0, s - 8.0 * sum(top)))
    comp = at(T)
    wt = float(np.sum((r[:-1] + r[1:]) * 0.5 * np.diff(ts)) / 100.0)
    return round(s), round(comp, 1), round(wt, 1)


def _grade(score):
    if score >= 93:
        return "S"
    if score >= 86:
        return "A"
    if score >= 78:
        return "B"
    if score >= 68:
        return "C"
    return "D"


def _verdict(score, risks):
    kinds = {r["kind"] for r in risks[:2]}
    if score >= 93:
        lead = "Elite - hold this pacing"
    elif score >= 86:
        lead = "Strong hook and pacing"
    elif score >= 78:
        lead = "Decent, one weak stretch"
    elif score >= 68:
        lead = "Leaks attention mid-clip"
    else:
        lead = "High swipe risk - revise"
    if "hook" in kinds:
        lead += "; slow open is the top problem"
    elif "dead_air" in kinds:
        lead += "; dead air is the top problem"
    elif "ending" in kinds:
        lead += "; ending trails"
    elif "pacing" in kinds:
        lead += "; pacing sags mid-clip"
    return lead


def analyze(path, moments=None, series=None):
    try:
        dur = _probe_duration(path)
        if dur <= 0.5:
            return None
        rms = _audio_curve(path)
        ts, i, mm, ai = _interest_grid(dur, moments, series, rms)
        r = _curve_from_interest(ts, i, mm)
        risks = _find_risks(ts, i, ai, mm, dur)
        score, comp, wt = _score_curve(ts, r, risks)
        stride = max(1, int(math.ceil(len(ts) / float(CURVE_STRIDE_TARGET))))
        curve = [[round(float(ts[k]), 2), round(float(r[k]), 1)]
                 for k in range(0, len(ts), stride)]
        if (len(ts) - 1) % stride:
            curve.append([round(float(ts[-1]), 2), round(float(r[-1]), 1)])
        return {"score": int(score), "completion": comp,
                "grade": _grade(score),
                "verdict": _verdict(score, risks),
                "curve": curve, "risks": risks, "watch_time": wt,
                "model": "retention-heuristics-v1"}
    except Exception:
        return None


def enrich_clip(clip, moments=None, series=None, out_dir=None, reporter=None):
    try:
        if not isinstance(clip, dict) or clip.get("retention"):
            return clip
        name = clip.get("file") or clip.get("name") or clip.get("path") or ""
        if not name:
            return clip
        path = name if os.path.isabs(name) else os.path.join(out_dir or "", name)
        if not os.path.isfile(path):
            return clip
        rep = analyze(path, moments, series)
        if rep and reporter and hasattr(reporter, "log"):
            reporter.log("[retention] %s -> %s/100 (%s)"
                         % (name, rep["score"], rep["grade"]))
        if rep:
            clip["retention"] = rep
    except Exception:
        pass
    return clip


# ------------------------------------------------------------- auto-revision
def _plan_cuts(report, duration, mm):
    protected = [(max(0.0, st - 0.75), en) for (st, en, sc) in mm]
    cand = []
    for r in report.get("risks", []):
        if r["kind"] in ("dead_air", "pacing", "hook"):
            cand.append((float(r["t0"]), float(r["t1"])))
    cand.sort()
    merged = []
    for (a, b) in cand:
        if merged and a <= merged[-1][1] + 0.25:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out, total = [], 0.0
    for (a, b) in merged:
        a = max(0.0, a)
        b = min(duration - 0.3, b)
        if b - a < 0.6:
            continue
        if any(a < pe and ps < b for (ps, pe) in protected):
            continue
        if total + (b - a) > duration * 0.18:
            continue
        out.append((a, b))
        total += (b - a)
    if duration - total < 12.0:
        return []
    return out


def _keep_segments(cuts, duration):
    keep = []
    cur = 0.0
    for (a, b) in cuts:
        if a - cur > 0.4:
            keep.append((cur, a))
        cur = max(cur, b)
    if duration - cur > 0.4:
        keep.append((cur, duration))
    return keep


def _shift_moments(mm, cuts):
    out = []
    for (st, en, sc) in mm:
        d = sum((b - a) for (a, b) in cuts if a <= st)
        ns, ne = st - d, en - d
        if any(a - 0.001 <= ns and ne <= b + 0.001 for (a, b) in cuts):
            continue
        if ns < 0:
            continue
        out.append((ns, ne, sc))
    return out


def _filter_graph(keep):
    v, a, parts = [], [], []
    for idx, (s, e) in enumerate(keep):
        v.append("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d]"
                 % (s, e, idx))
        a.append("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[a%d]"
                 % (s, e, idx))
        parts.append("[v%d][a%d]" % (idx, idx))
    fc = ";".join(v + a)
    fc += ";%sconcat=n=%d:v=1:a=1[vout][aout]" % ("".join(parts), len(keep))
    return fc


def _render(src, keep, dst, log=None):
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-i", src,
           "-filter_complex", _filter_graph(keep),
           "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", dst]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       errors="replace", timeout=1200)
    ok = p.returncode == 0 and os.path.isfile(dst) \
        and os.path.getsize(dst) > 10000
    if not ok:
        tail = (p.stderr or "")[-400:]
        if log:
            log("[retention] render error: " + tail)
        raise RuntimeError("revision render failed")


def improve_clip(src, moments=None, series=None, reporter=None):
    def log(m):
        if reporter and hasattr(reporter, "log"):
            reporter.log(str(m))

    v1 = analyze(src, moments, series)
    if not v1:
        raise RuntimeError("could not analyze clip audio")
    dur = _probe_duration(src)
    mm = _moment_list(moments)
    cuts = _plan_cuts(v1, dur, mm)
    if not cuts:
        log("[retention] no safe cuts - V1 stays (%s/100)" % v1["score"])
        return {"improved": False, "chosen": "v1",
                "file": os.path.basename(src), "file_v2": None,
                "report_v1": v1, "report_v2": None, "applied": []}
    keep = _keep_segments(cuts, dur)
    if len(keep) < 2:
        log("[retention] nothing left to keep - V1 stays")
        return {"improved": False, "chosen": "v1",
                "file": os.path.basename(src), "file_v2": None,
                "report_v1": v1, "report_v2": None, "applied": []}
    dst = os.path.splitext(src)[0] + "_AIv2.mp4"
    log("[retention] rendering V2 with %d cut(s)..." % len(cuts))
    _render(src, keep, dst, log)
    v2 = analyze(dst, _shift_moments(mm, cuts), None)
    better = bool(v2) and v2["score"] > v1["score"]
    chosen = "v2" if better else "v1"
    applied = ["Trim %.1fs (%s-%s)" % (b - a, _fmt_t(a), _fmt_t(b))
               for (a, b) in cuts]
    log("[retention] V1 %s/100 vs V2 %s/100 -> kept %s"
        % (v1["score"], (v2 or {}).get("score", "?"), chosen))
    return {"improved": better, "chosen": chosen,
            "file": os.path.basename(dst if chosen == "v2" else src),
            "file_v2": os.path.basename(dst),
            "report_v1": v1, "report_v2": v2, "applied": applied}
