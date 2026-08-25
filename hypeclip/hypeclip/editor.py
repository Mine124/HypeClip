"""Clip editing studio: EDL save/load + FFmpeg render of edits."""
from __future__ import annotations
import collections
import glob
import os
import subprocess
import threading
import urllib.parse
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import DATA_DIR
from .utils import esc_drawtext, ff_filter_path, probe_duration, resolve_bin, run

router = APIRouter(prefix="/api/editor", tags=["editor"])
EDIT_DIR = os.path.join(DATA_DIR, "edits")
JOBS: dict = {}
os.makedirs(EDIT_DIR, exist_ok=True)

ASPECTS = {"original": None, "9:16": (1080, 1920),
           "16:9": (1920, 1080), "1:1": (1080, 1080)}


def _safe(name: str) -> str:
    n = os.path.basename(name or "")
    if not n.lower().endswith(".mp4"):
        raise HTTPException(400, "must be an .mp4 clip")
    return n


def _path(name: str) -> str:
    p = os.path.join(DATA_DIR, "output", _safe(name))
    if not os.path.isfile(p):
        raise HTTPException(404, "clip not found")
    return p


@router.get("/clips")
def list_clips():
    out_dir = os.path.join(DATA_DIR, "output")
    out = []
    for f in sorted(glob.glob(os.path.join(out_dir, "*.mp4")),
                    key=os.path.getmtime, reverse=True):
        b = os.path.basename(f)
        out.append({"file": b,
                    "url": "/clips/" + urllib.parse.quote(b),
                    "duration": round(probe_duration(f), 1)})
    return out


def _edl_path(file: str) -> str:
    return os.path.join(EDIT_DIR,
                        os.path.splitext(_safe(file))[0] + ".json")


@router.post("/save")
def save_edl(body: dict):
    file = body.get("file", "")
    edl = body.get("edl") or {}
    os.makedirs(EDIT_DIR, exist_ok=True)
    with open(_edl_path(file), "w", encoding="utf-8") as f:
        json.dump(edl, f, indent=1)
    return {"ok": True}


@router.get("/edl")
def load_edl(file: str):
    p = _edl_path(file)
    if not os.path.isfile(p):
        return {}
    return json.load(open(p, encoding="utf-8"))


class RenderReq(BaseModel):
    file: str
    edl: dict = {}


def _build_cmd(src: str, dest: str, e: dict) -> tuple[list[str], float]:
    t0 = max(0.0, float(e.get("t0", 0)))
    t1 = float(e.get("t1")) if e.get("t1") else probe_duration(src)
    t1 = min(t1, probe_duration(src))
    spd = min(max(float(e.get("speed", 1)), 0.25), 4.0)
    out_dur = (t1 - t0) / spd

    vf: list[str] = []
    tgt = ASPECTS.get(e.get("aspect", "original"))
    if tgt:
        W, H = tgt
        vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:"
                  f"flags=lanczos")
        vf.append(f"crop={W}:{H}")
    b = float(e.get("brightness", 0))
    c = float(e.get("contrast", 1))
    s = float(e.get("saturation", 1))
    if (b, c, s) != (0, 1, 1):
        vf.append(f"eq=brightness={b}:contrast={c}:saturation={s}")
    if e.get("enhance"):
        vf.append("hqdn3d=1.5:1.5:6:6,cas=strength=0.5,"
                  "eq=saturation=1.04:contrast=1.02")
    fi = float(e.get("fade_in", 0))
    fo = float(e.get("fade_out", 0))
    if fi > 0:
        vf.append(f"fade=t=in:st=0:d={fi}")
    if fo > 0:
        vf.append(f"fade=t=out:st={max(0, out_dur - fo):.2f}:d={fo}")

    for txt in (e.get("texts") or [])[:4]:
        content = (txt.get("text") or "").strip()
        if not content:
            continue
        size = int(float(txt.get("size", 56)) *
                   (tgt[1] if tgt else 1080) / 1080)
        ypos = min(max(float(txt.get("y", 80)), 2), 96)
        color = (txt.get("color") or "white").replace("#", "0x")
        vf.append(
            f"drawtext=text='{esc_drawtext(content)}'"
            f":fontsize={size}:fontcolor={color}"
            f":x='(w-text_w)/2':y='h*{ypos}/100-text_h/2'"
            f":borderw=max(3\\,(h//200)):bordercolor=black@0.7"
            f":enable='between(t,{float(txt.get('t0', 0)):.2f},"
            f"{float(txt.get('t1', out_dur)):.2f})'")

    if spd != 1.0:
        vf.append(f"setpts={1.0 / spd:.5f}*PTS")

    vol = float(e.get("volume_db", 0))
    mute = bool(e.get("mute"))
    af: list[str] = []
    if mute:
        af.append("volume=0")
    elif abs(vol) > 0.01:
        af.append(f"volume={vol}dB")
    if spd != 1.0:
        sp = spd
        while sp > 2.0:
            af.append("atempo=2.0"); sp /= 2.0
        while sp < 0.5:
            af.append("atempo=0.5"); sp *= 2.0
        af.append(f"atempo={sp:.4f}")

    cmd = [resolve_bin("ffmpeg"), "-y", "-hide_banner",
           "-ss", f"{t0:.3f}", "-i", src, "-t", f"{(t1 - t0):.3f}"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-r", "30", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "19", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", dest]
    return cmd, out_dur


@router.post("/render")
def render_edit(req: RenderReq):
    src = _path(req.file)
    edl = req.edl or {}
    if not edl:
        p = _edl_path(req.file)
        if os.path.isfile(p):
            edl = json.load(open(p, encoding="utf-8"))
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"state": "running", "logs": collections.deque(maxlen=80),
                 "result": None, "error": None}

    class Rep:
        @staticmethod
        def log(m):
            JOBS[jid]["logs"].append(str(m))

    def go():
        try:
            stem = os.path.splitext(os.path.basename(src))[0]
            dest = os.path.join(os.path.dirname(src),
                                f"{stem}_edit-{jid[:4]}.mp4")
            Rep.log("building your edit...")
            cmd, _dur = _build_cmd(src, dest, edl)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr[-500:])
            Rep.log("done!")
            JOBS[jid]["result"] = {
                "file": os.path.basename(dest),
                "url": "/clips/" + urllib.parse.quote(os.path.basename(dest)),
                "duration": round(probe_duration(dest), 1),
                "score": "", "start": ""}
            JOBS[jid]["state"] = "done"
        except Exception as ex:  # noqa: BLE001
            JOBS[jid]["state"] = "error"
            JOBS[jid]["error"] = str(ex)
    threading.Thread(target=go, daemon=True).start()
    return {"job_id": jid}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404)
    return {"state": j["state"], "error": j["error"],
            "result": j["result"], "logs": list(j["logs"])}
