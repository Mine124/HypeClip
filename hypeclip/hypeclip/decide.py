"""Decision engine v3: transient-aligned SFX with intensity tiers,
protected comedy/suspense pauses, continuous effect intensities,
dead-air surgeon with protection, critic, retention predictor."""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .config import DATA_DIR
from .intel import audio_db
from .utils import run
OUTCOMES = os.path.join(DATA_DIR, "outcomes.json")

# doctrine: 'intensity' is the master dial (0-1) scaling every effect
PACING = {
    "reaction": dict(zoom=False, shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=False, intensity=0.25,
                     note="emotional/reactive - let it breathe"),
    "funny":    dict(zoom=True, shake=True, flash=True, bloom=False,
                     grain=False, vignette=False, beat=True, intensity=0.85,
                     note="comedy - interrupts welcome"),
    "clutch":   dict(zoom=True, shake=True, flash=False, bloom=False,
                     grain=False, vignette=False, beat=True, intensity=0.70,
                     note="clutch - emphasize payoff only"),
    "rage":     dict(zoom=True, shake=True, flash=False, bloom=False,
                     grain=False, vignette=False, beat=False, intensity=0.75,
                     note="rage - shake ok, keep cuts honest"),
    "fail":     dict(zoom=True, shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=False, intensity=0.55,
                     note="fail - one zoom, no circus"),
    "win":      dict(zoom=True, shake=False, flash=False, bloom=False,
                     grain=False, vignette=False, beat=True, intensity=0.60,
                     note="win - steady, confident"),
    "highlight": dict(zoom=False, shake=False, flash=False, bloom=False,
                      grain=False, vignette=False, beat=False, intensity=0.30,
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


# ------------------------------------------------------- transient engine
def find_transients(db: np.ndarray) -> list[dict]:
    """Genuine acoustic impacts: steep dB rises. Returns
    [{t, strength}] sorted by time. Strength = total rise across the edge."""
    out: list[dict] = []
    if db.size < 4:
        return out
    d = np.diff(db)
    thr = max(4.5, float(np.percentile(d, 94)))
    i = 0
    while i < d.size:
        if d[i] >= thr:
            j = i
            while j + 1 < d.size and d[j + 1] >= thr * 0.8:
                j += 1
            peak_i = int(np.argmax(db[i:j + 2])) + i
            out.append({"t": float(peak_i),
                        "strength": float(db[peak_i]
                                          - db[max(0, i - 1)])})
            i = j + 1
        else:
            i += 1
    return out


# ------------------------------------------------------ protected pauses
def analyze_silences(wav_db: np.ndarray, rel_floor: float = 4.0,
                     min_len: float = 0.35) -> tuple[list, float]:
    if wav_db.size < 6:
        return [], -60.0
    floor = float(np.percentile(wav_db, 20))
    quiet = wav_db < floor + rel_floor
    spans, i = [], 0
    while i < wav_db.size:
        if quiet[i]:
            j = i
            while j < wav_db.size and quiet[j]:
                j += 1
            if (j - i) >= min_len:
                spans.append((float(i), float(j)))
            i = j
        else:
            i += 1
    return spans, floor


def find_protected_pauses(wav_path: str) -> list[dict]:
    """Silences of 0.35-1.6s that precede a >=5dB energy rise are almost
    always comedic/suspense beats. The surgeon may never cut these."""
    db = audio_db(wav_path)
    silences, floor = analyze_silences(db)
    out = []
    for a, b in silences:
        if not (0.35 <= (b - a) <= 1.6) or b >= db.size - 1:
            continue
        before = float(db[max(0, int(a) - 1)])
        after_i = min(int(b) + 1, db.size - 1)
        if db[after_i] - max(before, floor) >= 5.0:
            out.append({"a": a, "b": b,
                        "reason": f"pause-then-{db[after_i] - before:.0f}dB "
                                  f"rise (comedy/suspense beat)"})
    return out


# ---------------------------------------------------------- SFX taste v2
def sfx_plan(wav_path: str, texts: str, settings, r, pool: list[str],
             protected: list[dict] | None = None):
    events: list[dict] = []
    notes: list[str] = []
    protected = protected or []
    db = audio_db(wav_path)
    n = db.size
    transients = find_transients(db)

    def find(name):
        for p in pool:
            if os.path.splitext(os.path.basename(p))[0].lower() == name:
                return p
        return None

    def in_protected(t: float) -> bool:
        return any(sp["a"] - 0.1 <= t <= sp["b"] + 0.1 for sp in protected)

    def push_outside(t: float) -> float:
        for sp in protected:
            if sp["a"] - 0.15 <= t <= sp["b"] + 0.15:
                return sp["b"] + 0.25
        return t

    dur_est = max(5.0, n)
    intent_t = min(max(settings.pre_roll, 0.2), dur_est * 0.35)

    # --- snap intended impact to the nearest REAL transient (+-0.8s) ---
    snapped, tier_gain, tier_note = intent_t, 0.0, "guessed"
    cand = [tr for tr in transients if abs(tr["t"] - intent_t) <= 0.8]
    if cand:
        best = max(cand, key=lambda t_: t_["strength"])
        snapped = push_outside(best["t"])
        s = best["strength"]
        if s >= 13:
            tier_gain, tier_note = 0.0, f"STRONG transient ({s:.0f}dB)"
        elif s >= 8:
            tier_gain, tier_note = -3.0, f"MEDIUM transient ({s:.0f}dB)"
        else:
            tier_gain, tier_note = -6.0, f"subtle transient ({s:.0f}dB)"

    air = find("airhorn")
    if air:
        events.append({"t": snapped, "file": air,
                       "gain_db": settings.sfx_volume_db + tier_gain})
        notes.append(f"impact @ {snapped:.2f}s [{tier_note}]")

    # anticipation: a protected pause IS detected suspense -> riser leads in
    riser = find("riser")
    if riser and protected and snapped > 1.8:
        pa = min(protected, key=lambda sp: abs(sp["a"] - snapped))
        if snapped - pa["b"] < 3.0:
            rt = max(0.2, pa["a"] - 1.4)
            events.append({"t": rt, "file": riser,
                           "gain_db": settings.sfx_volume_db - 7})
            notes.append(f"riser @ {rt:.2f}s leading into protected "
                         f"suspense pause")

    t = (texts or "").lower()
    boom = find("vine_boom")
    bt = min(dur_est - 1, max(1.0, dur_est * 0.55))
    if boom and any(w in t for w in ("lol", "lmao", "bruh", "haha",
                                     "fall", "fail", "oof")):
        bt = push_outside(bt + 0.15)      # post-punchline placement
        if abs(bt - snapped) >= 1.5:
            events.append({"t": bt, "file": boom,
                           "gain_db": settings.sfx_volume_db - 4})
            notes.append("cartoon boom AFTER punchline zone (comedy)")

    if not transients:
        notes.append("restraint: no genuine transients found - minimal SFX")
    return events, notes


# -------------------------------------------------------------- doctrine
def pacing_plan(category: str, score: float):
    return PACING.get(category, PACING["highlight"])


def punch_decision(category: str, score: float, intensity: float = 0.5):
    """Returns (do_zoom, intensity_fraction, reason). Fraction scales with
    doctrine intensity + event importance - dials, not switches."""
    base = {"funny": 0.11, "reaction": 0.09, "clutch": 0.09,
            "rage": 0.08, "fail": 0.07}.get(category, 0.0)
    if base and (score >= 55 or category in ("funny", "reaction")):
        frac = _clamp(base * (0.7 + 0.6 * intensity), 0.04, 0.13)
        return True, frac, f"{category} emphasis @ doctrine intensity " \
                           f"{intensity:.2f}"
    return False, 0.0, "held steady - tone benefits from calm camera"


# ------------------------------------------------------ dead-air surgeon
def find_dead_air(wav_path: str, min_pause: float = 1.2,
                  rel_floor: float = 4.0,
                  protected: list[dict] | None = None) -> list[tuple]:
    db = audio_db(wav_path)
    if db.size < 10:
        return []
    protected = protected or []
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
    if protected:
        kept = []
        for a, b in spans:
            hit = any(not (b < sp["a"] - 0.15 or a > sp["b"] + 0.15)
                      for sp in protected)
            (kept if not hit else []).append((a, b)) if not hit else None
        spans = [(a, b) for (a, b) in spans
                 if all(b < sp["a"] - 0.15 or a > sp["b"] + 0.15
                        for sp in protected)]
        del kept
    return spans


def build_trimmed(src: str, dest: str, start: float, dur: float,
                  pauses: list[tuple[float, float]],
                  protected: list[dict] | None = None):
    from .utils import resolve_bin
    lo, hi = start, start + dur
    inner = [(max(lo, a), min(hi, b)) for a, b in pauses]
    inner = [(a, b) for a, b in inner if b - a >= min(1.0, dur * 0.04)]
    if protected:
        inner = [(a, b) for a, b in inner
                 if all(b < sp["a"] - 0.15 or a > sp["b"] + 0.15
                        for sp in protected)]
    if not inner:
        return None, []
    kept, cursor = [], lo
    for a, b in inner:
        if a - cursor >= 0.8:
            kept.append((cursor, a))
        cursor = max(cursor, b)
    if hi - cursor >= 0.8:
        kept.append((cursor, hi))
    if not kept or len(kept) > 4:
        return None, []

    inputs: list[str] = []
    fc: list[str] = []
    for k, (a, b) in enumerate(kept):
        inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src]
        fc.append(f"[{k}:v]null[v{k}];[{k}:a]anull[a{k}]")
    fc.append("".join(f"[v{k}][a{k}]" for k in range(len(kept)))
              + f"concat=n={len(kept)}:v=1:a=1[outv][outa]")
    cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", dest]
    run(cmd)

    mapping = {"spans": [{"cut_start": a - lo, "cut_end": b - lo}
                         for a, b in inner]}
    total = sum(b - a for a, b in kept)
    mapping["total_removed"] = dur - total
    mapping["new_dur"] = total
    return dest, mapping


def remap(t: float, mapping: dict | None) -> float:
    if not mapping:
        return t
    for sp in mapping["spans"]:
        if t >= sp["cut_end"]:
            t -= (sp["cut_end"] - sp["cut_start"])
        elif t > sp["cut_start"]:
            t = sp["cut_start"]
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
