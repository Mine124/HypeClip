"""Style Profiles: learn editing rhythm from reference clips you upload."""
from __future__ import annotations
import glob
import json
import math
import os
import subprocess
import threading
import uuid

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile

from .config import DATA_DIR

router = APIRouter(prefix="/api/style", tags=["style"])
ROOT = os.path.join(DATA_DIR, "styles")
REFS = os.path.join(ROOT, "refs")
os.makedirs(REFS, exist_ok=True)


def _p(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ")[:40].strip()
    if not safe:
        raise HTTPException(400, "bad profile name")
    return os.path.join(ROOT, safe + ".json")


@router.post("/upload_ref")
async def upload_ref(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
    dest = os.path.join(REFS, uuid.uuid4().hex[:10] + ext)
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return {"ok": True, "ref": dest}


def _analyze_ref(path: str) -> dict:
    from .utils import probe_duration, resolve_bin, run
    dur = probe_duration(path)
    proc = subprocess.run(
        [resolve_bin("ffmpeg"), "-i", path,
         "-vf", "select='gt(scene,0.3)',metadata=print",
         "-an", "-f", "null", "-"], capture_output=True, text=True)
    cuts = proc.stderr.count("pts_time")
    raw = run([resolve_bin("ffmpeg"), "-v", "error", "-i", path,
               "-ac", "1", "-ar", "4000", "-vn", "-f", "f32le", "-"],
              capture_bytes=True)
    x = np.frombuffer(raw, np.float32)
    sr = 4000
    n = min(x.size // sr, int(dur) or 1)
    seg = x[:n * sr].reshape(n, sr) if n else np.zeros((1, sr), np.float32)
    rms = np.sqrt(np.maximum((seg ** 2).mean(axis=1), 1e-9))
    db = 20 * np.log10(rms + 1e-9)
    floor = float(np.percentile(db, 20))
    silence = float(np.mean(db < floor + 4.0))
    onsets = float(np.mean(np.diff(db) > 4.5)) * 60.0
    return {"dur": round(dur, 1), "cuts_per_min":
            round(cuts / max(dur / 60, 0.1), 1),
            "dyn_std": round(float(np.std(db)), 1),
            "silence_frac": round(silence, 2),
            "onsets_per_min": round(onsets, 1),
            "loud_med": round(float(np.median(db)), 1)}


def _profile_from(refs: list[dict]) -> dict:
    med = lambda k: (sorted(r[k] for r in refs)[len(refs) // 2]
                     if refs else 0)
    I = _clamp(0.12 + 0.055 * med("cuts_per_min")
               + 0.035 * med("onsets_per_min")
               + 0.03 * med("dyn_std") - 0.35 * med("silence_frac"), 0, 1)
    return {
        "refs": len(refs),
        "avg_len": round(med("dur")),
        "cuts_per_min": round(med("cuts_per_min"), 1),
        "dyn_std": round(med("dyn_std"), 1),
        "silence_frac": round(med("silence_frac"), 2),
        "onsets_per_min": round(med("onsets_per_min"), 1),
        "intensity": round(I, 2),
        "overrides": {
            "zoom_punch": I > 0.42,
            "zoom_strength": round(_clamp(0.22 + 0.55 * I, 0.2, 0.85), 2),
            "shake": round(_clamp(I - 0.25, 0, 1) * 0.8, 2),
            "beat_sync": I > 0.55,
            "fx_look": "capcut" if I > 0.62 else "none",
            "bloom": I > 0.7, "grain": False, "vignette": False,
            "sfx_volume_db": round(-4 + 11 * I),
            "flash_intro": I > 0.75,
        },
    }


def _clamp(v, a, b):
    return max(a, min(b, v))


@router.post("/build")
def build_profile(body: dict):
    name = body.get("name", "").strip() or f"profile-{uuid.uuid4().hex[:4]}"
    ref_paths = body.get("refs") or []
    if len(ref_paths) < 1:
        raise HTTPException(400, "upload at least one reference clip")
    analyses = [_analyze_ref(p) for p in ref_paths
                if os.path.isfile(p)]
    prof = _profile_from(analyses)
    prof["_name"] = name
    prof["_analyses"] = analyses
    os.makedirs(ROOT, exist_ok=True)
    json.dump(prof, open(_p(name), "w", encoding="utf-8"), indent=1)
    return {"ok": True, "name": name, "profile": prof}


@router.get("/list")
def list_profiles():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
            out.append({"name": d.get("_name"),
                        "intensity": d.get("intensity"),
                        "refs": d.get("refs")})
        except Exception:
            pass
    return out


@router.get("/get")
def get_profile(name: str):
    p = _p(name)
    if not os.path.isfile(p):
        raise HTTPException(404, "unknown profile")
    return json.load(open(p, encoding="utf-8"))
