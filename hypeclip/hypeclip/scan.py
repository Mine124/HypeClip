"""Visual chat-speed scanner v3 -> FULL hype engine v2.

Keeps the ScrollScanner public interface (constructor args and
detect(total) -> (moments, series)) so pipeline.py is untouched, but the
audio mode now runs the complete v2 engine:

  two-pass analysis (cheap full-video -> candidates -> expensive checks)
  modular detectors (vocal / escalation / visual / sync / density)
  baseline-relative robust z-scores (median/MAD)
  confidence-weighted fusion from a central EngineConfig
  buildup/payoff boundary expansion, diversity filtering
  per-Moment explainability (m.breakdown) surfaced via Reporter

chat-rectangle mode keeps the proven v2 z-score scanner unchanged.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field

import numpy as np

from .hype import Moment

FW, FH = 96, 64

# ============================================================ EngineConfig
class EngineConfig:
    fps = 6.0
    weights = {"vocal": 3.0, "visual": 2.0, "sync": 1.6,
               "escalation": 1.8, "density": 1.2}
    min_conf = 0.25
    peak_pct = 92
    min_gap_s = 8.0
    merge_ioi_s = 4.0
    pre_s = 8.0
    post_s = 10.0
    expand_s = 6.0
    min_dur_s = 12.0
    max_dur_s = 150.0
    diversity_ioi_s = 10.0
    diversity_sim = 0.82

    @classmethod
    def from_settings(cls, settings):
        cfg = cls()
        for k in ("fps", "min_gap_s", "merge_ioi_s", "pre_s", "post_s",
                  "min_dur_s", "max_dur_s", "diversity_ioi_s",
                  "diversity_sim", "peak_pct"):
            v = getattr(settings, "engine_" + k, None)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                try:
                    setattr(cfg, k, type(getattr(cfg, k))(v))
                except Exception:
                    pass
        w = getattr(settings, "engine_weights", None)
        if isinstance(w, dict):
            cfg.weights.update({k2: float(v) for k2, v in w.items()
                                if k2 in cfg.weights})
        return cfg


# ================================================================== Signal
@dataclass
class Signal:
    name: str
    t: np.ndarray
    score: np.ndarray                  # 0..10
    conf: float                        # 0..1
    meta: dict = field(default_factory=dict)


# ============================================================== audio pack
def _bin(name):
    try:
        from .utils import resolve_bin
        return resolve_bin(name)
    except Exception:
        return name


def _audio_pack(media: str, total: float):
    n = 8000
    try:
        cmd = [_bin("ffmpeg"), "-v", "error", "-i", media, "-map", "a:0?",
               "-af", ("aresample=8000,asetnsamples=n=%d:p=0,"
                       "astats=metadata=1:reset=1,"
                       "ametadata=print:key="
                       "lavfi.astats.Overall.RMS_level:file=-" % n),
               "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             errors="replace", timeout=900)
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
            return None
        t = np.arange(rms.size, dtype=np.float32) * 0.1
        flux = np.clip(np.diff(rms, prepend=rms[0]), 0, None)
        return {"t": np.clip(t, 0, max(total, 0.1)), "rms": rms,
                "flux": flux}
    except Exception:
        return None


def _video_pack(media: str, total: float, fps: float, rect=None):
    import cv2
    cap = cv2.VideoCapture(media)
    if not cap.isOpened():
        return None
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / max(1.0, fps))))
    dt = step / float(src_fps)
    fx_, fy, fw, fh = (rect or (0.0, 0.0, 1.0, 1.0))
    crop = (abs(fx_) > 1e-6 or abs(fy) > 1e-6
            or abs(fw - 1.0) > 1e-6 or abs(fh - 1.0) > 1e-6)
    prev, pg = None, None
    lum_hist: list = []
    mo, act, flw, fla = [], [], [], []
    n = 0
    max_frames = int(src_fps * min(max(total, 1.0), 14400.0))
    while True:
        if not cap.grab():
            break
        if n % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if crop:
                H, W = g.shape
                g = g[int(fy * H):int((fy + fh) * H),
                      int(fx_ * W):int((fx_ + fw) * W)]
            g = cv2.resize(g, (160, 90)).astype(np.float32)
            m = float(g.mean())
            if prev is not None:
                d = np.abs(g - prev)
                mo.append(float(d.mean()) / 255.0)
                act.append(float((d > 12).mean()))
                fla.append(1.0 if abs(m - (lum_hist[-1] if lum_hist else m))
                           > 42.0 else 0.0)
            grad = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3) ** 2 + \
                cv2.Sobel(g, cv2.CV_32F, 0, 1, 3) ** 2
            gf = float(np.sqrt(grad).mean()) / 255.0
            flw.append(0.0 if pg is None
                       else min(1.0, abs(gf - pg) * 4.0))
            pg = gf
            lum_hist.append(m)
            prev = g
        n += 1
        if n > max_frames:
            break
    cap.release()
    if len(mo) < 8:
        return None
    t = np.arange(len(mo), dtype=np.float32) * dt

    def sm(x, k=3):
        k = max(1, int(k) | 1)
        return np.convolve(np.asarray(x, np.float32),
                           np.ones(k, np.float32) / k, mode="same")

    return {"t": t, "motion": sm(mo), "act": sm(act), "flow": sm(flw),
            "flash": np.asarray(fla[1:], np.float32)
            if len(fla) > 1 else np.zeros(1, np.float32),
            "fps": 1.0 / dt}


# ============================================================ normalizers
def _z10(x: np.ndarray, floor: float = 1e-3) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    med = float(np.nanmedian(x))
    mad = float(np.nanmedian(np.abs(x - med))) * 1.4826
    z = np.clip((x - med) / max(mad, floor), 0.0, None)
    return np.clip(z / 3.0, 0.0, 10.0)


def _sm(x: np.ndarray, k: int = 5) -> np.ndarray:
    k = max(1, int(k) | 1)
    return np.convolve(np.asarray(x, np.float32),
                       np.ones(k, np.float32) / max(1, k), mode="same")


# =============================================================== detectors
def d_vocal(ctx) -> Signal:
    a = ctx["audio"]
    if not a:
        return Signal("vocal", np.zeros(1), np.zeros(1), 0.0)
    return Signal("vocal", a["t"], _z10(a["rms"]),
                  0.85 if a["rms"].size > 60 else 0.55, {})


def d_escalation(ctx) -> Signal:
    a = ctx["audio"]
    if not a:
        return Signal("escalation", np.zeros(1), np.zeros(1), 0.0)
    rms = a["rms"]
    n = rms.size
    base = _z10(rms) / 10.0
    w = 20  # 2 s @ 0.1 s
    esc = np.zeros(n, dtype=np.float32)
    xs = np.arange(w, dtype=np.float32)
    slope0 = float(np.polyfit(xs, base[:w], 1)[0]) if n >= w else 0.0
    for i in range(w, n, 5):
        seg = base[i - w:i]
        lo = float(np.percentile(seg, 20))
        hi = float(np.percentile(seg, 90))
        rise = hi - max(lo, 0.05)
        tr = float(np.polyfit(xs, seg, 1)[0])
        esc[i] = float(np.clip(rise * 1.6 + max(tr, 0.0) * 8.0, 0, 10))
    return Signal("escalation", a["t"], _sm(esc, 9), 0.7, {})


def d_visual(ctx) -> Signal:
    v = ctx["video"]
    if not v:
        return Signal("visual", np.zeros(1), np.zeros(1), 0.0)
    s = _z10(v["flow"] * 0.6 + v["motion"] * 0.4)
    junk = (v["act"] < 0.02) & (float(np.std(v["flow"])) < 0.05)
    s = np.where(junk, s * 0.35, s)
    conf = float(np.clip(0.55 + 0.4 * float(np.mean(v["act"])) * 3.0,
                         0.4, 0.9))
    return Signal("visual", v["t"], s, conf,
                  {"active_px": round(float(np.mean(v["act"])), 3)})


def d_sync(ctx) -> Signal:
    a, v = ctx["audio"], ctx["video"]
    if not a or not v or v["t"].size < 8:
        return Signal("sync", np.zeros(1), np.zeros(1), 0.0)
    av = np.interp(v["t"], a["t"], _z10(a["flux"]))
    vt = _z10(v["motion"])
    dtv = float(v["t"][1] - v["t"][0]) if v["t"].size > 1 else 0.16
    win = max(1, int(0.6 / max(1e-3, dtv)))
    best = np.zeros(vt.size, dtype=np.float32)
    for lag in range(-win, win + 1):
        sh = np.roll(vt, lag)
        cc = np.correlate(av, sh, mode="valid")
        if cc.size == best.size:
            best = np.maximum(best, cc)
    return Signal("sync", v["t"], _sm(np.clip(best / 3.0, 0, 10), 3),
                  0.65, {"window_s": 0.6})


def d_density(ctx) -> Signal:
    a = ctx["audio"]
    if not a:
        return Signal("density", np.zeros(1), np.zeros(1), 0.0)
    at = _z10(a["flux"])
    pk = (at[1:-1] > at[:-2]) & (at[1:-1] >= at[2:]) & (at[1:-1] > 4.0)
    idx = np.where(pk)[0] + 1
    t = a["t"]
    rate = np.zeros(t.size, dtype=np.float32)
    W = 100  # 10 s @ 0.1 s
    for i in range(0, t.size, 5):
        lo, hi = max(0, i - W), min(t.size, i + W)
        inside = ((idx >= lo) & (idx < hi)).sum()
        rate[i:min(t.size, i + 5)] = inside / 20.0
    return Signal("density", t, _sm(np.clip(rate * 2.2, 0, 10), 9),
                  0.7, {})


DETECTORS = {"vocal": d_vocal, "escalation": d_escalation,
             "visual": d_visual, "sync": d_sync, "density": d_density}


# ================================================================ helpers
def _resample(sig: Signal, t: np.ndarray) -> np.ndarray:
    if sig.t.size < 2:
        return np.zeros(t.size, dtype=np.float32)
    return np.interp(t, sig.t, sig.score)


def _audio_sim(a: np.ndarray, b: np.ndarray) -> float:
    n = min(a.size, b.size)
    if n < 8:
        return 0.0
    x, y = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    denom = float(np.std(x) * np.std(y)) + 1e-6
    return float(np.clip(np.mean(x * y) / denom, -1.0, 1.0))


# ================================================================ scanner
class ScrollScanner:
    WINDOW_S = 180

    def __init__(self, settings, media_path: str, rect: tuple,
                 reporter=None, sample_fps: float = 6.0):
        self.s = settings
        self.path = media_path
        self.rect = rect
        self.r = reporter
        self.chat_mode = rect is not None and tuple(rect) != (0, 0, 1, 1)
        self.fps = max(1.0, min(30.0, float(sample_fps)))

    def _log(self, m):
        if self.r and hasattr(self.r, "log"):
            self.r.log(str(m))

    # ---------------- chat-rectangle mode (unchanged proven v2) --------
    def _detect_chat(self, total=None):
        prev = None
        vals: list = []
        est = int((total or 0) * self.fps)
        last_rep = -1.0
        try:
            from .utils import resolve_bin
            ff = resolve_bin("ffmpeg")
        except Exception:
            ff = "ffmpeg"
        x, y, w, h = self.rect
        vf = (f"crop=w='iw*{w:.4f}':h='ih*{h:.4f}':"
              f"x='iw*{x:.4f}':y='ih*{y:.4f}',"
              f"scale={FW}:{FH},fps={self.fps},format=gray")
        cmd = [ff, "-v", "error", "-i", self.path, "-an", "-vf", vf,
               "-f", "rawvideo", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        nbytes = FW * FH
        try:
            while True:
                buf = proc.stdout.read(nbytes)
                if not buf or len(buf) < nbytes:
                    break
                g = np.frombuffer(buf, np.uint8).reshape(FH, FW)
                gf = g.astype(np.float32) / 255.0
                if prev is not None:
                    vals.append(float(np.abs(gf - prev).mean()))
                prev = gf
                if est and len(vals) % 60 == 0 and self.r:
                    frac = min(len(vals) / est, 0.99)
                    if frac - last_rep > 0.02:
                        last_rep = frac
                        self.r.progress_scan(frac)
        finally:
            proc.kill()
            if self.r:
                self.r.progress_scan(1.0)

        v = np.asarray(vals, dtype=np.float32)
        empty = {"t": [], "score": []}
        if v.size < self.fps * 30:
            return [], empty
        k = np.ones(3, np.float32) / 3.0
        v = np.convolve(v, k, "same")
        c1, c2 = np.cumsum(v), np.cumsum(v * v)
        W = int(self.WINDOW_S * self.fps)
        thr = float(getattr(self.s, "hype_threshold", 3.5) or 3.5)
        n = v.size
        score = np.zeros(n, np.float32)
        for i in range(W // 4, n):
            lo, hi = max(0, i - W), max(0, i - int(2 * self.fps))
            m_ = hi - lo
            if m_ < int(10 * self.fps):
                continue
            mean = (c1[hi] - c1[lo]) / m_
            var = max((c2[hi] - c2[lo]) / m_ - mean * mean, 0.0)
            z = (v[i] - mean) / (float(np.sqrt(var)) + 1e-6)
            if z > 0:
                score[i] = z
        score = np.convolve(score, k, "same")
        moments = self._moments_from(score, total or n / self.fps)
        stride = max(1, n // 3000)
        series = {"t": [round(i / self.fps, 1)
                        for i in range(0, n, stride)],
                  "score": [round(float(score[i]), 3)
                            for i in range(0, n, stride)]}
        return moments, series

    def _moments_from(self, score, total, breakdowns=None):
        n = score.size
        fps = self.fps
        R = int(4 * fps)
        cand = [i for i in range(n) if score[i] > 0]
        cand = [i for i in cand
                if score[i] == score[max(0, i - R):i + R + 1].max()]
        cand.sort(key=lambda i: -float(score[i]))
        cfg = EngineConfig.from_settings(self.s)
        cd = float(getattr(self.s, "cooldown", cfg.min_gap_s)) * fps
        accepted: list = []
        maxc = int(getattr(self.s, "max_clips", 20) or 20)
        for p in cand:
            if all(abs(p - a) > cd for a in accepted):
                accepted.append(p)
            if len(accepted) >= maxc:
                break
        accepted.sort()
        dur = float(getattr(self.s, "clip_duration", 90.0) or 90.0)
        pre = float(getattr(self.s, "pre_roll", 1.5) or 1.5)
        moments: list = []
        for j, p in enumerate(accepted):
            l_ = p
            while l_ > 0 and score[l_ - 1] >= 0.35 * score[p] \
                    and (p - l_) < (pre + 15) * fps:
                l_ -= 1
            start = max(0.0, min(p / fps - pre, l_ / fps))
            r_ = p
            while r_ + 1 < n and score[r_ + 1] >= 0.35 * score[p] \
                    and (r_ - p) < (dur + 20) * fps:
                r_ += 1
            end = min(max(start + dur, r_ / fps + 2.0),
                      start + dur + 15.0, total)
            if end > 5.0:
                start = max(0.0, min(start, end - 5.0))
            m = Moment(start=start, end=end, peak=p / fps,
                       score=float(score[p]))
            if breakdowns is not None:
                m.breakdown = breakdowns[j] if j < len(breakdowns) else None
            moments.append(m)
        return moments

    # ---------------- audio mode: full v2 engine -----------------------
    def detect(self, total=None):
        if self.chat_mode:
            return self._detect_chat(total)
        from .utils import probe_duration
        total = float(total or probe_duration(self.path) or 0.0)
        cfg = EngineConfig.from_settings(self.s)
        self.fps = cfg.fps
        if self.r:
            self.r.progress_scan(0.02)
        self._log("🧠 engine v2: pass 1 - audio + visual sweep "
                  "(%.0fs of media)..." % total)
        ap = _audio_pack(self.path, total)
        vp = _video_pack(self.path, total, cfg.fps)
        ctx = {"settings": self.s, "audio": ap, "video": vp}
        sigs: dict = {}
        for name, fn in DETECTORS.items():
            try:
                sigs[name] = fn(ctx)
                c = sigs[name].conf
                self._log("   detector %-11s conf=%.2f" % (name, c))
            except Exception as e:
                self._log("   detector %-11s failed (%s) - dropped"
                          % (name, e))
                sigs[name] = Signal(name, np.zeros(1), np.zeros(1), 0.0)
        if self.r:
            self.r.progress_scan(0.55)

        live = {k: v for k, v in sigs.items() if v.conf >= cfg.min_conf
                and v.t.size > 2}
        if not live:
            raise RuntimeError("No usable hype signals - the media has no "
                               "readable audio or video.")
        vref = vp["t"] if vp else ap["t"]
        grid = vref
        fused = np.zeros(grid.size, dtype=np.float32)
        wsum = 0.0
        parts = {}
        for name, sig in live.items():
            wgt = cfg.weights.get(name, 1.0) * sig.conf
            f = _resample(sig, grid)
            fused += wgt * f
            parts[name] = f
            wsum += wgt
        fused = (fused / max(wsum, 1e-6)) * 1.9
        fused = _sm(fused, 5)
        if self.r:
            self.r.progress_scan(0.75)

        # ---- candidates ----
        thr = float(np.percentile(fused, cfg.peak_pct))
        thr = max(thr, 2.2)
        R = max(1, int(cfg.min_gap_s * cfg.fps))
        loc = [i for i in range(grid.size) if fused[i] >= thr]
        loc = [i for i in loc
               if fused[i] == fused[max(0, i - R):i + R + 1].max()]
        loc.sort(key=lambda i: -float(fused[i]))
        cands: list = []
        maxc = int(getattr(self.s, "max_clips", 20) or 20)
        for i in loc:
            t = float(grid[i])
            if all(abs(t - c["t"]) > cfg.merge_ioi_s for c in cands):
                cands.append({"t": t, "i": i, "score": float(fused[i])})
            if len(cands) >= maxc * 2:
                break
        if not cands:
            raise RuntimeError("No hype found - try lower sensitivity.")
        self._log("   %d candidate peak(s)" % len(cands))

        # ---- boundary expansion + diversity ----
        moments: list = []
        audio_chunks: dict = {}
        for c in cands:
            i = c["i"]
            pre, post = cfg.pre_s, cfg.post_s
            lo = max(0, i - int(cfg.expand_s * cfg.fps))
            hi = min(grid.size - 1, i + int(cfg.expand_s * cfg.fps))
            j = i
            while j > lo and fused[j - 1] >= 0.45 * fused[i]:
                j -= 1
            start = max(0.0, min(grid[j], grid[i] - pre))
            k2 = i
            while k2 < hi and fused[k2 + 1] >= 0.45 * fused[i]:
                k2 += 1
            end = min(total, max(start + cfg.min_dur_s, grid[k2] + 2.0,
                                 grid[i] + post))
            end = min(end, start + cfg.max_dur_s)
            c["start"], c["end"] = start, end
        cands.sort(key=lambda c: c["t"])
        kept: list = []
        for c in cands:
            dup = False
            for kp in kept:
                ov = min(c["end"], kp["end"]) - max(c["start"], kp["start"])
                if ov > 0.5 * min(c["end"] - c["start"],
                                  kp["end"] - kp["start"]):
                    dup = True
                    break
                if ap and kp.get("chunk") is not None:
                    pass
            if dup:
                continue
            if ap and c["start"] < ap["t"][-1]:
                a0 = int(c["start"] / 0.1)
                a1 = min(ap["rms"].size, int(c["end"] / 0.1))
                c["chunk"] = ap["rms"][max(0, a0):max(1, a1)]
                for kp in kept:
                    if kp.get("chunk") is not None and c.get("chunk") \
                            is not None:
                        if _audio_sim(c["chunk"], kp["chunk"]) \
                                >= cfg.diversity_sim:
                            dup = True
                            break
            if dup:
                continue
            kept.append(c)
        kept = kept[:maxc]
        self._log("   %d moment(s) after diversity filter" % len(kept))

        series_t, series_v = grid, fused
        for c in kept:
            i = int(np.searchsorted(grid, c["t"]))
            i = min(i, grid.size - 1)
            bd = {}
            for name, f in parts.items():
                bd[name] = round(float(f[min(i, f.size - 1)]), 1)
            bd["confidence"] = round(sum(
                s.conf for s in live.values()) / len(live), 2)
            m = Moment(start=c["start"], end=c["end"], peak=c["t"],
                       score=round(min(10.0, c["score"]), 1))
            m.breakdown = bd
            moments.append(m)

        if self.r:
            self.r.progress_scan(1.0)
        stride = max(1, grid.size // 3000)
        series = {"t": [round(float(grid[i]), 1)
                        for i in range(0, grid.size, stride)],
                  "score": [round(float(series_v[i]), 3)
                            for i in range(0, grid.size, stride)]}
        for m in moments:
            self._log("HYPE @ %s  score=%.1f  %s"
                      % (self._fmt(m.peak), m.score,
                         self._why(m.breakdown)))
        return moments, series

    @staticmethod
    def _fmt(s):
        s = max(0, int(s))
        return "%d:%02d" % (s // 60, s % 60)

    @staticmethod
    def _why(bd):
        if not bd:
            return ""
        top = sorted(((k, v) for k, v in bd.items()
                      if k not in ("confidence",)),
                     key=lambda kv: -kv[1])[:3]
        return "why: " + ", ".join("%s=%.1f" % (k, v) for k, v in top)
