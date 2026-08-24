import bootstrap  # MUST be first

import os
import socket
import sys
import threading
import time
import webbrowser

# Quieter networking on Windows: kills harmless WinError 10054 spam
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from hypeclip.config import APP_VERSION

PORT = int(os.environ.get("HYPECLIP_PORT", "8500"))
BASE = f"http://127.0.0.1:{PORT}"


def port_open() -> bool:
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.25).close()
        return True
    except OSError:
        return False


def main():
    # Already running? Just open the dashboard.
    if port_open():
        webbrowser.open(BASE)
        return

    from hypeclip.server import app
    import uvicorn
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=PORT,
                                   log_level="warning"),
        daemon=True).start()

    for _ in range(80):
        if port_open():
            break
        time.sleep(0.1)
    webbrowser.open(BASE)
    print(f"HypeClip Studio v{APP_VERSION} running at {BASE}", flush=True)

    try:
        from hypeclip.tray import start_async
        start_async(BASE)
    except Exception:
        pass

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        os._exit(0)


if __name__ == "__main__":
    main()
