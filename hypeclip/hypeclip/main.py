from __future__ import annotations
import argparse
import sys

from . import pipeline
from .config import Settings


class CliReporter(pipeline.Reporter):
    BAR = 24

    def __init__(self):
        self._last_bar = -1

    def log(self, msg):
        sys.stdout.write("\n" + str(msg) + "\n")
        sys.stdout.flush()

    def stage(self, name):
        self._last_bar = -1
        sys.stdout.write(f"\n=== {name.upper()} ===\n")
        sys.stdout.flush()

    def progress(self, fraction):
        if fraction is None:
            return
        pct = int(min(max(fraction, 0), 1) * 100)
        if pct == self._last_bar:
            return
        self._last_bar = pct
        filled = int(self.BAR * pct / 100)
        bar = "#" * filled + "-" * (self.BAR - filled)
        sys.stdout.write(f"\r[{bar}] {pct:3d}%")
        sys.stdout.flush()


def main():
    p = argparse.ArgumentParser(prog="hypeclip",
                                description="Turn YouTube live streams into hype clips.")
    p.add_argument("url", nargs="?")
    p.add_argument("--mode", choices=["auto", "vod", "live"], default="auto")
    p.add_argument("--clips", type=int, default=5)
    p.add_argument("--duration", type=float, default=30)
    p.add_argument("--pre-roll", type=float, default=10)
    p.add_argument("--sensitivity", type=float, default=3.0)
    p.add_argument("--cooldown", type=float, default=90)
    p.add_argument("--height", type=int, default=720, choices=[480, 720, 1080])
    p.add_argument("--aspect", choices=["16:9", "9:16", "1:1"], default="16:9")
    p.add_argument("--caption-style", choices=["karaoke", "tiktok", "clean"],
                   default="karaoke")
    p.add_argument("--whisper", default="small")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--no-sfx", action="store_true")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--port", type=int, default=8500)
    args = p.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run("hypeclip.server:app", host="0.0.0.0", port=args.port)
        return
    if not args.url:
        p.error("give a YouTube URL (or use --serve)")

    s = Settings()
    s.update({
        "mode": args.mode, "max_clips": args.clips, "clip_duration": args.duration,
        "pre_roll": args.pre_roll, "hype_threshold": args.sensitivity,
        "cooldown": args.cooldown, "max_height": args.height,
        "aspect": args.aspect, "autocaptions": not args.no_captions,
        "caption_style": args.caption_style, "whisper_model": args.whisper,
        "sfx_enabled": not args.no_sfx,
    })
    clips = pipeline.run(args.url, s, CliReporter())
    print("\n\nOutput:")
    for c in clips:
        print(f"  - {c['file']}  (score {c['score']})")


if __name__ == "__main__":
    main()