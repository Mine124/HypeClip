"""Eagle Eye: click-to-track object tracking + camera-follow crops.
Uses YOLOv8n ONNX when available (auto-downloaded), falls back to
motion-energy tracking. Produces smooth camera paths per clip."""
from __future__ import annotations
import glob
import math
import os
import shutil
import subprocess
import urllib.request

import numpy as np

from .config import DATA_DIR
from .utils import ff_filter_path, probe_duration, resolve_bin, run

MODEL_URL = ("https://huggingface.co/unclecode/yolo-nas/resolve/main/"
             "yolov8n.onnx")   # ~12 MB COCO-pretrained detector
TRACKER_DIR = os.path.join(DATA_DIR, "bin", "tracker")


# ----------------------------------------------------------------- engine
class _Engine:
    """Lazy YOLO-onnxruntime singleton. detect() -> list of boxes."""
    def __init__(self):
        self.sess = None
        self.names = None
        self.failed = False

    def _load(self):
        if self.sess or self.failed:
            return
        try:
            import onnxruntime as ort
            os.makedirs(TRACKER_DIR, exist_ok=True)
            mp = os.path.join(TRACKER_DIR, "yolov8n.onnx")
            if not os.path.isfile(mp):
                print("[eagle] downloading YOLO detector (~12 MB)...",
                      flush=True)
                urllib.request.urlretrieve(MODEL_URL, mp + ".tmp")
                os.replace(mp + ".tmp", mp)
            provs = ort.get_available_providers()
            use = [p for p in ["CUDAExecutionProvider",
                               "CPUExecutionProvider"] if p in provs]
            self.sess = ort.InferenceSession(mp, providers=use)
            self.in_name = self.sess.get_inputs()[0].name
        except Exception as e:  # noqa: BLE001
            print(f"[eagle] YOLO unavailable ({e}) - motion fallback", flush=True)
            self.failed = True

    def ready(self) -> bool:
        self._load()
        return self.sess is not None

    def detect(self, frame_bgr) -> tuple[list, int, int]:
        import cv2
        self._load()
        H, W = frame_bgr.shape[:2]
        if not self.sess:
            return [], W, H
        blob = cv2.dnn.blobFromImage(frame_bgr, 1 / 255.0, (640, 640),
                                     swapRB=True, crop=False)
        out = self.sess.run(None, {self.in_name: blob})[0][0]  # (84,8400)
        out = out.T                                            # (8400,84)
        boxes, scores = [], []
        for row in out:
            cls_scores = row[4:]
            cid = int(np.argmax(cls_scores))
            conf = float(cls_scores[cid])
            if conf < 0.35:
                continue
            cx, cy, w, h = row[:4] * np.array(
                [W / 640.0, H / 640.0, W / 640.0, H / 640.0])
            boxes.append([cx - w / 2, cy - h / 2, w, h])
            scores.append(conf)
        idx = cv2.dnn.NMSBoxes(boxes, scores, 0.4, 0.45)
        final = []
        for i in np.array(idx).flatten() if len(idx) else []:
            x, y, w, h = boxes[i]
            final.append({"box": [float(x), float(y), float(w), float(h)],
                          "conf": float(scores[i]),
                          "label": str(int(cid)) if False else None})
        return final, W, H


ENG = _Engine()


# ------------------------------------------------------------- sampling
def _frames(path, start, dur, max_n=60):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    n = min(max_n, max(8, int(dur * 2)))          # ~2 samples/sec
    step = max(1, int(fps * dur / n))
    f0 = int(start * fps)
    for k in range(n):
        idx = f0 + k * step
        if total and idx >= total:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if ok:
            yield (start + k * step / fps), fr
    cap.release()


def _motion_center(frames_iter) -> list[tuple[float, float]]:
    centers = []
    prev = None
    for t, fr in frames_iter:
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) \
            if "cv2" in dir() else None
        if g is None:
            break
        g = cv2.resize(g, (96, 54)).astype(np.float32)
        if prev is not None:
            diff = np.abs(g - prev).mean(axis=0)
            s = diff.sum()
            if s > 1e-3:
                centers.append((t, float((diff * np.arange(96)).sum() / s)))
        prev = g
    return centers


def _smooth(pts: list[tuple[float, float]], win: float = 1.2,
            fps_s: float = 2.0) -> list[tuple[float, float]]:
    """Gaussian-ish smoothing + clamp to valid crop range."""
    if not pts:
        return pts
    k = int(max(1, win * fps_s))
    xs = np.array([p[1] for p in pts])
    ker = np.hanning(k * 2 + 1); ker /= ker.sum()
    xs_s = np.convolve(xs, ker, mode="same")
    return [(pts[i][0], float(xs_s[i])) for i in range(len(pts))]


def build_track(media: str, start: float, dur: float,
                norm_click: tuple[float, float], aspect: str
                ) -> dict | None:
    """Returns {'cmd_file': path} describing a camera that follows the
    clicked object. Writes an ffmpeg sendcmd script animating crop x/y."""
    try:
        import cv2
    except ImportError:
        cv2 = None

    ar = {"9:16": 9 / 16, "1:1": 1.0}.get(aspect)
    samples = []
    used_ai = False
    if ENG.ready():
        try:
            # first pass: find best-matching detection to the click
            best = None
            for t, fr in _frames(media, start, dur, max_n=24):
                dets, W, H = ENG.detect(fr)
                if not dets:
                    continue
                nx, ny = norm_click
                for d in dets:
                    x, y, w, h = d["box"]
                    cx, cy = (x + w / 2) / W, (y + h / 2) / H
                    dist = math.hypot(nx - cx, ny - cy)
                    area = (w * h) / (W * H)
                    score_ = -dist + 0.15 * min(area, .5)
                    if best is None or score_ > best[0]:
                        best = (score_, d["box"], W, H)
            if best:
                used_ai = True
                bx = best[1]
                # second pass: track nearest similar box over time
                tgt_ar = math.sqrt((bx[2] * bx[3]) / max(ar, 1e-6))
                for t, fr in _frames(media, start, dur, max_n=48):
                    dets, W, H = ENG.detect(fr)
                    if not dets:
                        continue
                    bb, bd = None, 1e9
                    for d in dets:
                        x, y, w, h = d["box"]
                        dd = math.hypot((x + w/2)/W - (bx[0]+bx[2]/2)/W,
                                        (y+h/2)/H - (bx[1]+bx[3]/2)/H) \
                             + abs(math.log((w*h)/(bx[2]*bx[3]+1e-6)))
                        if dd < bd:
                            bd, bb = dd, (x + w / 2, y + h / 2)
                    if bb:
                        samples.append((t, bb))
        except Exception:
            pass

    if not samples:
        # ---- fallback: horizontal motion energy ----
        try:
            samples = [(t, (cx * 1920, 540))
                       for t, cx in _motion_center(_frames(media, start, dur))]
            used_ai = False
        except Exception:
            return None
    if len(samples) < 4:
        return None

    # ---- build smooth camera path -------------------------------------
    src_w, src_h = probe_dims_safe(media)
    if not src_w:
        src_w, src_h = 1920, 1080
    sw, sh = src_w
    sw, sh = src_w, src_h
    cw = min(sw, int(round(sh * (ar or 16 / 9))))
    ch = int(round(cw / (ar or 16 / 9)))

    xs = np.interp(
        np.arange(0, dur, 0.25),
        [p[0] for p in samples],
        [p[1][0] for p in samples])
    ys = np.interp(
        np.arange(0, dur, 0.25),
        [p[0] for p in samples],
        [p[1][1] for p in samples])
    # smooth both axes
    def sm(v, k=7):
        ker = np.hanning(k); ker /= ker.sum()
        return np.convolve(v, ker, mode="same")
    xs, ys = sm(xs), sm(ys)

    lines = []
    for i, tt in enumerate(np.arange(0, dur, 0.25)):
        x = int(np.clip(xs[i] - cw / 2, 0, max(0, sw - cw)))
        y = int(np.clip(ys[i] - ch / 2, 0, max(0, sh - ch)))
        lines.append(f"{tt:.2f} crop x {x};")
        lines.append(f"{tt:.2f} crop y {y};")

    cmd_file = os.path.join(os.path.dirname(plan_dest_hint()),
                            f"track_{abs(hash((media,start,dur)))%99999}.txt")
    with open(cmd_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"cmd_file": cmd_file, "ai": used_ai,
            "samples": len(samples)}


def probe_dims_safe(p):
    try:
        from .utils import probe_dims
        return probe_dims(p)
    except Exception:
        return None


def plan_dest_hint():
    import tempfile
    return os.path.join(tempfile.gettempdir(), "hc")
