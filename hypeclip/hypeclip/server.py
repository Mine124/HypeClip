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
    threading.Thread(target=_run, args=(job,), daemon=T
