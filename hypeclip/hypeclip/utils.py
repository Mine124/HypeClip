from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import threading
import unicodedata

from .config import BUNDLED_ASSETS, DATA_DIR

_BIN_CACHE: dict[str, str | None] = {}
_PATH_INJECTED = {"done": False}


def _bundled(name: str) -> str | None:
    cand = os.path.normpath(
        os.path.join(os.path.dirname(BUNDLED_ASSETS), "bin", name))
    return cand if os.path.isfile(cand) else None


def _inject_path(folder: str):
    """Make the tools folder visible to EVERYTHING: yt-dlp, subprocesses."""
    if _PATH_INJECTED["done"] or not folder:
        return
    try:
        cur = os.environ.get("PATH", "")
        if folder.lower() not in cur.lower():
            os.environ["PATH"] = folder + os.pathsep + cur
        _PATH_INJECTED["done"] = True
        print(f"[hypeclip] media tools on PATH: {folder}", flush=True)
    except Exception:
        pass


def resolve_bin(name: str) -> str:
    if name in _BIN_CACHE:
        return _BIN_CACHE[name]
    found = shutil.which(name) or _bundled(name)
    if not found and name == "ffmpeg":
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    if found:
        _inject_path(os.path.dirname(found))
        print(f"[hypeclip] using {name}: {found}", flush=True)
    _BIN_CACHE[name] = found
    if not found:
        raise RuntimeError(f"'{name}' not found on this system.")
    return found


# ---------------------------------------------------------------- self-heal
def ensure_ffmpeg() -> str:
    """Guarantee ffmpeg+ffprobe exist and are visible. Order:
    1) already resolvable (PATH / bundle)  2) Data\\bin from a previous run
    3) download a portable build once (~100 MB) into Data\\bin."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    pex = "ffprobe.exe" if os.name == "nt" else "ffprobe"

    # 1) already fine?
    try:
        p = resolve_bin("ffmpeg")
        resolve_bin("ffprobe")
        return p
    except Exception:
        pass

    # 2) fetched on a previous run?
    local = os.path.join(DATA_DIR, "bin")
    if os.path.isfile(os.path.join(local, exe)):
        _inject_path(local)
        _BIN_CACHE["ffmpeg"] = os.path.join(local, exe)
        _BIN_CACHE["ffprobe"] = os.path.join(local, pex)
        print(f"[hypeclip] using ffmpeg from Data: {_BIN_CACHE['ffmpeg']}",
              flush=True)
        return _BIN_CACHE["ffmpeg"]

    # 3) download once
    print("[hypeclip] ffmpeg not found - downloading media tools "
          "(~100 MB, one time only)...", flush=True)
    import tempfile
    import urllib.request
    import zipfile
    url = ("https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
           "ffmpeg-master-latest-win64-gpl.zip")
    tmp_zip = os.path.join(tempfile.gettempdir(), "hc_ffmpeg.zip")
    urllib.request.urlretrieve(url, tmp_zip)
    os.makedirs(local, exist_ok=True)
    got = []
    with zipfile.ZipFile(tmp_zip) as z:
        for n in z.namelist():
            b = os.path.basename(n)
            if b.lower() in ("ffmpeg.exe", "ffprobe.exe"):
                with z.open(n) as src, \
                        open(os.path.join(local, b), "wb") as dst:
                    dst.write(src.read())
                got.append(b)
    try:
        os.remove(tmp_zip)
    except Exception:
        pass
    if exe not in got:
        raise RuntimeError("ffmpeg download failed - check internet connection.")
    _inject_path(local)
    _BIN_CACHE["ffmpeg"] = os.path.join(local, exe)
    _BIN_CACHE["ffprobe"] = os.path.join(local, pex)
    print(f"[hypeclip] media tools ready: {local}", flush=True)
    return _BIN_CACHE["ffmpeg"]


def which_ffmpeg():
    ensure_ffmpeg()


def run(cmd: list[str], capture_bytes: bool = False):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=not capture_bytes)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({os.path.basename(cmd[0])}):\n"
                           f"{(proc.stderr or '')[-2000:]}")
    return proc.stdout


def probe(path: str) -> dict:
    try:
        out = run([resolve_bin("ffprobe"), "-v", "error", "-print_format",
                   "json", "-show_format", "-show_streams", path])
        return json.loads(out)
    except Exception:
        return _parse_stderr(path)


def _parse_stderr(path: str) -> dict:
    proc = subprocess.run([resolve_bin("ffmpeg"), "-hide_banner", "-i", path],
                          capture_output=True, text=True)
    txt = proc.stderr
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", txt)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    w = h = 0
    m = re.search(r"Video:.*?, (\d+)x(\d+)", txt)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
    return {"format": {"duration": dur},
            "streams": [{"width": w, "height": h}] if w else []}


def probe_duration(path: str) -> float:
    try:
        return float(probe(path)["format"]["duration"])
    except Exception:
        return 0.0


def probe_dims(path: str) -> tuple[int, int]:
    try:
        for s in probe(path).get("streams", []):
            if s.get("width"):
                return int(s["width"]), int(s["height"])
    except Exception:
        pass
    return 1280, 720


_NVENC = {"checked": False, "ok": False}


def has_nvenc() -> bool:
    if not _NVENC["checked"]:
        try:
            out = subprocess.run([resolve_bin("ffmpeg"), "-hide_banner",
                                  "-encoders"],
                                 capture_output=True, text=True).stdout
            _NVENC["ok"] = "h264_nvenc" in out
        except Exception:
            _NVENC["ok"] = False
        _NVENC["checked"] = True
    return _NVENC["ok"]


def pick_encoder(mode: str) -> list[str]:
    if mode == "off":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    if mode == "force" or (mode == "auto" and has_nvenc()):
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def ff_filter_path(p: str) -> str:
    p = os.path.abspath(p).replace("\\", "/").replace("'", r"\'")
    p = re.sub(r"^([A-Za-z]):", r"\1\\:", p)
    return f"'{p}'"


def esc_drawtext(text: str) -> str:
    for ch, rep in (("\\", "\\\\"), ("'", "\\\\'"), (":", "\\:"), ("%", "\\%")):
        text = text.replace(ch, rep)
    return text


def safe_name(s: str, maxlen: int = 48) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")
    return s[:maxlen] or "stream"


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class Lock:
    def __init__(self):
        self._m = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(self, key: str) -> threading.Lock:
        with self._m:
            return self._locks.setdefault(key, threading.Lock())
