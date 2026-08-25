"""Decision engine v2: pacing doctrine, dead-air surgeon, critic,
retention predictor. Every choice carries a reason."""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .config import DATA_DIR
from .intel import audio_db

OUTCOMES = os.path.join(DATA_DIR, "outcomes.json")

# what each moment-type is ALLOWED to use (doctrine, not vibes)
PACING = {
    "reaction": dict(zoom=False, shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=False,
                     note="emotional/reactive - let it breathe"),
    "funny":    dict(zoom=True,  shake=True,  flash=True,  bloom=False,
                     grain=False, vignette=False, beat=True,
                     note="comedy - interrupts welcome"),
    "clutch":   dict(zoom=True,  shake=True,  flash=False, bloom=False,
                     grain=False, vignette=False, beat=True,
                     note="clutch - emphasize payoff only"),
    "rage":     dict(zoom=True,  shake=True,  flash=False, bloom=False,
                     grain=False, vignette=False, beat=False,
                     note="rage - shake ok, keep cuts honest"),
    "fail":     dict(zoom=True,  shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=False,
                     note="fail - one zoom, no circus"),
    "win":      dict(zoom=True,  shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=True,
                     note="win - steady, confident"),
    "highlight": dict(zoom=False, shake=False, flash=False, bloom=False,
                      grain=False, vignette=False, beat=False,
                      note="default - clean and calm"),
}


def _clamp(v, a, b):
    return max(a, min(b, v))


def _n(v, scale):
    return float(np.clip(v / scale, 0, 1))


def _perf_simple(s: dict) -> float:
    v = max(int(s.get("views") or 0), 50)
    l = int(s.get("likes") or 0)
    c = int(s.get("comments") or 0)
    return min(1.0, (math.log10(v) / 6.0) * 0.6
               + min(((l * 3 + c * 6) / v), 0.5) * 0.8)


def _calibration() -> float:
    try:
        d = json.load(open(OUTCOMES, encoding="utf-8"))
        samples = d.get("samples", [])
        if len(samples) < 10:
            return 1.0
        m = float(np.mean([_perf_simple(s) for s in samples]))
        return _clamp(0.6 + m * 0.9, 0.75, 1.35)
    except Exception:
        return 1.0


def features_from_db(db: np.ndarray, start: float, dur: float,
                     peak_score: float, texts: str = "") -> dict:
    n = db.size
    a = int(np.clip(start, 0, max(0, n - 2)))
    b = int(np.clip(start + dur, 2, n))
    seg = db[a:b] if b > a else np.zeros(4, dtype=np.float32)
    h = min(4, max(1, seg.size - 1))
    tail = seg[-4:] if seg.size >= 4 else seg
    t = (texts or "").lower()
    return {
        "dur": float(dur),
        "pace": float(np.std(seg)) if seg.size > 4 else 0.0,
        "hook": float(seg[1:h + 1].max() - seg[0]) if seg.size > 2 else 0.0,
        "ending": float(seg.max() - tail.min()) if seg.size else 0.0,
        "payoff": float(_clamp((peak_score - 2) / 14.0, 0, 1)) * 20.0,
        "dead": float(np.mean(seg[:3] < np.percentile(db, 25) + 3))
                if seg.size > 3 else 0.0,
        "lenfit": 1.0 if 22 <= dur <= 80 else (0.55 if 15 <= dur <= 110 else 0.2),
        "emotion": 1.0 if any(w in t for w in
                              ("no way", "insane", "crazy", "let's go",
                               "lets go", "won", "omg", "sheesh")) else 0.4,
    }


def predict(f: dict) -> dict:
    raw = (0.22 * _n(f["hook"], 12) + 0.18 * _n(f["pace"], 9)
           + 0.16 * _n(f["payoff"], 20) + 0.12 * _n(f["ending"], 8)
           + 0.12 * f["lenfit"] + 0.10 * (1.0 - f["dead"])
           + 0.10 * f["emotion"])
    cal = _calibration()
    avg = _clamp(28 + raw * 62 * cal, 15, 96)
    return {
        "avg_watch_pct": round(avg),
        "completion": round(_clamp(avg * 1.25, 10, 97)),
        "swipe_prob": round(_clamp(100 - avg * 1.05, 4, 92)),
        "share_prob": round(_clamp(raw * 26 * (1.15 - f["dead"]), 1, 42)),
        "comment_prob": round(_clamp(raw * 17, 1, 30)),
        "score": int(round(raw * 100)),
        "calibrated": cal != 1.0,
    }


# ------------------------------------------------------------- SFX taste
def sfx_plan(wav_path: str, texts: str, settings, r, pool: list[str]):
    events: list[dict] = []
    notes: list[str] = []
    db = audio_db(wav_path)
    n = db.size

    def find(name):
        for p in pool:
            if os.path.splitext(os.path.basename(p))[0].lower() == name:
                return p
        return None

    dur_est = max(5.0, n)
    impact_t = min(max(settings.pre_roll, 0.2), dur_est * 0.35)
    ia = int(np.clip(impact_t, 0, max(0, n - 1)))
    spike = bool(n > ia + 2
                 and (db[ia] - db[int(np.clip(ia - 3, 0, n - 1))] > 5.0))
    conf = 0.85 if spike else 0.45

    air = find("airhorn")
    if air:
        gain = settings.sfx_volume_db if conf > 0.6 \
            else settings.sfx_volume_db - 6
        events.append({"t": impact_t, "file": air, "gain_db": gain})
        notes.append(f"impact @ {impact_t:.1f}s conf={conf:.2f}"
                     + ("" if conf > 0.6 else " -> softened -6dB"))

    riser = find("riser")
    if riser and spike and impact_t > 1.8:
        events.append({"t": impact_t - 1.6, "file": riser,
                       "gain_db": settings.sfx_volume_db - 7})
        notes.append("riser before genuine drop")

    t = (texts or "").lower()
    boom = find("vine_boom")
    if boom and any(w in t for w in ("lol", "lmao", "bruh", "haha",
                                     "fall", "fail", "oof")):
        events.append({"t": min(dur_est - 1, max(1.0, dur_est * 0.55)),
                       "file": boom,
                       "gain_db": settings.sfx_volume_db - 4})
        notes.append("cartoon boom (comedy markers)")

    if not spike:
        notes.append("restraint: flat energy -> no stacked SFX")
    return events, notes


# ---------------------------------------------------------- pacing matrix
def pacing_plan(category: str, score: float):
    doc = PACING.get(category, PACING["highlight"])
    return doc


def punch_decision(category: str, score: float):
    if category in ("funny", "reaction"):
        return True, 0.10, "pattern-interrupt suits comedy beats"
    if category == "clutch" and score >= 60:
        return True, 0.09, "emphasis on clutch payoff"
    if category == "rage":
        return True, 0.08, "amped frustration framing"
    return False, 0.0, "held steady - tone benefits from calm camera"


# ------------------------------------------------------ dead-air surgeon
def find_dead_air(wav_path: str, min_pause: float = 1.2,
                  rel_floor: float = 4.0) -> list[tuple[float, float]]:
    db = audio_db(wav_path)
    if db.size < 10:
        return []
    floor = float(np.percentile(db, 20)) + rel_floor
    quiet = db < floor
    spans, i = [], 0
    while i < db.size:
        if quiet[i]:
            j = i
            while j < db.size and quiet[j]:
                j += 1
            if (j - i) >= min_pause:
                spans.append((float(i), float(j)))
            i = j
        else:
            i += 1
    return spans


def build_trimmed(src: str, dest: str, start: float, dur: float,
                  pauses: list[tuple[float, float]]):
    """Removes internal pauses from the [start,start+dur] window.
    Returns (new_src, mapping) where mapping converts original-relative
    times to trimmed-relative times."""
    from .utils import resolve_bin
    lo, hi = start, start + dur
    inner = [(max(lo, a), min(hi, b)) for a, b in pauses]
    inner = [(a, b) for a, b in inner if b - a >= min(1.0, dur * 0.04)]
    if not inner:
        return None, []
    kept, cursor = [], lo
    for a, b in inner:
        if a - cursor >= 0.8:
            kept.append((cursor, a))
        cursor = max(cursor, b)
    if hi - cursor >= 0.8:
        kept.append((cursor, hi))
    removed = sum(b - a for a, b in inner) \
        - (lo and 0)
    if not kept or len(kept) > 4:
        return None, []          # too chopped -> leave it alone

    inputs: list[str] = []
    fc: list[str] = []
    for k, (a, b) in enumerate(kept):
        inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src]
        fc.append(f"[{k}:v]scale=iw/2*2:ih/2*2[v{k}]"
                  .replace("/2*2", ""))
        fc[-1] = f"[{k}:v]null[v{k}];[{k}:a]anull[a{k}]"
    fc.append("".join(f"[v{k}][a{k}]" for k in range(len(kept)))
              + f"concat=n={len(kept)}:v=1:a=1[outv][outa]")
    cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", dest]
    from .utils import run
    run(cmd)

    mapping = []
    new_t = 0.0
    ki = 0
    for a, b in inner:
        while ki < len(kept) and kept[ki][1] <= a:
            new_t += kept[ki][1] - kept[ki][0]
            ki += 1
        mapping.append({"cut_start": a - lo, "cut_end": b - lo,
                        "shift_after": -(b - a)})
    total = sum(b - a for a, b in kept)
    return dest, {"spans": inner, "total_removed": dur - total,
                  "new_dur": total}


def remap(t: float, mapping: dict | None) -> float:
    if not mapping:
        return t
    for sp in mapping["spans"]:
        if t >= sp[1]:
            t -= (sp[1] - sp[0])
        elif t > sp[0]:
            t = sp[0]
    return t


# ------------------------------------------------------------------ critic
def critique(feats: dict, pred: dict, fx_on: list[str],
             category: str) -> list[str]:
    issues = []
    if feats["hook"] < 4:
        issues.append("weak hook - front lacks an energy rise")
    if feats["dead"] > 0.34:
        issues.append("slow open - dead air in first seconds")
    budget = PACING.get(category, PACING["highlight"])
    over = [f for f in fx_on if not budget.get(
        {"zoom": "zoom", "shake": "shake", "flash": "flash",
         "bloom": "bloom", "grain": "grain", "vignette": "vignette",
         "beat": "beat"}.get(f, ""), True)]
    if over:
        issues.append(f"over-edited for tone: {','.join(over)}")
    if feats["dur"] > 110:
        issues.append("long for shorts - consider trimming")
    if pred["score"] < 48:
        issues.append("low predicted retention")
    return issues
