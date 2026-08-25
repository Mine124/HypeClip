"""Caption Brain v2.1: fixed emphasis detection, wrapped karaoke,
reading-speed governor."""
from __future__ import annotations
import json
import os
import re
import statistics

from .config import DATA_DIR

DEFAULTS = {
    "enabled": True,
    "font": "Arial Black",
    "size_pct": 5.6,
    "uppercase": True,
    "primary": "#FFFFFF",
    "highlight": "#FFC400",
    "outline": "#000000",
    "outline_px": 5,
    "shadow_px": 1,
    "back_box": 0,
    "position": "bottom",
    "y_pct": 12,
    "words_per_group": 3,
    "max_line_chars": 22,
    "effect": "pop",
    "effect_ms": 180,
    "emphasis_color": "#FFC400",
    "censor": False,
}

_ALIGNS = {"bottom": 2, "center": 5, "top": 8}
PROFANE = {"fuck", "shit", "bitch", "asshole", "dick", "cunt", "whore"}
EMPH_HINTS = re.compile(r"[!?]$")


def _mask(word: str, enabled: bool) -> str:
    core = word.strip("!,.?\"'")
    if not enabled or core.lower() not in PROFANE or len(core) < 3:
        return word
    low = word.lower()
    i = low.find(core.lower())
    if i == -1:
        return word
    pre = word[:i]
    post = word[i + len(core):]
    return pre + core[0] + "*" * (len(core) - 2) + core[-1] + post


def _ass_color(hexstr: str, alpha: str = "00") -> str:
    h = (hexstr or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return "&H{}{}{}{}".format(alpha, h[4:6], h[2:4], h[0:2]).upper()


def _inline(hexstr: str) -> str:
    h = (hexstr or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    # ASS inline color is &HBBGGRR& (BGR order!)
    return "{\\1c&H" + h[4:6] + h[2:4] + h[0:2] + "&}"


def _is_emph(word: str, med_len: float) -> bool:
    """Emphasis = statistically unusual word OR punctuation energy.
    No longer depends on ALL-CAPS (Whisper returns lowercase)."""
    core = word.strip("!,.?\"'\"“”")
    if len(core) < 3:
        return False
    score = 0
    letters = [c for c in core if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6 \
            and len(letters) >= 2:
        score += 1
    if EMPH_HINTS.search(word):
        score += 1
    if med_len and len(core) >= max(4, round(med_len * 1.8)):
        score += 2          # unusually long word = usually the payload
    return score >= 2


def _ts(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap(text: str, limit: int) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > limit:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\\N".join(lines)


def _fake_words(seg: dict) -> list[dict]:
    text = seg["text"].strip()
    toks = text.split()
    total = sum(len(t) + 1 for t in toks)
    dur = max(0.2, seg["end"] - seg["start"])
    out, t = [], seg["start"]
    for tok in toks:
        d = dur * (len(tok) + 1) / total
        out.append({"w": tok, "s": t, "e": t + d}); t += d
    return out


class CaptionStyle:
    def __init__(self, d: dict | None = None):
        self.d = {**DEFAULTS, **{k: v for k, v in (d or {}).items()
                                 if k in DEFAULTS and v is not None}}

    @classmethod
    def load_active(cls) -> "CaptionStyle":
        try:
            with open(os.path.join(DATA_DIR, "last_caption.json"),
                      encoding="utf-8") as f:
                return cls(json.load(f))
        except Exception:
            return cls()

    def save_active(self):
        with open(os.path.join(DATA_DIR, "last_caption.json"), "w",
                  encoding="utf-8") as f:
            json.dump(self.d, f, indent=1)

    def _header(self, w: int, h: int) -> str:
        d = self.d
        sc = max(0.5, h / 720.0)
        fs = max(10, int(d["size_pct"] / 100 * h))
        ol = max(0, round(d["outline_px"] * sc))
        sh = max(0, round(d["shadow_px"] * sc))
        bs = 4 if d["back_box"] > 0 else 1
        back_a = format(max(0, min(255,
            round((100 - d["back_box"]) * 2.55))), "02X")
        align = _ALIGNS.get(d["position"], 2)
        mv = 0 if d["position"] == "center" else int(h * d["y_pct"] / 100)
        sec = _ass_color(d["highlight"]) if d["effect"] == "karaoke" \
            else "&H00FFFFFF"
        return (
            "[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
            "MarginV, Encoding\n"
            f"Style: Cap,{d['font']},{fs},{_ass_color(d['primary'])},{sec},"
            f"{_ass_color(d['outline'])},{_ass_color('#101010', back_a)},"
            f"-1,0,0,0,100,100,0,0,{bs},{ol},{sh},{align},60,60,{mv},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, "
            "MarginR, MarginV, Effect, Text\n")

    def _fx_tag(self, w: int, h: int) -> str:
        d, ms = self.d, int(self.d["effect_ms"])
        eff = d["effect"]
        if eff == "fade":
            return "{\\fad(" + str(ms // 2) + "," + str(ms // 2) + ")}"
        if eff == "pop":
            return ("{\\fscx62\\fscy62\\t(0," + str(ms) +
                    ",\\fscx106\\fscy106)\\t(" + str(ms) + "," +
                    str(int(ms * 1.7)) + ",\\fscx100\\fscy100)}")
        if eff == "bounce":
            return ("{\\fscx55\\fscy55\\t(0," + str(int(ms * .5)) +
                    ",\\fscx114\\fscy114)\\t(" + str(int(ms * .5)) + "," +
                    str(ms) + ",\\fscx94\\fscy94)\\t(" + str(ms) + "," +
                    str(int(ms * 1.4)) + ",\\fscx100\\fscy100)}")
        if eff == "slide_up":
            al = _ALIGNS.get(d["position"], 2)
            y = h - int(h * d["y_pct"] / 100) if al == 2 else \
                h // 2 if al == 5 else int(h * d["y_pct"] / 100)
            return ("{\\move(" + str(w // 2) + "," + str(y + 36) + "," +
                    str(w // 2) + "," + str(y) + ",0," + str(ms) + ")}")
        return ""

    def _groups(self, segments: list[dict]) -> list[dict]:
        d = self.d
        n = max(1, int(d["words_per_group"]))
        flat = []
        for seg in segments:
            ws = seg.get("words") or _fake_words(seg)
            for wd in ws:
                flat.append({**wd, "w": _mask(wd.get("w", ""),
                                              d["censor"])})
        if not flat:
            return []
        chars = sum(len(x["w"]) + 1 for x in flat)
        secs = max(0.5, flat[-1]["e"] - flat[0]["s"])
        cps = chars / secs
        g = n
        if cps > 19:
            g = min(n, 2)
        elif cps < 9:
            g = min(n + 1, 5)
        raw, cur, width = [], [], 0
        prev_e = None
        for wd in flat:
            gap_break = prev_e is not None and wd["s"] - prev_e > 0.55
            if cur and (len(cur) >= g or gap_break
                        or width > d["max_line_chars"] * 2):
                raw.append(cur); cur, width = [], 0
            cur.append(wd); width += len(wd["w"]) + 1
            prev_e = wd["e"]
        if cur:
            raw.append(cur)
        out = []
        for chunk in raw:
            out.append({"s": chunk[0]["s"], "e": chunk[-1]["e"],
                        "chunk": chunk})
        for i, grp in enumerate(out):
            nxt = out[i + 1]["s"] if i + 1 < len(out) else grp["e"] + 1
            grp["e"] = min(nxt, grp["e"] + 0.8)
        return out

    def dialogues(self, segments: list[dict], w: int, h: int,
                  calm: bool = False) -> list[str]:
        d = self.d
        fx = "" if calm else self._fx_tag(w, h)
        emph_col = _inline(d.get("emphasis_color", "#FFC400"))
        reset = "{\\r}"
        groups = self._groups(segments)

        # median word length across clip -> emphasis baseline
        lens = [len((wd.get("w") or "").strip("!,.?\"'"))
                for seg in segments
                for wd in (seg.get("words") or [])]
        med = statistics.median(lens) if lens else 0.0

        out = []
        for grp in groups:
            toks = [(x["w"], x["e"] - x["s"],
                     _is_emph(x["w"], med)) for x in grp["chunk"]]
            text = " ".join(x[0] for x in toks).strip()
            if not text:
                continue
            if d["uppercase"]:
                toks = [(wd.upper(), du, em) for wd, du, em in toks]
            # restraint: max ONE emphasized word per group (the strongest)
            emph_idx = [i for i, (_, _, em) in enumerate(toks) if em]
            if len(emph_idx) > 1:
                keep = max(emph_idx,
                           key=lambda i: len(toks[i][0].strip("!,.?\"'")))
                toks = [(wd, du, i == keep) for i, (wd, du, _) in
                        enumerate(toks)]
            elif not emph_idx and toks:
                # guarantee at least one visual anchor per group:
                longest = max(range(len(toks)),
                              key=lambda i: len(toks[i][0]))
                toks[longest] = (toks[longest][0], toks[longest][1], True)

            body_words = []
            plain = []
            for wd, du, em in toks:
                clean = wd.replace("{", "(").replace("}", "")
                plain.append(clean)
                body_words.append((emph_col + clean + reset) if em
                                  else clean)
            if d["effect"] == "karaoke":
                body = " ".join(
                    "{\\k" + str(max(1, round(du * 100))) + "}" + bw
                    for (bw, (_, du, _)) in zip(body_words, toks))
                body = _wrap(body.replace("}{", "} {"), d["max_line_chars"]
                             + 14).replace("} {", "}{")
            else:
                body = _wrap(" ".join(body_words),
                             d["max_line_chars"] + 12)
            out.append(f"Dialogue: 0,{_ts(grp['s'])},{_ts(grp['e'])},"
                       f"Cap,,0,0,0,,{fx}{body}")
        return out

    def write_ass(self, segments: list[dict], path: str, w: int, h: int,
                  calm: bool = False):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._header(w, h) +
                    "\n".join(self.dialogues(segments, w, h, calm=calm))
                    + "\n")
