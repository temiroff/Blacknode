"""A shared record of the commands Blacknode shells out to.

Nodes drive real tools — ``ros2``, ``docker``, colcon — and until now the only
trace a command left was its return value, or a fragment of its text embedded in
a timeout message. A graph that sat for a minute inside ``docker exec`` looked
identical to one doing nothing.

Runtimes call :func:`record` around each subprocess so the editor can show what
is running, how long it has taken, and what it printed.
"""
from __future__ import annotations

import itertools
import sys
import threading
import time
from typing import Any

MAX_ENTRIES = 300
_OUTPUT_LIMIT = 4000

_lock = threading.Lock()
_entries: list[dict[str, Any]] = []
_ids = itertools.count(1)


def _trim(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= _OUTPUT_LIMIT else text[:_OUTPUT_LIMIT] + "\n… truncated"


class Entry:
    """Handle for one in-flight command; call :meth:`finish` when it returns."""

    __slots__ = ("_record",)

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    def finish(
        self,
        ok: bool,
        stdout: str = "",
        stderr: str = "",
        error: str = "",
        exit_code: int | None = None,
    ) -> None:
        with _lock:
            self._record.update(
                status="ok" if ok else "failed",
                finished_at=time.time(),
                duration_ms=round((time.time() - self._record["started_at"]) * 1000, 1),
                stdout=_trim(stdout),
                stderr=_trim(stderr),
                error=_trim(error),
                exit_code=exit_code,
            )


_suppress = threading.local()


class suppress:
    """Hide spawns from the audit hook while a caller records them itself.

    Runtimes that wrap a subprocess in :func:`record` already report duration,
    exit code and output. Without this the same command would appear twice: once
    richly, once as a bare spawn.
    """

    def __enter__(self) -> None:
        _suppress.on = getattr(_suppress, "on", 0) + 1

    def __exit__(self, *_exc: Any) -> None:
        _suppress.on = max(0, getattr(_suppress, "on", 0) - 1)


def install_spawn_hook() -> None:
    """Log every subprocess Blacknode starts, whoever starts it.

    Nodes shell out from a dozen packages, so instrumenting each call site would
    both miss cases and drift. CPython raises a ``subprocess.Popen`` audit event
    for every spawn, which catches them all with no cooperation from callers.
    The hook only sees the launch, so these entries carry the command and no
    exit status - callers that want detail wrap themselves in :func:`record`.
    """
    if getattr(install_spawn_hook, "_installed", False):
        return
    install_spawn_hook._installed = True  # type: ignore[attr-defined]

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event != "subprocess.Popen" or getattr(_suppress, "on", 0):
            return
        try:
            command = args[1]
            text = command if isinstance(command, str) else " ".join(str(part) for part in command)
        except Exception:  # pragma: no cover - never break a spawn over logging
            return
        entry = record(text.strip(), backend="host", source="spawn")
        entry.finish(True)

    sys.addaudithook(hook)


def record(command: str, *, backend: str = "", source: str = "") -> Entry:
    """Log a command as started. ``command`` is display text, never re-executed."""
    entry: dict[str, Any] = {
        "id": next(_ids),
        "command": command,
        "backend": backend,
        "source": source,
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "duration_ms": None,
        "stdout": "",
        "stderr": "",
        "error": "",
        "exit_code": None,
    }
    with _lock:
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            del _entries[: len(_entries) - MAX_ENTRIES]
    return Entry(entry)


def entries(limit: int = 100, after_id: int = 0) -> list[dict[str, Any]]:
    """Most recent commands, oldest first. ``after_id`` polls only what is new."""
    with _lock:
        items = [dict(e) for e in _entries if e["id"] > after_id]
    return items[-max(1, min(limit, MAX_ENTRIES)):]


def active_count() -> int:
    with _lock:
        return sum(1 for e in _entries if e["status"] == "running")


def clear() -> None:
    with _lock:
        _entries.clear()
