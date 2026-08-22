"""Runs before any hypeclip import.
1. portable.flag next to the exe -> all data stays in <folder>\Data
2. AI-patch overlay in Data\app shadows the bundled package."""
import os
import sys


def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _default_data_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "HypeClip")
    return os.path.dirname(os.path.abspath(__file__))


def apply_portable_mode():
    flag = os.path.join(_exe_dir(), "portable.flag")
    if not os.path.isfile(flag):
        return
    data_root = os.path.join(_exe_dir(), "Data")
    try:
        os.makedirs(data_root, exist_ok=True)
        probe = os.path.join(data_root, ".wtest")
        open(probe, "w").close()
        os.remove(probe)
    except OSError:
        print("WARN: portable folder read-only, using %LOCALAPPDATA%", flush=True)
        return
    os.environ["HYPECLIP_PORTABLE"] = "1"
    os.environ["HYPECLIP_DATA_DIR"] = data_root
    cache = os.path.join(data_root, "cache")
    os.makedirs(cache, exist_ok=True)
    os.environ.setdefault("HF_HOME", os.path.join(cache, "huggingface"))
    os.environ.setdefault("XDG_CACHE_HOME", cache)
    os.environ.setdefault("CTRANSLATE2_CACHE", os.path.join(cache, "ctranslate2"))


def apply_overlay():
    root = os.path.join(
        os.getenv("HYPECLIP_DATA_DIR") or _default_data_dir(), "app")
    if os.path.isfile(os.path.join(root, "hypeclip", "__init__.py")):
        if root not in sys.path:
            sys.path.insert(0, root)


apply_portable_mode()
apply_overlay()