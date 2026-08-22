"""Data-driven caption styling: grouping, fonts, colors, effects."""
from __future__ import annotations
import json
import os

from .config import DATA_DIR

DEFAULTS = {
    "enabled": True,
    "font": "Arial Black",
    "size_pct": 6.4,          # % of video height
    "uppercase": True,
    "primary": "#FFFFFF",
    "highlight": "#FFB300",
    "outline": "#000000",
    "outline_px": 5,          # measured at 720p, scales with height
    "shadow_px": 1,
    "back_box": 0,            # 0-90 (% opacity background pill)
    "position": "bottom",     # bottom | center | top
    "y_pct": 12,              # margin from edge, % of height
    "words_per_group": 2,
    "max_line_chars": 24,
    "effect": "pop",          # pop | bounce | slide_up | fade | karaoke | none
    "effect_ms": 220,
}

_ALIGNS = {"bottom": 2, "center": 5, "top": 8}


def _ass_color(hexstr: str, alpha: str = "00") -> str:
    h = (hexstr or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return "&H{}{}{}{}".format(alpha, h[4:6], h[2:4], h[0:2]).upper()


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
    """No word timestamps? Split evenly by word length."""
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

    # ------------------------------------------------------------- ASS output
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
            return ("{\\fscx35\\fscy35\\t(0," + str(ms) +
                    ",\\fscx108\\fscy108)\\t(" + str(ms) + "," +
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
        return ""  # none / karaoke

    def _groups(self, segments: list[dict]) -> list[dict]:
        n = max(1, int(self.d["words_per_group"]))
        raw = []
        for seg in segments:
            words = seg.get("words") or _fake_words(seg)
            for i in range(0, len(words), n):
                chunk = words[i:i + n]
                raw.append({"s": chunk[0]["s"], "e": chunk[-1]["e"],
                            "chunk": chunk})
        for i, g in enumerate(raw):
            nxt = raw[i + 1]["s"] if i + 1 < len(raw) else g["e"] + 1
            g["e"] = min(nxt, g["e"] + 0.8)
        return raw

    def dialogues(self, segments: list[dict], w: int, h: int) -> list[str]:
        d = self.d
        fx = self._fx_tag(w, h)
        out = []
        for g in self._groups(segments):
            words = [(x["w"], x["e"] - x["s"]) for x in g["chunk"]]
            text = " ".join(x["w"] for x in g["chunk"]).strip()
            if not text:
                continue
            if d["uppercase"]:
                text = text.upper()
            text = text.replace("{", "(").replace("}", "")
            body = _wrap(text, int(d["max_line_chars"]))
            if d["effect"] == "karaoke":
                parts = []
                for wd, dur in words:
                    parts.append("{\\k" + str(max(1, round(dur * 100))) + "}" +
                                 wd.upper())
                body = _wrap(" ".join(parts).replace(" ", "", 0),
                             999)  # keep \k tags intact
                body = " ".join(p for p in parts)
                body = body.replace("{\\k", "{\\k")  # noop guard
            out.append(f"Dialogue: 0,{_ts(g['s'])},{_ts(g['e'])},Cap,,0,0,0,,"
                       f"{fx}{body}")
        return out

    def write_ass(self, segments: list[dict], path: str, w: int, h: int):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._header(w, h) +
                    "\n".join(self.dialogues(segments, w, h)) + "\n")
