from __future__ import annotations
import collections
import glob
import json
import os
import queue as _queue
import subprocess
import sys
import threading
import traceback
import urllib.parse
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import licensing as license_module
from . import pipeline, updater
from .branding import router as branding_router
from .captionstyle import DEFAULTS, CaptionStyle
from .config import APP_VERSION, DATA_DIR, RESOURCE_DIR, WEB_DIR, Settings
from .editor import router as editor_router
from .learn import router as learn_router
from .stylelearn import router as style_router
from .utils import ff_filter_path, resolve_bin, run

app = FastAPI(title="HypeClip Studio")
jobs: dict = {}
exports: dict = {}
LAST_OPTS_PATH = os.path.join(DATA_DIR, "last_options.json")
PRESET_DIR = os.path.join(DATA_DIR, "presets")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
_DL: dict = {"state": "idle", "frac": 0.0, "error": None, "path": None}
os.makedirs(PRESET_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def web_dir() -> str:
    ov = os.path.join(DATA_DIR, "web")
    return ov if os.path.isfile(os.path.join(ov, "index.html")) else WEB_DIR


class Job(pipeline.Reporter):
    def __init__(self, url: str, settings: Settings):
        self.id = uuid.uuid4().hex[:12]
        self.url, self.s = url, settings
        self.state, self.phase = "queued", "queued"
        self.title = ""
        self.frac = 0.0
        self.scan_frac = 0.0
        self.logs = collections.deque(maxlen=600)
        self.moments: list = []
        self.series = None
        self.last_series = None
        self.clips: list = []
        self.error: str | None = None
        self.media_url = ""
        self.duration = 0.0
        self.stop_evt = threading.Event()
        self._sel_q: "_queue.Queue" = _queue.Queue()
        self._cmd_q: "_queue.Queue" = _queue.Queue()

    def log(self, m): self.logs.append(str(m))

    def stage(self, n):
        n = str(n)
        if n == "scan":
            self.scan_frac = 0.0
        self.phase = n
        self.log("> " + n)

    def progress(self, f): self.frac = max(self.frac, min(float(f or 0), 1))
    def progress_scan(self, f): self.scan_frac = min(float(f or 0), 1)
    def moment(self, m): self.moments.append(m)
    def set_series(self, s): self.last_series = s
    def clip(self, c): self.clips.append(c)
    def media_ready(self, key, fname, dur):
        self.media_url = "/media/" + urllib.parse.quote(key + "/" + fname)
        self.duration = float(dur or 0)
    def review(self, moments, series):
        self.moments = moments
        if series:
            self.series = series
        self.phase = "review"

    def wait_selection(self):
        self.phase = "awaiting_selection"
        return self._sel_q.get()

    def wait_command(self):
        self.phase = "awaiting_command"
        return self._cmd_q.get()

    def snapshot(self):
        return {"id": self.id, "state": self.state, "stage": self.phase,
                "title": self.title, "progress": round(self.frac, 3),
                "scan_frac": round(self.scan_frac, 3),
                "media_url": self.media_url,
                "duration": round(self.duration, 1),
                "error": self.error, "moments": self.moments,
                "series": self.series, "clips": self.clips,
                "logs": list(self.logs)[-300:]}

    def select(self, mode: str, rect):
        if self.phase == "scan":
            self.log("ignored extra start - scan already running")
            return
        try:
            while True:
                self._sel_q.get_nowait()
        except _queue.Empty:
            pass
        self._sel_q.put({"mode": mode, "rect": rect})

    def command(self, kind: str, value=None):
        self._cmd_q.put((kind, value))


class StartReq(BaseModel):
    url: str
    options: dict = {}
    use_last: bool = False


@app.post("/api/jobs")
def start_job(req: StartReq):
    s = Settings()
    if req.use_last:
        try:
            s.update(json.load(open(LAST_OPTS_PATH, encoding="utf-8")))
        except Exception:
            pass
    cap = req.options.pop("caption", None)
    if isinstance(cap, dict):
        CaptionStyle(cap).save_active()
    s.update(req.options)
    try:
        json.dump({k: getattr(s, k) for k in (
            "mode", "max_clips", "clip_duration", "pre_roll",
            "hype_threshold", "cooldown", "max_height", "fps", "gpu",
            "workers", "aspect", "smart_reframe", "fx_look", "bloom",
            "grain", "vignette", "zoom_punch", "zoom_strength", "shake",
            "beat_sync", "flash_intro", "progress_bar", "autocaptions",
            "whisper_model", "sfx_enabled", "sfx_volume_db",
            "music_volume_db", "duck_music")},
            open(LAST_OPTS_PATH, "w", encoding="utf-8"))
    except Exception:
        pass
    job = Job(req.url.strip(), s)
    jobs[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return {"job_id": job.id}


@app.post("/api/jobs/upload")
async def start_upload_job(options: str = Form("{}"),
                           file: UploadFile = File(...)):
    s = Settings()
    try:
        s.update(json.loads(options or "{}"))
    except Exception:
        pass
    s.ensure_dirs()
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
    dest = os.path.join(UPLOAD_DIR, uuid.uuid4().hex[:10] + ext)
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if os.path.getsize(dest) < 10000:
        os.remove(dest)
        raise HTTPException(400, "uploaded file looks empty")
    s.uploaded_file = dest
    name = os.path.basename(file.filename or dest)
    job = Job(name, s)
    job.title = name
    jobs[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return {"job_id": job.id}


def _run(job: Job):
    job.state = "running"
    job.s._licensed = license_module.is_licensed()
    try:
        if job.url and job.url.startswith("http"):
            try:
                from . import youtube as yt
                job.title = yt.video_info(job.url, job.s)["title"]
            except Exception:
                pass
        pipeline.run(job.url, job.s, job, job.stop_evt)
        job.state = "stopped" if job.stop_evt.is_set() else "done"
    except Exception as e:
        job.state, job.error = "error", str(e)
        job.log("ERROR: " + str(e))
        traceback.print_exc()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    return jobs[job_id].snapshot()


@app.delete("/api/jobs/{job_id}")
def stop_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    jobs[job_id].stop_evt.set()
    jobs[job_id].state = "stopping"
    return {"ok": True}


@app.post("/api/jobs/{job_id}/select")
def job_select(job_id: str, body: dict):
    if job_id not in jobs:
        raise HTTPException(404)
    jobs[job_id].select(body.get("mode", "audio"), body.get("rect"))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/rescan")
def job_rescan(job_id: str, body: dict):
    if job_id not in jobs:
        raise HTTPException(404)
    jobs[job_id].command("rescan", body.get("threshold", 3.0))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/confirm")
def job_confirm(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    jobs[job_id].command("confirm")
    return {"ok": True}


@app.post("/api/export")
def start_export(body: dict):
    from . import platforms
    fname = os.path.basename(body.get("file", ""))
    platform = body.get("platform", "")
    if platform not in platforms.PRESETS:
        raise HTTPException(400, "unknown platform")
    src = os.path.join(Settings().out_dir, fname)
    if not os.path.isfile(src):
        raise HTTPException(404, "clip not found")
    ex = {"id": uuid.uuid4().hex[:10], "state": "running",
          "platform": platform,
          "logs": collections.deque(maxlen=100), "result": None,
          "error": None}

    class Rep:
        @staticmethod
        def log(m):
            ex["logs"].append(str(m))

    exports[ex["id"]] = ex

    def go():
        try:
            s = Settings()
            ex["result"] = platforms.export_clip(
                src, platform, s.out_dir, gpu_mode=s.gpu,
                smart_reframe=bool(body.get("smart_reframe", True)),
                workdir=s.work_dir, reporter=Rep())
            ex["state"] = "done"
        except Exception as e:
            ex["state"], ex["error"] = "error", str(e)
            Rep.log("ERROR " + str(e))
    threading.Thread(target=go, daemon=True).start()
    return {"export_id": ex["id"]}


@app.get("/api/export/{export_id}")
def get_export(export_id: str):
    ex = exports.get(export_id)
    if not ex:
        raise HTTPException(404)
    return {"id": ex["id"], "state": ex["state"],
            "platform": ex["platform"], "error": ex["error"],
            "result": ex["result"], "logs": list(ex["logs"])}


@app.post("/api/upload")
async def upload(kind: str, file: UploadFile = File(...)):
    s = Settings(); s.ensure_dirs()
    folder = {"music": s.music_dir, "watermark": s.wm_dir,
              "sfx": s.sfx_dir}.get(kind)
    if not folder:
        raise HTTPException(400, "bad kind")
    ext = os.path.splitext(file.filename or "")[1].lower()
    dest = os.path.join(folder, f"{uuid.uuid4().hex[:8]}{ext}")
    with open(dest, "wb") as f:
        f.write(await file.read())
    return {"path": dest, "name": os.path.basename(file.filename or dest)}


@app.post("/api/reveal")
def reveal(body: dict):
    path = body.get("path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(404)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)]
                         if os.path.isfile(path)
                         else ["explorer", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", path])
    return {"ok": True}


@app.post("/api/reveal_clip")
def reveal_clip(body: dict):
    path = os.path.join(Settings().out_dir,
                        os.path.basename(body.get("file", "")))
    if not os.path.isfile(path):
        raise HTTPException(404)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", path])
    return {"ok": True}


@app.get("/api/meta")
def meta():
    from .utils import has_nvenc
    return {"version": APP_VERSION, "out_dir": Settings().out_dir,
            "nvenc": has_nvenc(),
            "manifest_configured": bool(updater.MANIFEST_URL),
            "licensed": license_module.is_licensed(),
            "tier": license_module.status().get("tier", "free")}


# ------------------------- licensing -------------------------
class LicenseReq(BaseModel):
    key: str


@app.post("/api/license/activate")
def license_activate(req: LicenseReq):
    ok, msg = license_module.activate(req.key)
    return {"ok": ok, "message": msg, **license_module.status()}


@app.get("/api/license/status")
def license_status():
    return license_module.status()


@app.get("/api/download/logs")
def download_logs():
    import tempfile
    import zipfile
    zpath = os.path.join(tempfile.gettempdir(), "hypeclip_logs.zip")
    srcs = []
    for pat in ("*.log", "*.txt"):
        srcs += glob.glob(os.path.join(DATA_DIR, pat))
    with zipfile.ZipFile(zpath, "w") as z:
        for s in sorted(set(srcs)):
            try:
                z.write(s, arcname=os.path.basename(s))
            except OSError:
                pass
    return FileResponse(zpath, filename="hypeclip_logs.zip")


# ------------------------- captions -------------------------
@app.get("/api/caption/defaults")
def caption_defaults():
    return DEFAULTS


@app.post("/api/caption/preview")
def caption_preview(body: dict):
    cs = CaptionStyle(body.get("style") or {})
    w, h = 960, 540
    seg = {"start": 0.3, "end": 3.8,
           "text": "this caption style goes absolutely crazy",
           "words": [
               {"w": "this", "s": 0.30, "e": 0.55},
               {"w": "caption", "s": 0.55, "e": 0.95},
               {"w": "style", "s": 0.95, "e": 1.30},
               {"w": "goes", "s": 1.30, "e": 1.55},
               {"w": "absolutely", "s": 1.55, "e": 2.15},
               {"w": "CRAZY!", "s": 2.15, "e": 2.70},
               {"w": "wow", "s": 2.90, "e": 3.40},
           ]}
    ass = os.path.join(Settings().work_dir, "_preview.ass")
    os.makedirs(Settings().work_dir, exist_ok=True)
    cs.write_ass([seg], ass, w, h)
    out = os.path.join(Settings().out_dir, "_preview.mp4")
    cmd = [resolve_bin("ffmpeg"), "-y", "-v", "error",
           "-f", "lavfi", "-i", f"color=c=0x151a28:s={w}x{h}:d=4:r=30",
           "-vf", f"ass={ff_filter_path(ass)}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    run(cmd)
    return {"url": "/clips/" + urllib.parse.quote("_preview.mp4")
            + "?v=" + uuid.uuid4().hex[:6]}


def _preset_path(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ")[:40].strip()
    if not safe:
        raise HTTPException(400, "bad preset name")
    return os.path.join(PRESET_DIR, "cap_" + safe + ".json")


@app.get("/api/caption/presets")
def caption_presets():
    out = []
    for f in sorted(os.listdir(PRESET_DIR)):
        if f.startswith("cap_") and f.endswith(".json"):
            try:
                d = json.load(open(os.path.join(PRESET_DIR, f),
                                   encoding="utf-8"))
                out.append({"name": d.get("_name", f[4:-5])})
            except Exception:
                pass
    return out


@app.post("/api/caption/presets")
def caption_save(body: dict):
    name = body.get("name", "").strip()
    p = _preset_path(name)
    json.dump({**body.get("style", {}), "_name": name},
              open(p, "w", encoding="utf-8"), indent=1)
    return {"ok": True}


@app.delete("/api/caption/presets")
def caption_delete(name: str):
    p = _preset_path(name)
    if os.path.isfile(p):
        os.remove(p)
    return {"ok": True}


# --------------- updates / AI patch studio ---------------
@app.get("/api/update/files")
def update_files():
    return [{"path": p} for p in updater.module_list()]


@app.get("/api/update/file")
def update_file(path: str):
    try:
        return {"path": path, "code": updater.read_module(path)}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/update/validate")
def update_validate(body: dict):
    err = updater.validate_code(body.get("code", "")) \
        if (body.get("path", "") or "x").endswith(".py") else None
    return {"ok": err is None, "error": err}


@app.post("/api/update/apply")
def update_apply(body: dict):
    try:
        bak = updater.apply_code(body.get("path", ""), body.get("code", ""),
                                 reporter=lambda m: print(m, flush=True))
        return {"ok": True, "backup": bak}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/update/apply_many")
def update_apply_many(body: dict):
    try:
        done = updater.apply_many(body.get("text", ""),
                                  reporter=lambda m: print(m, flush=True))
        return {"ok": True, "files": done}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/update/backups")
def update_backups():
    return updater.list_backups()


@app.post("/api/update/restore")
def update_restore(body: dict):
    try:
        updater.restore_backup(body.get("name", ""))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/update/check")
def update_check(body: dict = None):
    try:
        return updater.check_online((body or {}).get("url"))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/update/dl_start")
def dl_start(body: dict):
    url = body.get("url") or ""
    if not url:
        raise HTTPException(400, "missing url")
    _DL.update(state="running", frac=0.0, error=None, path=None)

    def go():
        try:
            _DL["path"] = updater.download_installer(
                url, lambda f: _DL.update(frac=f))
            _DL["state"] = "done"
        except Exception as e:
            _DL["state"], _DL["error"] = "error", str(e)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@app.get("/api/update/dl_status")
def dl_status():
    return {"state": _DL.get("state"), "frac": round(_DL.get("frac", 0), 3),
            "error": _DL.get("error")}


@app.post("/api/update/run_installer")
def run_installer():
    if not _DL.get("path"):
        raise HTTPException(400, "nothing downloaded")
    threading.Timer(1.0, updater.launch_installer_and_exit,
                    args=[_DL["path"]]).start()
    return {"ok": True}


@app.post("/api/update/apply_remote")
def apply_remote(body: dict):
    try:
        done = updater.apply_remote_files(body.get("manifest") or {})
        return {"ok": True, "files": done}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/system/restart")
def system_restart():
    threading.Timer(1.0, updater.restart_app).start()
    return {"ok": True}


app.include_router(branding_router)
app.include_router(editor_router)
app.include_router(learn_router)
app.include_router(style_router)


@app.get("/")
def index():
    return FileResponse(os.path.join(web_dir(), "index.html"))


Settings().ensure_dirs()
os.makedirs(Settings().work_dir, exist_ok=True)
app.mount("/clips", StaticFiles(directory=Settings().out_dir), name="clips")
app.mount("/media", StaticFiles(directory=Settings().work_dir), name="media")
app.mount("/static", StaticFiles(directory=web_dir()), name="static")
