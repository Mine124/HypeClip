"""Hook Optimizer: finds the strongest possible first moment using the
Whisper word stream. Kills filler intros ('okay guys...', 'so basically'),
lands 0.3s before the first high-energy word, preserves context."""
from __future__ import annotations
import re

# chains of throat-clearing that humans skip
_WEAK = re.compile(
    r"^(okay|ok|alright|right|so|well|now|um+|uh+|erm|hmm|like|anyway[sz]?|"
    r"basically|literally|guys|chat|y'know|you know|i guess)[,.! ]*$", re.I)
# tokens that signal we've hit payload
_STRONG = re.compile(
    r"(no\s*way|what+|bro|bruh|yo|dude|let'?s\s*go+|oh\s*my|stop|wait|"
    r"insane|crazy|kidding|clutch|won|win|lost|omg|shee+s+h|ay+)|[!?]{1,}", re.I)


def _words(segments: list[dict]) -> list[dict]:
    out = []
    for s in segments:
        for w in s.get("words") or []:
            out.append(w)
    return out


def best_trim(segments: list[dict], max_look: float = 6.0,
              min_clip: float = 15.0,
              cur_dur: float = 999.0) -> tuple[float, str]:
    """Returns (seconds_to_cut_from_front, reason). 0.0 = keep as-is."""
    words = _words(segments)
    if not words:
        return 0.0, "no word stream"
    if cur_dur - max_look < min_clip:
        return 0.0, "clip too short to trim"

    # collect filler prefix
    i, filler_end = 0, 0.0
    while i < len(words):
        w = words[i]
        tok = (w.get("w") or "").strip()
        if tok and _WEAK.match(tok):
            filler_end = float(w.get("e", 0))
            i += 1
            continue
        break

    first = words[i] if i < len(words) else None
    first_tok = (first.get("w") or "").strip() if first else ""
    strong_hit = bool(first_tok and _STRONG.search(first_tok))

    if strong_hit and filler_end <= 0:
        # payload is already word #1 -> maybe even pull tighter to it
        t0 = float(first.get("s", 0))
        if t0 > 1.4:
            d = round(min(t0 - 0.35, max_look), 2)
            return d, f"cold-open onto '{first_tok}'"
        return 0.0, "already opens on payload"

    if filler_end > 0:
        # cut the fillers, land just before the first real word
        d = round(max(0.0, filler_end - 0.30), 2)
        if d >= 0.6:
            nxt = first_tok[:20] if first_tok else "?"
            return d, f"skipped filler intro -> '{nxt}'"

    # nothing obvious: fall back to loudest word onset in window
    if first is None:
        return 0.0, "empty"
    look = [w for w in words if float(w.get("s", 0)) <= max_look]
    if not look:
        return 0.0, "no early speech"
    loudest = max(look, key=lambda w: len((w.get("w") or "")))
    lt = float(loudest.get("s", 0))
    if lt > 1.6:
        return round(lt - 0.35, 2), f"opens near peak word '{loudest.get('w','')}'"
    return 0.0, "intro already tight"
