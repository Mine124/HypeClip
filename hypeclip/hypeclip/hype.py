from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

_KW_RAW = {
    r"\bp+o+g+(?:gers|champ|u|s)?\b": 2.0,
    r"\bles+go+(?:o+d+)?\b|\blet'?s\s+go+\b|\blfg\b": 2.5,
    r"\bno+\s*way+\b": 2.2,
    r"\binsane\b|\bcra+a?zy+\b|\bbananas?\b|\bnuts?\b": 1.5,
    r"\bw+t+f+\b": 1.6,
    r"\bholy\b|\bda+m+n?\b|\bjesus\b|\bchrist\b|\blord\b": 1.4,
    r"\bl+m+f?a+o+\b|\brofl\b|\bk+y+s+\b|\bscream\w*\b": 1.2,
    r"\bclap\w*\b|\bapplause\b": 1.0,
    r"\bg+g+\b": 1.1,
    r"\be+z+z?(?:clap)?\b|\bfree\s*win\b|\beasy\s*(?:clap|win|gg)\b": 1.1,
    r"\bf\s*in\s*the\s*chat\b|\bpress\s*f\b": 1.6,
    r"\bshe*e+sh+\b|\blet\s*him\s*cook\b|\bhe\s*cook\w*\b|\bcooked\b": 1.3,
    r"\brigged\b|\bscam\w*\b|\brobbed\b|\bref\b|\bfixed\b": 1.2,
    r"\bomegalul\b|\bkekw+\b|\bl+u+l+\w*\b|\bpepe\w*\b|\bmonka\w+\b|\bsadge\b|\bcopium\b|\bcopes?\b": 1.1,
    r"\bwhat+s+\b|\bsus\b|\bhuh\b": 0.9,
}
KEYWORDS = [(re.compile(p, re.I), w) for p, w in _KW_RAW.items()]
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2190-\u21FF]")


@dataclass
class Moment:
    start: float
    end: float
    peak: float
    score: float


class HypeAnalyzer:
    WINDOW = 240
    LOCAL_MAX_R = 5

    def __init__(self, settings):
        self.s = settings
        self.bins: dict[int, list[tuple[str, float]]] = defaultdict(list)

    def add(self, t: float, text: str, money: float = 0.0):
        self.bins[int(t)].append((text or "", float(money or 0)))

    def _features(self, sec: int):
        items = self.bins.get(sec)
        if not items:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        n = len(items)
        letters = caps = excl = emoji_hits = 0
        kw = money = 0.0
        for text, mn in items:
            letters += sum(1 for c in text if c.isalpha())
            caps += sum(1 for c in text if c.isupper())
            excl += text.count("!") + text.count("1")
            emoji_hits += len(EMOJI.findall(text))
            money += mn
            for rx, w in KEYWORDS:
                if rx.search(text):
                    kw += w
        kw = min(kw, 2.0 * n)
        caps_ratio = caps / letters if letters else 0.0
        excl_rate = excl / max(sum(len(t) for t, _ in items), 1)
        return (float(n), caps_ratio, kw / n, excl_rate,
                min(emoji_hits / n, 10.0), money)

    def detect(self, total: float | None = None):
        if not self.bins:
            return [], {"t": [], "score": []}

        n = int(max(self.bins)) + 1
        cnt = np.zeros(n); caps = np.zeros(n); kw = np.zeros(n)
        exc = np.zeros(n); emo = np.zeros(n); mon = np.zeros(n)
        for sec in self.bins:
            if sec < n:
                cnt[sec], caps[sec], kw[sec], exc[sec], emo[sec], mon[sec] = \
                    self._features(sec)

        csum = np.cumsum(cnt)
        csum2 = np.cumsum(cnt * cnt)
        thr = float(self.s.hype_threshold)
        W, PAD = self.WINDOW, 5

        score = np.zeros(n)
        for i in np.nonzero(cnt)[0]:
            lo, hi = max(0, i - W), max(0, i - PAD)
            m_ = hi - lo
            if m_ < 30:
                continue
            mean = (csum[hi] - csum[lo]) / m_
            var = max((csum2[hi] - csum2[lo]) / m_ - mean * mean, 0.0)
            std = np.sqrt(var)
            if cnt[i] < max(5.0, mean * 1.3):
                continue
            z = (cnt[i] - mean) / (std + 1e-9)
            boost = (1.0 + 0.8 * caps[i] + 0.15 * min(kw[i], 3.0)
                     + 8.0 * exc[i] + 0.05 * emo[i] + min(mon[i], 100.0) / 25.0)
            score[i] = max(z, 0.0) * boost

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

        moments = []
        dur = float(self.s.clip_duration)
        pre = float(self.s.pre_roll)
        for p in accepted:
            start = max(0.0, p - pre)
            l = p
            while l - 1 > 0 and score[l - 1] >= 0.35 * score[p] and p - l < pre + 15:
                l -= 1
            start = min(start, float(l))
            endc = start + dur
            r = p
            while r + 1 < n and score[r + 1] >= 0.35 * score[p] and r - p < dur + 20:
                r += 1
            endc = min(max(endc, r + 3.0), start + dur + 20.0)
            if total:
                endc = min(endc, float(total))
                start = max(0.0, min(start, endc - 5.0))
            moments.append(Moment(start=start, end=endc, peak=float(p),
                                  score=float(score[p])))

        stride = max(1, n // 4000)
        series = {
            "t": [int(i) for i in range(0, n, stride)],
            "score": [round(float(score[i]), 3) for i in range(0, n, stride)],
        }
        return moments, series