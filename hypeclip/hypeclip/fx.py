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
                                 0.10 + 0.10 * float(plan["zoom_strength"]))
        g.step(f"zoompan=z='{zexpr}'"
               f":x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2'"
               f":d=1:s={W}x{H}:fps={fps}")
    else:
        g.step(f"scale={W}:{H}:flags=lanczos")

    sh = float(plan.get("shake") or 0)
    if sh > 0.01:
        amp = int(4 + 26 * sh)
        T = float(plan["impact_t"])
        g.step(
            f"crop=iw*0.96:ih*0.96"
            f":x='(iw-ow)/2+{amp}*exp(-2.2*abs(t-{T}))*sin(41*t)'"
            f":y='(ih-oh)/2+{amp * 0.6}*exp(-2.2*abs(t-{T}))*cos(33*t)'"
            f",scale={W}:{H}")

    # ---------------- LIGHT enhance (in-filtergraph) ----------------
    if plan.get("enhance") and plan.get("enhance_mode", "light") == "light":
        g.step(ENHANCE_LIGHT)

    # ---------------- look ----------------
    grade = GRADES.get(plan.get("look", "none"), "")
    if grade:
        g.step(grade)
    if plan.get("bloom"):
        a = g.cur
        small_w = max(160, (W // 4) // 2 * 2)
        small_h = max(90, (H // 4) // 2 * 2)
        sigma_small = max(2.0, H / 280.0)
        b = f"{a}_sm"
        c = f"{a}_blur"
        opacity = 0.28 + (0.10 if plan.get("look") == "vhs" else 0.0)
        g.parts.append(
            f"[{a}]split[{a}_o][{b}_raw];"
            f"[{b}_raw]scale={small_w}:{small_h},gblur=sigma={sigma_small},"
            f"scale={W}:{H}[{c}];"
            f"[{a}_o][{c}]blend=all_mode=screen:all_opacity={opacity}"
            f"[{a}_bl]")
        g.cur = f"{a}_bl"
    if plan.get("grain") and plan.get("look") != "vhs":
        g.step("noise=alls=7:allf=t")
    if plan.get("vignette"):
        g.step("vignette=PI/4.6")

    # ---------------- overlays ----------------
    if plan.get("flash_intro"):
        g.step("fade=t=in:st=0:d=0.16:color=white")
    for bt in kicks[:5]:
        g.step(f"fade=t=in:st={bt:.2f}:d=0.06:color=white")

    title = (plan.get("title") or "").strip()
    if title:
        alpha = ("if(lt(t,0.25),(t-0.1)/0.15,"
                 "if(lt(t,2.8),1,max(0,(3.2-t)/0.4)))")
        yexpr = f"ih*0.72-{int(H * 0.03)}*clip((t-0.15)/0.5\\,0\\,1)"
        g.step(f"drawtext=text='{esc_drawtext(title)}'"
               f":fontsize={int(H * 0.062)}:fontcolor=white"
               f":borderw={max(3, H // 200)}:bordercolor=black@0.65"
               f":x='(w-text_w)/2':y='{yexpr}':alpha='{alpha}'")
    if plan.get("progress_bar"):
        g.step("drawbox=x=0:y=ih-8:w=iw:h=8:color=black@0.35:t=fill")
        g.step(f"drawbox=x=0:y=ih-7:w='iw*clip(t/{dur:.2f}\\,0\\,1)':h=6:"
               f"color=white@0.85:t=fill")

    if has_wm:
        wmi = 1 + len(sfx_events) + (1 if has_music else 0)
        nxt = "wmov"
        g.parts.append(
            f"[{g.cur}][{wmi}:v]overlay=x=W-w-28:y=28"
            f":enable='between(t,0.4,{dur:.2f})'[{nxt}]")
        g.cur = nxt

    if has_sub:
        sii = 1 + len(sfx_events) + (1 if has_music else 0) \
            + (1 if has_wm else 0)
        t0 = float(sub.get("t0", 0.5))
        sdur = float(sub.get("dur", 4.0))
        t1 = min(dur - 0.2, t0 + sdur)
        pos = _SUB_POS.get(sub.get("pos", "br"), _SUB_POS["br"])
        amp = int(H * 0.03) + 10
        y_bob = f"+{amp}*abs(sin(2.6*(t-{t0:.2f})))"
        pos_expr = pos + y_bob
        enable = f"between(t,{t0:.2f},{t1:.2f})"
        g.parts.append(
            f"[{sii}:v]scale=iw*0.26:-1,format=rgba[simg];")
        g.parts.append(
            f"[{g.cur}][simg]overlay={pos_expr}"
            f":enable='{enable}'[subov]")
        g.cur = "subov"

    if plan.get("subs"):
        g.step(f"ass={ff_filter_path(plan['subs'])}")

    g.step("fade=t=out:st=%.2f:d=0.35" % max(0, dur - 0.4))
    g.step("format=yuv420p")

    # ---------------- audio ----------------
    aparts: list[str] = []
    labels = ["0:a"]
    for i, ev in enumerate(sfx_events):
        ms = int(max(0.0, ev["t"]) * 1000)
        aparts.append(f"[{i + 1}:a]volume={ev.get('gain_db', 0)}dB,"
                      f"adelay={ms}:all=1[e{i}]")
        labels.append(f"[e{i}]")

    base_a = "mix0"
    if len(labels) > 1:
        aparts.append("".join(labels) +
                      f"amix=inputs={len(labels)}:normalize=0[mixraw];"
                      f"[mixraw]alimiter=limit=0.95[{base_a}]")
    else:
        aparts.append(f"[0:a]anull[{base_a}]")

    final_a = "aout"
    if has_music:
        mi = 1 + len(sfx_events)
        mv = music.get("volume_db", -16.0)
        aparts.append(f"[{mi}:a]volume={mv}dB,atrim=0:{dur:.2f},"
                      f"afade=t=out:st={max(0, dur - 1.2):.2f}:d=1.2[mus]")
        if music.get("duck"):
            aparts.append(f"[{base_a}][mus]sidechaincompress="
                          f"threshold=0.04:ratio=9:attack=8:release=420[ducked];"
                          f"[ducked][mus]amix=inputs=2:normalize=0[finalm]")
        else:
            aparts.append(f"[{base_a}][mus]amix=inputs=2:normalize=0[finalm]")
    else:
        aparts.append(f"[{base_a}]anull[finalm]")
    aparts.append(f"[finalm]loudnorm=I=-14:TP=-1.5:LRA=11[{final_a}]")

    # ---------------- assemble ----------------
    fc = ";".join(g.parts) + ";" + ";".join(aparts)
    enc = pick_encoder(plan.get("encoder_mode", "auto"))
    cmd = [resolve_bin("ffmpeg"), "-y", "-hide_banner"]
    if nvidia and not enhance_applied:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-ss", f"{seek_start:.3f}", "-i", media,
            "-t", f"{dur:.3f}"]
    for ev in sfx_events:
        cmd += ["-i", ev["file"]]
    if has_music:
        cmd += ["-stream_loop", "-1", "-i", music["file"]]
    if has_wm:
        cmd += ["-loop", "1", "-i", plan["watermark"]]
    if has_sub:
        cmd += ["-loop", "1", "-i", sub["file"]]
    cmd += ["-filter_complex", fc,
            "-map", f"[{g.cur}]", "-map", f"[{final_a}]",
            *enc,
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-threads", "0",
            plan["dest"]]
    tags = []
    if any("nvenc" in x for x in enc):
        tags.append("nvenc")
    if enhance_applied:
        tags.append("ai-heavy")
    elif plan.get("enhance"):
        tags.append("ai-light")
    reporter.log(f"FX render ({plan.get('look')}"
                 + ("," + ",".join(tags) if tags else "") + ")"
                 + (" +subscribe" if has_sub else "")
                 + f" - {dur:.0f}s @ {W}x{H}{fps}")
    _run_ffmpeg_progress(cmd, dur, reporter)
