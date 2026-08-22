from __future__ import annotations

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


def transcribe_audio(wav_path: str, settings, reporter) -> list[dict]:
    reporter.log(f"transcribing ({settings.whisper_model} on {device()})...")
    segments, _ = get_model(settings.whisper_model).transcribe(
        wav_path, beam_size=5, vad_filter=True,
        condition_on_previous_text=False, word_timestamps=True)
    out = []
    for seg in segments:
        txt = (seg.text or "").strip()
        if not txt:
            continue
        item = {"start": float(seg.start), "end": float(seg.end), "text": txt}
        if seg.words:
            item["words"] = [{"w": w.word.strip(), "s": float(w.start),
                              "e": float(w.end)}
                             for w in seg.words if w.word.strip()]
        out.append(item)
    reporter.log(f"{len(out)} caption segments")
    return out


def write_srt(segments, path):
    def ts(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(path, "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{ts(s['start'])} --> {ts(s['end'])}\n{s['text']}\n\n")


def write_ass(segments, path, style_obj, w: int, h: int):
    style_obj.write_ass(segments, path, w, h)
