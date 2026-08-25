from __future__ import annotations
import glob
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile

from . import beats as beatmod
from . import reframe
from .config import DATA_DIR
from .utils import (esc_drawtext, ff_filter_path, has_nvenc, pick_encoder,
                    probe_dims, resolve_bin, run)

GRADES = {
    "none": "",
    "capcut": "eq=saturation=1.22:contrast=1.06:brightness=0.01,"
              "unsharp=5:5:0.6:5:5:0.0",
    "cinematic": "curves=r='0/0.02 0.5/0.53 1/0.99'"
                 ":g='0/0.01 0.5/0.5 1/0.99'"
                 ":b='0/0.05 0.5/0.48 1/0.95',"
                 "colorbalance=rs=-0.06:bs=0.09:rm=0.02:bm=-0.04,"
                 "eq=saturation=0.92:contrast=1.08",
    "noir": "hue=s=0,eq=contrast=1.22:brightness=-0.03,unsharp=5:5:0.8",
    "vhs": "eq=saturation=1.18:contrast=0.96,colorbalance=rs=0.07:bs=-0.06,"
           "chromashift=rh=5:bh=-5,noise=alls=12:allf=t,gblur=sigma=0.6",
}

ENHANCE_LIGHT = ("hqdn3d=1.5:1.5:6:6,"
                 "cas=strength=0.5,"
                 "eq=saturation=1.05:contrast=1.02")

# ---- Heavy (neural) enhancement -------------------------------------------
ESRGAN_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
              "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip")


def _esrgan_exe() -> str | None:
    root = os.path.join(DATA_DIR, "bin", "realesrgan")
    hits = glob.glob(os.path.join(root, "**", "realesrgan-ncnn-vulkan.exe"),
                     recursive=True)
    return hits[0] if hits else None


def _ensure_esrgan(reporter) -> str:
    exe = _esrgan_exe()
    if exe:
        return exe
    reporter.log("first-time setup: downloading AI engine (~65 MB, one time)...")
    import tempfile
    root = os.path.join(DATA_DIR, "bin", "realesrgan")
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), "hc_esrgan.zip")
    urllib.request.urlretrieve(ESRGAN_URL, tmp)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(root)
    try:
        os.remove(tmp)
    except OSError:
        pass
    exe = _esrgan_exe()
    if not exe:
        raise RuntimeError("AI engine download failed - check internet.")
    reporter.log("AI engine ready")
    return exe


def _enhance_heavy(plan: dict, reporter) -> str | None:
    """Neural frame-by-frame upscale. Returns path to enhanced clip segment."""
    src = plan["src"]
    start, dur = float(plan["start"]), float(plan["dur"])
    fps, W, H = int(plan["fps"]), int(plan["W"]), int(plan["H"])
    work = os.path.dirname(plan["dest"])
    fin = os.path.join(work, "enhanced.mp4")
    if os.path.isfile(fin) and os.path.getsize(fin) > 0:
        return fin

    exe = _ensure_esrgan(reporter)
    fin_dir = os.path.join(work, "f_in")
    fout_dir = os.path.join(work, "f_out")
    for d in (fin_dir, fout_dir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    # extract frames at HALF target size (upscale 2x next -> exact target)
    half_w, half_h = max(160, W // 2 // 2 * 2), max(90, H // 2 // 2 * 2)
    vf: list[str] = []
    if plan.get("aspect") != "16:9":
        try:
            sw, sh = probe_dims(src)
            cw, ch = reframe.write_sendcmd(src, start, dur, sw, sh,
                                           plan["aspect"],
                                           plan.get("sendcmd")
                                           or os.path.join(work, "_he_cmd.txt"))
            vf.append(f"sendcmd=f={ff_filter_path(plan.get('sendcmd')
                                                 or os.path.join(work, '_he_cmd.txt'))}")
            vf.append(f"crop={cw}:{ch}:x='(iw-ow)/2':y=(ih-oh)/2")
        except Exception:
            ar = {"9:16": 9 / 16, "1:1": 1.0}.get(plan["aspect"], 16 / 9)
            cw = min(sw, int(round(sh * ar)))
            vf.append(f"crop={cw}:{int(round(cw / ar))}:x='(iw-ow)/2':y=(ih-oh)/2")
    vf += [f"scale={half_w}:{half_h}:flags=lanczos", f"fps={fps}"]

    expected = max(1, int(dur * fps))
    reporter.log(f"AI enhance: extracting {expected} frames "
                 f"(~{(expected * 0.0006):.1f} GB temp disk)...")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error",
         "-hwaccel", "cuda",
         "-ss", f"{max(0.0, start):.3f}", "-i", src, "-t", f"{dur:.3f}",
         "-vf", ",".join(vf), "-start_number", "0",
         os.path.join(fin_dir, "%06d.png")])

    reporter.log("AI enhance: running neural upscale on GPU "
                 "(the long part - watch the percentages)...")
    proc = subprocess.Popen(
        [exe, "-i", fin_dir, "-o", fout_dir,
         "-n", "realesr-animevideov3", "-s", "2", "-f", "png"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last_pct = -1
    while proc.poll() is None:
        done_n = len(glob.glob(os.path.join(fout_dir, "*.png")))
        pct = int(min(done_n / expected, 1.0) * 100)
        if pct >= last_pct + 10:
            last_pct = pct
            reporter.log(f"AI enhance {pct}%")
        time.sleep(3)
    if proc.returncode != 0:
        raise RuntimeError("neural upscaler failed (GPU/Vulkan issue?)")

    reporter.log("AI enhance: reassembling clip...")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error",
         "-framerate", str(fps), "-i", os.path.join(fout_dir, "%06d.png"),
         "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", src,
         "-map", "0:v:0", "-map", "1:a:0?",
         "-vf", f"scale={W}:{H}:flags=lanczos",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", fin])

    shutil.rmtree(fin_dir, ignore_errors=True)
    shutil.rmtree(fout_dir, ignore_errors=True)
    return fin


class Graph:
    def __init__(self):
        self.parts: list[str] = []
        self.cur = "0:v"

    def step(self, body: str, out: str | None = None):
        nxt = out or f"v{len(self.parts)}"
        self.parts.append(f"[{self.cur}]{body}[{nxt}]")
        self.cur = nxt


def _zoom_expression(punch_t: float, fps: int, punch_amp: float,
                     kicks: list[float], kick_amp: float) -> str:
    terms = [f"{punch_amp:.3f}*exp(-4*(in-{punch_t * fps:.0f})/{fps})"
             f"*gte(in,{punch_t * fps:.0f})"]
    for kt in kicks[:6]:
        terms.append(f"{kick_amp:.3f}*exp(-9*(in-{kt * fps:.0f})/{fps})"
                     f"*gte(in,{kt * fps:.0f})")
    return "min(2.4,max(1.0,1+" + "+".join(terms) + "))"


_SUB_POS = {
    "tl": "x=28:y=28",
    "tr": "x=W-w-28:y=28",
    "bl": "x=28:y=H-h-28",
    "br": "x=W-w-28:y=H-h-28",
}


def _run_ffmpeg_progress(cmd: list[str], dur: float, reporter):
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    buf = b""
    last_pct = -1
    try:
        while True:
            chunk = proc.stderr.read(256)
            if not chunk:
                break
            buf += chunk
            parts = buf.split(b"\r")
            buf = parts[-1]
            for p in parts[:-1]:
                m = re.search(rb"time=(\d+):(\d+):(\d+(?:\.\d+)?)", p)
                if m and dur > 0:
                    secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 \
                        + float(m.group(3))
                    pct = int(min(secs / dur, 1.0) * 100)
                    if pct >= last_pct + 10 or (pct == 100 and last_pct < 100):
                        last_pct = pct
                        try:
                            reporter.log(f"render {pct}%")
                        except Exception:
                            pass
        rc = proc.wait()
    finally:
        try:
            proc.stderr.close()
        except Exception:
            pass
    if rc != 0:
        raise RuntimeError(f"FFmpeg render failed (exit code {rc}). "
                           f"If this repeats, try a different Color Grade.")


def render_clip(plan: dict, reporter) -> None:
    import time as _time
    dur = float(plan["dur"])
    fps = int(plan["fps"])
    W, H = int(plan["W"]), int(plan["H"])
    g = Graph()
    music = plan.get("music") or {}
    sfx_events = plan.get("sfx_events") or []
    sub = plan.get("subscribe") or {}
    has_music = bool(music.get("file"))
    has_wm = bool(plan.get("watermark"))
    has_sub = bool(sub.get("file")) and os.path.isfile(sub["file"])
    try:
        nvidia = has_nvenc()
    except Exception:
        nvidia = False

    # ---------------- HEAVY neural enhance (runs first, pre-cut) ----------
    media = plan["src"]
    seek_start = max(0.0, float(plan["start"]))
    enhance_applied = False
    if plan.get("enhance") and plan.get("enhance_mode") == "heavy":
        t0 = _time.time()
        try:
            out = _enhance_heavy(plan, reporter)
            if out:
                media = out
                seek_start = 0.0          # enhanced file IS the cut segment
                enhance_applied = True
                reporter.log(f"AI enhance finished in "
                             f"{(_time.time() - t0) / 60:.1f} min")
        except Exception as e:  # noqa: BLE001
            reporter.log(f"heavy AI enhance failed ({e}) - "
                         f"continuing without enhancement")

    # ---------------- layout ----------------
    if plan["aspect"] != "16:9":
        src_w, src_h = probe_dims(media)
        cmd_file = plan.get("sendcmd")
        if plan["smart_reframe"] and cmd_file and not enhance_applied:
            cw, ch = reframe.write_sendcmd(media, seek_start, dur,
                                           src_w, src_h, plan["aspect"],
                                           cmd_file)
            g.step(f"sendcmd=f={ff_filter_path(cmd_file)}")
            g.step(f"crop={cw}:{ch}:x='(iw-ow)/2':y=(ih-oh)/2")
        elif not enhance_applied:
            ar = {"9:16": 9 / 16, "1:1": 1.0}[plan["aspect"]]
            cw = min(src_w, int(round(src_h * ar)))
            g.step(f"crop={cw}:{int(round(cw / ar))}:x='(iw-ow)/2':y=(ih-oh)/2")

    g.step(f"fps={fps}")

    # ---------------- motion ----------------
    kicks: list[float] = []
    punch_amp = 0.0
    if plan["zoom_punch"]:
        punch_amp = 0.25 + 0.45 * float(plan["zoom_strength"])
    if plan["beat_sync"] and plan.get("wav"):
        kicks = beatmod.strongest_beats(
            plan["wav"], 5, avoid=[plan["impact_t"]],
            window=(0.4, max(0.5, dur - 0.8)), min_gap=1.2)[:5]

    if punch_amp > 0 or kicks:
        ss = 1.6 if punch_amp > 0 else 1.25
        g.step(f"scale={int(W * ss) // 2 * 2}:-2:flags=lanczos")
        zexpr = _zoom_expression(float(plan["impact_t"]), fps, punch_amp,
                                 kicks,
                                 0.10 + 0.10 * f
