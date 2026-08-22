from __future__ import annotations
import hashlib
import os

AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a")


def list_sfx(sfx_dir: str) -> list[str]:
    if not os.path.isdir(sfx_dir):
        return []
    return sorted(os.path.join(sfx_dir, f) for f in os.listdir(sfx_dir)
                  if f.lower().endswith(AUDIO_EXTS))


def ensure_defaults(sfx_dir: str, reporter=None):
    if not list_sfx(sfx_dir):
        if reporter:
            reporter.log("no SFX found - synthesizing default pack...")
        from .synth import synthesize_all
        synthesize_all(sfx_dir)


def _pick(pool: list[str], prefer: str | None, seed: str) -> str:
    if prefer:
        for p in pool:
            if os.path.splitext(os.path.basename(p))[0].lower() == prefer.lower():
                return p
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(pool)
    return pool[idx]


def mix_into(video: str, events: list[dict], sfx_dir: str, vol_db: float,
             out_path: str, reporter, prefer: str | None = None) -> bool:
    from pydub import AudioSegment
    from .utils import run

    ensure_defaults(sfx_dir, reporter)
    pool = list_sfx(sfx_dir)
    if not pool:
        return False

    base = AudioSegment.from_file(video)
    for ev in events:
        eff = AudioSegment.from_file(_pick(pool, prefer, video + str(ev)))
        eff = eff.apply_gain(vol_db)
        pos = int(max(0.0, float(ev["t"])) * 1000)
        pos = min(pos, max(len(base) - len(eff) - 1, 0))
        base = base.overlay(eff, position=pos)

    tmp = out_path + ".mix.wav"
    base.export(tmp, "wav")
    run(["ffmpeg", "-y", "-i", video, "-i", tmp, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", out_path])
    os.remove(tmp)
    return True