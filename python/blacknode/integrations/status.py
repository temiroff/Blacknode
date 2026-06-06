"""Best-effort driver heartbeat to the editor-server.

A driver runs as its own process (``blacknode slack`` / ``telegram``), separate
from the editor. So the canvas can't know a bot is live unless the driver tells
it. This posts a small heartbeat to the editor-server; the editor polls it and
shows a truthful live/offline badge on the trigger node. It is **best-effort**:
if the editor isn't running, posts fail silently and the bot is unaffected.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

_INTERVAL = 5.0  # seconds between heartbeats; editor treats >15s stale as offline


def _editor_url() -> str:
    return os.environ.get("BLACKNODE_EDITOR_URL", "http://127.0.0.1:7777").rstrip("/")


class DriverStatus:
    def __init__(self, driver: str, workflow: str = "", label: str = "") -> None:
        self.driver = driver
        self.workflow = workflow
        self.label = label  # the connected bot's identity, e.g. "@BlacknodeAgentBot"
        self.state = "starting"
        self.processed = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _post(self) -> None:
        payload = json.dumps({
            "name": self.driver,
            "workflow": self.workflow,
            "label": self.label,
            "state": self.state,
            "processed": self.processed,
            "pid": os.getpid(),
            "ts": time.time(),
        }).encode("utf-8")
        req = urllib.request.Request(
            _editor_url() + "/drivers/status",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            pass  # editor not running / unreachable — heartbeat is best-effort

    def start(self) -> "DriverStatus":
        self.state = "listening"
        self._post()

        def _loop() -> None:
            while not self._stop.wait(_INTERVAL):
                self._post()

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        return self

    def mark_processing(self) -> None:
        self.state = "processing"
        self._post()

    def mark_listening(self) -> None:
        self.processed += 1
        self.state = "listening"
        self._post()

    def stop(self) -> None:
        self._stop.set()
        self.state = "stopped"
        self._post()
