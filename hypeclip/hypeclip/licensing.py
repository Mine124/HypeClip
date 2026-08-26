"""HypeClip licensing: local owner unlock + renewable trial.

All logic is local. No network calls. No third-party services.

Behavior:
  - Entering OWNER_KEY once activates the machine-folder permanently
    (saved to Data/license.json, survives restarts).
  - Without a key, a renewable 30-day trial starts on first launch.
  - Trial can be reset/renewed by simply entering OWNER_KEY again.

Compatibility:
  - Several friendly aliases are exposed in case server.py calls a
    differently-named function than expected.
  - A module-level __getattr__ catches any unknown attribute access
    and returns a permissive object instead of crashing.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import sys as _sys
from pathlib import Path as _Path

try:  # optional overrides from config (must all be optional!)
    from .config import APP_VERSION as _APP_VERSION
except Exception:  # pragma: no cover
    _APP_VERSION = "?"
try:
    from .config import LICENSE_REQUIRED as _LICENSE_REQUIRED
except Exception:  # pragma: no cover
    _LICENSE_REQUIRED = False

APP_VERSION = _APP_VERSION
LICENSE_REQUIRED = bool(_LICENSE_REQUIRED)

# ---------------------------------------------------------------- keys ---
# OWNER key: enter this ONCE in the app to unlock permanently.
OWNER_KEY = "HYPEC-OWNER-2026-8888"

TRIAL_DAYS = 30

_KEY_PREFIX = "HYPEC-"


def data_dir() -> _Path:
    """Resolve the app's writable Data folder in all modes."""
    candidates = []
    # Next to the executable (portable layout)
    exe_dir = None
    try:
        exe_dir = _Path(_sys.executable).resolve().parent
        candidates.append(exe_dir)
    except Exception:
        pass
    # Current working directory (debug runs / when launcher cd's first)
    try:
        candidates.append(_Path.cwd())
    except Exception:
        pass
    for c in candidates:
        d = c / "Data"
        if d.is_dir():
            return d
        if c.name.lower() == "data":
            return c
    # Fallback: create next to cwd
    fallback = (_Path.cwd() / "Data")
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return fallback


LICENSE_FILE = data_dir() / "license.json"

DEFAULT_STATE = {
    "mode": "trial",           # "owner" | "trial" | "unlicensed"
    "started": None,            # ISO date of trial start
    "activated_at": None,
    "key": "",
}


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def _load() -> dict:
    st = dict(DEFAULT_STATE)
    try:
        if LICENSE_FILE.exists():
            raw = _json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                st.update(raw)
    except Exception:
        pass
    if not st.get("started"):
        st["started"] = _today_iso()
        _save(st)
    return st


def _save(state: dict) -> None:
    try:
        LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(
            _json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def normalize_key(raw: str) -> str:
    k = (raw or "").strip().upper()
    while "-" in k:
        head, rest = k.split("-", 1)
        if head == _KEY_PREFIX.rstrip("-"):
            k = _KEY_PREFIX.rstrip("-") + "-" + rest.replace(" ", "")
            break
        # tolerate spaces around dashes anywhere
        k = "-".join(p.strip() for p in raw.strip().upper().split())
        break
    return k


def is_valid_key(key: str) -> bool:
    return normalize_key(key) == OWNER_KEY


def activate(key: str) -> dict:
    """Try to activate. Returns the resulting state dict."""
    st = _load()
    if is_valid_key(key):
        st.update({
            "mode": "owner",
            "activated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "key": OWNER_KEY,
        })
        _save(st)
        return st
    return st


def deactivate() -> None:
    _save(dict(DEFAULT_STATE))


def days_left() -> int:
    st = _load()
    if st.get("mode") == "owner":
        return 9999
    try:
        started = _dt.date.fromisoformat(str(st.get("started")))
    except Exception:
        started = _dt.date.today()
    left = TRIAL_DAYS - (_dt.date.today() - started).days
    return max(0, int(left))


def is_active() -> bool:
    st = _load()
    if st.get("mode") == "owner":
        return True
    if os.environ.get("HC_NO_TRIAL"):
        return False
    return days_left() > 0


def is_trial() -> bool:
    return _load().get("mode") != "owner"


def status() -> dict:
    st = _load()
    return {
        "required": LICENSE_REQUIRED,
        "active": is_active(),
        "mode": "owner" if st.get("mode") == "owner" else (
            "trial" if days_left() > 0 else "expired"),
        "days_left": days_left(),
        "version": APP_VERSION,
        "file": str(LICENSE_FILE),
    }


# ------------------------------------------------------- compat aliases --
check = is_valid_key
verify = is_valid_key
verify_key = is_valid_key
validate = is_valid_key
remaining_days = days_left
trial_days_left = days_left
license_state = status
get_status = status
state = status


class _Permissive:
    """Absorbs unexpected calls/attribute reads gracefully."""

    def __call__(self, *a, **k):
        return is_active()

    def get(self, k, d=None):
        return d if d is not None else _DEFAULT_VIEW(k)

    def __getattr__(self, name):
        return self

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return is_active()

    def __str__(self):
        return _json.dumps(status())


def _DEFAULT_VIEW(name: str):
    s = status()
    for key in ("active", "mode", "days_left", "required"):
        if name.lower().endswith(key) or name.lower().startswith(key):
            return s[key]
    return None


def __getattr__(name: str):  # PEP 562
    low = name.lower()
    if "expired" in low:
        return not is_active()
    if "valid" in low or "activ" in low:
        return is_active()
    return _Permissive()


__all__ = [
    "OWNER_KEY", "TRIAL_DAYS", "activate", "deactivate",
    "is_valid_key", "is_active", "is_trial", "days_left",
    "status", "normalize_key", "data_dir", "LICENSE_FILE",
    "check", "verify", "verify_key", "validate", "remaining_days",
    "trial_days_left", "license_state", "get_status", "state",
]
