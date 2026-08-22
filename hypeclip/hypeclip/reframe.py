from __future__ import annotations
import os

SAMPLE_EVERY = 0.4


def _track_path(video: str, start: float, dur: float) -> list[tuple[float, int]] | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    path: list[tuple[float, int]] = []
    prev = None
    smooth_x = None
    t = start
    while t < start + dur:
        f = int(t * fps)
        if f >= total > 0:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            diff = np.abs(gray - prev).mean(axis=0)
            if diff.sum() > 1e-3:
                cx = float((diff * np.arange(160)).sum() / diff.sum())
                smooth_x = cx if smooth_x is None else 0.75 * smooth_x + 0.25 * cx
        prev = gray
        if smooth_x is not None:
            path.append((t - start, int(smooth_x)))
        t += SAMPLE_EVERY
    cap.release()
    return path or None


def write_sendcmd(video: str, start: float, dur: float, src_w: int, src_h: int,
                  aspect: str, out_path: str) -> tuple[int, int]:
    ar = {"9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}[aspect]
    cw = min(src_w, int(round(src_h * ar)))
    ch = int(round(cw / ar))

    track = _track_path(video, start, dur) or []
    lines: list[str] = []
    last_x: int | None = None

    def emit(ts: float, x: int):
        lines.append(f"{max(0.0, ts):.2f} crop x {max(0, min(src_w - cw, x))};")

    if not track:
        emit(0.0, (src_w - cw) // 2)
    else:
        for i, (ts, nx) in enumerate(track):
            px = int(nx / 160 * (src_w - cw))
            if last_x is None or abs(px - last_x) > cw * 0.02 or i == 0:
                emit(ts, px)
                last_x = px
        emit(dur, last_x if last_x is not None else (src_w - cw) // 2)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return cw, ch