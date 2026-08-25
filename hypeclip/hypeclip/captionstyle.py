"""Data-driven caption styling v2: adaptive grouping, keyword emphasis,
profanity masking, calm mode."""
from __future__ import annotations
import json
import os
import re

from .config import DATA_DIR

DEFAULTS = {
    "enabled": True,
    "font": "Arial Black",
    "size_pct": 5.6,          # % of frame HEIGHT (1080x1920 -> ~107px)
    "uppercase": True,
    "primary": "#FFFFFF",
    "highlight": "#FFC400",   # gold - reads as 'important' cross-platform
    "outline": "#000000",
    "outline_px": 5,          # @720p reference, scales
    "shadow_px": 1,
    "back_box": 0,
    "position": "bottom",
    "y_pct": 12,              # stays above TikTok/Shorts UI safe zone
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
    pre = word[:word.lower().find(core.lower())] if core.lower() in word.lower() else ""
    post = word[len(pre) + len(core):]
    return pre + core[0] + "*" * (len(core) - 2) + core[-1] + post


def _ass_color(hexstr: str, alpha: str = "00") -> str:
    h = (hexstr or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return "&H{}{}{}{}".format(alpha, h[4:6], h[2:4], h[0:2]).upper()


def _inline(hexstr: str) -> str:
    """Inline \\1c override tag from hex RGB."""
    h = (hexstr or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return "{\\1c&H{}{}{}&}".format(h[4:6], h[2:4], h[0:2]).replace("\\c", "\\1c")


def _is_emph(word: str) -> bool:
    core = word.strip("!,.?\"'")
    return (core.isupper() and len(core) >= 2) or bool(EMPH_HINTS.search(word))


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
        p = os.path.join(DATA_DIR, "last_caption.json")
        try:
            with open(p, encoding="utf-8") as f:
                return cls(json.load(f))
        except Exception:
            return cls()

    def save_active(self):
        with open(os.path.join(DATA_DIR, "last_caption.json"), "w",
                  encoding="utf-8") as f:
            json.dump(self.d, f, indent=1)

    # ------------------------------------------------------------- header
    def _header(self, w: int, h: int) -> str:
        d = self.d
        sc = max(0.5, h / 720.0)
        fs = max(10, int(d["size_pct"] / 100 * h))
        ol = max(0, round(d["outline_px"] * sc))
        sh = max(0, round(d["shadow_px"] * sc))
        bs = 4 if d["back_box"] > 0 else 1
        back_a = format(max(0, min(255, round((100 - d["back_box"]) * 2.55))), "02X")
        align = _ALIGNS.get(d["position"], 2)
        mv = 0 if d["position"] == "center" else int(h * d["y_pct"] / 100)
        sec = _ass_color(d["highlight"]) if d["effect"] == "karaoke" \
            else "&H00FFFFFF"
        return (
            "[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
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
            return ("{\\fscx60\\fscy60\\t(0," + str(ms) +
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

    # ------------------------------------------------------- smart groups
    def _groups(self, segments: list[dict]) -> list[dict]:
        d = self.d
        n = max(1, int(d["words_per_group"]))
        flat = []
        for seg in segments:
            ws = seg.get("words") or _fake_words(seg)
            for wd in ws:
                flat.append({**wd, "w": _mask(wd.get("w", ""), d["censor"])})
        if not flat:
            return []
        # speech-rate adaptivity: fast talkers get fewer words on screen
        chars = sum(len(x["w"]) + 1 for x in flat)
        secs = max(0.5, flat[-1]["e"] - flat[0]["s"])
        cps = chars / secs
        g = n
        if cps > 19:
            g = min(n, 2)
        elif cps < 9:
            g = min(n + 1, 5)
        raw, cur, cur_chars = [], [], 0
        prev_e = None
        for wd in flat:
            gap_break = prev_e is not None and wd["s"] - prev_e > 0.55
            if cur and (len(cur) >= g or gap_break
                        or cur_chars + len(wd["w"]) > d["max_line_chars"] * 2):
                raw.append(cur); cur, cur_chars = [], 0
            cur.append(wd); cur_chars += len(wd["w"]) + 1
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

    # --------------------------------------------------------- dialogues
    def dialogues(self, segments: list[dict], w: int, h: int,
                  calm: bool = False) -> list[str]:
        d = self.d
        fx = "" if calm else self._fx_tag(w, h)
        emph_col = _inline(d.get("emphasis_color", "#FFC400"))
        reset = "{\\r}"
        out = []
        for grp in self._groups(segments):
            words = [(x["w"], x["e"] - x["s"],
                      _is_emph(x["w"])) for x in grp["chunk"]]
            text = " ".join(x[0] for x in words).strip()
            if not text:
                continue
            if d["uppercase"]:
                text = text.upper()
                words = [(wd.upper(), du, em) for wd, du, em in words]
            text = text.replace("{", "(").replace("}", "")
            if d["effect"] == "karaoke":
                body = " ".join(
                    "{\\k" + str(max(1, round(du * 100))) + "}"
                    + ((emph_col if em else "") + wd.upper()
                       + (reset if em else ""))
                    for wd, du, em in words)
            else:
                body = " ".join(
                    (emph_col if em else "") + wd + (reset if em else "")
                    for wd, _, em in words)
                body = _wrap(body.replace("}{", "}{"), d["max_line_chars"] + 12)
            out.append(f"Dialogue: 0,{_ts(grp['s'])},{_ts(grp['e'])},"
                       f"Cap,,0,0,0,,{fx}{body}")
        return out

    def write_ass(self, segments: list[dict], path: str, w: int, h: int,
                  calm: bool = False):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._header(w, h) +
                    "\n".join(self.dialogues(segments, w, h, calm=calm)) + "\n")
