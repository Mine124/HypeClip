"""Face-layout compositor: builds the 9:16 'facecam top, gameplay bottom'
vertical composition from a user-selected face region.

The face band is the user-drawn rectangle scaled into the top 25% of the
frame; the gameplay band is a center-crop of the full source frame
filling the remaining 75%. Output preserves the source timeline (same
start/duration), so it can drop in as a clip source with start=0.

Self-contained + guarded: any failure returns "" and the caller falls
back to normal rendering. Never raises into the pipeline.
"""
from __future__ import annotations

import os
import subprocess


def _bin(name):
    try:
        from .utils import resolve_bin
        return resolve_bin(name)
    except Exception:
        return name


def build_composite(src, start, dur, face_rect, out_path,
                    reporter=None) -> str:
    """Render src[start:start+dur] as a two-band 9:16 composite.

    face_rect: normalized (x, y, w, h) in 0..1 relative to the full frame.
    Returns out_path on success, else "". Never raises.
    """
    def log(m):
        if reporter and hasattr(reporter, "log"):
            reporter.log(str(m))
        else:
            print("[layout] " + str(m), flush=True)

    try:
        from .utils import probe_dims
        w, h = probe_dims(src)
        if not w or not h:
            return ""
        fx_, fy, fw, fh = (min(max(float(v), 0.0), 1.0)
                           for v in (face_rect[0], face_rect[1],
                                     face_rect[2], face_rect[3]))
        if fw < 0.02 or fh < 0.02:
            return ""

        out_h = 1280 if h < 1000 else 1920
        out_h += out_h % 2
        out_w = int(round(out_h * 9 / 16)) // 2 * 2
        face_h = out_h // 4 // 2 * 2
        game_h = out_h - face_h

        vf = (
            "[0:v]crop=w='iw*%(fw).4f':h='ih*%(frh).4f':"
            "x='iw*%(fx).4f':y='ih*%(fy).4f',"
            "scale=%(ow)d:%(fbh)d:force_original_aspect_ratio=increase,"
            "crop=%(ow)d:%(fbh)d,setsar=1[face];"
            "[0:v]crop=w='min(iw\\,ih*3/4)':h='ih':"
            "x='(iw-min(iw\\,ih*3/4))/2':y=0,"
            "scale=%(ow)d:%(gbh)d,setsar=1[game];"
            "[face][game]vstack=inputs=2[v]"
        ) % {"fw": fw, "frh": fh, "fx": fx_, "fy": fy,
             "ow": out_w, "fbh": face_h, "gbh": game_h}

        cmd = [_bin("ffmpeg"), "-y", "-v", "error",
               "-ss", f"{float(start):.3f}", "-t", f"{float(dur):.3f}",
               "-i", src, "-filter_complex", vf,
               "-map", "[v]", "-map", "0:a:0?",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", out_path]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           errors="replace", timeout=1800)
        ok = p.returncode == 0 and os.path.isfile(out_path) \
            and os.path.getsize(out_path) > 50000
        if not ok:
            log("composite failed: " + (p.stderr or "")[-220:])
            return ""
        return out_path
    except Exception as e:
        log("composite error: " + str(e))
        return ""
