from __future__ import annotations
import queue
import re
import threading
import time
from dataclasses import dataclass

_ID_RES = [
    re.compile(r"(?:youtube\.com/(?:watch\?.*?v=|live/|embed/|v/)|youtu\.be/|"
               r"youtube\.com/shorts/)([\w-]{11})"),
    re.compile(r"^([\w-]{11})$"),
]


@dataclass
class ChatMsg:
    t: float
    text: str
    money: float = 0.0


def parse_video_id(text: str) -> str | None:
    text = (text or "").strip()
    for rx in _ID_RES:
        m = rx.search(text)
        if m:
            return m.group(1)
    return None


def _ydl_base_opts(settings) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "socket_timeout": 25}
    if settings.cookies_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_browser,)
    return opts


def video_info(url: str, settings) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_base_opts(settings)) as ydl:
        i = ydl.extract_info(url, download=False)
    return {
        "id": i.get("id"),
        "title": i.get("title") or "stream",
        "duration": float(i.get("duration") or 0),
        "is_live": bool(i.get("is_live")),
        "channel": i.get("channel") or i.get("uploader") or "",
        "start_epoch": i.get("timestamp") or i.get("release_timestamp"),
    }


def _normalize(raw: dict, stream_epoch0: float | None) -> ChatMsg | None:
    ts = raw.get("time_in_seconds")
    if isinstance(ts, (int, float)) and ts >= 0:
        t = float(ts)
    else:
        u = raw.get("timestamp")
        if not isinstance(u, (int, float)):
            return None
        t_unix = u / 1_000_000.0
        if t_unix > 1e9:
            base = stream_epoch0
            t = t_unix - base if base else t_unix
        else:
            t = float(u)
    money = raw.get("money")
    return ChatMsg(
        t=t,
        text=(raw.get("message") or "").strip(),
        money=float(money) if isinstance(money, (int, float)) else 0.0,
    )


def fetch_chat_replay(url: str, settings, on_batch=None) -> list[ChatMsg]:
    try:
        from chat_downloader import ChatDownloader
    except ImportError as e:
        raise RuntimeError("pip install chat-downloader") from e

    msgs: list[ChatMsg] = []
    chat = ChatDownloader().get_chat(url)
    try:
        for raw in chat:
            m = _normalize(raw, None)
            if m:
                msgs.append(m)
                if on_batch and len(msgs) % 500 == 0:
                    on_batch(len(msgs))
    except Exception as e:
        if len(msgs) < 10:
            raise RuntimeError(
                f"Could not retrieve chat replay ({e}). "
                f"The archive must have chat replay enabled.") from e
    return msgs


class LiveChatThread(threading.Thread):
    def __init__(self, url: str, stream_epoch0: float | None):
        super().__init__(daemon=True)
        self.url = url
        self.stream_epoch0 = stream_epoch0
        self.q: "queue.Queue[ChatMsg]" = queue.Queue()
        self.error: Exception | None = None
        self.dead = False
        self.join_epoch = time.time()
        self._first_seen: float | None = None
        self._stop = threading.Event()

    def run(self):
        try:
            from chat_downloader import ChatDownloader
            chat = ChatDownloader().get_chat(self.url)
            for raw in chat:
                if self._stop.is_set():
                    break
                m = _normalize(raw, self.stream_epoch0)
                if not m:
                    continue
                if self.stream_epoch0 is None and m.t > 1e9:
                    if self._first_seen is None:
                        self._first_seen = m.t - (time.time() - self.join_epoch)
                    m.t -= self._first_seen
                self.q.put(m)
        except Exception as e:
            self.error = e
        finally:
            self.dead = True

    def stop(self):
        self._stop.set()