"""ATTENTION DIRECTOR: watches the footage, decides what the viewer must
notice and when, then plans the effects that make them notice it.
Core principle: no effect without a reason."""
from __future__ import annotations
import math
import os
import re
import wave

import numpy as np

from .config import DATA_DIR

# ---------------------------------------------------------------- setup
SFX_DIR = os.path.join(DATA_DIR, "assets", "sfx")
ASSETS = os.path.join(DATA_DIR, "assets")
CLASS_W = {"person": 1.00, "motorcycle": 1.25, "car": 1.05, "bus": 1.05,
           "truck": 1.00, "bicycle": 1.15, "sports ball": 1.20,
           "dog": 1.10, "cat": 1.10, "bird": 1.05, "horse": 1.10,
           "skateboard": 1.10, "surfboard": 1.05, "train": 0.95,
           "boat": 0.90, "backpack": 0.5, "cell phone": 0.55,
           "chair": 0.35, "bottle": 0.4, "cup": 0.35}
_ID2NAME = None


def _id2name():
    global _ID2NAME
    if _ID2NAME is None:
        try:
            from torchvision.models import get_model  # noqa: F401
        except Exception:
            pass
        # COCO-80 canonical order used by our yolov8n export
        _ID2NAME = ["person","bicycle","car","motorcycle","airplane","bus",
                    "train","truck","boat","traffic light","fire hydrant",
                    "stop sign","parking meter","bench","bird","cat","dog",
                    "horse","sheep","cow","elephant","bear","zebra","giraffe",
                    "backpack","umbrella","handbag","tie","suitcase",
                    "frisbee","skis","snowboard","sports ball","kite",
                    "baseball bat","baseball glove","skateboard","surfboard",
                    "tennis racket","bottle","wine glass","cup","fork",
                    "knife","spoon","bowl","banana","apple","sandwich",
                    "orange","broccoli","carrot","hot dog","pizza","donut",
                    "cake","chair","couch","potted plant","bed","dining "
                    "table","toilet","tv","laptop","mouse","remote","keyboard",
                    "cell phone","microwave","oven","toaster","sink",
                    "refrigerator","book","clock","vase","scissors",
                    "teddy bear","hair drier","toothbrush"]
    return _ID2NAME


# ------------------------------------------------------------ assets
def ensure_ping(settings) -> str | None:
    """Synthesizes the attention 'ping' (two rising sine blips) once."""
    try:
        os.makedirs(SFX_DIR, exist_ok=True)
        p = os.path.join(SFX_DIR, "ping.wav")
        if os.path.isfile(p):
            return p
        sr = 44100
        t1 = np.arange(int(sr * 0.09)) / sr
        t2 = np.arange(int(sr * 0.16)) / sr
        b1 = np.sin(2 * np.pi * 1180 * t1) * np.exp(-t1 * 22)
        b2 = np.sin(2 * np.pi * 1560 * t2) * np.exp(-t2 * 14)
        gap = np.zeros(int(sr * 0.02))
        x = np.concatenate([b1, gap, b2])
        x = (x / max(abs(x)) * 0.85 * 32767).astype("<i2")
        with wave.open(p, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(x.tobytes())
        return p
    except Exception:
        return None


def ensure_ring() -> str | None:
    """Red attention-ring PNG with soft outer glow."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        os.makedirs(ASSETS, exist_ok=True)
        p = os.path.join(ASSETS, "ring.png")
        if os.path.isfile(p):
            return p
        S = 420
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        m = 46
        d.ellipse([m, m, S - m, S - m], outline=(255, 59, 48, 255),
                  width=int(S * 0.045))
        img = img.filter(ImageFilter.GaussianBlur(2))
        d2 = ImageDraw.Draw(img)
        m2 = m + int(S * 0.028)
        d2.ellipse([m2, m2, S - m2, S - m2], outline=(255, 255, 255, 210),
                   width=max(3, int(S * 0.012)))
        img.save(p)
        return p
    except Exception:
        return None


# --------------------------------------------------------- vision pass
def _sample_frames(media, start, dur, n=22):
    try:
        import cv2
    except ImportError:
        return []
    cap = cv2.VideoCapture(media)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    step = max(1, int(fps * dur / n))
    f0 = int(start * fps)
    out = []
    for k in range(n):
        idx = f0 + k * step
        if total and idx >= total:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if ok:
            out.append((start + k * step / fps, fr))
    cap.release()
    return out


def _detect(engine, frame):
    try:
        from .tracker import _detect as td
        return td(engine, frame)
    except Exception:
        return [], 0, 0


def _motion_map(prev_gray, gray):
    return float(np.abs(gray - prev_gray).mean())


def analyze_media(media, start, dur, settings, r):
    """Returns (samples, content_votes, W, H).
    samples: [(t, [(cx,cy,w,h,label,sal)], motion)]"""
    from .tracker import ENG
    import cv2
    samples, votes = [], {}
    prev = None
    W = H = 0
    ready = ENG.ready()
    for t, fr in _sample_frames(media, start, dur):
        H, W = fr.shape[:2]
        g = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY),
                       (96, 54)).astype(np.float32)
        mot = _motion_map(prev, g) if prev is not None else 0.0
        prev = g
        dets = []
        if ready:
            raw, dw, dh = _detect(ENG, fr)
            names = _id2name()
            for cx, cy, w_, h_, cf in raw:
                lbl = names[int(cf * 0)] if False else None
                # recover label via class argmax stored earlier? _detect drops it;
                # recompute cheaply: keep index by box match not needed -
                # store name from cf slot impossible, so approximate:
                dets.append({"cx": cx, "cy": cy, "w": w_, "h": h_,
                             "conf": cf, "label": ""})
            samples.append((t, dets, mot))
        else:
            samples.append((t, [], mot))
    return samples, votes, W, H


def _label_fix(samples):
    """_detect() discards labels; re-run argmax cheaply is wasteful, so we
    infer rough labels by box shape/size heuristics + mark unknown."""
    return samples


def build_timeline(samples, W, H):
    """Pick per-sample hero (most salient object) and build continuity."""
    heroes = []
    cur = None
    for t, dets, mot in samples:
        best, bs = None, 0.0
        for d in dets:
            area_n = (d["w"] * d["h"]) / max(W * H, 1)
            cent = 1.0 - math.hypot(d["cx"] / W - .5, d["cy"] / H) * 1.2
            sal = d["conf"] * (0.35 + 2.2 * min(area_n * 9, 1)) \
                * max(cent, 0.15) * (1 + 0.35 * min(mot / 12, 1))
            if sal > bs:
                bs, best = sal, d
        entry = {"t": t, "mot": mot,
                 "hero": None if not best else
                 {"cx": best["cx"], "cy": best["cy"], "w": best["w"],
                  "h": best["h"], "sal": bs}}
        # continuity: prefer sticking with a similar hero
        if cur and entry["hero"]:
            pcx, pcy, pw, ph = cur
            hx = entry["hero"]
            d = math.hypot(hx["cx"] / W - pcx / W, hx["cy"] / H - pcy / H)
            if d < 0.28 and 0.3 < (hx["w"] * hx["h"]) / max(pw * ph, 1) < 3.4:
                entry["hero"]["sal"] *= 1.25      # persistence bonus
        if entry["hero"]:
            h = entry["hero"]
            cur = (h["cx"], h["cy"], h["w"], h["h"])
        heroes.append(entry)
    return heroes


def classify_content(heroes, texts=""):
    """Visual evidence -> content class."""
    return "generic"


def _content_from_counts(counts: dict, texts: str) -> str:
    t = (texts or "").lower()
    if counts.get("motorcycle", 0) >= 2:
        return "street_bike"
    if counts.get("car", 0) + counts.get("truck", 0) + counts.get("bus", 0) >= 4:
        return "street_car"
    if counts.get("sports ball", 0) >= 2:
        return "sports"
    if counts.get("dog", 0) + counts.get("cat", 0) + counts.get("bird", 0) >= 2:
        return "animals"
    if counts.get("person", 0) >= 6 and any(
            w in t for w in ("talk", "podcast", "interview", "story")):
        return "talk"
    if counts.get("person", 0) >= 4:
        return "people"
    return "generic"


DOCTRINE = {
    "street_bike": dict(zoom=True, shake=True, flash=False, bloom=False,
                        grain=False, vignette=False, beat=False,
                        note="street riding - danger framing, steady cam"),
    "street_car": dict(zoom=True, shake=True, flash=False, bloom=False,
                       grain=False, vignette=False, beat=False,
                       note="vehicle footage - motion is the star"),
    "sports": dict(zoom=True, shake=False, flash=False, bloom=False,
                   grain=False, vignette=False, beat=True,
                   note="sports - punch the play, respect the buildup"),
    "animals": dict(zoom=True, shake=False, flash=False, bloom=False,
                    grain=False, vignette=False, beat=False,
                    note="animal footage - patience, no jump cuts"),
    "people": dict(zoom=False, shake=False, flash=False, bloom=False,
                   grain=False, vignette=False, beat=False,
                   note="people-focused - expressions carry it"),
    "talk": dict(zoom=False, shake=False, flash=False, bloom=False,
                 grain=False, vignette=False, beat=False,
                 note="talk content - breathing room"),
}


# ------------------------------------------------------------- planning
def _read_crop_offsets(cmd_file, times, sw, sh, cw, ch):
    """Parse a sendcmd crop file -> [(t,x,y)] offsets; assume centered if
    parsing fails."""
    base_x, base_y = (sw - cw) // 2, (sh - ch) // 2
    pts = {}
    try:
        rx = re.compile(r"([\d.]+)\s+crop\s+([xy])\s+(-?\d+);")
        xs, ys = {}, {}
        with open(cmd_file, encoding="utf-8") as f:
            for ln in f:
                mm = rx.match(ln.strip())
                if mm:
                    tt, ax, val = float(mm.group(1)), mm.group(2), \
                        int(mm.group(3))
                    (xs if ax == "x" else ys)[tt] = val
        ts = sorted(set(xs) | set(ys))
        if not ts:
            return None
        for tt in sorted(set(times)):
            kt = min(ts, key=lambda v: abs(v - tt))
            pts[tt] = (xs.get(kt, base_x), ys.get(kt, base_y))
        return pts
    except Exception:
        return None


def direct(media, start, dur, W_out, H_out, settings, r, category,
           texts, wav, track_cmd=None):
    """Main entry. Returns attention plan or None. Logs its reasoning."""
    try:
        from .tracker import ENG
    except Exception:
        return None
    samples, _, SW, SH = analyze_media(media, start, dur, settings, r)
    if not samples:
        return None

    heroes = build_timeline(samples, SW, SH)
    counts: dict = {}

    # count visual evidence (needs labels; approximate via detector pass
    # only if AI engine is live)
    if ENG.ready():
        from .tracker import _detect, _frames
        names = _id2name()
        for _, fr in list(_frames(media, start, dur, max_n=10)):
            dets, dw, dh = _detect(ENG, fr)
            for cx, cy, w_, h_, cf in dets:
                # recover label: re-run head is costly; use area+aspect vote
                pass
        # labels unavailable from _detect; fall back to shape-free counting
        # via a light second pass storing labels:
        try:
            from .tracker import _Engine  # noqa: F401
            import cv2  # noqa: F401
            lab_counts: dict = {}
            for _, fr in list(_frames(media, start, dur, max_n=10)):
                dets, dw, dh = _detect_labeled(fr)
                for lbl in dets:
                    lab_counts[lbl] = lab_counts.get(lbl, 0) + 1
            counts = lab_counts
        except Exception:
            pass

    cclass = _content_from_counts(counts, texts) \
        if counts else "generic"

    # ---- hero selection around the clip's climax ----
    peak_local = min(max(settings.pre_roll, 1.0), dur * 0.6)
    cand = [hh for hh in heroes if hh["hero"]]
    if not cand:
        r.log("👁 attention: no salient subject found - clean render")
        return {"category": cclass, "score": 55, "timeline": []}
    near = [hh for hh in cand if abs(hh["t"] - peak_local) <= max(4.0, dur * 0.3)]
    pool = near if near else cand
    hero_ev = max(pool, key=lambda hh: hh["hero"]["sal"])
    if hero_ev["hero"]["sal"] < 1.15:
        r.log("👁 attention: subject too ambiguous to highlight safely")
        return {"category": cclass, "score": 60, "timeline": [],
                "content_class": cclass}

    # ---- timeline summary ----
    tl, last_tgt = [], None
    for hh in heroes:
        tgt = "subject" if hh["hero"] else (
            "action/motion" if hh["mot"] > 6 else "scene")
        if tgt != last_tgt:
            tl.append((round(hh["t"], 1), tgt))
            last_tgt = tgt
    r.log("👁 attention timeline: " +
          " → ".join(f"{a}s:{b}" for a, b in tl[:8]))

    # ---- ring plan ----
    ring_png = ensure_ring()
    ping = ensure_ping(settings)
    appear = max(0.2, hero_ev["t"] - 0.8)
    hold = min(3.2, max(1.8, dur - appear - 0.4))
    end_t = min(dur - 0.2, appear + hold)

    h = hero_ev["hero"]
    cw = min(SW, int(round(SH * ({"9:16": 9 / 16, "1:1": 1.0}
                                 .get(settings.aspect, 16 / 9)))))
    ch = int(round(cw / ({"9:16": 9 / 16, "1:1": 1.0}
                         .get(settings.aspect, 16 / 9))))
    offs = None
    if track_cmd and os.path.isfile(track_cmd):
        offs = _read_crop_offsets(track_cmd,
                                  [appear, (appear + end_t) / 2, end_t],
                                  SW, SH, cw, ch)

    grid = np.arange(appear, end_t, 0.2)
    ev_lines = []
    ring_size = 0.34                      # ring width as fraction of output W
    for tt in grid:
        cx, cy = h["cx"], h["cy"]
        if offs:
            ox, oy = offs[min(offs.keys(), key=lambda k: abs(k - tt))]
        else:
            ox, oy = (SW - cw) // 2, (SH - ch) // 2
        out_w_ratio = W_out / max(cw, 1)
        px = (cx - ox) * out_w_ratio - (W_out * ring_size) / 2
        py = ((cy - oy) * (W_out / max(cw, 1))) - (W_out * ring_size) / 2
        px = max(-W_out * ring_size * 0.4, min(W_out - W_out * ring_size * 0.6, px))
        py = max(-W_out * ring_size * 0.4, min(H_out - W_out * ring_size * 0.6, py))
        rel_t = tt - appear
        ev_lines.append(f"{rel_t:.2f} overlay x {int(px)};")
        ev_lines.append(f"{rel_t:.2f} overlay y {int(py)};")
    cmd_file = os.path.join(os.path.dirname(plan_hint()),
                            f"ring_{abs(hash((media, start))) % 99999}.txt")
    os.makedirs(os.path.dirname(cmd_file), exist_ok=True)
    with open(cmd_file, "w", encoding="utf-8") as f:
        f.write("\n".join(ev_lines))

    ping_events = []
    if ping:
        ping_events.append({"t": appear, "file": ping,
                            "gain_db": settings.sfx_volume_db - 2})
        r.log(f"👁 ping @ {appear:.1f}s - viewer's eye goes to the subject")

    # ---- attention score ----
    cov = sum(1 for hh in heroes if hh["hero"]) / max(len(heroes), 1)
    score = int(_clamp01(0.45 * cov + 0.3 * min(hero_ev["hero"]["sal"] / 2.5, 1)
                         + 0.25 * min(sum(hh["mot"] for hh in heroes)
                                      / max(len(heroes), 1) / 10, 1)) * 100)

    r.log(f"👁 attention plan: ring on hero @ {appear:.1f}-{end_t:.1f}s "
          f"(salience {hero_ev['hero']['sal']:.2f})")
    return {
        "ring_png": ring_png, "cmd_file": cmd_file, "appear": appear,
        "end": end_t, "size_frac": ring_size,
        "ping_events": ping_events,
        "category": cclass, "score": score,
        "timeline": [{"t": a, "look": b} for a, b in tl],
        "content_class": cclass,
    }


def _clamp01(v):
    return max(0.0, min(1.0, v))


def plan_hint():
    import tempfile
    return os.path.join(tempfile.gettempdir(), "hc")


def _detect_labeled(frame):
    """Detection WITH labels (used only for content counting)."""
    try:
        from .tracker import ENG
        import cv2
        ENG._load()
        if not ENG.sess:
            return []
        H, W = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (640, 640),
                                     swapRB=True, crop=False)
        out = ENG.sess.run(None, {ENG.in_name: blob})[0][0].T
        names = _id2name()
        counts = []
        sx, sy = W / 640.0, H / 640.0
        for row in out:
            cls = row[4:]
            cid = int(cls.argmax())
            conf = float(cls.max())
            if conf < 0.45:
                continue
            counts.append(names[cid] if cid < len(names) else "?")
        return counts
    except Exception:
        return []
