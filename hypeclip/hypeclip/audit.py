"""Render audit: inspects the EXPORTED file (not the plan) for real defects,
scores it, and quarantines clips that fail the quality gate."""
from __future__ import annotations
import os
import shutil

import numpy as np

from .config import DATA_DIR
from .utils import probe_duration, resolve_bin, run

QUAR_DIR = os.path.join(DATA_DIR, "quarantine")


def _mono(path: str, sr: int = 16000) -> np.ndarray:
    raw = run([resolve_bin("ffmpeg"), "-v", "error", "-i", path,
               "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
              capture_bytes=True)
    return np.frombuffer(raw, np.float32)


def audit_clip(path: str, expected_dur: float | None = None) -> dict:
    issues: list[str] = []
    score = 100

    # ---- container / duration ----
    dur = probe_duration(path)
    if dur < 4:
        issues.append(f"clip too short ({dur:.1f}s)")
        score -= 40
    if expected_dur:
        drift = abs(dur - expected_dur) / max(expected_dur, 1)
        if drift > 0.18:
            issues.append(f"duration drifted {drift * 100:.0f}% from plan "
                          f"({dur:.1f}s vs {expected_dur:.1f}s)")
            score -= 15

    # ---- audio ----
    try:
        x = _mono(path)
        if x.size:
            clip_frac = float(np.mean(np.abs(x) > 0.995))
            if clip_frac > 0.004:
                issues.append(f"audio clipping ({clip_frac * 100:.1f}% "
                              f"of samples)")
                score -= 18
            rms_db = 20 * np.log10(float(np.sqrt(np.mean(x ** 2))) + 1e-9)
            if rms_db < -30:
                issues.append(f"audio very quiet ({rms_db:.0f}dBFS)")
                score -= 15
    except Exception as e:  # noqa: BLE001
        issues.append(f"audio probe failed ({e})")
        score -= 10

    # ---- video defects (whole-clip detectors, cheap) ----
    try:
        proc = subprocess.run(
            [resolve_bin("ffmpeg"), "-i", path,
             "-vf", "blackdetect=d=1.0:pic_th=0.98,"
                    "freezedetect=n=-60dB:d=2.5",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True)
        err = proc.stderr
        blacks = err.count("black_start")
        freezes = err.count("freeze_start")
        if blacks:
            issues.append(f"{blacks} black segment(s) ≥1s")
            score -= 15
        if freezes:
            issues.append(f"{freezes} frozen segment(s) ≥2.5s")
            score -= 12
    except Exception:
        pass

    score = max(0, min(100, score))
    quarantine = score < 55 or len(issues) >= 3
    return {"score": score, "issues": issues, "quarantine": quarantine}


def quarantine_move(path: str, reason: str) -> str:
    os.makedirs(QUAR_DIR, exist_ok=True)
    dest = os.path.join(QUAR_DIR, os.path.basename(path))
    n = 2
    while os.path.exists(dest):
        stem, ext = os.path.splitext(os.path.basename(path))
        dest = os.path.join(QUAR_DIR, f"{stem}-{n}{ext}")
        n += 1
    shutil.move(path, dest)
    with open(dest + ".txt", "w", encoding="utf-8") as f:
        f.write(reason)
    return dest
