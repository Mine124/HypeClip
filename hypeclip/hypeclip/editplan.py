"""EDITPLAN — the editorial brain v1.
Builds ONE validated edit plan before rendering:
  signal timeline -> emotion curve -> events -> hook candidates ->
  doctrine intensity -> SFX/punch decisions -> attention-budget validation ->
  compiled plan-dict (consumed unchanged by fx.render_clip) + decision log.
Every entry: effect/start/end/intensity/target/reason/confidence."""
from __future__ import annotations
import math

import numpy as np

from . import decide, hooks
from .config import DATA_DIR
from .intel import audio_db


def _clamp(v, a, b):
    return max(a, min(b, v))


# ------------------------------------------------------------ signals
def collect_audio(wav_path: str) -> dict:
    db = audio_db(wav_path)
    n = db.size
    out = {"db": db, "onsets": [], "silences": [], "floor": -60.0}
    if n < 6:
        return out
    out["floor"] = float(np.percentile(db, 20))
    d = np.diff(db)
    thr = float(np.percentile(d, 92))
    for i in range(n - 1):
        if d[i] > max(4.5, thr) and db[i + 1] > out["floor"] + 6:
            out["onsets"].append({"t": float(i + 1),
                                  "strength": float(d[i])})
    quiet = db < out["floor"] + 4.0
    i = 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) >= 0.6:
                out["silences"].append((float(i), float(j)))
            i = j
        else:
            i += 1
    return out


def emotion_timeline(db: np.ndarray, step: float = 2.0) -> list[dict]:
    """Arousal curve: [{t,arousal,label}] — editing intensity follows this."""
    n = db.size
    if n < 4:
        return []
    floor = float(np.percentile(db, 15))
    ceil = float(np.percentile(db, 95))
    rng = max(6.0, ceil - floor)
    out = []
    t = 0.0
    while t < n:
        a, b = int(t), int(min(t + step, n))
        if b <= a:
            break
        ar = _clamp((float(db[a:b].mean()) - floor) / rng, 0, 1)
        label = ("calm" if ar < .25 else "building" if ar < .5
                 else "tense" if ar < .75 else "peak")
        out.append({"t": round(t, 1), "arousal": round(ar, 2),
                    "label": label})
        t += step
    return out


def event_timeline(sig: dict, words: list[dict], top_n: int = 6) -> list[dict]:
    """Merge acoustic onsets + emphatic words into ranked events."""
    events = []
    med_w = 0.0
    lens = [len((w.get("w") or "").strip("!,.?\"'")) for w in words] \
        if words else []
    if lens:
        med_w = float(np.median(lens))
    for o in sig["onsets"]:
        events.append({"t": o["t"], "kind": "audio_spike",
                       "importance": _clamp(o["strength"] / 14, 0, 1),
                       "reason": f"+{o['strength']:.0f}dB jump"})
    for w in words or []:
        tok = (w.get("w") or "").strip("!,.?\"'")
        if len(tok) >= 4 and med_w and len(tok) >= med_w * 1.9 \
                and any(c.isdigit() or c.isupper() for c in tok):
            events.append({"t": float(w.get("s", 0)), "kind": "key_word",
                           "importance": 0.55,
                           "word": tok[:18],
                           "reason": f"emphatic token '{tok[:14]}'"})
    events.sort(key=lambda e: -e["importance"])
    kept: list[dict] = []
    for e in events:
        if all(abs(e["t"] - k["t"]) > 1.0 for k in kept):
            kept.append(e)
        if len(kept) >= top_n:
            break
    kept.sort(key=lambda e: e["t"])
    return kept


# ------------------------------------------------------- hook candidates
def hook_candidates(segments: list[dict], wav_db: np.ndarray,
                    cur_dur: float) -> list[dict]:
    """Generate & score multiple openings. Report-only here (upstream hook
    trim already applied); informs future auto-selection + user A/B."""
    cands = [{"type": "chronological", "cut": 0.0}]
    d, why = hooks.best_trim(segments, cur_dur=cur_dur)
    if d > 0:
        cands.append({"type": "payload", "cut": d, "note": why})

    def feats_for(cut):
        f = decide.features_from_db(wav_db, cut, max(5.0, cur_dur - cut), 8.0)
        t = " ".join((w.get("w") or "") for s in segments
                     for w in (s.get("words") or [])
                     if float(w.get("s", 0)) >= cut)[:400].lower()
        f["emotion"] = 1.0 if any(x in t for x in
                                  ("no way", "insane", "let", "omg")) \
            else f["emotion"]
        return f

    scored = []
    for c in cands:
        f = feats_for(c["cut"])
        p = decide.predict(f)
        scored.append({**c, "pred_score": p["score"],
                       "watch": p["avg_watch_pct"]})
    # energy-open candidate: strongest rise in first 6s
    if wav_db.size > 8:
        rises = [(float(wav_db[i + 1] - wav_db[i]), i + 1)
                 for i in range(min(6, wav_db.size - 1))]
        r, idx = max(rises)
        if r > 4 and idx > 1.2:
            f = decide.features_from_db(wav_db, idx, max(5.0, cur_dur - idx),
                                        8.0)
            p = decide.predict(f)
            scored.append({"type": "energy_open", "cut": round(idx - 0.3, 2),
                           "pred_score": p["score"],
                           "watch": p["avg_watch_pct"]})
    scored.sort(key=lambda c: -c["pred_score"])
    return scored


# --------------------------------------------------- attention budget
def enforce_attention_budget(sfx_events: list[dict], punch_on: bool,
                             ring_on: bool, dur: float, doctrine: dict):
    """Viewer attention is finite: max 1 audio stinger per 1.5s window,
    punch suppressed if a ring is active, hard cap by doctrine tier."""
    notes = []
    # deconflict audio stingers
    kept = []
    for ev in sorted(sfx_events, key=lambda e: -e.get("gain_db", -99)):
        if all(abs(ev["t"] - k["t"]) >= 1.5 for k in kept):
            kept.append(ev)
        else:
            notes.append(f"dropped '{os.path.basename(ev['file'])}' @"
                         f"{ev['t']:.1f}s - too close to a louder cue")
    kept.sort(key=lambda e: e["t"])
    # ring vs punch: ring wins (camera already directing)
    if ring_on and punch_on:
        punch_on = False
        notes.append("punch-in suppressed - attention ring already directing")
    # global density cap
    cap = 4 if doctrine.get("beat") else 3
    if len(kept) > cap:
        dropped = len(kept) - cap
        kept = kept[:cap]
        notes.append(f"density cap: dropped {dropped} extra cue(s)")
    return kept, punch_on, notes


# ------------------------------------------------------------- compile
def build(media_src: str, start: float, dur: float, wav: str,
          segments: list[dict], settings, r, category: str,
          caption_texts: str, ctx: dict, idx: int) -> tuple[dict, list[str]]:
    """Returns (plan_updates, decision_log). plan_updates merge into the
    render plan dict exactly as fx.render_clip expects."""
    log: list[str] = []

    sig = collect_audio(wav)
    emo = emotion_timeline(sig["db"])
    words = [w for s in segments for w in (s.get("words") or [])]
    events = event_timeline(sig, words)
    cands = hook_candidates(segments, sig["db"], dur)
    if len(cands) > 1:
        alt = cands[1]
        log.append(f"🪝 alt-hook available: '{alt['type']}' cut@{alt['cut']:.1f}s "
                   f"predicts {alt['pred_score']} "
                   f"(kept current: {cands[0]['pred_score']})")

    doc = decide.pacing_plan(category, 70)
    log.append(f"🧭 doctrine[{category}]: {doc['note']}")

    # ---- SFX ----
    events_sfx: list[dict] = []
    if settings.sfx_enabled:
        pool_raw = os.listdir(settings.sfx_dir) if os.path.isdir(
            settings.sfx_dir) else []
        pool = [os.path.join(settings.sfx_dir, p) for p in pool_raw
                if p.lower().endswith((".wav", ".mp3", ".ogg"))]
        if pool:
            try:
                events_sfx, notes = decide.sfx_plan(
                    wav, caption_texts, settings, r, pool)
                log.extend("🧭 " + n for n in notes)
            except Exception as e:  # noqa: BLE001
                log.append(f"(sfx planner error: {e})")

    # ---- punch ----
    punch_on = settings.zoom_punch and doc["zoom"]
    amp = settings.zoom_strength
    do_punch, p_amp, why = decide.punch_decision(
        category, int(_clamp(score_of(events), 0, 99)))
    if do_punch and doc["zoom"]:
        punch_on = True
        amp = max(amp, p_amp)
        log.append(f"🧭 punch-in {int(p_amp * 100)}%: {why}")
    elif not doc["zoom"] and settings.zoom_punch:
        log.append("🧭 punch-in withheld by doctrine")

    # ---- attention ring passthrough flag ----
    ring_on = bool((ctx.get("tracks_by_index") or {}).get(idx)) or \
        bool(ctx.get("ring_planned"))

    # ---- budget ----
    events_sfx, punch_on, bnotes = enforce_attention_budget(
        events_sfx, punch_on and not ring_on, ring_on, dur, doc)
    log.extend("⚖ " + n for n in bnotes)

    impact_t = min(settings.pre_roll, dur * 0.6)
    if sig["onsets"]:
        nearest = min(sig["onsets"], key=lambda o: abs(o["t"] - impact_t))
        if abs(nearest["t"] - impact_t) <= 0.8:
            impact_t = nearest["t"]
            log.append(f"🧭 impact snapped to transient @ {impact_t:.2f}s")

    peak_emo = max(emo, key=lambda e: e["arousal"])["t"] if emo else impact_t
    log.append(f"👁 emotion curve: {len(emo)} windows, peak arousal @ "
               f"{peak_emo:.0f}s")

    updates = {
        "sfx_events": events_sfx,
        "zoom_punch": punch_on,
        "zoom_strength": amp,
        "shake": settings.shake if doc["shake"] else 0.0,
        "flash_intro": settings.flash_intro and doc["flash"],
        "bloom": settings.bloom and doc["bloom"],
        "grain": settings.grain and doc["grain"],
        "vignette": settings.vignette and doc["vignette"],
        "beat_sync": settings.beat_sync and doc["beat"],
        "impact_t": impact_t,
        "decision_log": {
            "emotion_timeline": emo,
            "events": events,
            "hook_candidates": cands,
            "doctrine": doc["note"],
            "content_category": category,
        },
    }
    return updates, log


def score_of(events: list[dict]) -> float:
    return 40.0 + 30.0 * max((e["importance"] for e in events), default=0)


def score_hook_alternatives_note():
    return ("CUO upgrade path: understand.py will fill segments/events "
            "semantically; editplan.consume_cuo(cuo) is the reserved hook.")
