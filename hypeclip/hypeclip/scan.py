"""Visual chat-speed scanner: watches a user-selected rectangle of the video
and measures how fast it scrolls. Sustained fast scrolling == hype.

v2 (hardened): every Settings read goes through _num(), which converts
blanks (_SafeBlank), None, and bad strings into safe defaults. This kills
the "float() argument must be ... not '_SafeBlank'" crash at its source,
and the scan now always reports progress_scan(1.0) when the frame loop
ends (fixes the UI sticking at ~98%).
"""
from __future__ import annotations
import subprocess

import numpy as np

from .hype import Moment

FW, FH = 96, 64

_DEF_THRESHOLD = 3.5
_DEF_COOLDOWN = 8.0
_DEF_MAX_CLIPS = 20
_DEF_CLIP_DUR = 90.0
_DEF_PREROLL = 1.5


def _num(v, default):
    """Coerce any setting value to float; blanks/None/bad strings -> default.

    Deliberately does NOT call float() directly on unknown objects: a
    _SafeBlank str()s to a repr that float() rejects, so we always land
    on the default instead of crashing (or on a hardened-blank 0.0).
    """
    if isinstance(v, bool):
        return float(default)
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return f if f == f else float(default)  # NaN guard
    try:
        f = float(str(v).strip())
        return f if f == f else float(default)
    except Exception:
        return float(default)


class ScrollScanner:
    WINDOW_S = 180

    def __init__(self, settings, media_path: str, rect: tuple,
                 reporter=None, sample_fps: float = 6.0):
        self.s = settings
        self.path = media_path
        self.rect = rect
        self.r = reporter
        self.fps = max(1.0, min(30.0, float(sample_fps)))

    def _frames(self):
        from .utils import resolve_bin
        x, y, w, h = self.rect
        vf = (f"crop=w='iw*{w:.4f}':h='ih*{h:.4f}':"
              f"x='iw*{x:.4f}':y='ih*{y:.4f}',"
              f"scale={FW}:{FH},fps={self.fps},format=gray")
        cmd = [resolve_bin("ffmpeg"), "-v", "error", "-i", self.path,
               "-an", "-vf", vf, "-f", "rawvideo", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        nbytes = FW * FH
        try:
            while True:
                buf = proc.stdout.read(nbytes)
                if not buf or len(buf) < nbytes:
                    break
                yield np.frombuffer(buf, np.uint8).reshape(FH, FW)
        finally:
            proc.kill()

    def detect(self, total=None):
        prev = None
        vals: list[float] = []
        est = int(_num(total, 0.0) * self.fps)
        last_report = -1.0

        try:
            for i, frame in enumerate(self._frames()):
                g = frame.astype(np.float32) / 255.0
                if prev is not None:
                    vals.append(float(np.abs(g - prev).mean()))
                prev = g
                if est and i % 60 == 0 and self.r:
                    frac = min(i / est, 0.99)
                    if frac - last_report > 0.02:
                        last_report = frac
                        self.r.progress_scan(frac)
        finally:
            # ALWAYS complete the scan bar, even if the frame source died
            if self.r:
                self.r.progress_scan(1.0)

        v = np.asarray(vals, dtype=np.float32)
        empty = {"t": [], "score": []}
        if v.size < self.fps * 30:
            return [], empty

        k = np.ones(3, dtype=np.float32) / 3.0
        v = np.convolve(v, k, "same")
        csum = np.cumsum(v)
        csum2 = np.cumsum(v * v)
        W = int(self.WINDOW_S * self.fps)
        thr = _num(self.s.hype_threshold, _DEF_THRESHOLD)
        n = v.size

        score = np.zeros(n, dtype=np.float32)
        for i in range(W // 4, n):
            lo, hi = max(0, i - W), max(0, i - int(2 * self.fps))
            m_ = hi - lo
            if m_ < int(10 * self.fps):
                continue
            mean = (csum[hi] - csum[lo]) / m_
            var = max((csum2[hi] - csum2[lo]) / m_ - mean * mean, 0.0)
            std = float(np.sqrt(var)) + 1e-6
            z = (v[i] - mean) / std
            if z > 0:
                score[i] = z

        score = np.convolve(score, k, "same")

        R = int(4 * self.fps)
        cand = [i for i in range(n) if score[i] >= thr]
        cand = [i for i in cand
                if score[i] == score[max(0, i - R):i + R + 1].max()]
        cand.sort(key=lambda i: -score[i])

        cd = _num(self.s.cooldown, _DEF_COOLDOWN) * self.fps
        accepted: list[int] = []
        for p in cand:
            if all(abs(p - a) > cd for a in accepted):
                accepted.append(p)
            if len(accepted) >= int(_num(self.s.max_clips, _DEF_MAX_CLIPS)):
                break
        accepted.sort()

        total_num = _num(total, 0.0)
        total_dur = total_num if total_num > 0 else n / self.fps
        dur = _num(self.s.clip_duration, _DEF_CLIP_DUR)
        pre = _num(self.s.pre_roll, _DEF_PREROLL)

        moments: list[Moment] = []
        for p in accepted:
            l_ = p
            while l_ > 0 and score[l_ - 1] >= 0.35 * score[p] \
                    and (p - l_) < (pre + 15) * self.fps:
                l_ -= 1
            start = max(0.0, min(p / self.fps - pre, l_ / self.fps))
            r_ = p
            while r_ + 1 < n and score[r_ + 1] >= 0.35 * score[p] \
                    and (r_ - p) < (dur + 20) * self.fps:
                r_ += 1
            end = min(max(start + dur, r_ / self.fps + 2.0),
                      start + dur + 15.0, total_dur)
            if end > 5.0:
                start = max(0.0, min(start, end - 5.0))
            moments.append(Moment(start=start, end=end,
                                  peak=p / self.fps, score=float(score[p])))

        stride = max(1, n // 3000)
        series = {"t": [round(i / self.fps, 1) for i in range(0, n, stride)],
                  "score": [round(float(score[i]), 3)
                            for i in range(0, n, stride)]}
        return moments, series
