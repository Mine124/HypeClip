"""HypeClip central configuration. Pure ASCII. Self-contained.

Defines everything the rest of the app imports from this module,
including a real Settings class, web/resource paths, and a quiet,
smarter fallback for legacy imports. No network access.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from typing import Any, Dict, Iterator, Optional
except Exception:  # very old Python shield
    Any = object

# ------------------------------------------------------------------ app ---
APP_NAME = "HypeClip Studio"
APP_VERSION = "3.9.6"
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
CLIPS_DIR = OUTPUT_DIR
BIN_DIR = DATA_DIR / "bin"
CACHE_DIR = DATA_DIR / "cache"

for _d in (WORK_DIR, OUTPUT_DIR, BIN_DIR, CACHE_DIR):
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

# Where packaged resources live (icons, sfx, fonts...). Portable layout puts
# extra files either beside the exe, inside _internal, or in Data/assets.
RESOURCE_DIR = _first_existing([
    BASE_DIR / "Resources",
    BASE_DIR / "resources",
    BASE_DIR / "Data" / "assets",
    Path(BASE_DIR),
])

# Web UI folder served by the local server.
WEB_DIR = _first_existing([
    BASE_DIR / "web",
    BASE_DIR / "ui",
    BASE_DIR / "Data" / "web",
    _MEIP / "web" if _MEIP else BASE_DIR / "web",
    BASE_DIR / "web",
])

# Legacy name other modules may import. Empty = nothing forced to bundle.
BUNDLED_ASSETS: list = []

ICON_PATH = _first_existing([BASE_DIR / "icon.ico"])[0] if False else (
    BASE_DIR / "icon.ico")

# Hugging Face models land inside our portable cache automatically.
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "0")

# -------------------------------------------------------------- defaults ---
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


# ------------------------------------------------------------- settings ----
class Settings:
    """Real settings class: dict-like, attribute-like, JSON-persistent."""

    def __init__(self, overrides: Optional[dict] = None):
        self._data: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        try:
            if SETTINGS_FILE.is_file():
                disk = json.loads(
                    SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(disk, dict):
                    self._data.update(disk)
        except Exception:
            pass
        if isinstance(overrides, dict):
            self._data.update(overrides)

    # -- persistence -----------------------------------------------------
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

    # -- dict API --------------------------------------------------------
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

    # -- attribute API ---------------------------------------------------
    def _resolve(self, key: str) -> Any:
        try:
            store = object.__getattribute__(self, "_data")
        except Exception:
            return None
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
        return self._resolve(name)

    def __repr__(self) -> str:
        return "<Settings %s>" % (", ".join(sorted(self._data)[:12])[:120])


# Friendly aliases other modules may have used over time.
AppConfig = Settings
Config = Settings


_settings_singleton: Optional[Settings] = None


def settings() -> Settings:
    global _settings_singleton
    if _settings_singleton is None:
        _settings_singleton = Settings()
    return _settings_singleton


def get_setting(key: str, default: Any = None) -> Any:
    val = settings()._resolve(key)
    return default if val is None else val


# -------------------------------------------------- tolerant legacy names ---
class _Permissive:
    """Absorbs unknown legacy imports safely.
    Callable, attribute-chainable, empty-iterable, int/float-safe."""

    def __init__(self, label: str = "?"):
        self.label = label

    def __call__(self, *a, **k):
        return _Permissive(self.label + "()")

    def __getitem__(self, k):
        return None

    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return _Permissive(self.label + "." + k)

    def __iter__(self):
        return iter(())

    def __bool__(self) -> bool:
        return True

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __fspath__(self) -> str:
        return str(DATA_DIR)

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return "<permissive:%s>" % self.label


def _fallback(name: str):
    low = name.lower()
    if "web" in low:
        return WEB_DIR
    if "resource" in low or low.endswith(("assets", "asset")):
        return RESOURCE_DIR
    if "version" in low:
        return APP_VERSION
    if low in ("name", "title", "tagline"):
        return APP_NAME
    if low == "host":
        return HOST
    if low in ("port", "listen_port", "server_port"):
        return PORT
    if low in ("settings", "prefs", "preferences", "defaults",
               "default_settings", "config_obj"):
        return settings()
    if "flag" in low:
        return FEATURE_FLAGS
    if low.endswith(("_dir", "_folder")) or "_path" in low \
            or low in ("outdir", "workdir", "cachedir"):
        for kw, target in (("out", OUTPUT_DIR), ("clip", OUTPUT_DIR),
                           ("export", OUTPUT_DIR), ("work", WORK_DIR),
                           ("bin", BIN_DIR), ("ffmpeg", BIN_DIR),
                           ("cache", CACHE_DIR)):
            if kw in low:
                return target
        return DATA_DIR
    return _Permissive(name)


def __getattr__(name: str):
    # Never intercept Python internals (stops the __path__ spam and keeps
    # the import machinery happy).
    if name.startswith("__"):
        raise AttributeError(name)
    if os.environ.get("HC_CONFIG_VERBOSE"):
        sys.stderr.write("[config] fallback import: %s\n" % name)
    return _fallback(name)


__all__ = [
    "APP_NAME", "APP_VERSION", "HOST", "PORT",
    "LICENSE_REQUIRED", "TRIAL_DAYS",
    "base_dir", "data_dir", "BASE_DIR", "DATA_DIR", "WORK_DIR",
    "OUTPUT_DIR", "CLIPS_DIR", "BIN_DIR", "CACHE_DIR",
    "RESOURCE_DIR", "WEB_DIR", "BUNDLED_ASSETS", "ICON_PATH",
    "DEFAULT_SETTINGS", "FEATURE_FLAGS", "SETTINGS_FILE",
    "Settings", "AppConfig", "Config", "settings", "get_setting",
]
