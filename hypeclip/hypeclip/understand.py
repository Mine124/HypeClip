"""Clip Understanding v1 (heuristic CUO). Builds a structured
ClipUnderstanding object from audio + vision signals. LLM-upgradeable:
when understand_llm lands it replaces build() internals; schema stays."""
from __future__ import annotations

import numpy as np


def _clamp(v, a, b):
    return max(a, min(b, v))


def _db(path):
    try:
        from .intel import audio_db
        return audio_db(path)
    except Exception:
        return np.zeros(0, dtype=np.float32)


def _transients(db):
    out, d = [], np.diff(db)
    if d.size == 0:
        return out
    thr = max(4.5, float(np.percentile(d, 93)))
    i = 0
    while i < d.size:
        if d[i] >= thr:
            j = i
            while j + 1 < d.size and d[j + 1] >= thr * 0.8:
                j += 1
            pk = int(np.argmax(db[i:j + 2])) + i
            out.append({"t": float(pk),
                        "strength": float(db[pk] - db[max(0, i - 1)])})
            i = j + 1
        else:
            i += 1
    return out


def _silences(db):
    if db.size < 4:
        return []
    floor = float(np.percentile(db, 20)) + 4.0
    q = db < floor
    spans, i = [], 0
    while i < db.size:
        if q[i]:
            j = i
            while j < db.size and q[j]:
                j += 1
            if (j - i) >= 0.5:
                spans.append((float(i), float(j)))
            i = j
        else:
            i += 1
    return spans


def _arc(db, step=2.0):
    n = db.size
    if n < 4:
        return []
    lo = float(np.percentile(db, 15))
    hi = float(np.percentile(db, 95))
    rng = max(6.0, hi - lo)
    out, t = [], 0.0
    while t < n:
        a, b = int(t), int(min(t + step, n))
        if b <= a:
            break
        ar = _clamp((float(db[a:b].mean()) - lo) / rng, 0, 1)
        lab = ("calm" if ar < .25 else "curious" if ar < .45
               else "tense" if ar < .65 else "anticipation" if ar < .82
               else "peak")
        out.append({"t": round(t, 1), "arousal": round(ar, 2),
                    "label": lab})
        t += step
    return out


def _visual_counts(video, start, dur, max_n=8):
    """Uses Eagle-Eye engine WITH labels (single pass)."""
    counts, W, H = {}, 0, 0
    try:
        from .tracker import ENG
        import cv2
        ENG._load()
        if not ENG.sess:
            return counts
        cap = cv2.VideoCapture(video)
        if not cap.isOpened():
            return counts
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        tot = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        names = ["person", "bicycle", "car", "motorcycle", "airplane",
                 "bus", "train", "truck", "boat", "traffic light",
                 "fire hydrant", "stop sign", "parking meter", "bench",
                 "bird", "cat", "dog", "horse", "sheep", "cow",
                 "elephant", "bear", "zebra", "giraffe", "backpack",
                 "umbrella", "handbag", "tie", "suitcase", "frisbee",
                 "skis", "snowboard", "sports ball", "kite",
                 "baseball bat", "baseball glove", "skateboard",
                 "surfboard", "tennis racket", "bottle", "wine glass",
                 "cup", "fork", "knife", "spoon", "bowl", "banana",
                 "apple", "sandwich", "orange", "broccoli", "carrot",
                 "hot dog", "pizza", "donut", "cake", "chair", "couch",
                 "potted plant", "bed", "dining table", "toilet", "tv",
                 "laptop", "mouse", "remote", "keyboard", "cell phone"]
        step = max(1, int(fps * dur / max_n))
        for k in range(max_n):
            idx = int((start + k * step / fps) * fps)
            if tot and idx >= tot:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok:
                continue
            Hh, Ww = fr.shape[:2]
            W, H = Ww, Hh
            blob = cv2.dnn.blobFromImage(fr, 1 / 255.0, (640, 640),
                                         swapRB=True, crop=False)
            o = ENG.sess.run(None, {ENG.in_name: blob})[0][0].T
            for row in o:
                cid = int(row[4:].argmax())
                cf = float(row[4:].max())
                if cf >= 0.5 and cid < len(names):
                    counts[names[cid]] = counts.get(names[cid], 0) + 1
        cap.release()
    except Exception:
        pass
    return counts


def _content_type(counts, texts=""):
    t = (texts or "").lower()
    if counts.get("motorcycle", 0) >= 2:
        return "street_bike"
    if counts.get("car", 0) + counts.get("bus", 0) + \
            counts.get("truck", 0) >= 4:
        return "street_vehicle"
    if counts.get("sports ball", 0) >= 2:
        return "sports"
    if counts.get("dog", 0) + counts.get("cat", 0) + \
            counts.get("bird", 0) >= 2:
        return "animals"
    if any(k in t for k in ("game", "kill", "clutch", "respawn")):
        return "gaming"
    if any(k in t for k in ("podcast", "interview", "story")):
        return "talk"
    if counts.get("person", 0) >= 5:
        return "people"
    return "generic"


def build(media_video: str | None, wav: str, texts: str = "",
          start_offset: float = 0.0) -> dict:
    """Returns the CUO dict. Never raises."""
    cuo = {"schema": "cuo.v1", "lexical": False,
           "content_type": "generic", "primary_subject": "",
           "events": [], "emotion_timeline": [], "attention_timeline": [],
           "dialogue_beats": [], "setup": None, "peak": None,
           "reaction": None, "payoff_end": None,
           "emphasis_words": [], "keywords": [],
           "protected_beats": [], "why_interesting": "", "warnings": []}
    try:
        db = _db(wav)
        if db.size < 6:
            cuo["warnings"].append("no usable audio")
            return cuo

        emo = _arc(db)
        cuo["emotion_timeline"] = emo
        if emo:
            peak = max(emo, key=lambda e: e["arousal"])
            cuo["peak"] = peak["t"]
            pre = [e for e in emo if e["t"] < peak["t"]]
            cuo["setup"] = pre[0]["t"] if pre else 0.0

        tr = _transients(db)
        sil = _silences(db)
        for tr_ in sorted(tr, key=lambda x: -x["strength"])[:5]:
            ev = {"t": tr_["t"], "kind": "impact",
                  "importance": _clamp(tr_["strength"] / 14, 0, 1),
                  "note": f"+{tr_['strength']:.0f}dB"}
            cuo["events"].append(ev)
        for a, b in sil:
            nxt_i = min(int(b) + 1, db.size - 1)
            rise = db[nxt_i] - db[int(a)]
            if 0.35 <= (b - a) <= 1.6 and rise >= 5:
                cuo["events"].append({"t": a, "kind": "suspense_pause",
                                      "importance": 0.7,
                                      "note": f"{b-a:.1f}s -> +{rise:.0f}dB"})
                cuo["protected_beats"].append({"a": a, "b": b})
        cuo["events"].sort(key=lambda e: e["t"])

        if media_video and os.path.isfile(media_video):
            cuo["visual_counts"] = _visual_counts(
                media_video, start_offset, min(dur := db.size, 120.0))
            cuo["content_type"] = _content_type(
                cuo["visual_counts"], texts)

        pk = cuo["peak"] if cuo["peak"] is not None else dur * 0.4
        cuo["why_interesting"] = (
            f"Arousal climbs from {emo[0]['label']} to a {emo and 'peak'} "
            f"around {pk:.0f}s with {len(tr)} hard audio hits; "
            f"content reads as {cuo['content_type'].replace('_', ' ')}.")
        cuo["lexical"] = bool(texts)
    except Exception as e:  # noqa: BLE001
        cuo["warnings"].append(str(e)[:160])
    return cuo


import os  # noqa: E402  (kept late-safe for tooling)


def summarize(cuo: dict) -> str:
    if cuo.get("warnings") and not cuo.get("emotion_timeline"):
        return "understanding unavailable"
    tl = " → ".join(f"{e['t']:.0f}s:{e['label']}"
                    for e in cuo.get("emotion_timeline", [])[:6])
    return (f"[{cuo['content_type']}] arc: {tl} · "
            f"{len(cuo['events'])} events · "
            f"{len(cuo['protected_beats'])} protected beats")
