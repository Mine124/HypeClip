"""Detects the platform behind a media URL and which features it supports."""
import re

_YT = re.compile(r"(youtube\.com|youtu\.be)", re.I)
_TW = re.compile(r"(?:^|\.)twitch\.tv", re.I)
_TT = re.compile(r"tiktok\.com", re.I)


def detect(url: str) -> dict:
    u = (url or "").strip()
    if _YT.search(u):
        return {"platform": "youtube", "has_chat": True}
    if _TW.search(u):
        is_clip = "clip" in u.lower()
        return {"platform": "twitch", "has_chat": not is_clip}
    if _TT.search(u):
        return {"platform": "tiktok", "has_chat": False}
    return {"platform": "other", "has_chat": False}
