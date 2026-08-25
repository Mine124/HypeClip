"""Licensing: offline-friendly license keys bound to a machine hash.
Key format: HC-XXXXX-XXXXX-XXXXX-XXXXX. Free tier = no key
(watermark + 720p cap). Machine transfers limited to 2."""
from __future__ import annotations
import hashlib
import json
import os
import uuid

from .config import DATA_DIR

LICENSE_FILE = os.path.join(DATA_DIR, "license.json")
SALT = "hypeclip.v1"


def _machine_id() -> str:
    raw = (f"{os.getenv('COMPUTERNAME', '')}-"
           f"{os.getenv('PROCESSOR_IDENTIFIER', '')}")
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Cryptography")
        raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        winreg.CloseKey(k)
    except Exception:
        pass
    return hashlib.sha256((raw + SALT).encode()).hexdigest()[:32]


def normalize_key(key: str) -> str:
    k = (key or "").strip().upper().replace(" ", "").replace("-", "")
    return "-".join(k[i:i + 5] for i in range(0, len(k), 5))


def _secret() -> str:
    return "HC9-signing-" + SALT


def _key_digest(key_core: str, mid: str) -> str:
    h = hashlib.sha256(f"{_secret()}|{key_core}|{mid}".encode()) \
        .hexdigest().upper()
    return h[:15]


def make_license() -> str:
    """Run locally to generate customer keys:
    python -c \"import sys; sys.path.insert(0,'.');
    from hypeclip.licensing import make_license; print(make_license())\""""
    core = uuid.uuid4().hex[:15].upper()
    digest = _key_digest(core, "ACTIVATE")
    groups = [core[i:i + 5] for i in range(0, 15, 5)]
    return "HC-" + "-".join(groups) + "-" + digest[:5]


def _stored() -> dict | None:
    try:
        return json.load(open(LICENSE_FILE, encoding="utf-8"))
    except Exception:
        return None


def activate(key: str) -> tuple[bool, str]:
    key = normalize_key(key)
    parts = key.split("-")
    if len(parts) != 5 or parts[0] != "HC":
        return False, "invalid key format"
    stored = _stored()
    prev_mid = (stored or {}).get("mid")
    mid = prev_mid or _machine_id()
    core = "".join(parts[1:4])
    expect = _key_digest(core, "ACTIVATE")
    if parts[4] != expect[:5]:
        return False, "key rejected"
    transfers = (stored or {}).get("transfers", 0)
    if prev_mid and prev_mid != mid:
        if transfers >= 2:
            return False, "machine transfer limit reached - contact support"
        mid = _machine_id()
        transfers += 1
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump({"key": key, "mid": mid, "tier": "creator",
               "transfers": transfers},
              open(LICENSE_FILE, "w", encoding="utf-8"), indent=1)
    return True, "activated"


def status() -> dict:
    st = _stored()
    licensed = bool(st) and st.get("tier") in ("creator", "studio")
    return {"licensed": licensed,
            "tier": st.get("tier") if licensed else "free",
            "mid": (st or {}).get("mid", "")}


def is_licensed() -> bool:
    return status()["licensed"]
