"""HypeClip configuration - v2 (hardened).

v2 enhancements over the original:
  - TYPED Settings SPEC: every setting has type, default, and bounds.
  - BLANK-PROOF ASSIGNMENT: __setattr__ coerces every write to a known
    setting. _SafeBlank placeholders, None, NaN, and garbage strings are
    converted to the field default at the SOURCE. This kills the entire
    "float() argument ... not '_SafeBlank'" bug class at its root.
  - update() is tolerant: known keys are coerced; unknown keys are kept
    (other modules may stash extras); blank unknown keys are dropped.
  - engine_* keys for the v2 hype engine are first-class settings.
  - HF cache is pinned into Data\\cache\\huggingface and symlink warnings
    silenced before any model library imports.
  - Path resolution is frozen-aware and identical for dev runs and
    PyInstaller builds.
"""
from __future__ import annotations

import os
import sys

APP_VERSION = "4.3.1"

# ------------------------------------------------------------------ paths
def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_base() -> str:
    if _frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resource_base() -> str:
    if _frozen():
        return getattr(sys, "_MEIPASS", "") or os.path.dirname(
            os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _app_base()
DATA_DIR = os.path.join(BASE_DIR, "Data")
RESOURCE_DIR = _resource_base()
WEB_DIR = os.path.join(RESOURCE_DIR, "web")
BUNDLED_ASSETS = os.path.join(DATA_DIR, "assets")
ASSETS_DIR = BUNDLED_ASSETS          # alias (some modules use either name)
BIN_DIR = os.path.join(DATA_DIR, "bin")

for _d in (DATA_DIR, BIN_DIR, ASSETS_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:
        pass

# ---- environment hardening (must run before model libraries import) ----
try:
    os.environ.setdefault(
        "HF_HOME", os.path.join(DATA_DIR, "cache", "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
except Exception:
    pass

# ============================================================ Settings spec
# name: (python type, default, (min, max) or None)
# Bool coercion also accepts "0/1/true/false/yes/no/on/off/auto".
def _S(t, d, bounds=None):
    return (t, d, bounds)


SETTINGS_SPEC = {
    # --- core job ---
    "mode":            _S(str, "auto"),
    "max_clips":       _S(int, 20, (1, 100)),
    "clip_duration":   _S(float, 90.0, (10.0, 180.0)),
    "pre_roll":        _S(float, 1.5, (0.0, 10.0)),
    "hype_threshold":  _S(float, 3.5, (0.5, 10.0)),
    "cooldown":        _S(float, 8.0, (0.0, 300.0)),
    "max_height":      _S(int, 1080, (360, 2160)),
    "fps":             _S(int, 60, (24, 120)),
    "gpu":             _S(bool, True),
    "workers":         _S(int, 3, (1, 8)),
    "aspect":          _S(str, "9:16"),
    "smart_reframe":   _S(bool, True),
    # --- look / fx ---
    "fx_look":         _S(str, "clean"),
    "bloom":           _S(bool, False),
    "grain":           _S(bool, False),
    "vignette":        _S(bool, False),
    "zoom_punch":      _S(bool, True),
    "zoom_strength":   _S(int, 20, (0, 45)),
    "shake":           _S(float, 0.3, (0.0, 1.0)),
    "beat_sync":       _S(bool, True),
    "flash_intro":     _S(bool, False),
    "progress_bar":    _S(bool, True),
    "enhance":         _S(bool, False),
    "enhance_mode":    _S(str, "light"),
    # --- audio / captions ---
    "autocaptions":    _S(bool, True),
    "whisper_model":   _S(str, "small"),
    "sfx_enabled":     _S(bool, True),
    "sfx_volume_db":   _S(float, -6.0, (-40.0, 6.0)),
    "music_volume_db": _S(float, -18.0, (-48.0, 0.0)),
    "duck_music":      _S(bool, True),
    "music_file":      _S(str, ""),
    # --- branding / overlays ---
    "watermark_file":  _S(str, ""),
    "sub_name":        _S(str, ""),
    "sub_dur":         _S(float, 3.0, (0.5, 30.0)),
    "sub_pos":         _S(str, "bottom-right"),
    "sub_when":        _S(str, "start"),
    "title_text":      _S(str, ""),
    # --- sources / wizard ---
    "uploaded_file":   _S(str, ""),
    "scan_fps":        _S(float, 6.0, (1.0, 30.0)),
    "auto_render":     _S(bool, False),
    "keep_temp":       _S(bool, False),
    "cookies_browser": _S(str, ""),
    # --- v2 hype engine (EngineConfig overrides in scan.py) ---
    "engine_fps":            _S(float, 6.0, (1.0, 30.0)),
    "engine_peak_pct":       _S(float, 92.0, (50.0, 99.9)),
    "engine_min_gap_s":      _S(float, 8.0, (0.0, 120.0)),
    "engine_merge_ioi_s":    _S(float, 4.0, (0.0, 60.0)),
    "engine_pre_s":          _S(float, 8.0, (0.0, 60.0)),
    "engine_post_s":         _S(float, 10.0, (0.0, 90.0)),
    "engine_min_dur_s":      _S(float, 12.0, (5.0, 60.0)),
    "engine_max_dur_s":      _S(float, 150.0, (20.0, 600.0)),
    "engine_diversity_ioi_s": _S(float, 10.0, (0.0, 120.0)),
    "engine_diversity_sim":  _S(float, 0.82, (0.5, 1.0)),
    # engine_weights: dict, no bounds (handled specially)
    # --- internal ---
    "_licensed":       _S(bool, False),
}

SETTINGS_DEFAULTS = {k: v[1] for k, v in SETTINGS_SPEC.items()}


# ------------------------------------------------------------- coercion
def _is_blank(v) -> bool:
    if v is None:
        return True
    try:
        cls_name = type(v).__name__ or ""
        if "SafeBlank" in cls_name or cls_name.startswith("_Safe"):
            return True
    except Exception:
        pass
    if isinstance(v, float) and v != v:          # NaN
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _coerce_bool(v, default):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on", "auto"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return bool(default)


def _coerce(v, t, default, bounds):
    """Coerce any incoming value (including blanks) to (type, default)."""
    if t is bool:
        return _coerce_bool(v, default)
    if _is_blank(v):
        return default
    try:
        if t is int:
            f = float(str(v).strip())
            out = int(round(f))
        elif t is float:
            out = float(str(v).strip())
        elif t is str:
            out = str(v)
        elif t is dict:
            return dict(v) if isinstance(v, dict) else default
        else:
            out = v
    except Exception:
        return default
    if isinstance(out, float) and out != out:    # NaN
        return default
    if bounds and t in (int, float):
        out = max(bounds[0], min(bounds[1], out))
    return out


# ================================================================ Settings
class Settings:
    """Typed, blank-proof, bounds-checked settings object.

    Assignment to any known field is coerced on write; reading a known
    field that was never set returns its default. Unknown attributes are
    allowed (other modules stash extras) and reading one raises
    AttributeError normally.
    """

    def __init__(self, **initial):
        object.__setattr__(self, "_values", {})
        for k, (t, d, b) in SETTINGS_SPEC.items():
            self._values[k] = d
        if initial:
            self.update(initial)

    # -- attribute protocol ------------------------------------------------
    def __getattr__(self, name):
        vals = object.__getattribute__(self, "_values")
        if name in vals:
            return vals[name]
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        spec = SETTINGS_SPEC.get(name)
        if spec is not None:
            t, d, b = spec
            self._values[name] = _coerce(value, t, d, b)
            return
        if _is_blank(value):
            return                       # drop blank extras silently
        object.__setattr__(self, name, value)

    # -- public API --------------------------------------------------------
    def update(self, data: dict) -> "Settings":
        if not isinstance(data, dict):
            return self
        for k, v in data.items():
            try:
                setattr(self, k, v)      # coercion happens in __setattr__
            except Exception:
                continue
        return self

    def snapshot(self) -> dict:
        """Typed dict of every known setting (for last_options.json)."""
        return dict(self._values)

    def ensure_dirs(self) -> "Settings":
        for d in (self.out_dir, self.work_dir, self.music_dir,
                  self.wm_dir, self.sfx_dir,
                  os.path.join(DATA_DIR, "subs"),
                  os.path.join(DATA_DIR, "quarantine"),
                  os.path.join(DATA_DIR, "uploads"),
                  os.path.join(DATA_DIR, "presets"),
                  os.path.join(DATA_DIR, "vre"),
                  os.path.join(DATA_DIR, "backups"),
                  os.path.join(DATA_DIR, "cache", "huggingface")):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass
        try:                                  # override web UI location
            os.makedirs(os.path.join(ASSETS_DIR, "web"), exist_ok=True)
        except Exception:
            pass
        return self

    # -- directory properties ----------------------------------------------
    @property
    def out_dir(self) -> str:
        return os.path.join(DATA_DIR, "clips")

    @property
    def work_dir(self) -> str:
        return os.path.join(DATA_DIR, "work")

    @property
    def music_dir(self) -> str:
        return os.path.join(DATA_DIR, "music")

    @property
    def wm_dir(self) -> str:
        return os.path.join(DATA_DIR, "watermarks")

    @property
    def sfx_dir(self) -> str:
        return os.path.join(DATA_DIR, "sfx")

    # -- last-options persistence (optional convenience) --------------------
    def save_last(self, path: str) -> bool:
        try:
            import json
            json.dump(self.snapshot(), open(path, "w", encoding="utf-8"))
            return True
        except Exception:
            return False

    def load_last(self, path: str) -> bool:
        try:
            import json
            data = json.load(open(path, encoding="utf-8"))
            if isinstance(data, dict):
                self.update(data)
            return True
        except Exception:
            return False


# expose module-level defaults for introspection / UI schema consumers
DEFAULTS = dict(SETTINGS_DEFAULTS)
