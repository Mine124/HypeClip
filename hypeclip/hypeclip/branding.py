"""Cartoon subscribe-button generator + API."""
from __future__ import annotations
import json
import math
import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import DATA_DIR

router = APIRouter(prefix="/api/streamers", tags=["branding"])

SUB_DIR = os.path.join(DATA_DIR, "subs")
STORE = os.path.join(DATA_DIR, "streamers.json")
SS = 3
CW, CH = 1440, 600


def _load() -> dict:
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except Exception:
        return {"active": None, "streamers": []}


def _save(d: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(d, open(STORE, "w", encoding="utf-8"), indent=1)


def slug(name: str) -> str:
    keep = "".join(c for c in name.lower() if c.isalnum() or c in "-_ ")
    return keep.strip().replace(" ", "_")[:32] or "streamer"


def _font(size: int, heavy: bool = True):
    from PIL import ImageFont
    cands = ["arialbd.ttf", "Arial Bold.ttf", "impact.ttf",
             "segoeuib.ttf", "arial.ttf"] if heavy else \
            ["arial.ttf", "segoeui.ttf"]
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _blob(cx, cy, rx, ry, wobble=0.05, lobes=6, rot=0.0):
    pts = []
    for i in range(72):
        th = 2 * math.pi * i / 72
        r = 1 + wobble * math.sin(lobes * th + rot)
        pts.append((cx + rx * r * math.cos(th),
                    cy + ry * r * math.sin(th)))
    return pts


def _star(cx, cy, ro, ri, n=12, rot=0.0):
    pts = []
    for i in range(n * 2):
        r = ro if i % 2 == 0 else ri
        th = math.pi * i / n + rot
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
    return pts


def _outlined(d, xy, text, font, fill, ow, ocol=(15, 15, 25)):
    d.text(xy, text, font=font, fill=fill, stroke_width=ow,
           stroke_fill=ocol, anchor="mm")


def generate(name: str, style: str = "bubble",
             accent=(124, 92, 255)) -> str:
    from PIL import Image, ImageDraw
    os.makedirs(SUB_DIR, exist_ok=True)

    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx, cy = CW // 2, CH // 2 + 40
    bw, bh = 560, 250

    light = tuple(min(255, int(c * 1.45)) for c in accent)

    if style == "burst":
        pts = _star(cx, cy, bw + 60, bh + 10, n=16, rot=math.pi / 16)
        d.polygon(pts, fill=accent + (255,), outline=(15, 15, 25, 255),
                  width=22)
    elif style == "wobble":
        d.polygon(_blob(cx, cy, bw, bh, wobble=0.07, lobes=5, rot=0.7),
                  fill=accent + (255,), outline=(15, 15, 25, 255))
        d.polygon(_blob(cx - bw * .18, cy - bh * .22, bw * .34, bh * .3,
                        wobble=.12, lobes=4),
                  fill=light + (110,))
    else:  # bubble
        layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle([cx - bw, cy - bh, cx + bw, cy + bh],
                             radius=int(bh * 0.95), fill=accent + (255,),
                             outline=(15, 15, 25, 255), width=22)
        ld.rounded_rectangle([cx - bw + 46, cy - bh + 38,
                              cx + bw - 180, cy - 10],
                             radius=90, fill=light + (95,))
        layer = layer.rotate(-5, center=(cx, cy), expand=False,
                             resample=Image.BICUBIC)
        img.alpha_composite(layer)
        d = ImageDraw.Draw(img)

    for sx, sy, sr in [(cx - bw - 70, cy - bh - 40, 26),
                       (cx + bw + 60, cy - 80, 20),
                       (cx + bw * .4, cy + bh + 70, 16)]:
        d.polygon(_star(sx, sy, sr, sr * 0.38, n=8),
                  fill=(255, 255, 255, 235))

    f_sub = _font(148)
    f_name = _font(88)
    _outlined(d, (cx, cy - 8), "SUBSCRIBE", f_sub, (255, 255, 255, 255), 14)

    nw = int(f_name.getlength(name.upper())) if hasattr(f_name, "getlength") \
        else 26 * len(name)
    rw = min(CW - 160, nw + 140)
    ry0, ry1 = 52, 190
    d.rounded_rectangle([cx - rw // 2, ry0, cx + rw // 2, ry1],
                        radius=60, fill=(255, 209, 61, 255),
                        outline=(15, 15, 25, 255), width=18)
    _outlined(d, (cx, (ry0 + ry1) // 2 - 6), name.upper(), f_name,
              (30, 22, 5, 255), 8, ocol=(255, 255, 255, 200))

    cur = [(cx + bw - 30, cy + bh - 130), (cx + bw - 30, cy + bh + 96),
           (cx + bw + 12, cy + bh + 44), (cx + bw + 66, cy + bh + 132),
           (cx + bw + 108, cy + bh + 112), (cx + bw + 56, cy + bh + 26),
           (cx + bw + 118, cy + bh + 8)]
    d.polygon(cur, fill=(255, 255, 255, 255), outline=(15, 15, 25, 255))

    out = img.resize((CW // SS, CH // SS), Image.LANCZOS)
    path = os.path.join(SUB_DIR, slug(name) + ".png")
    out.save(path)
    return path


def active_png() -> str | None:
    st = _load()
    if not st.get("active"):
        return None
    p = os.path.join(SUB_DIR, slug(st["active"]) + ".png")
    return p if os.path.isfile(p) else None


class AddReq(BaseModel):
    name: str
    style: str = "bubble"
    activate: bool = True


@router.get("")
def list_streamers():
    return _load()


@router.post("")
def add_streamer(req: AddReq):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    if req.style not in ("bubble", "burst", "wobble"):
        raise HTTPException(400, "style must be bubble | burst | wobble")
    generate(name, req.style)
    st = _load()
    if not any(s["name"].lower() == name.lower() for s in st["streamers"]):
        st["streamers"].append({"name": name, "style": req.style})
    if req.activate or not st.get("active"):
        st["active"] = name
    _save(st)
    return {"ok": True, "active": st["active"]}


@router.delete("")
def del_streamer(name: str):
    st = _load()
    st["streamers"] = [s for s in st["streamers"]
                       if s["name"].lower() != (name or "").lower()]
    if st.get("active", "").lower() == (name or "").lower():
        st["active"] = st["streamers"][0]["name"] if st["streamers"] else None
    _save(st)
    return {"ok": True}


@router.post("/activate")
def activate(body: dict):
    st = _load()
    nm = (body.get("name") or "").strip()
    if not any(s["name"].lower() == nm.lower() for s in st["streamers"]):
        raise HTTPException(404, "unknown streamer")
    st["active"] = nm
    _save(st)
    return {"ok": True, "active": nm}


@router.get("/preview.png")
def preview(name: str, style: str = "bubble"):
    p = os.path.join(SUB_DIR, slug(name) + ".png")
    if not os.path.isfile(p):
        p = generate(name, style)
    return FileResponse(p, media_type="image/png")
