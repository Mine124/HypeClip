"""Update engine: online manifest + in-app CODE updates (py AND web files)."""
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
WEB_OVERLAY = os.path.join(DATA_DIR, "web")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

PY_OK = (".py",)
WEB_OK = (".html", ".css", ".js")


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _live_pkg() -> str:
    import hypeclip
    return os.path.dirname(os.path.abspath(hypeclip.__file__))


def _bundled_pkg() -> str | None:
    cand = os.path.join(RESOURCE_DIR, "app_src", "hypeclip")
    return cand if os.path.isdir(cand) else None


def _seed_overlay():
    if not _is_frozen():
        return
    t = OVERLAY_ROOT
    os.makedirs(t, exist_ok=True)
    if os.path.isfile(os.path.join(t, "hypeclip", "__init__.py")):
        return
    src = _bundled_pkg()
    if not src:
        raise RuntimeError("Bundled source missing.")
    shutil.copytree(src, os.path.join(t, "hypeclip"))


def _roots(rel: str) -> tuple[str, str]:
    """Returns (view_dir, target_dir) for a rel path like 'hypeclip/fx.py'."""
    rel = rel.replace("\\", "/").lstrip("/")
    if rel.startswith("hypeclip/"):
        if _is_frozen():
            _seed_overlay()
            base_view = os.path.join(OVERLAY_ROOT, "hypeclip")
            if not os.path.isfile(os.path.join(base_view, "__init__.py")):
                base_view = _bundled_pkg() or _live_pkg()
            return base_view, os.path.join(OVERLAY_ROOT, "hypeclip")
        return _live_pkg(), _live_pkg()
    if rel.startswith("web/"):
        if _is_frozen():
            base_view = WEB_OVERLAY
            if not os.path.isfile(os.path.join(base_view, "index.html")):
                base_view = os.path.join(RESOURCE_DIR, "web")
            return base_view, WEB_OVERLAY
        return os.path.join(RESOURCE_DIR, "web"), os.path.join(RESOURCE_DIR, "web")
    raise ValueError("path must start with hypeclip/ or web/")


def safe_rel(rel: str) -> str:
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    ext = os.path.splitext(rel)[1].lower()
    ok = PY_OK if rel.startswith("hypeclip/") else \
        WEB_OK if rel.startswith("web/") else None
    if not ok or ext not in ok:
        raise ValueError("illegal module path")
    p = os.path.normpath(rel)
    if p.startswith("..") or os.path.isabs(p):
        raise ValueError("illegal module path")
    return p.replace("\\", "/")


def module_list() -> list[str]:
    seen = set()

    def walk(root, prefix):
        if not os.path.isdir(root):
            return
        for dp, _dn, fn in os.walk(root):
            if "__pycache__" in dp:
                continue
            for f in fn:
                if f.endswith(PY_OK + WEB_OK):
                    rel = prefix + os.path.relpath(
                        os.path.join(dp, f), root).replace("\\", "/")
                    seen.add(rel)

    try:
        walk(_live_pkg() if not _is_frozen() else
             (os.path.join(OVERLAY_ROOT, "hypeclip")
              if os.path.isfile(os.path.join(OVERLAY_ROOT, "hypeclip",
                                             "__init__.py"))
              else (_bundled_pkg() or _live_pkg())), "hypeclip/")
    except Exception:
        pass
    web_base = WEB_OVERLAY if _is_frozen() and \
        os.path.isfile(os.path.join(WEB_OVERLAY, "index.html")) \
        else os.path.join(RESOURCE_DIR, "web")
    walk(web_base, "web/")
    return sorted(seen)


def read_module(rel: str) -> str:
    rel = safe_rel(rel)
    view, tgt = _roots(rel)
    p = os.path.join(view, rel.split("/", 1)[1])
    if not os.path.isfile(p):
        p = os.path.join(tgt, rel.split("/", 1)[1])
    with open(p, encoding="utf-8") as f:
        return f.read()


def validate_code(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"


def _backup(rel: str, existed: bool) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = rel.replace("/", "__")
    name = f"{stamp}__{safe}"
    dst = os.path.join(BACKUP_DIR, name)
    view, tgt = _roots(rel)
    cur = os.path.join(tgt, rel.split("/", 1)[1])
    if existed and os.path.isfile(cur):
        shutil.copy2(cur, dst)
    with open(dst + ".meta.json", "w") as f:
        json.dump({"rel": rel, "existed": existed}, f)
    return name


def apply_code(rel: str, code: str, reporter=lambda m: None) -> str:
    rel = safe_rel(rel)
    if rel.endswith(".py"):
        err = validate_code(code)
        if err:
            raise ValueError(f"rejected - {err}")
    view, tgt = _roots(rel)
    sub = rel.split("/", 1)[1]
    final = os.path.join(tgt, sub)
    existed = os.path.isfile(final)
    bak = _backup(rel, existed)
    os.makedirs(os.path.dirname(final), exist_ok=True)
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
    os.replace(tmp, final)
    reporter(f"patched {rel} (backup {bak})")
    return bak


def apply_many(text: str, reporter=lambda m: None) -> list[str]:
    """Parse '=== FILE: path ===' blocks and apply each."""
    import re
    parts = re.split(r"^===\s*FILE:\s*(.+?)\s*===[ \t]*$",
                     text, flags=re.MULTILINE)
    done = []
    i = 1
    while i + 1 <= len(parts) - 1:
        rel, code = parts[i].strip(), parts[i + 1].strip("\n")
        if rel:
            apply_code(rel, code, reporter)
            done.append(rel)
        i += 2
    if not done:
        raise ValueError("No '=== FILE: path ===' blocks found.")
    return done


def list_backups() -> list[dict]:
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if not f.endswith(".meta.json"):
            continue
        name = f[:-len(".meta.json")]
        try:
            meta = json.load(open(os.path.join(BACKUP_DIR, f)))
        except Exception:
            continue
        out.append({"name": name, "module": meta.get("rel", "?"),
                    "time": name.split("__")[0],
                    "size": os.path.getsize(os.path.join(BACKUP_DIR, name))
                    if os.path.isfile(os.path.join(BACKUP_DIR, name)) else 0})
    return out


def restore_backup(name: str):
    name = os.path.basename(name)
    meta_p = os.path.join(BACKUP_DIR, name + ".meta.json")
    meta = json.load(open(meta_p))
    rel = safe_rel(meta["rel"])
    _view, tgt = _roots(rel)
    dst = os.path.join(tgt, rel.split("/", 1)[1])
    src = os.path.join(BACKUP_DIR, name)
    if meta.get("existed") and os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    elif os.path.isfile(dst):
        os.remove(dst)
    os.remove(meta_p)


def _fetch(url: str):
    return urllib.request.Request(url, headers={"User-Agent": "HypeClip-Updater"})


def check_online(url: str | None = None) -> dict:
    url = url or MANIFEST_URL
    if not url:
        return {"ok": False, "error": "No update URL configured."}
    with urllib.request.urlopen(_fetch(url), timeout=20) as r:
        m = json.loads(r.read().decode())
    latest = m.get("version", "0.0.0")
    cur_t = tuple(int(x) for x in APP_VERSION.split(".")[:3] if x.isdigit())
    new_t = tuple(int(x) for x in latest.split(".")[:3] if x.isdigit())
    return {"ok": True, "current": APP_VERSION, "latest": latest,
            "update_available": new_t > cur_t, "notes": m.get("notes", ""),
            "installer_url": m.get("installer_url", ""),
            "files": m.get("files", [])}


def download_file(url: str, dest: str, cb=None) -> str:
    with urllib.request.urlopen(_fetch(url), timeout=30) as r, \
            open(dest, "wb") as f:
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


def apply_remote_files(manifest: dict, cb=None) -> list[str]:
    done = []
    files = manifest.get("files", [])
    for i, entry in enumerate(files):
        tmp = os.path.join(tempfile.gettempdir(), f"hc_patch_{i}.py")
        download_file(entry["url"], tmp,
                      lambda f_, i=i, n=max(1, len(files)): cb and cb((i + f_) / n))
        if entry.get("sha256"):
            h = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
            if h != entry["sha256"]:
                os.remove(tmp)
                raise ValueError(f"checksum mismatch {entry['path']}")
        code = open(tmp, encoding="utf-8").read()
        apply_code(entry["path"], code)
        os.remove(tmp)
        done.append(entry["path"])
    return done


def download_installer(installer_url: str, cb=None) -> str:
    dest = os.path.join(tempfile.gettempdir(),
                        f"HypeClip-Setup-{int(time.time())}.exe")
    return download_file(installer_url, dest, cb)


def launch_installer_and_exit(path: str):
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP \
        if os.name == "nt" else 0
    subprocess.Popen([path], close_fds=True, creationflags=flags)
    os._exit(0)


def restart_app():
    cmd = [sys.executable]
    if not _is_frozen():
        cmd.append(os.path.abspath(sys.argv[0]))
    cmd += sys.argv[1:]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP \
        if os.name == "nt" else 0
    subprocess.Popen(cmd, close_fds=True, creationflags=flags)
    os._exit(0)
