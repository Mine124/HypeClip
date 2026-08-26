"""Intelligence pack: signal fusion, natural boundaries, hook detection,
viral scoring, categories, metadata, thumbnails, clip understanding."""
from __future__ import annotations
import json
import math
import os
import re
import subprocess

import numpy as np

SR = 4000


# ------------------------------------------------------------ audio utils
def _mono(path: str) -> np.ndarray | None:
    try:
        from .utils import resolve_bin, run
        raw = run([resolve_bin("ffmpeg"), "-v", "error", "-i", path,
                   "-ac", "1", "-ar", str(SR), "-vn", "-f", "f32le", "-"],
                  capture_bytes=True)
        return np.frombuffer(raw, np.float32)
    except Exception:
        return None


def audio_db(path: str) -> np.ndarray:
    """Per-second loudness in dB."""
    x = _mono(path)
    if x is None or x.size < SR:
        return np.zeros(0)
    n = x.size // SR
    rms = np.sqrt(np.maximum((x[:n * SR].reshape(n, SR) ** 2).mean(axis=1),
                             1e-9))
    return 20.0 * np.log10(rms + 1e-6)


# ------------------------------------------------- natural boundaries + hook
def adjust_boundaries(moments: list, media_path: str, settings, reporter):
    """Replace fixed-length cuts with buildup→climax→decay boundaries and
    shift starts onto the energy rise (hook). Audio-only, cheap."""
    db = audio_db(media_path)
    if db.size < 30:
        return
    floor = float(np.percentile(db, 20))
    total = float(db.size)
    cap = min(float(settings.clip_duration) * 1.35, 150.0)
    changed = 0
    for m in moments:
        peak = float(m.peak)
        lo = max(0.0, peak - max(settings.pre_roll * 2.0, 12.0))
        start = max(0.0, peak - settings.pre_roll)
        i = int(min(peak, total - 2)) - 1
        quiet_run = 0
        while i > lo:
            if db[i] < floor + 4.0:
                quiet_run += 1
                if quiet_run >= 2:
                    start = float(i + 1)
                    break
            else:
                quiet_run = 0
            i -= 1
        seg_lo, seg_hi = int(start), int(min(start + 7, peak, total - 2))
        best_k, best_rise = 0.0, 0.0
        for k in range(seg_hi - seg_lo - 1):
            rise = float(db[seg_lo + k + 1] - db[seg_lo + k])
            if rise > best_rise:
                best_rise, best_k = rise, float(k)
        if best_rise > 4.0 and best_k > 1.5:
            start = start + (best_k - 0.9)
        start = max(0.0, min(start, peak - 4.0))
        search_hi = int(min(total - 2, peak + cap))
        end = min(start + cap, total)
        j = int(min(max(peak + 12, start + 18), search_hi))
        calm = 0
        while j < search_hi:
            if db[j] < floor + 4.5:
                calm += 1
                if calm >= 2:
                    end = float(j)
                    break
            else:
                calm = 0
            j += 1
        end = max(end, peak + 5.0)
        end = min(end, start + cap, total)
        if end - start < 12.0:
            end = min(start + 12.0, total)
            start = max(0.0, end - 12.0)
        if abs(end - m.end) > 1.5 or abs(start - m.start) > 1.5:
            changed += 1
        m.start, m.end = round(start, 1), round(end, 1)
    reporter.log(f"smart boundaries applied on {changed}/{len(moments)} clips "
                 f"(buildup→climax→decay + hook alignment)")


# ------------------------------------------------------------ categories
_CAT_WORDS = {
    "clutch": ["clutch", "ace", "1v", "insane", "no way",
               "letsgo", "let's go", "clip it", "whattt", "omg"],
    "funny": ["lol", "lmao", "laugh", "bruh", "meme", "nahh", "broo",
              "hahaha", "deadass"],
    "fail": ["died", "down bad", "oof", "threw", "grief", "fail", "oops"],
    "win": ["won", "winner", "victory", "champion", "gg ", "we win"],
    "rage": ["hacker", "cheater", "rigged", "uninstall", "kicked", "scam"],
    "reaction": ["what", "screaming", "nooo", "yooo", "sheesh"],
}
CAT_EMOJI = {"funny": "😂", "clutch": "🎯", "win": "🏆", "fail": "💀",
             "rage": "😡", "reaction": "😲", "highlight": "⭐"}


def classify(text: str) -> tuple[str, list[str]]:
    t = (text or "").lower()
    scores = {}
    for cat, words in _CAT_WORDS.items():
        s = sum(t.count(w) for w in words)
        if s:
            scores[cat] = s
    if not scores:
        return "highlight", []
    cat = max(scores, key=scores.get)
    tags = [c for c, s in sorted(scores.items(), key=lambda kv: -kv[1])[:3]]
    return cat, tags


# ------------------------------------------------------------ viral score
def viral_score(db: np.ndarray, start: float, end: float,
                peak_score: float, texts: str) -> tuple[int, list[str]]:
    reasons = []
    n = db.size
    if n < 10:
        return 50, ["not enough data"]
    a, b = int(np.clip(start, 0, n - 2)), int(np.clip(end, 2, n))
    seg = db[a:b]
    if seg.size < 4:
        return 50, ["not enough data"]
    dur = b - a
    pace = float(np.std(seg))
    p_pts = int(np.clip(pace / 9.0, 0, 1) * 25)
    reasons.append(("✓ fast pacing" if p_pts >= 15 else "✗ flat pacing"))
    h = min(4, seg.size - 1)
    rise = float(np.max(seg[1:h + 1]) - seg[0]) if h >= 1 else 0.0
    h_pts = int(np.clip(rise / 10.0, 0, 1) * 20)
    reasons.append(("✓ strong hook" if h_pts >= 12 else "✗ weak opening"))
    if float(np.mean(seg[:3])) < float(np.percentile(db, 25)) + 3:
        reasons.append("✗ slow intro")
        h_pts = max(0, h_pts - 6)
    pay = int(np.clip((peak_score - 2) / 14.0, 0, 1) * 25)
    reasons.append(("✓ big climax" if pay >= 15 else "✗ mild climax"))
    tail = seg[-4:] if seg.size >= 4 else seg
    drop = float(seg.max() - tail.min())
    e_pts = int(np.clip(drop / 8.0, 0, 1) * 15)
    reasons.append(("✓ clean ending" if e_pts >= 9 else "✗ abrupt ending"))
    l_pts = 15 if 22 <= dur <= 80 else (8 if 15 <= dur <= 110 else 3)
    reasons.append(("✓ good length" if l_pts >= 12 else "✗ length off"))
    if re.search(r"\b(lol|lmao|haha|no way|insane|crazy)\b",
                 (texts or "").lower()):
        reasons.append("✓ funny/emotional beat")
        p_pts = min(25, p_pts + 4)
    score = int(np.clip(p_pts + h_pts + pay + e_pts + l_pts, 5, 99))
    order = {"✓": 0, "✗": 1}
    reasons.sort(key=lambda r: (order[r[0]], r))
    return score, reasons[:6]


# ------------------------------------------------------------ metadata
_STOP = set("""a an the and or but is are was were be been this that these those
it its i you he she they we my your our their of to in on at for with from by
as so just like really very much more some any no yeah ok okay um uh oh ah
gonna wanna got get gotcha dude man bro guys""".split())


def make_metadata(texts: str, src_title: str, cat: str) -> dict:
    words = [w.strip("!,.?,").lower() for w in re.split(r"\s+", texts or "")]
    freq: dict[str, int] = {}
    for w in words:
        if len(w) > 3 and w not in _STOP and not w.isdigit():
            freq[w] = freq.get(w, 0) + 1
    kws = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:6]]
    shout = ""
    for ln in (texts or "").split(". "):
        letters = [c for c in ln if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6 \
                and len(ln.strip()) > 4:
            shout = ln.strip().strip(".").title()
            break
    title_bits = [b for b in [shout, src_title[:38]] if b]
    title = (" | ".join(title_bits) or "insane moment")[:90]
    cat_tag = {"funny": "#funny", "clutch": "#clutch", "win": "#win",
               "fail": "#fail", "rage": "#rage",
               "reaction": "#reaction"}.get(cat, "#highlights")
    tags = ["#shorts", "#fyp", "#viral", cat_tag, "#gaming"] + \
           ["#" + k for k in kws[:3]]
    desc = (f"{shout or 'Best moment'} — clipped from "
            f"{src_title[:60]}.\n\n{' '.join(tags)}")
    seo = min(99, 55 + (12 if shout else 0) + min(len(kws) * 3, 18)
              + (10 if len(desc) > 80 else 0))
    return {"title": title, "desc": desc, "hashtags": " ".join(tags[:8]),
            "keywords": kws, "seo": seo}


# ------------------------------------------------------------ thumbnails
def thumbnails(video: str, impact_t: float, out_dir: str, stem: str,
               count: int = 3) -> list[str]:
    from .utils import resolve_bin
    urls = []
    offs = [0.0, 1.2, -1.2] if count >= 3 else [0.0]
    for i, off in enumerate(offs[:count]):
        t = max(0.1, impact_t + off)
        dest = os.path.join(out_dir, f"{stem}_thumb{i + 1}.jpg")
        try:
            subprocess.run(
                [resolve_bin("ffmpeg"), "-y", "-v", "error",
                 "-ss", f"{t:.2f}", "-i", video, "-frames", "1",
                 "-vf", "scale=1080:-2", "-q:v", "3", dest],
                check=True, capture_output=True)
            urls.append("/clips/" + os.path.basename(dest))
        except Exception:
            continue
    return urls


# ---------------------------------------------------- post-render finalizer
def finalize(wav: str, texts: str, src_title: str, peak_score: float,
             start: float, dur: float, video: str, impact_t: float,
             out_dir: str, stem: str) -> dict:
    """Called by pipeline after captions+render. Returns rich clip info."""
    db = audio_db(wav)
    cat, tags = classify(texts)
    viral, reasons = viral_score(db, 0.0, dur, peak_score, texts)
    meta = make_metadata(texts, src_title, cat)
    thumbs = thumbnails(video, impact_t, out_dir, stem)

    # ---- clip understanding (CUO v1) ----
    try:
        from . import understand
        cuo_video = video if video and os.path.isfile(video) else None
        cuo = understand.build(cuo_video, wav, texts, start)
        with open(os.path.join(out_dir, f"{stem}.cuo.json"), "w",
                  encoding="utf-8") as _f:
            json.dump(cuo, _f, indent=1)
        reasons.append("🧠 " + understand.summarize(cuo))
    except Exception:
        pass

    return {"viral": viral, "reasons": reasons, "category": cat,
            "tags": tags, "meta": meta, "thumb": thumbs[0] if thumbs else "",
            "thumbs": thumbs}
