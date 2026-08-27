"""HypeClip licensing: local owner unlock + renewable trial.

All logic is local. No network calls. No third-party services.

Behavior:
  - Entering OWNER_KEY once activates permanently (saved to Data/license.json).
  - Without a key, a renewable 30-day trial starts on first launch.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

try:
    from .config import APP_VERSION as APP_VERSION
except Exception:  # pragma: no cover
    APP_VERSION = "?"
try:
    from .config import LICENSE_REQUIRED as LICENSE_REQUIRED
except Exception:  # pragma: no cover
    LICENSE_REQUIRED = False

# ---------------------------------------------------------------- keys ---
# Owner key: enter this ONCE in the app to unlock permanently.
OWNER_KEY = "HYPEC-OWNER-2026-8888"

TRIAL_DAYS = 30
_KEY_PREFIX = "HYPEC-"


def data_dir() -> Path:
    """Resolve the app's writable Data folder in every mode."""
    candidates = []
    try:
        candidates.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        candidates.append(Path.cwd())
    except Exception:
        pass
    for c in candidates:
        d = c / "Data"
        if d.is_dir():
            return d
        if c.name.lower() == "data":
            return c
    fallback = Path.cwd() / "Data"
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
    return datetime.date.today().isoformat()


def _load() -> dict:
    st = dict(DEFAULT_STATE)
    try:
        if LICENSE_FILE.is_file():
            raw = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
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
        LICENSE_FILE.write_text(json.dumps(state, indent=2),
                                encoding="utf-8")
    except Exception:
        pass


def normalize_key(raw: str) -> str:
    k = (raw or "").strip().upper().replace(" ", "")
    if k.startswith(_KEY_PREFIX.rstrip("-")):
        k = _KEY_PREFIX.rstrip("-") + "-" + k[len(_KEY_PREFIX.rstrip("-")):]
        while "--" in k:
            k = k.replace("--", "-")
    return k


def is_valid_key(key: str) -> bool:
    return normalize_key(key) == OWNER_KEY


def activate(key: str) -> dict:
    """Try to activate. Returns the resulting state dict."""
    st = _load()
    if is_valid_key(key):
        st.update({
            "mode": "owner",
            "activated_at": datetime.datetime.now().isoformat(
                timespec="seconds"),
            "key": OWNER_KEY,
        })
        _save(st)
    return st


def deactivate() -> None:
    _save(dict(DEFAULT_STATE))


def days_left() -> int:
    st = _load()
    if st.get("mode") == "owner":
        return 9999
    try:
        started = datetime.date.fromisoformat(str(st.get("started")))
    except Exception:
        started = datetime.date.today()
    left = TRIAL_DAYS - (datetime.date.today() - started).days
    return max(0, int(left))


def is_active() -> bool:
    st = _load()
    if st.get("mode") == "owner":
        return True
    # Env override kept for diagnostics only.
    if os.environ.get("HC_NO_TRIAL"):
        return False
    return days_left() > 0


def is_trial() -> bool:
    return _load().get("mode") != "owner"


def status() -> dict:
    st = _load()
    owner = st.get("mode") == "owner"
    left = days_left()
    return {
        "required": bool(LICENSE_REQUIRED),
        "active": True if owner else left > 0,
        "mode": "owner" if owner else ("trial" if left > 0 else "expired"),
        "days_left": left,
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
    """Absorbs unexpected legacy calls gracefully."""

    def __call__(self, *a, **k):
        return is_active()

    def get(self, k, d=None):
        s = status()
        lk = str(k).lower()
        for key in ("active", "mode", "days_left", "required", "version"):
            if key in lk:
                return s[key]
        return d

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return is_active()

    def __str__(self):
        return json.dumps(status())


def __getattr__(name: str):  # PEP 562 legacy net
    low = name.lower()
    if "expired" in low:
        return not is_active()
    if "valid" in low or "activ" in low or "licensed" in low:
        return is_active()
    return _Permissive()


__all__ = [
    "OWNER_KEY", "TRIAL_DAYS", "activate", "deactivate",
    "is_valid_key", "is_active", "is_trial", "days_left",
    "status", "normalize_key", "data_dir", "LICENSE_FILE",
    "check", "verify", "verify_key", "validate", "remaining_days",
    "trial_days_left", "license_state", "get_status", "state",
]
