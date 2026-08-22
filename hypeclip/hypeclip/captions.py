from __future__ import annotations
import os

_MODELS: dict[str, object] = {}


def device() -> str:
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def get_model(name: str):
    if name not in _MODELS:
        from faster_whisper import WhisperModel
        dev = device()
        comp = "float16" if dev == "cuda" else "int8"
        _MODELS[name] = WhisperModel(name, device=dev, compute_type=comp)
    return _MODELS[name]


def slice_wav(src: str, start: float, dur: float, out_wav: str):
    from .utils import resolve_bin, run
    run([resolve_bin("ffmpeg"), "-y", "-v", "error",
         "-ss", f"{max(0.0, start):.3f}", "-i", src, "-t", f"{dur:.3f}",
         "-vn", "-ac", "1", "-ar", "16000", out_wav])


def transcribe_audio(wav_path: str, settings, reporter, word_ts: bool = False) -> list[dict]:
    reporter.log(f"transcribing ({settings.whisper_model} on {device()})...")
    segments, _ = get_model(settings.whisper_model).transcribe(
        wav_path, beam_size=5, vad_filter=True,
        condition_on_previous_text=False, word_timestamps=word_ts)
    out = []
    for seg in segments:
        txt = (seg.text or "").strip()
        if not txt:
            continue
        item = {"start": float(seg.start), "end": float(seg.end), "text": txt}
        if word_ts and seg.words:
            item["words"] = [{"w": w.word.strip(), "s": float(w.start),
                              "e": float(w.end)} for w in seg.words if w.word.strip()]
        out.append(item)
    reporter.log(f"{len(out)} caption segments")
    return out


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{_srt_ts(s['start'])} --> {_srt_ts(s['end'])}\n{s['text']}\n\n")


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{fs},{prim},{sec},&H00000000,&H{back},-1,0,0,0,100,100,0,0,{bs},{ol},{sh},2,70,70,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap(text: str, limit: int = 38) -> str:
    if len(text) <= limit:
        return text
    sp = text.rfind(" ", 0, limit)
    return text[:sp] + "\\N" + text[sp + 1:] if sp != -1 else text


_STYLES = {
    "karaoke": dict(font="Arial Black", fs=.068, prim="&H00FFFFFF",
                    sec="&H0000A5FF", back="00000000", bs=1, ol=5, sh=1, mv=.13),
    "tiktok":  dict(font="Arial Black", fs=.062, prim="&H00FFFFFF",
                    sec="&H00FFFFFF", back="90000000", bs=1, ol=6, sh=2, mv=.11),
    "clean":   dict(font="Verdana",     fs=.042, prim="&H00FFFFFF",
                    sec="&H00FFFFFF", back="A0000000", bs=3, ol=3, sh=0, mv=.075),
}


def write_ass(segments, path, style: str, w: int, h: int):
    st = _STYLES.get(style, _STYLES["tiktok"])
    head = _ASS_HEADER.format(
        w=w, h=h, font=st["font"], fs=int(st["fs"] * h), prim=st["prim"],
        sec=st["sec"], back=st["back"], bs=st["bs"],
        ol=max(2, int(st["ol"] * h / 720)), sh=st["sh"], mv=int(st["mv"] * h))

    lines = []
    for s in segments:
        if style == "karaoke" and s.get("words"):
            chunks = []
            for wd in s["words"]:
                cs = max(1, int(round((wd["e"] - wd["s"]) * 100)))
                chunks.append("{\\k%d}%s" % (cs, wd["w"].upper()))
            text = " ".join(chunks)
        else:
            text = s["text"].replace("{", "(").replace("}", "").strip()
            if style in ("karaoke", "tiktok"):
                text = text.upper()
            text = _wrap(text)
        lines.append(f"Dialogue: 0,{_ass_ts(s['start'])},{_ass_ts(s['end'])},"
                     f"Cap,,0,0,0,,{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")