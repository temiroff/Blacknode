"""Persistent run history for the Blacknode editor server.

A run is one invocation of ``/cook`` or ``/cook-stream``. The store captures
the cook event stream, derives a status + summary, and writes one JSON file
per run under ``editor-server/runs/``.

Design notes
------------
* Append-only on disk. Each run is written exactly twice: once at start
  (status ``running``) and once at finalize. This keeps crashed runs visible.
* Bounded retention. When the run count exceeds ``max_runs`` the oldest
  finished files are removed. Pending runs are never auto-deleted.
* Thread-safe. The store uses an :class:`RLock` so concurrent ``/cook-stream``
  requests don't corrupt the index.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_MAX_RUNS = 200
_RUN_FILE_GLOB = "*.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class _RunBuffer:
    run_id: str
    node_id: str
    port: str
    node_type: str
    started_at: str
    started_perf: float
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"
    error: str | None = None
    value: Any = None
    finished_at: str | None = None
    duration_ms: float | None = None
    node_count: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    cached_nodes: int = 0
    _seen_nodes: set[str] = field(default_factory=set)


class RunStore:
    def __init__(self, root: str | os.PathLike, *, max_runs: int = DEFAULT_MAX_RUNS) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_runs = max_runs
        self._lock = threading.RLock()
        self._pending: dict[str, _RunBuffer] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    def begin(self, *, node_id: str, port: str, node_type: str) -> str:
        run_id = str(uuid.uuid4())
        buf = _RunBuffer(
            run_id=run_id,
            node_id=node_id,
            port=port,
            node_type=node_type,
            started_at=_iso_now(),
            started_perf=time.perf_counter(),
        )
        with self._lock:
            self._pending[run_id] = buf
            self._write_record(self._summary(buf, include_events=True))
        return run_id

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            buf = self._pending.get(run_id)
            if buf is None:
                return
            stamped = dict(event)
            stamped.setdefault("ts", _iso_now())
            buf.events.append(stamped)
            self._update_counters(buf, stamped)

    def finalize_success(self, run_id: str, *, value: Any = None) -> dict[str, Any] | None:
        return self._finalize(run_id, status="success", value=value)

    def finalize_error(self, run_id: str, *, error: str) -> dict[str, Any] | None:
        return self._finalize(run_id, status="error", error=error)

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        records = self._read_all_records()
        records.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return [self._summary_dict(r) for r in records[:limit]]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        path = self._path_for(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def delete_run(self, run_id: str) -> bool:
        path = self._path_for(run_id)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in self.root.glob(_RUN_FILE_GLOB):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
            self._pending.clear()
        return removed

    # ── Internals ──────────────────────────────────────────────────────────

    def _finalize(
        self,
        run_id: str,
        *,
        status: str,
        value: Any = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            buf = self._pending.pop(run_id, None)
            if buf is None:
                return None
            buf.status = status
            buf.value = value
            buf.error = error
            buf.finished_at = _iso_now()
            buf.duration_ms = round((time.perf_counter() - buf.started_perf) * 1000, 3)
            record = self._summary(buf, include_events=True)
            self._write_record(record)
            self._prune()
            return record

    def _summary(self, buf: _RunBuffer, *, include_events: bool) -> dict[str, Any]:
        record: dict[str, Any] = {
            "run_id": buf.run_id,
            "started_at": buf.started_at,
            "finished_at": buf.finished_at,
            "duration_ms": buf.duration_ms,
            "status": buf.status,
            "node_id": buf.node_id,
            "port": buf.port,
            "node_type": buf.node_type,
            "node_count": buf.node_count,
            "model_calls": buf.model_calls,
            "tool_calls": buf.tool_calls,
            "cached_nodes": buf.cached_nodes,
        }
        if buf.error is not None:
            record["error"] = buf.error
        if buf.status == "success":
            record["value"] = buf.value
        if include_events:
            record["events"] = list(buf.events)
        return record

    def _summary_dict(self, record: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "run_id",
            "started_at",
            "finished_at",
            "duration_ms",
            "status",
            "node_id",
            "port",
            "node_type",
            "node_count",
            "model_calls",
            "tool_calls",
            "cached_nodes",
            "error",
        )
        return {key: record.get(key) for key in keys if key in record}

    def _update_counters(self, buf: _RunBuffer, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind in {"start", "node_start"}:
            node_id = event.get("node_id")
            if isinstance(node_id, str) and node_id not in buf._seen_nodes:
                buf._seen_nodes.add(node_id)
                buf.node_count += 1
        elif kind == "success" and event.get("cached"):
            buf.cached_nodes += 1
        elif kind == "model_call":
            buf.model_calls += 1
        elif kind == "tool_call":
            buf.tool_calls += 1

    def _path_for(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_")
        return self.root / f"{safe}.json"

    def _write_record(self, record: dict[str, Any]) -> None:
        path = self._path_for(record["run_id"])
        try:
            path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass

    def _read_all_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.root.glob(_RUN_FILE_GLOB):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    def _prune(self) -> None:
        finished: list[tuple[float, Path]] = []
        for path in self.root.glob(_RUN_FILE_GLOB):
            try:
                stat = path.stat()
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") == "running":
                continue
            finished.append((stat.st_mtime, path))
        if len(finished) <= self.max_runs:
            return
        finished.sort(key=lambda item: item[0])
        excess = len(finished) - self.max_runs
        for _, path in finished[:excess]:
            try:
                path.unlink()
            except OSError:
                continue


def derive_status_from_events(events: Iterable[dict[str, Any]]) -> str:
    """Best-effort status reading for replayed event logs."""
    saw_error = False
    saw_done = False
    for event in events:
        kind = event.get("type")
        if kind == "error":
            saw_error = True
        elif kind == "done":
            saw_done = True
            if event.get("error"):
                saw_error = True
    if not saw_done:
        return "running"
    return "error" if saw_error else "success"
