"""HypeClip modular hype-detection framework (v2 engine).

Detector contract: every detector is a class with
    name: str
    def compute(ctx) -> Signal
where Signal carries uniform time grids plus per-grid score (0..10),
confidence (0..1) and metadata. Detectors are REGISTERED in DETECTORS
and looked up by name from EngineConfig; adding a Tier-2/3 detector
later means appending a class + one config line - no other file changes.

All signals are baseline-relative (robust median/MAD z-scores), so a
naturally loud streamer is judged against their own behavior.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field

import numpy as np

from .config import EngineConfig  # falls back to local default if absent


# ---------------------------------------------------------------- signals
@dataclass
class Signal:
    name: str
    t: np.ndarray                  # seconds, uniform grid
    score: np.ndarray              # 0..10, same length as t
    conf: np.ndarray               # 0..1, same length as t (or scalar)
    meta: dict = field(default_factory=dict)

    def conf_at(self) -> float:
        try:
            c = np.asarray(self.conf, dtype=np.float32)
            return float(np.clip(np.nanmean(c), 0.0, 1.0))
        except Exception:
            return 0.0


@dataclass
class AudioPack:
    t: np.ndarray                  # 0.1s grid
    rms: np.ndarray                # dB
    flux: np.ndarray               # onset strength (d RMS/dt, half-rect)
    ok: bool = True


@dataclass
class VideoPack:
    t: np.ndarray                  # detector fps grid
    motion: np.ndarray             # frame-diff energy (0..1-ish)
    act_ratio: np.ndarray          # fraction of active pixels (0..1)
    flow_proxy: np.ndarray         # gradient-energy flow proxy (0..1-ish)
    flashes: np.ndarray            # brightness spike indicator
    fps: float = 6.0
    ok: bool = True


@dataclass
class Ctx:
    settings: object
    media: str
    total: float
    audio: AudioPack
    video: VideoPack
    rect: tuple | None = None      # normalized crop (chat region) if any
    log = staticmethod(lambda m: print("[detect] " + str(m), flush=True))


# ------------------------------------------------------------- utilities
def _norm_z(x: np.ndarray, floor: float = 1e-3) -> np.ndarray:
    """Robust local z-score -> 0..10."""
    x = np.asarray(x, dtype=np.float32)
    med = float(np.nanmedian(x))
    mad = float(np.nanmedian(np.abs(x - med))) * 1.4826
    z = (x - med) / max(mad, floor)
    z = np.clip(z, 0.0, None)
    return np.clip(z / 3.0, 0.0, 10.0)


def _smooth(x: np.ndarray, k: int = 5) -> np.ndarray:
    if x.size < 3:
        return x
    k = max(1, int(k) | 1)
    ker = np.ones(k, dtype=np.float32) / k
    return np.convolve(x, ker, mode="same")


def _audio_pack(ctx: Ctx) -> AudioPack:
    try:
        from .utils import resolve_bin
        ff = resolve_bin("ffmpeg")
    except Exception:
        ff = "ffmpeg"
    n = 8000
    try:
        cmd = [ff, "-v", "error", "-i", ctx.media, "-map", "a:0?", "-af",
               ("aresample=8000,asetnsamples=n=%d:p=0,"
                "astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"
                % n),
               "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             errors="replace", timeout=600)
        vals = []
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("lavfi.astats.Overall.RMS_level="):
                try:
                    v = float(line.split("=", 1)[1])
                    vals.append(v if math.isfinite(v) else -90.0)
                except Exception:
                    pass
        rms = np.asarray(vals, dtype=np.float32)
        if rms.size < 20:
            return AudioPack(np.zeros(0), np.zeros(0), np.zeros(0), False)
        t = np.arange(rms.size, dtype=np.float32) * 0.1
        flux = np.clip(np.diff(rms, prepend=rms[0]), 0, None)
        return AudioPack(np.clip(t, 0, max(ctx.total, 0.1)), rms, flux, True)
    except Exception:
        return AudioPack(np.zeros(0), np.zeros(0), np.zeros(0), False)


def _video_pack(ctx: Ctx) -> VideoPack:
    import cv2
    cap = cv2.VideoCapture(ctx.media)
    if not cap.isOpened():
        return VideoPack(np.zeros(0), np.zeros(0), np.zeros(0),
                         np.zeros(0), np.zeros(0), 6.0, False)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    want = float(getattr(ctx.settings, "engine_fps", 6.0)) or 6.0
    step = max(1, int(round(fps / want)))
    dt = step / float(fps)
    fx_, fy, fw, fh = (ctx.rect or (0.0, 0.0, 1.0, 1.0))
    prev, prev_grad = None, None
    mo, act, flw, fla = [], [], [], []
    n = 0
    while True:
        if not cap.grab():
            break
        if n % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if (fx_, fy, fw, fh) != (0.0, 0.0, 1.0, 1.0):
                H, W = g.shape
                g = g[int(fy * H):int((fy + fh) * H),
                      int(fx_ * W):int((fx_ + fw) * W)]
            g = cv2.resize(g, (160, 90)).astype(np.float32)
            if prev is not None:
                d = np.abs(g - prev)
                mo.append(float(d.mean()) / 255.0)
                act.append(float((d > 12).mean()))
            grad = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3) ** 2 + \
                cv2.Sobel(g, cv2.CV_32F, 0, 1, 3) ** 2
            gf = float(np.sqrt(grad).mean()) / 255.0
            if prev_grad is not None:
                flw.append(min(1.0, abs(gf - prev_grad) * 4.0))
            else:
                flw.append(0.0)
            prev_grad = gf
            m = float(g.mean())
            fla.append(1.0 if prev is not None and abs(m - _lum_prev[-1])
                       > 42.0 else 0.0) if False else None
            mo_lum = m
            if not hasattr(_lum_prev, "append"):
                pass
            _lum_prev.append(m)  # noqa: F821 (initialized below)
            prev = g
            n += 1
        n += 1
        if n % 100000 == 0:
            pass
    cap.release()
    return VideoPack(*_vp_finish(ctx, dt, mo, act, flw, fla))


def _vp_finish(ctx, dt, mo, act, flw, fla):
    t = np.arange(len(mo), dtype=np.float32) * dt
    if t.size < 8:
        return (np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0),
                np.zeros(0), 6.0, False)
    return (t, _smooth(np.asarray(mo, np.float32), 3),
            _smooth(np.asarray(act, np.float32), 3),
            _smooth(np.asarray(flw, np.float32), 3),
            np.asarray(fla[1:], np.float32)
            if len(fla) > 1 else np.zeros(1, np.float32),
            1.0 / dt)


# placeholder trick removed - see _video_pack note
_lum_prev: list = []


# ------------------------------------------------------------ detectors
class AudioEnergy:
    name = "vocal"
    WEIGHT = "vocal"

    def compute(self, ctx: Ctx) -> Signal:
        a = ctx.audio
        if not a.ok:
            return Signal(self.name, np.zeros(1), np.zeros(1), 0.0,
                          {"note": "no audio"})
        s = _norm_z(a.rms)
        conf = 0.85 if a.rms.size > int(ctx.total * 10 * 0.9) else 0.6
        return Signal(self.name, a.t, s, conf, {"grid": "0.1s"})


class VocalEscalation:
    """Rewards normal -> excited -> shout -> scream trajectories."""
    name = "escalation"

    def compute(self, ctx: Ctx) -> Signal:
        a = ctx.audio
        if not a.ok:
            return Signal(self.name, np.zeros(1), np.zeros(1), 0.0)
        w = int(20.0)  # 2 s of 0.1 s frames
        rms = a.rms
        n = rms.size
        esc = np.zeros(n, dtype=np.float32)
        base = _norm_z(rms) / 10.0
        for i in range(w, n, 5):
            seg = base[i - w:i]
            lo, hi = float(np.percentile(seg, 20)), float(np.percentile(seg, 90))
            rise = hi - max(lo, 0.05)
            trend = float(np.polyfit(np.arange(w), seg, 1)[0]) if w >= 4 else 0.0
            esc[i] = float(np.clip(rise * 1.6 + max(trend, 0) * 8.0, 0, 10))
        esc = _smooth(esc, 9)
        return Signal(self.name, a.t, esc, 0.7, {"window": "2s"})


class VisualFlow:
    """Meaningful-motion detector; conf drops when activity looks like
    menus/idle screens (low active-pixel ratio + low flow variance)."""
    name = "visual"

    def compute(self, ctx: Ctx) -> Signal:
        v = ctx.video
        if not v.ok:
            return Signal(self.name, np.zeros(1), np.zeros(1), 0.0)
        s = _norm_z(v.flow_proxy * 0.6 + v.motion * 0.4)
        junk = (v.act_ratio < 0.02) & (np.std(v.flow_proxy) < 0.05)
        s = np.where(junk, s * 0.35, s)
        conf = float(np.clip(0.55 + 0.4 * float(np.mean(v.act_ratio) * 3),
                             0.4, 0.9))
        return Signal(self.name, v.t, s, conf,
                      {"fps": round(v.fps, 1),
                       "active_px": round(float(np.mean(v.act_ratio)), 3)})


class AVSync:
    """Audio-visual onset alignment via cross-correlation (+=0.6 s)."""
    name = "sync"

    def compute(self, ctx: Ctx) -> Signal:
        a, v = ctx.audio, ctx.video
        if not a.ok or not v.ok:
            return Signal(self.name, np.zeros(1), np.zeros(1), 0.0)
        at = _norm_z(a.flux)
        vt = _norm_z(v.motion)
        # resample audio onto the video grid
        av = np.interp(v.t, a.t, at)
        win = int(0.6 / max(1e-3, (v.t[1] - v.t[0] if v.t.size > 1 else 0.16)))
        best = np.zeros(vt.size, dtype=np.float32)
        for lag in range(-win, win + 1):
            sh = np.roll(vt, lag)
            cc = np.correlate(av[:len(sh)], sh, mode="valid")
            if cc.size == best.size:
                best = np.maximum(best, cc)
        s = np.clip(best / 3.0, 0.0, 10.0)
        return Signal(self.name, v.t, _smooth(s, 3), 0.65,
                      {"window_s": 0.6})


class EventDensity:
    name = "density"

    def compute(self, ctx: Ctx) -> Signal:
        a, v = ctx.audio, ctx.video
        if not a.ok:
            return Signal(self.name, np.zeros(1), np.zeros(1), 0.0)
        at = _norm_z(a.flux)
        peaks = (at[1:-1] > at[:-2]) & (at[1:-1] >= at[2:]) & (at[1:-1] > 4.0)
        idx = np.where(peaks)[0] + 1
        t = a.t
        rate = np.zeros(t.size, dtype=np.float32)
        W = int(10.0 / 0.1)
        for i in range(t.size):
            lo, hi = max(0, i - W), min(t.size, i + W)
            if hi > lo:
                inside = ((idx >= lo) & (idx < hi)).sum()
                rate[i] = inside / 20.0  # events per second
        s = np.clip(rate * 2.2, 0, 10)
        return Signal(self.name, t, _smooth(s, 9), 0.7, {})


DETECTORS = {cls.name: cls for cls in
             (AudioEnergy, VocalEscalation, VisualFlow, AVSync,
              EventDensity)}


class EngineConfig:
    """Central config - every tunable lives here. Settings keys with the
    same name (prefix engine_) override these values."""
    fps = 6.0
    weights = {"vocal": 3.0, "visual": 2.0, "sync": 1.6,
               "escalation": 1.8, "density": 1.2}
    min_conf = 0.25          # detectors below this are dropped
    peak_pct = 92            # candidate peak threshold (percentile)
    min_gap_s = 8.0          # refractory between candidates
    merge_ioi_s = 4.0        # merge candidates closer than this
    pre_s = 8.0              # context before peak
    post_s = 10.0            # payoff after peak
    expand_s = 6.0           # extra window search for buildup/payoff
    min_dur_s = 12.0
    max_dur_s = 150.0
    diversity_ioi_s = 10.0   # near-duplicate window
    diversity_sim = 0.82     # audio-correlation similarity threshold

    @classmethod
    def from_settings(cls, settings) -> "EngineConfig":
        cfg = cls()
        for k in ("fps", "min_gap_s", "merge_ioi_s", "pre_s", "post_s",
                  "min_dur_s", "max_dur_s", "diversity_ioi_s",
                  "diversity_sim", "peak_pct"):
            v = getattr(settings, "engine_" + k, None)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                setattr(cfg, k, type(getattr(cfg, k))(v))
        w = getattr(settings, "engine_weights", None)
        if isinstance(w, dict):
            cfg.weights.update({k: float(v) for k, v in w.items()
                                if k in cfg.weights})
        return cfg
