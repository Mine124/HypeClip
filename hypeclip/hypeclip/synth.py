from __future__ import annotations
import os
import wave

import numpy as np

SR = 44100


def _t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def _phase(freq: np.ndarray) -> np.ndarray:
    return np.cumsum(2 * np.pi * freq / SR)


def _save(path: str, x: np.ndarray):
    x = np.asarray(x, np.float32)
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def airhorn() -> np.ndarray:
    t = _t(1.15)
    bend = np.where(t < 0.22, np.linspace(0.88, 1.0, t.size), 1.0)
    out = np.zeros_like(t)
    for f0 in (233.08, 246.94, 293.66):
        ph = _phase(f0 * bend)
        out += 2 * ((ph / (2 * np.pi)) % 1.0) - 1.0
    out = np.tanh(out * 1.4)
    env = np.ones_like(t)
    a = int(0.008 * SR); env[:a] = np.linspace(0, 1, a)
    rel = t > 1.15 - 0.28
    env[rel] = np.cos(np.linspace(0, np.pi / 2, int(rel.sum()))) ** 2
    return out * env


def vine_boom() -> np.ndarray:
    t = _t(0.9)
    f = 38 + (110 - 38) * np.exp(-t * 7)
    body = np.sin(_phase(f)) * np.exp(-t * 5)
    rng = np.random.default_rng(7)
    click = np.convolve(rng.normal(0, 1, t.size), np.ones(24) / 24, "same")[:t.size]
    click *= np.exp(-t * 30) * 0.8
    return body + click


def womp_womp() -> np.ndarray:
    t = _t(0.5)
    f = 70 + (180 - 70) * np.exp(-t * 5)
    sq = np.sign(np.sin(_phase(f)))
    return np.tanh(sq * 2.5) * np.exp(-t * 6)


def notification() -> np.ndarray:
    t = _t(0.8)
    tone = np.sin(_phase(np.full_like(t, 1318.51))) + \
           0.55 * np.sin(_phase(np.full_like(t, 1975.53)))
    env = np.exp(-t * 7)
    a = int(0.002 * SR); env[:a] = np.linspace(0, 1, a)
    return tone * env


def riser() -> np.ndarray:
    t = _t(1.5)
    rng = np.random.default_rng(3)
    noise = np.convolve(rng.normal(0, 1, t.size), np.ones(16) / 16, "same")[:t.size]
    f = 180 + (850 - 180) * (t / t[-1]) ** 2
    return (noise * (t / t[-1]) ** 2 + 0.25 * np.sin(_phase(f))) * 0.8


EFFECTS = {"airhorn": airhorn, "vine_boom": vine_boom, "womp_womp": womp_womp,
           "notification": notification, "riser": riser}


def synthesize_all(directory: str):
    os.makedirs(directory, exist_ok=True)
    for name, fn in EFFECTS.items():
        _save(os.path.join(directory, f"{name}.wav"), fn())
    with open(os.path.join(directory, "README.txt"), "w") as f:
        f.write("Drop your own .wav/.mp3/.ogg sound effects here to replace "
                "the built-in synthesized placeholders.\n")