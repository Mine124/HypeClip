"""HypeClip central configuration. Pure ASCII. Self-contained.

Provides:
  - App identity and portable paths
  - A rich Settings class compatible with the whole codebase:
      Settings(), .ensure_dirs(), .work_dir/.out_dir/.cache_dir/...
  - Module-level helpers: web_dir(), resource_dir(), work_dir(), out_dir()
  - Quiet tolerant fallbacks for any legacy import (dunders excluded)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from typing import Any, Dict, Iterator, Optional
except Exception:  # pragma: no cover
    Any = object

# ------------------------------------------------------------------ app ---
APP_NAME = "HypeClip Studio"
APP_VERSION = "4.0.2"
APP_TAGLINE = "AI stream clipping studio"

HOST = "127.0.0.1"
PORT = int(os.environ.get("HC_PORT", "8500"))

# ------------------------------------------------------------- licensing ---
LICENSE_REQUIRED = False
TRIAL_DAYS = 30

# ----------------------------------------------------------------- paths ---
def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = base_dir() / "Data"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


BASE_DIR = base_dir()
DATA_DIR = data_dir()
WORK_DIR = DATA_DIR / "work"
OUTPUT_DIR = DATA_DIR / "clips"
OUT_DIR = OUTPUT_DIR          # alias kept for legacy imports
CLIPS_DIR = OUTPUT_DIR        # alias kept for legacy imports
BIN_DIR = DATA_DIR / "bin"
CACHE_DIR = DATA_DIR / "cache"

for _d in (WORK_DIR, OUTPUT_DIR, OUT_DIR, CLIPS_DIR, BIN_DIR, CACHE_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _meipass() -> Optional[Path]:
    p = getattr(sys, "_MEIPASS", None)
    return Path(p) if p else None


def _first_existing(cands):
    for c in cands:
        try:
            if c.is_dir():
                return c.resolve()
        except Exception:
            pass
    return cands[0]


_MEIP = _meipass()

RESOURCE_DIR = _first_existing([
    BASE_DIR / "Resources",
    BASE_DIR / "resources",
    BASE_DIR / "Data" / "assets",
    Path(BASE_DIR),
])

WEB_DIR = _first_existing([
    BASE_DIR / "web",
    BASE_DIR / "ui",
    BASE_DIR / "Data" / "web",
    (_MEIP / "web") if _MEIP else BASE_DIR / "web",
])

BUNDLED_ASSETS: list = []
ICON_PATH = BASE_DIR / "icon.ico"

# Hugging Face models live inside our portable cache automatically.
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "0")

# ------------------------------------------------------ defaults/settings ---
DEFAULT_SETTINGS: Dict[str, Any] = {
    "clip_count": 20,
    "clip_length": 90,
    "min_clip_length": 25,
    "max_clip_length": 180,
    "language": "en",
    "whisper_model": "small",
    "device": os.environ.get("HC_DEVICE", "auto"),
    "width": 1080,
    "height": 1920,
    "fps": 60,
    "format": "mp4",
    "captions_on": True,
    "caption_style": "karaoke",
    "skip_render": False,
    "ai_enhance": False,
    "enhance_level": "light",
    "sfx_enabled": True,
    "sfx_volume": 0.8,
    "music_volume": 0.35,
    "subscribe_sticker": True,
    "face_tracking": True,
}

FEATURE_FLAGS = {
    "editor_page": True,
    "attention_director": True,
    "critic_pass": True,
}

UPDATER_REPO_HINT = ""
SETTINGS_FILE = DATA_DIR / "settings.json"


class _SafeBlank:
    """Harmless placeholder for truly unknown attributes.
    Callable, path-like, empty-string-ish -- never crashes callers."""

    def __init__(self, label: str = "?"):
        self.label = label

    def __call__(self, *a, **k):
        return None

    def __fspath__(self) -> str:
        return str(DATA_DIR)

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter(())

    def __bool__(self) -> bool:
        return False


class Settings:
    """Rich settings object. Dict-like + attribute-like + JSON-persisted."""

    def __init__(self, overrides: Optional[dict] = None):
        self._data: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        try:
            if SETTINGS_FILE.is_file():
                disk = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(disk, dict):
                    self._data.update(disk)
        except Exception:
            pass
        if isinstance(overrides, dict):
            self._data.update(overrides)

    # ---- persistence ----
    @classmethod
    def load(cls) -> "Settings":
        return cls()

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._data, indent=2, default=str),
                encoding="utf-8")
        except Exception:
            pass

    # ---- real directories (used all over server.py) ----
    def ensure_dirs(self) -> bool:
        for d in (DATA_DIR, WORK_DIR, OUTPUT_DIR, BIN_DIR, CACHE_DIR):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        return True

    # Folder aliases as read-only properties (attribute access like
    # Settings().work_dir must return REAL paths, never None).
    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def work_dir(self) -> Path:
        return WORK_DIR

    @property
    def out_dir(self) -> Path:
        return OUTPUT_DIR

    @property
    def output_dir(self) -> Path:
        return OUTPUT_DIR

    @property
    def outdir(self) -> Path:
        return OUTPUT_DIR

    @property
    def clips_dir(self) -> Path:
        return OUTPUT_DIR

    @property
    def bin_dir(self) -> Path:
        return BIN_DIR

    @property
    def cache_dir(self) -> Path:
        return CACHE_DIR

    @property
    def resource_dir(self) -> Path:
        return RESOURCE_DIR

    @property
    def web_dir(self) -> Path:
        return WEB_DIR

    # ---- dict API ----
    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._resolve(key)

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        val = self._resolve(key)
        return default if val is None else val

    def pop(self, key: str, default: Any = None) -> Any:
        return self._data.pop(key, default)

    def update(self, other=None, **kw) -> None:
        if hasattr(other, "items"):
            for k, v in other.items():
                self._data[k] = v
        elif isinstance(other, dict):
            self._data.update(other)
        self._data.update(kw)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    # ---- internals ----
    def _resolve(self, key: str) -> Any:
        store = getattr(self, "_data", {})
        if key in store:
            return store[key]
        lk = str(key).lower()
        if lk in store:
            return store[lk]
        for k, v in store.items():
            if str(k).lower() == lk:
                return v
        return None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        val = self._resolve(name)
        if val is not None:
            return val
        if os.environ.get("HC_CONFIG_VERBOSE"):
            sys.stderr.write("[config] blank attr: %s\n" % name)
        return _SafeBlank(name)

    def __repr__(self) -> str:
        return "<Settings %d keys>" % len(getattr(self, "_data", {}))


AppConfig = Settings
Config = Settings

_singleton: Optional[Settings] = None


def settings() -> Settings:
    global _singleton
    if _singleton is None:
        _singleton = Settings()
        _singleton.ensure_dirs()
    return _singleton


def get_setting(key: str, default: Any = None) -> Any:
    return settings().get(key, default)


# ------------------------------------------- module-level helpers ----------
def web_dir() -> Path:
    """Directory served as /static. The web/ folder ships beside the exe."""
    if WEB_DIR.is_dir():
        return WEB_DIR
    alt = BASE_DIR / "web"
    if alt.is_dir():
        return alt
    try:
        alt.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return alt


def resource_dir() -> Path:
    return RESOURCE_DIR


def work_dir() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR


def out_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


outdir = out_dir
clips_dir = out_dir


# --------------------------------------------------- legacy import net -----
def _fallback(name: str):
    low = name.lower()
    if low == "settings":
        return settings()
    if "web" in low:
        return web_dir()
    if low.endswith(("resource", "resources")) or "asset" in low:
        return RESOURCE_DIR
    if "version" in low:
        return APP_VERSION
    if low in ("name", "title", "tagline"):
        return APP_NAME
    if low == "host":
        return HOST
    if low in ("port", "listen_port"):
        return PORT
    if "flag" in low:
        return FEATURE_FLAGS
    if low.endswith(("_dir", "_folder")) or "_path" in low \
            or low in ("outdir", "workdir", "cachedir", "clipsdir"):
        for kw, target in (("out", OUTPUT_DIR), ("clip", OUTPUT_DIR),
                           ("export", OUTPUT_DIR), ("work", WORK_DIR),
                           ("bin", BIN_DIR), ("ffmpeg", BIN_DIR),
                           ("cache", CACHE_DIR), ("static", web_dir()),
                           ("data", DATA_DIR)):
            if kw in low:
                return target
        return DATA_DIR
    if os.environ.get("HC_CONFIG_VERBOSE"):
        sys.stderr.write("[config] fallback import: %s\n" % name)
    return _SafeBlank(name)


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return _fallback(name)


__all__ = [
    "APP_NAME", "APP_VERSION", "HOST", "PORT",
    "LICENSE_REQUIRED", "TRIAL_DAYS",
    "base_dir", "data_dir", "BASE_DIR", "DATA_DIR",
    "WORK_DIR", "OUTPUT_DIR", "OUT_DIR", "CLIPS_DIR",
    "BIN_DIR", "CACHE_DIR", "RESOURCE_DIR", "WEB_DIR",
    "BUNDLED_ASSETS", "ICON_PATH",
    "DEFAULT_SETTINGS", "FEATURE_FLAGS", "SETTINGS_FILE",
    "Settings", "AppConfig", "Config", "settings", "get_setting",
    "web_dir", "resource_dir", "work_dir", "out_dir", "outdir", "clips_dir",
]
