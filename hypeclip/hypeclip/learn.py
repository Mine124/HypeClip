"""Outcome-driven learner: records how your POSTED clips performed (public
stats), fits a model, and retunes future hype selection - preferred length,
preferred stream-position zone, per-moment score boosts."""
from __future__ import annotations
import json
import math
import os
import threading

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import DATA_DIR

router = APIRouter(prefix="/api/learn", tags=["learning"])
STORE = os.path.join(DATA_DIR, "outcomes.json")
_LOCK = threading.Lock()
MIN_SAMPLES = 3


def _load() -> dict:
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except Exception:
        return {"samples": []}


def _save(d: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(d, open(STORE, "w", encoding="utf-8"), indent=1)


def _feats(s: dict) -> list[float]:
    return [min(float(s.get("len") or 90), 180) / 180.0,
            min(max(float(s.get("pos", 0.5)), 0), 1),
            min(float(s.get("score", 8)), 20) / 20.0]


def _perf(s: dict) -> float:
    v = max(int(s.get("views") or 0), 0)
    l = int(s.get("likes") or 0)
    c = int(s.get("comments") or 0)
    eng = (l * 3 + c * 6) / max(v, 50)
    return 0.65 * (math.log10(v + 10) / 6.0) + 0.35 * min(eng, 0.5) / 0.5


def _fit(samples: list[dict]):
    X = np.array([_feats(s) + [1.0] for s in samples], dtype=float)
    y = np.array([_perf(s) for s in samples], dtype=float)
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    return w


def _predict(w, feats: list[float]) -> float:
    return float(np.dot(np.array(feats + [1.0]), w))


def _insights(samples: list[dict]) -> dict:
    if len(samples) < MIN_SAMPLES:
        return {"trained": False, "samples": len(samples),
                "need": MIN_SAMPLES,
                "message": f"paste {MIN_SAMPLES - len(samples)} more posted "
                           f"clip link(s) and I start tuning selection"}
    w = _fit(samples)
    best = None
    for L in range(15, 181, 5):
        for P in np.linspace(0, 1, 21):
            p = _predict(w, [L / 180, float(P), 0.8])
            if best is None or p > best[0]:
                best = (p, L, float(P))
    return {"trained": True, "samples": len(samples),
            "best_len": best[1], "best_pos": round(best[2], 2),
            "avg_perf": round(float(np.mean([_perf(s) for s in samples])), 3),
            "weights": {k: round(float(x), 4) for k, x in
                        zip(["len", "pos", "score", "bias"], w)}}


# ------------------------------------------------------------------ API
class RecordReq(BaseModel):
    url: str
    len: float | None = None
    pos: float | None = None
    score: float | None = None


@router.post("/record")
def record(req: RecordReq):
    url = (req.url or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "paste the full link to your posted clip")
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            i = ydl.extract_info(url, download=False)
        meta = {"views": i.get("view_count") or 0,
                "likes": i.get("like_count") or 0,
                "comments": i.get("comment_count") or 0,
                "title": i.get("title") or "",
                "len": float(i.get("duration") or req.len or 90)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"couldn't read that link ({e})")

    with _LOCK:
        d = _load()
        if any(s.get("url") == url for s in d["samples"]):
            raise HTTPException(400, "already tracked")
        d["samples"].append({
            "url": url, "title": meta["title"],
            "views": meta["views"], "likes": meta["likes"],
            "comments": meta["comments"],
            "len": req.len or meta["len"],
            "pos": req.pos if req.pos is not None else 0.5,
            "score": req.score if req.score is not None else 8.0})
        _save(d)
    out = _insights(d["samples"])
    return {"ok": True, "title": meta["title"], **out}


@router.get("/insights")
def insights():
    d = _load()
    return _insights(d.get("samples", []))


@router.get("/list")
def list_all():
    d = _load()
    return [{"title": s.get("title"), "url": s.get("url"),
             "views": s.get("views"), "likes": s.get("likes")}
            for s in d.get("samples", [])]


# -------------------------------------------------- used by pipeline
def apply_model(moments: list, total: float | None, reporter) -> list:
    """Retune moment scores + cap lengths using everything learned so far."""
    d = _load()
    samples = d.get("samples", [])
    if len(samples) < MIN_SAMPLES:
        return moments
    ins = _insights(samples)
    if not ins.get("trained"):
        return moments
    try:
        w = _fit(samples)
    except Exception:
        return moments

    best_pos = float(ins["best_pos"])
    best_len = float(ins["best_len"])
    sigma = 0.18
    for m in moments:
        pos = (m.peak / total) if total else 0.5
        dist = abs(pos - best_pos)
        boost = 0.8 + 0.4 * math.exp(-(dist * dist) / (2 * sigma * sigma))
        m.score = float(m.score) * boost
        # gently prefer learned length: only ever shorten, never extend
        max_len = best_len * 1.15
        if (m.end - m.start) > max_len:
            m.end = m.start + max_len
    reporter.log(f"learner active: preferring ~{int(best_len)}s clips "
                 f"around {int(best_pos * 100)}% into streams "
                 f"({len(samples)} posted clips studied)")
    moments.sort(key=lambda x: -x.score)
    return moments
