"""Story chain engine - the scream is the payoff, not the clip.

build_chains() takes the engine's moments plus the fused intensity
series and connects micro-events into narrative arcs:

    setup (smaller peak) -> buildup (micro-events) -> payoff (big peak)

Consecutive moments are merged into one longer clip when they escalate
or sit close enough to be one story, and the merged Moment carries
structured metadata:

    m.story = {"kind": "buildup_payoff",
               "beats": [{"t": 252.1, "kind": "setup", "score": 4.2}, ...],
               "connection": 0.74}

Merged arcs keep the strongest member's score plus a story bonus.
Fully guarded: any failure returns the input list unchanged, so the
pipeline can never break because of this pass.
"""
from __future__ import annotations

import numpy as np


def _cfg(settings, name, default):
    v = getattr(settings, name, None)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return float(default)


def _micro_events(series) -> list:
    """Local maxima in the fused series above 30% of its P90 - these are
    the connective tissue between setup and payoff."""
    try:
        t = np.asarray(series.get("t") or [], dtype=np.float32)
        v = np.asarray(series.get("score") or series.get("v") or [],
                       dtype=np.float32)
    except Exception:
        return []
    if t.size < 8 or v.size != t.size:
        return []
    peak = float(np.percentile(v, 90)) or 1.0
    floor = peak * 0.30
    ev = []
    for i in range(1, v.size - 1):
        if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] >= floor:
            ev.append((float(t[i]), float(v[i])))
    return ev


def _fmt(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60)


def build_chains(moments, media, settings, reporter, series=None):
    def log(m):
        if reporter is not None and hasattr(reporter, "log"):
            reporter.log(str(m))
    try:
        if not moments or len(moments) < 2:
            return moments
        moments = sorted(moments, key=lambda m: m.peak)
        win = _cfg(settings, "story_window_s", 45.0)
        gap_join = _cfg(settings, "story_join_gap_s", 12.0)
        hard_max = max(_cfg(settings, "engine_max_dur_s", 150.0),
                       _cfg(settings, "clip_duration", 90.0))
        bonus = _cfg(settings, "story_bonus", 0.8)
        micro = _micro_events(series or {})

        # greedy chain growth: absorb later moments that escalate or
        # sit within join distance of the previous beat
        chains: list = []
        cur = [moments[0]]
        for nxt in moments[1:]:
            prev = cur[-1]
            gap = nxt.peak - prev.peak
            escalate = nxt.score >= prev.score * 0.85
            close = gap <= win and (nxt.start - prev.end) <= gap_join
            if close and (escalate or nxt.score >= prev.score):
                cur.append(nxt)
            else:
                chains.append(cur)
                cur = [nxt]
        chains.append(cur)

        out: list = []
        merged_n = 0
        for chain in chains:
            if len(chain) == 1:
                out.append(chain[0])
                continue
            start = chain[0].start
            end = chain[-1].end
            if end - start > hard_max:
                out.extend(chain)          # too long -> keep separate
                continue
            payoff = max(chain, key=lambda m: m.score)
            setups = [m for m in chain if m is not payoff]
            connection = 0.5
            if micro:
                span_beats = [e for e in micro
                              if start <= e[0] <= end]
                if span_beats:
                    coverage = len(span_beats) / max(1.0,
                                                     (end - start) / 10.0)
                    connection = float(np.clip(0.4 + 0.12 * coverage, 0.4,
                                               0.95))
            beats = []
            for k, m in enumerate(chain):
                kind = ("setup" if k == 0 and len(chain) > 1
                        else "payoff" if k == len(chain) - 1 else "beat")
                beats.append({"t": round(m.peak, 1),
                              "kind": kind,
                              "score": round(float(m.score), 1)})
            top = max(chain, key=lambda m: m.score)
            new_score = min(10.0, float(top.score) + bonus * connection)
            pay = max(chain, key=lambda m: m.score)
            m2 = type(pay)(start=start, end=end, peak=pay.peak,
                           score=round(new_score := min(10.0, new_score := new_score), 1)
                           if False else round(new_score_val, 1))
            m2 = pay
            m2.start = start
            m2.end = end
            m2.peak = pay.peak
            m2.score = round(min(10.0, float(pay.score) + bonus), 1)
            try:
                m2.story = {"kind": "buildup_payoff",
                            "beats": beats,
                            "connection": round(connection, 2)}
                m2.breakdown = dict(getattr(pay, "breakdown", None) or {})
                m2.breakdown["story"] = round(bonus, 1)
            except Exception:
                pass
            out.append(m2)
            merged_n += 1
            log("📖 STORY: setup @ %s (%.1f) -> payoff @ %s (%.1f) - "
                "one %.0fs arc, connection %.2f"
                % (_fmt(chain[0].peak), chain[0].score,
                   _fmt(pay.peak), pay.score, end - start, connection))
        if merged_n:
            log("📖 story pass: %d arc(s) merged from "
                "%d raw moment(s)" % (merged_n, len(moments)))
        return out
    except Exception as e:
        log(f"(story pass skipped: {e})")
        return moments
