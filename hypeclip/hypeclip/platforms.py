"""Clip export presets: any platform/resolution/fps/container on demand."""
from __future__ import annotations
import os

from .utils import (ff_filter_path, pick_encoder, probe, probe_dims,
                    probe_duration, resolve_bin, run)

PRESETS = {
    "tiktok":   dict(w=1080, h=1920, fps=60, maxrate="10000k", buf="16000k", dur=180, abps="192k", ext=".mp4"),
    "shorts":   dict(w=1080, h=1920, fps=60, maxrate="12000k", buf="18000k", dur=180, abps="192k", ext=".mp4"),
    "reels":    dict(w=1080, h=1920, fps=60, maxrate="9000k",  buf="14000k", dur=180, abps="192k", ext=".mp4"),
    "youtube":  dict(w=1920, h=1080, fps=60, maxrate="12000k", buf="20000k", dur=600, abps="192k", ext=".mp4"),
    "square":   dict(w=1080, h=1080, fps=60, maxrate="8000k",  buf="12000k", dur=600, abps="192k", ext=".mp4"),
    "hd720":    dict(w=1280, h=720,  fps=60, maxrate="6000k",  buf="9000k",  dur=600, abps="192k", ext=".mp4"),
    "sd480":    dict(w=854,  h=480,  fps=30, maxrate="2500k",  buf="4000k",  dur=600, abps="128k", ext=".mp4"),
    "webm_hd":  dict(w=1920, h=1080, fps=60, maxrate="0k",     buf="0k",     dur=600, abps="160k", ext=".webm"),
}


def _src_fps(path: str) -> float:
    try:
        for s in probe(path)["streams"]:
            if s.get("r_frame_rate"):
                num, den = s["r_frame_rate"].split("/")
                return float(num) / float(den or 1)
    except Exception:
        pass
    return 30.0


def export_clip(src: str, platform: str, out_dir: str, gpu_mode: str = "auto",
                smart_reframe: bool = True, workdir: str | None = None,
                reporter=lambda m: None) -> dict:
    p = PRESETS[platform]
    W, H = p["w"], p["h"]
    ext = p.get("ext", ".mp4")
    src_w, src_h = probe_dims(src)
    dur = probe_duration(src)
    out_dur = min(dur, float(p["dur"]))
    trimmed = dur > out_dur + 0.5

    vf: list[str] = []
    target_ar = W / H
    src_ar = src_w / src_h
    needs_crop = abs(src_ar - target_ar) > 0.02

    cmd_file = None
    if needs_crop and target_ar < 1.0 and smart_reframe:
        try:
            from . import reframe
            cmd_file = os.path.join(workdir or out_dir,
                                    f"_exp_{os.path.basename(src)}_{platform}.cmd")
            cw, ch = reframe.write_sendcmd(src, 0.0, out_dur, src_w, src_h,
                                           "9:16", cmd_file)
            vf.append(f"sendcmd=f={ff_filter_path(cmd_file)}")
            vf.append(f"crop={cw}:{ch}:x='(iw-ow)/2':y=(ih-oh)/2")
        except Exception:
            cmd_file = None
    if not cmd_file:
        if needs_crop:
            vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:"
                      f"flags=lanczos")
            vf.append(f"crop={W}:{H}")
        else:
            vf.append(f"scale={W}:{H}:flags=lanczos")

    fps = min(_src_fps(src), float(p["fps"]))
    vf.append(f"fps={fps}")
    if trimmed:
        vf.append("fade=t=out:st=%.2f:d=0.4" % max(0.0, out_dur - 0.4))

    stem = os.path.splitext(os.path.basename(src))[0].rsplit("_", 1)[0]
    dest = os.path.join(out_dir, f"{stem}_{platform}{ext}")
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(out_dir, f"{stem}_{platform}-{n}{ext}")
        n += 1

    if ext == ".webm":
        vargs = ["-c:v", "libvpx-vp9", "-deadline", "realtime",
                 "-cpu-used", "5", "-crf", "32", "-b:v", "0"]
        aargs = ["-c:a", "libopus", "-b:a", p["abps"]]
    else:
        vargs = pick_encoder(gpu_mode) + [
            "-maxrate", p["maxrate"], "-bufsize", p["buf"],
            "-profile:v", "high"]
        aargs = ["-c:a", "aac", "-b:a", p["abps"]]

    cmd = [resolve_bin("ffmpeg"), "-y", "-hide_banner", "-i", src,
           "-t", f"{out_dur:.3f}", "-vf", ",".join(vf),
           *vargs, *aargs,
           "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           "-movflags", "+faststart", dest]
    reporter(f"exporting {platform.upper()} "
             f"({W}x{H}@{int(fps)}, {ext.lstrip('.')})...")
    run(cmd)

    import urllib.parse
    return {"file": os.path.basename(dest),
            "url": "/clips/" + urllib.parse.quote(os.path.basename(dest)),
            "duration": round(probe_duration(dest), 1),
            "score": "", "start": "", "platform": platform}
