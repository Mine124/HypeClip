# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# This spec lives in <project>\packaging\ -> project root is one level up.
ROOT = os.path.abspath(SPECPATH)
PROJECT = os.path.normpath(os.path.join(ROOT, ".."))
BIN = os.path.join(PROJECT, "bin")

# ---------------------------------------------------------------
# HARD GUARD: every app module MUST exist and compile.
# A missing/broken file now fails the BUILD with a named error,
# instead of producing a ZIP that crashes on launch.
# When you add a new .py module to hypeclip/, add it here too.
# ---------------------------------------------------------------
REQUIRED_MODULES = [
    "server", "pipeline", "downloader", "youtube", "hype", "intel",
    "decide", "hooks", "captions", "captionstyle", "synth", "sfx",
    "beats", "reframe", "scan", "sources", "tracker", "director",
    "editor", "learn", "stylelearn", "branding", "platforms",
    "tray", "updater", "utils", "config", "audit", "editplan",
    "licensing", "understand",
]

for mod in REQUIRED_MODULES:
    mod_path = os.path.join(PROJECT, "hypeclip", mod + ".py")
    if not os.path.isfile(mod_path):
        raise SystemExit(
            f"BUILD FAILED: hypeclip/{mod}.py is MISSING from the repo. "
            f"Add the file (or remove '{mod}' from REQUIRED_MODULES).")

import py_compile
for mod in REQUIRED_MODULES:
    mod_path = os.path.join(PROJECT, "hypeclip", mod + ".py")
    try:
        py_compile.compile(mod_path, doraise=True)
    except py_compile.PyCompileError as e:
        raise SystemExit(
            f"BUILD FAILED: hypeclip/{mod}.py has a SYNTAX ERROR:\n{e}\n"
            f"Fix the file before building.")

print(f"[spec] all {len(REQUIRED_MODULES)} app modules present and "
      f"compile-clean [OK]")

datas = [
    (os.path.join(PROJECT, "web"), "web"),
]
pkg_src = os.path.join(PROJECT, "hypeclip")
if os.path.isdir(pkg_src):
    datas.append((pkg_src, "app_src"))
if os.path.isdir(BIN):
    for f in os.listdir(BIN):
        if f.lower().endswith(".exe"):
            datas.append((os.path.join(BIN, f), "bin"))

hidden = [
    "bootstrap",
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "yt_dlp", "pydub", "anyio", "pystray", "pyperclip", "requests",
    "python_multipart",
] + collect_submodules("chat_downloader") + collect_submodules("faster_whisper")
datas += collect_data_files("faster_whisper")

ENTRY = os.path.join(PROJECT, "run_app.py")

a = Analysis([ENTRY], pathex=[PROJECT], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib"])
pyz = PYZ(a.pure)

exe_gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="HypeClip",
              console=False, icon=os.path.join(ROOT, "icon.ico"))
exe_dbg = EXE(pyz, a.scripts, [], exclude_binaries=True,
              name="HypeClip-Debug", console=True,
              icon=os.path.join(ROOT, "icon.ico"))

coll = COLLECT(exe_gui, exe_dbg, a.binaries, a.zipfiles, a.datas,
               name="HypeClip")
