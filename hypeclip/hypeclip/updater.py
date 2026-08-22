from __future__ import annotations
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from .config import APP_VERSION, DATA_DIR, RESOURCE_DIR

MANIFEST_URL = os.getenv("HYPECLIP_UPDATE_URL", "")
OVERLAY_ROOT = os.path.join(DATA_DIR, "app")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")


def _bundled_pkg() -> str | None:
    cand = os.path.join(RESOURCE_DIR, "app_src", "hypeclip")
    return cand if os.path.isdir(cand) else None


def _live_pkg() -> str:
    import hypeclip
    return os.path.dirname(os.path.abspath(hypeclip.__file__))


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def target_pkg_dir() -> str:
    if _is_frozen():
        os.makedirs(OVERLAY_ROOT, exist_ok=True)
        return os.path.join(OVERLAY_ROOT, "hypeclip")
    return _live_pkg()


def view_pkg_dir() -> str:
    t = target_pkg_dir()
    if os.path.isfile(os.path.join(t, "__init__.py")):
        return t
    return _bundled_pkg() or _live_pkg()


def seed_overlay():
    if not _is_frozen():
        return
    t = target_pkg_dir()
    if os.path.isfile(os.path.join(t, "__init__.py")):
        return
    src = _bundled_pkg()
    if not src:
        raise RuntimeError("Bundled source not found in this installation.")
    shutil.copytree(src, t)


def _safe_rel(rel: str) -> str:
    rel = (rel or "").strip().replace("\\", "/")
    if rel.startswith("hypeclip/"):
        rel = rel[len("hypeclip/"):]
    p = os.path.normpath(rel)
    if p.startswith("..") or os.path.isabs(p) or not p.endswith(".py"):
        raise ValueError("illegal module path")
    return p.replace("\\", "/")


def module_list() -> list:
    root = view_pkg_dir()
    out = []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), root)
                out.append("hypeclip/" + rel.replace("\\", "/"))
    return sorted(out)


def read_module(rel: str) -> str:
    rel = _safe_rel(rel)
    p = os.path.join(view_pkg_dir(), rel)
    if not os.path.isfile(p):
        p = os.path.join(target_pkg_dir(), rel)
    with open(p, encoding="utf-8") as f:
        return f.read()


def validate_code(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"


def _backup(pkg_target: str, rel: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = stamp + "_" + rel.replace("/", "__")
    dst = os.path.join(BACKUP_DIR, name)
    cur = os.path.join(pkg_target, rel)
    if os.path.isfile(cur):
        shutil.copy2(cur, dst)
    else:
        with open(dst + ".NEW", "w") as f:
            f.write("")
    return name


def apply_code(rel: str, code: str, reporter=lambda m: None) -> str:
    rel = _safe_rel(rel)
    err = validate_code(code)
    if err:
        raise ValueError(f"patch rejected - {err}")
    seed_overlay()
    tgt = target_pkg_dir()
    os.makedirs(os.path.dirname(os.path.join(tgt, rel)), exist_ok=True)
    bak = _backup(tgt, rel)
    final = os.path.join(tgt, rel)
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
    os.replace(tmp, final)
    reporter(f"patched {rel} (backup {bak})")
    return bak


def list_backups() -> list:
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        full = os.path.join(BACKUP_DIR, f)
        if "_" not in f:
            continue
        out.append({"name": f,
                    "module": f.split("_", 1)[1].replace("__", "/"),
                    "time": f.split("_")[0],
                    "size": os.path.getsize(full)})
    return out


def restore_backup(name: str):
    name = os.path.basename(name)
    src = os.path.join(BACKUP_DIR, name)
    if not os.path.isfile(src):
        raise FileNotFoundError(name)
    rel = _safe_rel(name.split("_", 1)[1].replace("__", "/"))
    tgt = target_pkg_dir()
    dst = os.path.join(tgt, rel)
    if os.path.isfile(src + ".NEW"):
        if os.path.isfile(dst):
            os.remove(dst)
        os.remove(src + ".NEW")
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "HypeClip-Updater"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".")[:3] if x.isdigit())


def check_online(url: str | None = None) -> dict:
    url = url or MANIFEST_URL
    if not url:
        return {"ok": False,
                "error": "No update URL configured - paste a manifest URL."}
    m = _fetch_json(url)
    latest = m.get("version", "0.0.0")
    return {"ok": True, "current": APP_VERSION, "latest": latest,
            "update_available": _ver_tuple(latest) > _ver_tuple(APP_VERSION),
            "notes": m.get("notes", ""), "critical": bool(m.get("critical")),
            "installer_url": m.get("installer_url", ""),
            "files": m.get("files", [])}


def download_file(url: str, dest: str, cb=None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HypeClip-Updater"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if cb and total:
                cb(got / total)
    return dest


def apply_remote_files(manifest: dict, cb=None) -> list:
    done = []
    files = manifest.get("files", [])
    for i, entry in enumerate(files):
        rel = _safe_rel(entry["path"])
        tmp = os.path.join(tempfile.gettempdir(), "hc_patch_" + str(i) + ".py")
        download_file(entry["url"], tmp,
                      lambda f, i=i, n=max(1, len(files)): cb and cb((i + f) / n))
        if entry.get("sha256"):
            h = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
            if h != entry["sha256"]:
                os.remove(tmp)
                raise ValueError(f"checksum mismatch for {rel}")
        with open(tmp, encoding="utf-8") as f:
            code = f.read()
        err = validate_code(code)
        if err:
            raise ValueError(f"{rel}: {err}")
        apply_code(rel, code)
        os.remove(tmp)
        done.append(rel)
    return done


def download_installer(installer_url: str, cb=None) -> str:
    dest = os.path.join(tempfile.gettempdir(),
                        f"HypeClip-Setup-{int(time.time())}.exe")
    return download_file(installer_url, dest, cb)


def launch_installer_and_exit(installer_path: str):
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([installer_path], close_fds=True, creationflags=flags)
    os._exit(0)


def restart_app():
    cmd = [sys.executable]
    if not _is_frozen():
        cmd.append(os.path.abspath(sys.argv[0]))
    cmd += sys.argv[1:]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, close_fds=True, creationflags=flags)
    os._exit(0)