from __future__ import annotations
import os
import sys
from dataclasses import dataclass, fields

APP_VERSION = "3.8.0"


def resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    forced = os.getenv("HYPECLIP_DATA_DIR")
    if forced:
        return forced
    if getattr(sys, "frozen", False):
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "HypeClip")
    return resource_dir()


RESOURCE_DIR = resource_dir()
WEB_DIR = os.path.join(RESOURCE_DIR, "web")
BUNDLED_ASSETS = os.path.join(RESOURCE_DIR, "assets")
DATA_DIR = data_dir()


@dataclass
class Settings:
    # --- clip selection ---
    mode: str = "auto"
    max_clips: int = 5
    clip_duration: float = 90.0
    pre_roll: float = 8.0
    hype_threshold: float = 3.0
    cooldown: float = 90.0
    # --- autopilot ---
    auto_render: bool = True
    # --- visual enhancement ---
    enhance: bool = False
    enhance_mode: str = "light"          # light | heavy
    # --- layout / perf ---
    aspect: str = "9:16"
    smart_reframe: bool = True
    max_height: int = 1080
    fps: int = 60
    gpu: str = "auto"
    workers: int = 2
    # --- look (all OFF - clean output) ---
    fx_look: str = "none"
    bloom: bool = False
    grain: bool = False
    vignette: bool = False
    # --- motion (all OFF) ---
    zoom_punch: bool = False
    zoom_strength: float = 0.55
    shake: float = 0.0
    beat_sync: bool = False
    flash_intro: bool = False
    # --- overlays ---
    title_text: str = ""
    progress_bar: bool = False
    watermark_file: str = ""
    # --- captions ---
    autocaptions: bool = True
    caption_style: str = "tiktok"
    whisper_model: str = "small"
    # --- audio ---
    sfx_enabled: bool = True
    sfx_volume_db: float = 5.0
    music_file: str = ""
    music_volume_db: float = -16.0
    duck_music: bool = True
    # --- branding ---
    sub_name: str = ""
    sub_pos: str = "br"
    sub_when: str = "start"
    sub_dur: float = 4.0
    # --- scanner ---
    scan_fps: int = 6
    # --- eagle-eye tracking ---
    track_enabled: bool = False          # set per-job from wizard, kept for defaults
    # --- local upload ---
    uploaded_file: str = ""
    # --- io ---
    out_dir: str = os.path.join(DATA_DIR, "output")
    work_dir: str = os.path.join(DATA_DIR, "work")
    sfx_dir: str = os.path.join(DATA_DIR, "assets", "sfx")
    music_dir: str = os.path.join(DATA_DIR, "assets", "music")
    wm_dir: str = os.path.join(DATA_DIR, "assets", "watermarks")
    keep_temp: bool = False
    cookies_browser: str | None = os.getenv("YOUTUBE_COOKIES_BROWSER")

    def update(self, d: dict):
        types = {f.name: type(getattr(self, f.name)) for f in fields(self)}
        for k, v in (d or {}).items():
            if k not in types or v is None:
                continue
            cur = getattr(self, k)
            try:
                if isinstance(cur, bool):
                    v = bool(v) if not isinstance(v, str) \
                        else v.lower() in ("1", "true", "yes", "on")
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    v = int(float(v))
                elif isinstance(cur, float):
                    v = float(v)
                setattr(self, k, v)
            except (TypeError, ValueError):
                pass

    def ensure_dirs(self):
        for p in (self.out_dir, self.work_dir, self.sfx_dir,
                  self.music_dir, self.wm_dir):
            os.makedirs(p, exist_ok=True)
