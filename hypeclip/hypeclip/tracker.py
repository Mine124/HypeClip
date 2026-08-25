"""Eagle Eye: click-to-track object tracking + smooth camera-follow crops.
YOLOv8n ONNX detection when available (auto-downloaded ~12 MB, GPU-ready),
motion-energy fallback otherwise. Writes ffmpeg sendcmd scripts."""
from __future__ import annotations
import math
import os
import urllib.request

import numpy as np

from .config import DATA_DIR
from .utils import probe_dims

MODEL_URL = ("https://huggingface.co/unclecode/yolo-nas/resolve/main/"
             "yolov8n.onnx")
TRACKER_DIR = os.path.join(DATA_DIR, "bin", "tracker")


class _Engine:
    def __init__(self):
        self.sess = None
        self.in_name = None
        self.failed = False

    def _load(self):
        if self.sess or self.failed:
            return
        try:
            import onnxruntime as ort
            os.makedirs(TRACKER_DIR, exist_ok=True)
            mp = os.path.join(TRACKER_DIR, "yolov8n.onnx")
            if not os.path.isfile(mp):
                print("[eagle] downloading YOLO detector (~12 MB, once)...",
                      flush=True)
                urllib.request.urlretrieve(MODEL_URL, mp + ".tmp")
                os.replace(mp + ".tmp", mp)
            provs = ort.get_available_providers()
            use = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                   if p in provs]
            self.sess = ort.InferenceSession(mp, providers=use)
            self.in_name = self.sess.get_inputs()[0].name
            print(f"[eagle] detector ready ({use[0]})", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[eagle] YOLO unavailable ({e}) - motion fallback",
                  flush=True)
            self.failed = True

    def ready(self) -> bool:
        self._load()
        return self.sess is not None


ENG = _Engine()


def _frames(path, start, dur, max_n=48):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    n = min(max_n, max(8, int(dur * 2)))
    step = max(1, int(fps * dur / n))
    f0 = int(start * fps)
    for k in range(n):
        idx = f0 + k * step
        if total and idx >= total:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if ok:
            yield start + k * step / fps, fr
    cap.release()


def _detect(eng, frame):
    """Returns [(cx,cy,w,h,conf)] in pixels for one BGR frame."""
    import cv2
    H, W = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (640, 640),
                                 swapRB=True, crop=False)
    out = eng.sess.run(None, {eng.in_name: blob})[0][0].T  # (8400,84)
    boxes, scores = [], []
    sx, sy = W / 640.0, H / 640.0
    for row in out:
        cls = row[4:]
        conf = float(cls.max())
        if conf < 0.35:
            continue
        cx, cy, w, h = row[0] * sx, row[1] * sy, row[2] * sx, row[3] * sy
        boxes.append((cx - w / 2, cy - h / 2, w, h))
        scores.append(conf)
    keep = cv2.dnn.NMSBoxes([list(b) for b in boxes], scores, 0.4, 0.45)
    res = []
    for i in (np.array(keep).flatten() if len(keep) else []):
        x, y, w, h = boxes[int(i)]
        res.append((x + w / 2, y + h / 2, w, h, scores[int(i)]))
    return res, W, H


def _pick_target(eng, media, start, dur, nx, ny):
    """Find the detection closest to the user's click across sample frames."""
    best = None
    for _, fr in _frames(media, start, dur, max_n=20):
        dets, W, H = _detect(eng, fr)
        for cx, cy, w, h, cf in dets:
            dist = math.hypot(nx - cx / W, ny - cy / H)
            score = -dist + 0.12 * min((w * h) / (W * H), 0.4)
            if best is None or score > best[0]:
                best = (score, (cx, cy, w, h))
    return best[1] if best else None


def _follow(eng, media, start, dur, target_box):
    """Track nearest-similar box over time -> [(t,(cx,cy))]."""
    tx, ty, tw, th = target_box
    samples = []
    for t, fr in _frames(media, start, dur, max_n=48):
        dets, W, H = _detect(eng, fr)
        bb, bd = None, 1e9
        for cx, cy, w, h, cf in dets:
            d = math.hypot(cx / W - tx / W, cy / H - ty / H) \
                + abs(math.log((w * h) / (tw * th + 1e-6)))
            if d < bd:
                bd, bb = d, (cx, cy)
        if bb:
            samples.append((t, bb))
    return samples


def _motion_fallback(media, start, dur):
    """Column-wise motion energy centroid (no AI needed). Returns
    [(t,(cx_px,cy_px))] normalized to a 1920-wide virtual canvas."""
    try:
        import cv2
    except ImportError:
        return []
    prev = None
    out = []
    for t, fr in _frames(media, start, dur, max_n=48):
        g = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY),
                       (96, 54)).astype(np.float32)
        if prev is not None:
            diff = np.abs(g - prev).mean(axis=0)
            s = diff.sum()
            if s > 1e-3:
                cx01 = float((diff * np.arange(96)).sum() / s) / 96.0
                out.append((t, (cx01 * 1920.0, 540.0)))
        prev = g
    return out


def _smooth(v: np.ndarray, k: int = 7) -> np.ndarray:
    k = max(3, k | 1)
    ker = np.hanning(k)
    ker /= ker.sum()
    return np.convolve(v, ker, mode="same")


def build_track(media: str, start: float, dur: float,
                norm_click: tuple[float, float], aspect: str,
                out_path: str) -> dict | None:
    """Builds a sendcmd script animating crop x/y to follow the target.
    Writes to out_path. Returns {'ai':bool,'samples':int} or None."""
    dims = probe_dims(media)
    sw, sh = dims if dims else (1920, 1080)

    ar = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}.get(aspect, 16 / 9)
    cw = min(sw, int(round(sh * ar)))
    ch = int(round(cw / ar))

    samples = []
    used_ai = False
    if ENG.ready():
        try:
            tgt = _pick_target(ENG, media, start, dur,
                               norm_click[0], norm_click[1])
            if tgt:
                samples = _follow(ENG, media, start, dur, tgt)
                used_ai = bool(samples)
        except Exception as e:  # noqa: BLE001
            print(f"[eagle] AI pass failed ({e})", flush=True)
    if len(samples) < 4:
        samples = _motion_fallback(media, start, dur)
    if len(samples) < 4:
        return None

    grid = np.arange(0.0, dur, 0.25)
    ts = [p[0] for p in samples]
    xs = np.interp(grid, ts, [p[1][0] for p in samples])
    ys = np.interp(grid, ts, [p[1][1] for p in samples])
    xs, ys = _smooth(xs), _smooth(ys)

    lines = []
    for i, tt in enumerate(grid):
        x = int(np.clip(xs[i] - cw / 2, 0, max(0, sw - cw)))
        y = int(np.clip(ys[i] - ch / 2, 0, max(0, sh - ch)))
        lines.append(f"{tt:.2f} crop x {x};")
        lines.append(f"{tt:.2f} crop y {y};")

    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, out_path)
    return {"ai": used_ai, "samples": len(samples)}
