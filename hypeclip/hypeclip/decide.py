"""Decision engine: every editing action carries a confidence + reason.
Hosts the retention predictor (heuristic prior, self-calibrates from
outcomes.json once >=10 posted clips are tracked in the Learner)."""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .config import DATA_DIR
from .intel import audio_db

OUTCOMES = os.path.join(DATA_DIR, "outcomes.json")


# ------------------------------------------------------------ helpers
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
    """Affine correction learned from YOUR posting history."""
    try:
        d = json.load(open(OUTCOMES, encoding="utf-8"))
        samples = d.get("samples", [])
        if len(samples) < 10:
            return 1.0
        m = float(np.mean([_perf_simple(s) for s in samples]))
        return _clamp(0.6 + m * 0.9, 0.75, 1.35)
    except Exception:
        return 1.0


# ---------------------------------------------------- feature extraction
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


# ---------------------------------------------------- retention predictor
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


# ---------------------------------------------------- SFX taste engine
def sfx_plan(wav_path: str, texts: str, settings, r, pool: list[str]):
    """Decides WHETHER/WHICH/WHEN/LOUDNESS for sound effects.
    Returns (events, notes). Notes are human-readable justifications."""
    events: list[dict] = []
    notes: list[str] = []
    db = audio_db(wav_path)
    n = db.size

    def find(name):
        for p in pool:
            if os.path.splitext(os.path.basename(p))[0].lower() == name:
                return p
        return None

    floor = float(np.percentile(db, 25)) if n else -60.0
    dur_est = max(5.0, n)
    impact_t = min(max(settings.pre_roll, 0.2), dur_est * 0.35)

    # is there a genuine energy spike near the impact point?
    ia = int(np.clip(impact_t, 0, max(0, n - 1)))
    spike = bool(n > ia + 2
                 and (db[ia] - db[int(np.clip(ia - 3, 0, n - 1))] > 5.0))
    conf = 0.85 if spike else 0.45

    air = find("airhorn")
    if air:
        if conf > 0.6:
            events.append({"t": impact_t, "file": air,
                           "gain_db": settings.sfx_volume_db})
            notes.append(f"impact hit @ {impact_t:.1f}s "
                         f"(real spike detected, conf {conf:.2f})")
        else:
            events.append({"t": impact_t, "file": air,
                           "gain_db": settings.sfx_volume_db - 6})
            notes.append(f"soft impact only (weak spike, conf {conf:.2f}, -6dB)")

    riser = find("riser")
    if riser and spike and impact_t > 1.8:
        events.append({"t": impact_t - 1.6, "file": riser,
                       "gain_db": settings.sfx_volume_db - 7})
        notes.append("riser layered before drop")

    t = (texts or "").lower()
    boom = find("vine_boom")
    if boom and any(w in t for w in ("lol", "lmao", "bruh", "haha",
                                     "fall", "fail", "oof")):
        events.append({"t": min(dur_est - 1, max(1.0, dur_est * 0.55)),
                       "file": boom,
                       "gain_db": settings.sfx_volume_db - 4})
        notes.append("cartoon boom (comedy markers in speech)")

    if not spike and "boom" not in [e["file"] for e in events]:
        notes.append("restraint chosen: flat energy + no comedy markers "
                     "-> no layered SFX (silence is the right call)")
    return events, notes


# ---------------------------------------------------- punch-in decision
def punch_decision(category: str, score: float):
    """Returns (do_zoom, strength_fraction, reason)."""
    if category in ("funny", "reaction"):
        return True, 0.10, "pattern-interrupt suits comedy beats"
    if category == "clutch" and score >= 60:
        return True, 0.09, "emphasis on clutch payoff"
    if category == "rage":
        return True, 0.08, "amped frustration framing"
    return False, 0.0, "held steady - tone benefits from calm camera"
