from __future__ import annotations

import numpy as np

SR = 22050
FRAME = 1024
HOP = 512


def decode_mono(path: str) -> np.ndarray:
    from .utils import resolve_bin, run
    raw = run([resolve_bin("ffmpeg"), "-v", "error", "-i", path, "-ac", "1",
               "-ar", str(SR), "-f", "f32le", "-"], capture_bytes=True)
    return np.frombuffer(raw, np.float32)


def detect_onsets(audio_path: str, max_onsets: int = 12) -> list[tuple[float, float]]:
    x = decode_mono(audio_path)
    if x.size < FRAME * 4:
        return []

    n = (x.size - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    win = np.hanning(FRAME).astype(np.float32)
    mag = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    mag = np.log1p(mag * 40)

    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    k = np.hanning(5).astype(np.float32); k /= k.sum()
    flux = np.convolve(flux, k, "same")

    thr = flux.mean() + 1.8 * flux.std()
    picked: list[tuple[float, float]] = []
    last = -1.0
    for i in np.argsort(flux)[::-1]:
        if flux[i] < thr:
            break
        t = i * HOP / SR
        if t - last < 0.28:
            continue
        picked.append((float(t), float(flux[i])))
        last = t
        if len(picked) >= max_onsets:
            break
    picked.sort()
    return picked


def strongest_beats(audio_path: str, count: int, avoid: list[float],
                    window: tuple[float, float], min_gap: float = 1.0) -> list[float]:
    lo, hi = window
    cands = [(s, t) for t, s in detect_onsets(audio_path, 24)
             if lo <= t <= hi and all(abs(t - a) > 1.0 for a in avoid)]
    cands.sort(key=lambda p: -p[0])
    out: list[float] = []
    for _, t in cands:
        if all(abs(t - o) > min_gap for o in out):
            out.append(t)
        if len(out) >= count:
            break
    return sorted(out)