"""Audio-based hype detection: finds loudness/energy spikes vs a trailing
baseline. Used when a source has no chat (TikTok, direct files, etc.)."""
from __future__ import annotations

import numpy as np

from .hype import Moment

SR = 4000


class AudioHypeAnalyzer:
    WINDOW = 240
    LOCAL_MAX_R = 8

    def __init__(self, settings, media_path: str):
        self.s = settings
        self.path = media_path

    def _per_second_rms(self) -> np.ndarray:
        from .utils import resolve_bin, run
        raw = run([resolve_bin("ffmpeg"), "-v", "error", "-i", self.path,
                   "-ac", "1", "-ar", str(SR), "-vn", "-f", "f32le", "-"],
                  capture_bytes=True)
        x = np.frombuffer(raw, np.float32)
        n = x.size // SR
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        x = x[: n * SR]
        energy = (x * x).reshape(n, SR).mean(axis=1)
        return np.sqrt(np.maximum(energy, 0.0))

    def detect(self, total=None):
        rms = self._per_second_rms()
        n = int(rms.size)
        empty = {"t": [], "score": []}
        if n < 60:
            return [], empty

        db = 20.0 * np.log10(rms + 1e-6)
        med = float(np.median(db))
        csum = np.cumsum(db)
        csum2 = np.cumsum(db * db)
        thr = float(self.s.hype_threshold)
        W = self.WINDOW
        floor = max(float(rms.max()) * 0.05, 1e-4)

        score = np.zeros(n)
        for i in range(30, n):
            if rms[i] < floor:
                continue
            hi = max(30, i - 5)
            lo = max(0, hi - W)
            m_ = hi - lo
            if m_ < 25:
                continue
            mean = (csum[hi] - csum[lo]) / m_
            var = max((csum2[hi] - csum2[lo]) / m_ - mean * mean, 0.0)
            std = float(np.sqrt(var)) + 1e-6
            z = (db[i] - mean) / std
            if z <= 0:
                continue
            boost = 1.0 + 0.5 * min(max((db[i] - med) / 18.0, 0.0), 2.0)
            score[i] = z * boost

        score = np.convolve(score, np.array([0.25, 0.5, 0.25]), "same")

        cand = [i for i in range(n) if score[i] >= thr]
        cand = [i for i in cand
                if score[i] == score[max(0, i - self.LOCAL_MAX_R):
                                     i + self.LOCAL_MAX_R + 1].max()]
        cand.sort(key=lambda i: -score[i])

        cd = float(self.s.cooldown)
        accepted: list[int] = []
        for p in cand:
            if all(abs(p - a) > cd for a in accepted):
                accepted.append(p)
            if len(accepted) >= int(self.s.max_clips):
                break
        accepted.sort()

        total_dur = float(total or n)
        dur = max(10.0, min(float(self.s.clip_duration), total_dur * 0.8))
        pre = min(float(self.s.pre_roll), dur * 0.5)

        moments: list[Moment] = []
        for p in accepted:
            l = p
            while l - 1 > 0 and score[l - 1] >= 0.35 * score[p] and p - l < pre + 15:
                l -= 1
            start = max(0.0, min(p - pre, float(l)))
            r_ = p
            while r_ + 1 < n and score[r_ + 1] >= 0.35 * score[p] and r_ - p < dur + 20:
                r_ += 1
            end = min(max(start + dur, r_ + 3.0), start + dur + 20.0, total_dur)
            if end > 5.0:
                start = max(0.0, min(start, end - 5.0))
            moments.append(Moment(start=start, end=end,
                                  peak=float(p), score=float(score[p])))

        stride = max(1, n // 3000)
        series = {"t": [int(i) for i in range(0, n, stride)],
                  "score": [round(float(score[i]), 3)
                            for i in range(0, n, stride)]}
        return moments, series
