"""EditDesk v2: sequence editor with effects stack, color, chroma-key,
keyframed opacity/volume, shapes/images, transitions, scopes, detection."""
from __future__ import annotations
import collections
import glob
import json
import math
import os
import subprocess
import threading
import urllib.parse
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import DATA_DIR
from .utils import esc_drawtext, ff_filter_path, probe_duration, resolve_bin, run

router = APIRouter(prefix="/api/editor", tags=["editor"])
EDIT_DIR = os.path.join(DATA_DIR, "edits")
IMPORT_DIR = os.path.join(DATA_DIR, "media")
JOBS: dict = {}
for d in (EDIT_DIR, IMPORT_DIR):
    os.makedirs(d, exist_ok=True)

ASPECTS = {"original": None, "9:16": (1080, 1920), "16:9": (1920, 1080),
           "1:1": (1080, 1080)}
CONTAINERS = {"mp4": ".mp4", "mov": ".mov", "mkv": ".mkv",
              "webm": ".webm", "gif": ".gif"}
XF_MAP = {"fade": "fade", "dissolve": "dissolve", "flash": "fadewhite",
          "wipe_left": "wipeleft", "wipe_right": "wiperight",
          "wipe_up": "wipeup", "wipe_down": "wipedown",
          "slide_left": "slideleft", "slide_right": "slideright",
          "zoom": "zoomin", "blur": "hblur", "glitch": "pixelize",
          "circle_open": "circleopen", "circle_close": "circleclose",
          "radial": "radial", "squeeze": "squeezev", "gray": "fadegrays"}


def _safe(name: str) -> str:
    n = os.path.basename(name or "")
    if not n.lower().endswith(".mp4"):
        raise HTTPException(400, "must be an .mp4 clip")
    return n


def _out(name: str) -> str:
    p = os.path.join(DATA_DIR, "output", _safe(name))
    if not os.path.isfile(p):
        raise HTTPException(404, "clip not found")
    return p


# ------------------------------------------------------------- library
@router.get("/clips")
def list_clips():
    out_dir = os.path.join(DATA_DIR, "output")
    out = []
    for f in sorted(glob.glob(os.path.join(out_dir, "*.mp4")),
                    key=os.path.getmtime, reverse=True):
        b = os.path.basename(f)
        out.append({"file": b, "url": "/clips/" + urllib.parse.quote(b),
                    "duration": round(probe_duration(f), 1)})
    return out


@router.get("/library")
def library(q: str = "", kind: str = ""):
    out = []
    for f in sorted(glob.glob(os.path.join(IMPORT_DIR, "*")),
                    key=os.path.getmtime, reverse=True):
        b = os.path.basename(f)
        if q and q.lower() not in b.lower():
            continue
        ext = os.path.splitext(b)[1].lower()
        k = ("audio" if ext in (".mp3", ".wav", ".m4a", ".ogg")
             else "image" if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")
             else "video")
        if kind and kind != k:
            continue
        out.append({"file": b, "kind": k,
                    "url": "/media_import/" + urllib.parse.quote(b),
                    "size": os.path.getsize(f)})
    return out


@router.post("/import")
async def import_media(file: UploadFile = File(...)):
    name = os.path.basename(file.filename or f"import_{uuid.uuid4().hex[:6]}")
    dest = os.path.join(IMPORT_DIR, name)
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return {"ok": True, "file": name,
            "url": "/media_import/" + urllib.parse.quote(name)}


@router.post("/shape")
def make_shape(body: dict):
    from PIL import Image, ImageDraw
    kind = body.get("kind", "circle")
    color = body.get("color", "#7C5CFF").lstrip("#")
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    S = 480
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 20
    if kind == "circle":
        d.ellipse([m, m, S - m, S - m], fill=rgb)
    elif kind == "triangle":
        d.polygon([(S // 2, m), (S - m, S - m), (m, S - m)], fill=rgb)
    elif kind == "arrow":
        d.polygon([(m, S * .42), (S * .62, S * .42), (S * .62, S * .22),
                   (S - m, S * .5), (S * .62, S * .78), (S * .62, S * .58),
                   (m, S * .58)], fill=rgb)
    elif kind == "line":
        d.rounded_rectangle([m, S * .44, S - m, S * .56], radius=S * .06,
                            fill=rgb)
    elif kind == "star":
        pts = []
        for i in range(10):
            r = S // 2 - m if i % 2 == 0 else (S // 2 - m) * .45
            import math as _m
            a = _m.pi * i / 5 - _m.pi / 2
            pts.append((S / 2 + r * _m.cos(a), S / 2 + r * _m.sin(a)))
        d.polygon(pts, fill=rgb)
    else:
        d.rounded_rectangle([m, m, S - m, S - m], radius=40, fill=rgb)
    name = f"shape_{kind}_{uuid.uuid4().hex[:5]}.png"
    img.save(os.path.join(IMPORT_DIR, name))
    return {"ok": True, "file": name,
            "url": "/media_import/" + urllib.parse.quote(name)}


@router.post("/upload_asset")
async def upload_asset(file: UploadFile = File(...)):
    return await import_media(file)


@router.get("/asset")
def asset(name: str):
    p = os.path.join(IMPORT_DIR, os.path.basename(name))
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p)


# ------------------------------------------------------------- scopes
@router.get("/scopes")
def scopes(file: str, kind: str = "histogram", t: float = 0.0):
    src = _out(file)
    vf = {"histogram": "histogram", "vectorscope": "vectorscope",
          "waveform": "waveform"}.get(kind, "histogram")
    out = os.path.join(IMPORT_DIR, f"scope_{kind}.png")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error",
         "-ss", f"{max(0, float(t)):.2f}", "-i", src, "-frames", "1",
         "-vf", vf, out])
    return {"url": "/media_import/" + urllib.parse.quote(
        os.path.basename(out))}


# ------------------------------------------------------- detection tools
@router.post("/detect_scenes")
def detect_scenes(body: dict):
    src = _out(body.get("file", ""))
    proc = subprocess.run(
        [resolve_bin("ffmpeg"), "-i", src,
         "-vf", "select='gt(scene,0.35)',metadata=print",
         "-an", "-f", "null", "-"], capture_output=True, text=True)
    times, last = [], None
    for ln in proc.stderr.splitlines():
        if "lavfi.scene_score" in ln and "=" in ln:
            try:
                last = float(ln.split("=")[-1])
            except ValueError:
                pass
        elif "pts_time" in ln and last is not None and last > 0.35:
            try:
                times.append(round(float(ln.split("pts_time:")[-1]), 2))
            except ValueError:
                pass
            last = None
    return {"cuts": times[:80]}


@router.post("/detect_silence")
def detect_silence(body: dict):
    src = _out(body.get("file", ""))
    proc = subprocess.run(
        [resolve_bin("ffmpeg"), "-i", src, "-af",
         "silencedetect=noise=-38dB:d=1.2", "-f", "null", "-"],
        capture_output=True, text=True)
    spans, start = [], None
    for ln in proc.stderr.splitlines():
        if "silence_start" in ln:
            try:
                start = float(ln.split("silence_start:")[-1])
            except ValueError:
                start = None
        elif "silence_end" in ln and start is not None:
            try:
                end = float(ln.split("silence_end:")[-1].split("|")[0])
                spans.append([round(start, 2), round(end, 2)])
            except ValueError:
                pass
            start = None
    return {"spans": spans}


@router.post("/proxy")
def make_proxy(body: dict):
    src = _out(body.get("file", ""))
    stem = os.path.splitext(os.path.basename(src))[0]
    dest = os.path.join(IMPORT_DIR, f"proxy_{stem}.mp4")
    run([resolve_bin("ffmpeg"), "-y", "-v", "error", "-hwaccel", "cuda",
         "-i", src, "-vf", "scale=640:-2", "-r", "24",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-c:a", "aac", "-b:a", "96k", dest])
    return {"url": "/media_import/" + urllib.parse.quote(
        os.path.basename(dest))}


# ------------------------------------------------------------- EDL io
def _edl_path(key: str) -> str:
    safe = "".join(c for c in key if c.isalnum() or c in "-_.")[:60]
    return os.path.join(EDIT_DIR, safe + ".json")


@router.post("/save")
def save_edl(body: dict):
    key = body.get("project") or body.get("file") or "default"
    os.makedirs(EDIT_DIR, exist_ok=True)
    with open(_edl_path(key), "w", encoding="utf-8") as f:
        json.dump(body.get("data") or {}, f, indent=1)
    return {"ok": True}


@router.get("/edl")
def load_edl(project: str = "", file: str = ""):
    p = _edl_path(project or file)
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


# ------------------------------------------------------------- render
class RenderReq(BaseModel):
    project: str = ""
    clips: list[dict] = []
    transition: dict = {}
    texts: list[dict] = []
    overlays: list[dict] = []
    music: dict = {}
    master: dict = {}
    export: dict = {}


def _seg_cmd(src: str, dest: str, c: dict, W: int, H: int, fps: int) -> None:
    """Render one normalized segment (trim/transform/effects/color/keyframes/
    chroma/text-less). Audio normalized too."""
    dur_full = probe_duration(src)
    t0 = max(0.0, float(c.get("t0", 0)))
    t1 = min(float(c.get("t1")) or dur_full, dur_full)
    if t1 - t0 < 0.2:
        raise RuntimeError(f"{os.path.basename(src)}: trim too short")
    spd = min(max(float(c.get("speed", 1)), 0.25), 4.0)

    tr = c.get("transform", {})
    vf: list[str] = []
    # crop (mask-rect)
    cr = c.get("crop") or {}
    if any(float(cr.get(k) or 0) for k in ("x", "y", "w", "h")):
        cw = int(float(cr.get("w") or 100) / 100 * 1920) or 1920
        ch = int(float(cr.get("h") or 100) / 100 * 1080) or 1080
        cx = int(float(cr.get("x") or 0) / 100 * 1920)
        cy = int(float(cr.get("y") or 0) / 100 * 1080)
        vf.append(f"crop={cw}:{ch}:{cx}:{cy}")
    # chroma key before scaling
    ck = c.get("chroma") or {}
    if ck.get("enabled"):
        col = {"green": "0x00FF00", "blue": "0x0000FF"}.get(
            ck.get("color", "green"), "0x00FF00")
        sim = min(max(float(ck.get("similarity", 0.25)), 0.01), 0.6)
        blend = min(max(float(ck.get("softness", 0.1)), 0.0), 0.5)
        vf.append(f"chromakey={col}:{sim}:{blend}")
        if ck.get("despill"):
            vf.append("despill")

    # normalize geometry first
    vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:"
              f"flags=lanczos")
    vf.append(f"crop={W}:{H}")
    vf.append(f"fps={fps}")
    vf.append("setsar=1")

    # transform
    rot = int(tr.get("rotation", 0) or 0) % 360
    if rot:
        vf.append({"90": "transpose=1", "180": "transpose=1,transpose=1",
                   "270": "transpose=2"}[str(rot)])
    fx_ = tr.get("flip")
    if fx_ in ("h", "both"):
        vf.append("hflip")
    if fx_ in ("v", "both"):
        vf.append("vflip")
    scale_f = float(tr.get("scale", 1))
    px = float(tr.get("x", 0))
    py = float(tr.get("y", 0))
    op = tr.get("opacity")
    needs_pad = (abs(px) > 0.001 or abs(py) > 0.001
                 or abs(scale_f - 1) > 0.001)
    if needs_pad or (op is not None and not c.get("kf_opacity")):
        sw = max(2, int(W * scale_f) // 2 * 2)
        sh = max(2, int(H * scale_f) // 2 * 2)
        vf.append(f"scale={sw}:{sh}:flags=lanczos")
        oexpr = f"x=(W-w)/2+{px:.0f}:y=(H-h)/2+{py:.0f}"
        if op is not None and not c.get("kf_opacity"):
            oexpr += f":format=rgba:colorchannelmixer=aa={min(max(float(op),0),1):.3f}"
        vf.append(f"overlay={oexpr}")

    # ---- effects stack ----
    st = c.get("effects", {})
    if st.get("blur"):
        vf.append(f"gblur=sigma={min(max(float(st['blur']), .1), 40)}")
    if st.get("box_blur"):
        vf.append(f"boxblur={min(int(float(st['box_blurl']) or 2),20)}")
    if st.get("sharpen"):
        amt = min(max(float(st["sharpen"]), 0), 3)
        vf.append(f"unsharp=5:5:{amt}")
    if st.get("glow"):
        vf.append("split[a][b];[b]scale=W/8:H/8,gblur=sigma=4,"
                  "scale=W:H[b2];[a][b2]blend=all_mode=screen:"
                  "all_opacity=0.35")
    if st.get("grain"):
        vf.append("noise=alls=8:allf=t")
    if st.get("pixelate"):
        px_n = max(2, int(float(st["pixelate"])))
        vf.append(f"scale=W/{px_n}:H/{px_n}:flags=neighbor,"
                  f"scale={W}:{H}:flags=neighbor")
    if st.get("mosaic"):
        mn = max(4, int(float(st["mosaic"])))
        vf.append(f"scale=W/{mn}:H/{mn}:flags=neighbor,"
                  f"scale={W}:{H}:flags=neighbor")
    if st.get("vhs"):
        vf.append("chromashift=rh=4:bh=-4,noise=alls=10:allf=t,"
                  "eq=saturation=1.15:contrast=0.97")
    if st.get("rgbsplit"):
        sft = min(max(int(float(st["rgbsplit"])), 1), 30)
        try:
            vf.append(f"rgbashift=rh={sft}:bh=-{sft}")
        except Exception:
            vf.append("chromashift=rh=%d:bh=-%d" % (sft, sft))
    if st.get("emboss"):
        vf.append("convolution='-2 -1 0 -1 1 1 0 1 2":-2 -1 0 -1 1 1 0 1 2"
                  "":-2 -1 0 -1 1 1 0 1 2":-2 -1 0 -1 1 1 0 1 2"'")

    # ---- color ----
    co = c.get("color", {})
    cc: list[str] = []
    if co.get("exposure"):
        cc.append(f"gamma={min(max(1.0 - float(co['exposure']) * 0.8,.3),2):.3f}")
    if co.get("brightness"):
        cc.append(f"eq:brightness={float(co['brightness']):.3f}"[:0] or "")
    # build one eq where possible
    eqp = {}
    for k, key in (("brightness", "brightness"), ("contrast", "contrast"),
                   ("saturation", "saturation"), ("gamma", "gamma")):
        if co.get(k):
            eqp[key] = float(co[k])
    if eqp:
        cc.append("eq=" + ":".join(f"{k}={v:.3f}" for k, v in eqp.items()))
    if co.get("vibrance"):
        cc.append(f"vibrance=intensity={min(max(float(co['vibrance']),-1),1):.2f}")
    if co.get("hue"):
        cc.append(f"hue=h={float(co['hue']):.0f}")
    if co.get("temperature") or co.get("tint"):
        rs = float(co.get("temperature", 0)) * 0.3
        bs = -rs
        gs = float(co.get("tint", 0)) * 0.2
        cc.append(f"colorbalance=rs={rs:.2f}:gs={gs:.2f}:bs={bs:.2f}")
    if co.get("lift_gamma_gain"):
        lgg = co["lift_gamma_gain"]
        cc.append("colorlevels=rimax=%.3f:gimax=%.3f:bimax=%.3f"
                  % (1 - float(lgg.get("lift", 0)) * .3,
                     1 - float(lgg.get("gain", 0)) * .3,
                     1 - float(lgg.get("gamma_", 0)) * .3))
    if co.get("whites_blacks"):
        wb = co["whites_blacks"]
        cc.append("curves=all='%s'" % " ".join(
            f"{pt[0]:.2f}/{min(max(pt[1] + float(wb.get('whites', 0)) *.1 "
            f"- float(wb.get('blacks', 0)) *.1, 0),1):.3f}"
            for pt in [(0, 0), (0.25, 0.25), (0.5, 0.5),
                       (0.75, 0.75), (1, 1)]))
    if co.get("lut_file"):
        lut = os.path.join(IMPORT_DIR, os.path.basename(co["lut_file"]))
        if os.path.isfile(lut):
            vf.append(f"lut3d=file={ff_filter_path(lut)}")
    if cc:
        joined = ",".join(x for x in cc if x)
        # eq inside chains must be plain 'eq=...' not 'eq:'
        joined = joined.replace("eq:brightness=", "eq=brightness=")
        vf.append(joined)

    # keyframed opacity via sendcmd
    kf_o = c.get("kf_opacity") or []
    if len(kf_o) >= 2:
        lines = ["1.0 colorchannelmixer aa %.3f;" % float(kf_o[0]["v"])]
        prev_t, prev_v = 0.0, float(kf_o[0]["v"])
        for k in kf_o[1:]:
            kt, kv = float(k["t"]), float(k["v"])
            steps = max(1, int((kt - prev_t) / 0.25))
            for i2 in range(1, steps + 1):
                tt = prev_t + (kt - prev_t) * i2 / steps
                vv = prev_v + (kv - prev_v) * i2 / steps
                lines.append(f"{tt:.2f} colorchannelmixer aa {vv:.3f};")
            prev_t, prev_v = kt, kv
        vf.insert(0, "format=rgba,colorchannelmixer=aa="
                     f"{prev_v:.3f},sendcmd=f=cmd"
                     )  # placeholder replaced below
        # simpler: write cmd file & prepend
        cmd_file = dest + ".cmd"
        with open(cmd_file, "w") as f2:
            f2.write("\n".join(lines))
        vf = ([f"format=rgba,colorchannelmixer=aa={float(kf_o[0]['v']):.3f}",
               f"sendcmd=f={ff_filter_path(cmd_file)}"] + vf)

    # freeze frame / reverse / speed handled via filters
    if c.get("reverse"):
        vf.append("reverse")
    if spd != 1.0:
        vf.append(f"setpts={1.0 / spd:.5f}*PTS")
    if c.get("interp60") and fps >= 60:
        vf.append("minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:vsbmc=1")

    af: list[str] = []
    au = c.get("audio", {})
    if au.get("mute") or c.get("reverse"):
        af.append("volume=0")
    if au.get("denoise"):
        af.append("afftdn")
    if au.get("voice"):
        af.append("highpass=f=85,lowpass=f=11000,afftdn=nr=12,"
                  "equalizer=f=2800:t=q:w=1:g=3")
    if au.get("bass"):
        af.append(f"bass=g={float(au['bass']):.1f}")
    if au.get("treble"):
        af.append(f"treble=g={float(au['treble']):.1f}")
    eqb = au.get("eq")
    if eqb:
        for band, gain in eqb.items():
            freq = {"low": 120, "mid": 1200, "high": 6000}.get(band)
            if freq and gain:
                af.append(f"equalizer=f={freq}:t=q:w=1:g={float(gain):.1f}")
    if au.get("compressor"):
        af.append("acompressor=threshold=0.08:ratio=4")
    if au.get("limiter"):
        af.append("alimiter=limit=0.95")
    if au.get("normalize"):
        af.append("loudnorm=I=-14:TP=-1.5")
    vol = float(au.get("volume_db", 0) or 0)
    if abs(vol) > 0.01 and not au.get("mute"):
        af.append(f"volume={vol}dB")
    pan = float(au.get("pan", 0) or 0)
    if abs(pan) > 0.02:
        gl = max(0.0, 1 - max(pan, 0))
        gr = max(0.0, 1 - max(-pan, 0))
        af.append(f"pan=stereo|c0={gl:.2f}*c0|c1={gr:.2f}*c1")
    if au.get("pitch"):
        pr = min(max(float(au["pitch"]), 0.5), 2.0)
        af.append(f"asetrate=44100*{pr:.3f},aresample=44100,atempo={1/pr:.4f}")
    fi = float(au.get("fade_in", 0) or 0)
    fo = float(au.get("fade_out", 0) or 0)
    out_len = (t1 - t0) / spd
    if fi > 0:
        af.append(f"afade=t=in:st=0:d={fi}")
    if fo > 0:
        af.append(f"afade=t=out:st={max(0, out_len - fo):.2f}:d={fo}")
    kf_v = c.get("kf_volume") or []
    if len(kf_v) >= 2:
        lines = []
        prev_t, prev_v = 0.0, float(kf_v[0]["v"])
        for k in kf_v[1:]:
            kt, kv = float(k["t"]), float(k["v"])
            steps = max(1, int((kt - prev_t) / 0.25))
            for i2 in range(1, steps + 1):
                tt = prev_t + (kt - prev_t) * i2 / steps
                vv = prev_v + (kv - prev_v) * i2 / steps
                lines.append(f"{tt:.2f} volume {vv:.2f};")
            prev_t, prev_v = kt, kv
        cmd_file = dest + ".avol.cmd"
        with open(cmd_file, "w") as f2:
            f2.write("\n".join(lines))
        af.insert(0, "volume=1:eval=frame")
        af.insert(0, f"sendcmd=f={ff_filter_path(cmd_file)}")

    fi_v = float(c.get("fade_in", 0) or 0)
    fo_v = float(c.get("fade_out", 0) or 0)
    if fi_v > 0:
        vf.append(f"fade=t=in:st=0:d={fi_v}")
    if fo_v > 0:
        vf.append(f"fade=t=out:st={max(0, out_len - fo_v):.2f}:d={fo_v}")

    cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error",
           "-ss", f"{t0:.3f}", "-i", src, "-t", f"{(t1 - t0):.3f}"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if not af and spd != 1.0:
        sp2 = spd
        tmp = []
        while sp2 > 2.0:
            tmp.append("atempo=2.0"); sp2 /= 2.0
        while sp2 < 0.5:
            tmp.append("atempo=0.5"); sp2 *= 2.0
        tmp.append(f"atempo={sp2:.4f}")
        af = tmp
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-r", str(fps), "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            dest]
    run(cmd)


@router.post("/render")
def render_seq(req: RenderReq):
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"state": "running", "logs": collections.deque(maxlen=200),
                 "result": None, "error": None}

    class Rep:
        @staticmethod
        def log(m):
            JOBS[jid]["logs"].append(str(m))
            print(f"[edit:{jid}] {m}", flush=True)

    def go():
        tmp_files: list[str] = []
        try:
            clips = req.clips or []
            if not clips:
                raise RuntimeError("sequence is empty")
            ex = req.export or {}
            aspect = ex.get("aspect", "16:9")
            W, H = ASPECTS.get(aspect) or (1920, 1080)
            fps = int(ex.get("fps", 30))
            work = os.path.join(DATA_DIR, "editwork", jid)
            os.makedirs(work, exist_ok=True)

            segs = []
            for i, c in enumerate(clips):
                Rep.log(f"segment {i + 1}/{len(clips)}…")
                seg = os.path.join(work, f"seg{i}.mp4")
                src = _out(c.get("file", ""))
                data = dict(c)
                data.pop("file", None)
                _seg_cmd(src, seg, data, W, H, fps)
                segs.append(seg)
                tmp_files.append(seg)

            # transitions
            td = min(float(req.transition.get("dur", 0)), 2.5)
            xname = XF_MAP.get(req.transition.get("type", ""), "")
            n = len(segs)
            inputs: list[str] = []
            for s in segs:
                inputs += ["-i", s]

            def dur_of(p):
                return probe_duration(p)

            fc_parts: list[str] = []
            if n == 1:
                last_v, last_a = "0:v", "0:a"
            else:
                offs, acc = [], 0.0
                for i2 in range(n):
                    acc += dur_of(segs[i2])
                    offs.append(round(acc, 3))
                cur_v, cur_a = "[0:v]", "[0:a]"
                for i2 in range(1, n):
                    off = round(offs[i2 - 1] - td * i2, 3)
                    if td > 0.05 and xname and off > 0.05:
                        nv = f"[vx{i2}]"
                        fc_parts.append(
                            f"{cur_v}[{i2}:v]xfade=transition={xname}:"
                            f"duration={td:.2f}:offset={off:.2f}{nv}")
                        na = f"[ax{i2}]"
                        fc_parts.append(
                            f"{cur_a}[{i2}:a]acrossfade=d={td:.2f}{na}")
                        cur_v, cur_a = nv, na
                    else:
                        nv = f"[cx{i2}]"
                        fc_parts.append(
                            f"{cur_v}[{i2}:v]concat=n=2:v=1:a=0{nv}")
                        na = f"[ca{i2}]"
                        fc_parts.append(
                            f"{cur_a}[{i2}:a]concat=n=2:v=1:a=1{na}")
                        cur_v, cur_a = nv, na
                last_v, last_a = cur_v, cur_a

            total_dur = sum(dur_of(s) for s in segs) - max(0, n - 1) * td

            # overlays (shapes/images) then texts
            ov_inputs = []
            oi = n
            for ov in (req.overlays or [])[:6]:
                p = os.path.join(IMPORT_DIR, os.path.basename(
                    ov.get("file", "")))
                if not os.path.isfile(p):
                    continue
                inputs += ["-i", p]
                oi += 1
                lbl = f"[ov{oi}]"
                sc = float(ov.get("scale", 30)) / 100
                xp = f"(W-w)*{min(max(float(ov.get('x',50)),0),100)/100:.3f}"
                yp = f"(H-h)*{min(max(float(ov.get('y',50)),0),100)/100:.3f}"
                fc_parts.append(
                    f"[{oi}:v]scale=iw*{sc:.3f}:-1,format=rgba{lbl}")
                nxt = f"[ovo{oi}]"
                en = ""
                if ov.get("t1"):
                    en = f":enable='between(t,{float(ov.get('t0',0)):.2f}," \
                         f"{float(ov['t1']):.2f})'"
                fc_parts.append(
                    f"[{last_v}]{lbl.replace('[','').replace(']','')}|"
                    f"{last_v}" if False else
                    f"[{last_v}][{oi}:v]overlay=x={xp}:y={yp}{en}[{nxt}]")
                last_v = nxt
                del lbl

            for tx in (req.texts or [])[:6]:
                content = (tx.get("text") or "").strip()
                if not content:
                    continue
                size = int(float(tx.get("size", 64)))
                color = (tx.get("color") or "#FFFFFF").replace("#", "0x")
                y = min(max(float(tx.get("y", 85)), 2), 98)
                extra = ""
                if tx.get("outline"):
                    extra += f":borderw=max(3\\,(h//150)):bordercolor=black"
                if tx.get("shadow"):
                    extra += ":shadowcolor=black@0.7:shadowx=3:shadowy=3"
                if tx.get("bg"):
                    extra += ":box=1:boxcolor=black@0.45:boxborderw=14"
                font = tx.get("font")
                fnt = f":font='{esc_drawtext(font)}'" if font else ""
                fc_parts.append(
                    f"[{last_v}]drawtext=text='{esc_drawtext(content)}'"
                    f":fontsize={size}:fontcolor={color}{fnt}{extra}"
                    f":x='(w-text_w)/2':y='h*{y}/100-text_h/2'"
                    f":enable='between(t,{float(tx.get('t0', 0)):.2f},"
                    f"{float(tx.get('t1', total_dur)):.2f})'[txt{oi}]")
                oi += 1
                last_v = f"[txt{oi}]"

            # music
            mus = req.music or {}
            if mus.get("file"):
                mp = os.path.join(IMPORT_DIR, os.path.basename(mus["file"]))
                if os.path.isfile(mp):
                    inputs += ["-stream_loop", "-1", "-i", mp]
                    mi = oi
                    oi += 1
                    mvdb = float(mus.get("volume_db", -14))
                    fc_parts.append(
                        f"[{mi}:a]volume={mvdb}dB,atrim=0:"
                        f"{total_dur:.2f}[mus]")
                    fc_parts.append(
                        f"[{last_a}][mus]amix=inputs=2:duration=first:"
                        f"normalize=0[mixed]")
                    last_a = "[mixed]"

            master = req.master or {}
            maf = []
            if master.get("duck"):
                pass  # ducking handled implicitly by music level
            if master.get("normalize"):
                maf.append("loudnorm=I=-14:TP=-1.5")
            if maf:
                fc_parts.append(f"{last_a}" + "".join(maf).join(["", ""]) )
                # apply via -af instead
                fc_parts.pop()
                last_af = ",".join(maf)
            else:
                last_af = ""

            fmt = (req.export.get("format") or "mp4").lower()
            ext = CONTAINERS.get(fmt, ".mp4")
            stem = "sequence_" + uuid.uuid4().hex[:5]
            dest = os.path.join(DATA_DIR, "output", stem + ext)
            is_gif = fmt == "gif"

            cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error"]
            cmd += inputs
            if fc_parts:
                cmd += ["-filter_complex", ";".join(fc_parts)]
            gif_vf = (f"fps=14,scale=480:-2:flags=lanczos,"
                      f"split[a][b];[a]palettegen[p];[b][p]paletteuse")
            if is_gif:
                cmd += ["-map", last_v, "-vf", gif_vf,
                        "-loop", "0"]
            else:
                cmd += ["-map", last_v, "-map", last_a]
                if last_af:
                    cmd += ["-af", last_af]
                hw = bool(ex.get("hardware"))
                vcodec = ex.get("codec", "h264")
                if hw:
                    cv = "h264_nvenc" if vcodec == "h264" else "hevc_nvenc"
                    cmd += ["-c:v", cv, "-preset", "p5", "-cq",
                            str(int(ex.get("crf", 19))), "-b:v", "0"]
                elif fmt == "webm":
                    cmd += ["-c:v", "libvpx-vp9", "-crf",
                            str(int(ex.get("crf", 32))),
                            "-deadline", "realtime", "-cpu-used", "5",
                            "-b:v", "0"]
                elif vcodec == "hevc":
                    cmd += ["-c:v", "libx265", "-preset", "veryfast",
                            "-crf", str(int(ex.get("crf", 22)))]
                else:
                    cmd += ["-c:v", "libx264", "-preset", "veryfast",
                            "-crf", str(int(ex.get("crf", 19)))]
                cmd += ["-c:a", "aac", "-b:a",
                        str(int(ex.get("abitrate", 192))) + "k"]
                if fmt in ("webm",):
                    cmd[-4:] = ["-c:a", "libopus", "-b:a",
                                str(int(ex.get("abitrate", 128))) + "k"]
            if ex.get("res_scale"):
                pass
            cmd += ["-t", f"{total_dur:.2f}",
                    "-movflags" if not is_gif else "-loop", "+faststart"
                    if not is_gif else "0"]
            if is_gif:
                cmd[-2:] = ["-loop", "0"]
            cmd += [dest]
            Rep.log("encoding final cut…")
            run(cmd)
            for t in tmp_files + [os.path.join(work, f) for f in
                                  glob.glob(work + "/*.cmd")]:
                try:
                    os.remove(t)
                except OSError:
                    pass
            try:
                os.rmdir(work)
            except OSError:
                pass
            JOBS[jid]["result"] = {
                "file": os.path.basename(dest),
                "url": "/clips/" + urllib.parse.quote(
                    os.path.basename(dest)),
                "duration": round(probe_duration(dest), 1),
                "score": "", "start": ""}
            JOBS[jid]["state"] = "done"
        except Exception as ex:  # noqa: BLE001
            JOBS[jid]["state"] = "error"
            JOBS[jid]["error"] = str(ex)[:400]
    threading.Thread(target=go, daemon=True).start()
    return {"job_id": jid}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404)
    return {"state": j["state"], "error": j["error"],
            "result": j["result"], "logs": list(j["logs"])}
