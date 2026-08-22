import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.abspath(SPECPATH)
BIN = os.path.join(ROOT, "..", "bin")

datas = [
    (os.path.join(ROOT, "..", "web"), "web"),
]
pkg_src = os.path.join(ROOT, "..", "hypeclip")
if os.path.isdir(pkg_src):
    datas.append((pkg_src, "app_src"))
if os.path.isdir(BIN):
    for f in os.listdir(BIN):
        if f.lower().endswith(".exe"):
            datas.append((os.path.join(BIN, f), "bin"))

hidden = [
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "yt_dlp", "pydub", "anyio", "pystray", "pyperclip", "requests",
    "python_multipart",
] + collect_submodules("chat_downloader") + collect_submodules("faster_whisper")
datas += collect_data_files("faster_whisper")

a = Analysis(["run_app.py"], pathex=[os.path.join(ROOT, "..")], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib"])
pyz = PYZ(a.pure)

exe_gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="HypeClip",
              console=False, icon=os.path.join(ROOT, "icon.ico"))
exe_dbg = EXE(pyz, a.scripts, [], exclude_binaries=True, name="HypeClip-Debug",
              console=True, icon=os.path.join(ROOT, "icon.ico"))

coll = COLLECT(exe_gui, exe_dbg, a.binaries, a.zipfiles, a.datas, name="HypeClip")