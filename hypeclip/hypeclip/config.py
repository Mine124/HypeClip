"""HypeClip central configuration. Pure ASCII, no external dependencies.

Everything the pipeline needs: app identity, portable paths, default
settings, feature flags. Safe fallbacks for any module importing a
name that did not exist in older versions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ------------------------------------------------------------------ app ---
APP_NAME = "HypeClip Studio"
APP_VERSION = "3.9.5"
APP_TAGLINE = "AI stream clipping studio"

HOST = "127.0.0.1"
PORT = int(os.environ.get("HC_PORT", "8500"))

# ------------------------------------------------------------- licensing ---
# Owner unlocks permanently; everyone else gets the local trial handled by
# hypeclip/licensing.py. Nothing here forces activation.
LICENSE_REQUIRED = False
TRIAL_DAYS = 30

# ----------------------------------------------------------------- paths ---
def base_dir() -> Path:
    """Folder the frozen exe lives in (or project root when running raw)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = base_dir() / "Data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = data_dir()
WORK_DIR = DATA_DIR / "work"
OUTPUT_DIR = DATA_DIR / "clips"
BIN_DIR = DATA_DIR / "bin"
CACHE_DIR = DATA_DIR / "cache"

for _d in (WORK_DIR, OUTPUT_DIR, BIN_DIR, CACHE_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# Hugging Face models land inside our portable cache automatically.
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# -------------------------------------------------------------- defaults ---
DEFAULT_SETTINGS = {
    # general
    "clip_count": 20,
    "clip_length": 90,
    "min_clip_length": 25,
    "max_clip_length": 180,
    "language": "en",
    "whisper_model": "small",
    "device": os.environ.get("HC_DEVICE", "auto"),
    # export format
    "width": 1080,
    "height": 1920,
    "fps": 60,
    "format": "mp4",
    # toggles
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

# ------------------------------------------------------ tolerant fallback ---
def _fallback(name: str):
    """Return something sane for unknown legacy imports instead of crashing."""
    sys.stderr.write("[config] fallback import: %s\n" % name)
    low = name.lower()
    if low in ("settings", "prefs", "preferences", "defaults"):
        return DEFAULT_SETTINGS
    if low in ("feature_flags", "flags"):
        return FEATURE_FLAGS
    if "version" in low:
        return APP_VERSION
    if low == "port":
        return PORT
    if "url" in low or "repo" in low or "token" in low or "key" in low:
        return UPDATER_REPO_HINT
    if "required" in low or "strict" in low:
        return False
    if "path" in low or "dir" in low:
        return DATA_DIR
    return None


def __getattr__(name: str):
    return _fallback(name)


__all__ = [
    "APP_NAME", "APP_VERSION", "HOST", "PORT",
    "LICENSE_REQUIRED", "TRIAL_DAYS",
    "base_dir", "data_dir", "DATA_DIR", "WORK_DIR", "OUTPUT_DIR",
    "BIN_DIR", "CACHE_DIR",
    "DEFAULT_SETTINGS", "FEATURE_FLAGS", "UPDATER_REPO_HINT",
]
