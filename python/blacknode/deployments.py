"""Run a saved graph as a detached background process.

A *deployment* is one frozen graph running outside the editor, so it keeps
running when the editor is closed and other graphs can build on what it
publishes: deploy a camera publisher once, then keep editing a graph that
subscribes to its topic.

Design
------
* The deployable unit is a **snapshot** -- the workflow JSON plus the resolved
  package lock, hashed together. The hash is the version. Snapshots are frozen
  at deploy time, so editing the tab afterwards never changes what is running.
* Execution reuses :func:`blacknode.workflow.export_workflow_python`, which
  already emits a standalone script that bootstraps the runtime, cooks the
  graph live, and holds itself open while live nodes run. This module only
  supervises that script; it does not re-implement running a graph.
* The registry is one directory per deployment on disk, so state survives an
  editor-server restart. Liveness is re-checked against the OS on every read
  rather than trusted from the record.

This module deliberately imports nothing from the editor server, so the same
store can back the CLI and, later, non-local targets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .node import _NODE_REGISTRY
from .workflow import WorkflowRunError, export_workflow_python

SCHEMA_VERSION = 1
TARGET_LOCAL_PROCESS = "local-process"

#: Deployment kinds. A graph with live nodes stays up; one without runs once.
KIND_SERVICE = "service"
KIND_JOB = "job"

#: ``running`` -- alive. ``stopped`` -- terminated on request.
#: ``exited`` -- ended on its own with success. ``failed`` -- ended badly.
STATE_RUNNING = "running"
STATE_STOPPED = "stopped"
STATE_EXITED = "exited"
STATE_FAILED = "failed"

_RECORD_NAME = "deployment.json"
_SNAPSHOT_NAME = "snapshot.json"
_SCRIPT_NAME = "graph.py"
_LOG_NAME = "deployment.log"

_STOP_GRACE_SECONDS = 5.0


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "graph"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ── process helpers ────────────────────────────────────────────────────────
#
# These are pid-based rather than Popen-based on purpose: after an
# editor-server restart the Popen object is gone but the deployment is still
# running, and "what is running right now" has to stay answerable.


def process_alive(pid: int) -> bool:
    """Best-effort liveness check that never signals the process.

    ``os.kill(pid, 0)`` is not usable here: on Windows any signal other than
    the CTRL_* events routes to TerminateProcess, so probing with it would
    kill the very process being inspected.
    """
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Alive, owned by somebody else.
        return True
    except OSError:
        return False
    return True


def _terminate_pid(pid: int) -> None:
    """Stop a deployment and the child processes it started.

    Deployed graphs launch their own children (ROS 2 processes, stream
    servers), so killing only the script would orphan them. Both branches
    target the whole tree/group.
    """
    if not process_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return
    try:
        group = os.getpgid(int(pid))
    except (ProcessLookupError, OSError):
        group = None
    try:
        if group is not None:
            os.killpg(group, signal.SIGTERM)
        else:
            os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    deadline = time.monotonic() + _STOP_GRACE_SECONDS
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return
        time.sleep(0.1)
    try:
        if group is not None:
            os.killpg(group, signal.SIGKILL)
        else:
            os.kill(int(pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        return


def _spawn_kwargs() -> dict[str, Any]:
    """Detach the child so it outlives the editor server."""
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


# ── graph inspection ───────────────────────────────────────────────────────


def live_node_types(workflow: Mapping[str, Any]) -> list[str]:
    """Node types in this workflow that hold a background service open."""
    found: set[str] = set()
    for meta in (workflow.get("node_meta") or {}).values():
        if not isinstance(meta, Mapping):
            continue
        node_type = str(meta.get("type") or "")
        fn = _NODE_REGISTRY.get(node_type)
        if fn is not None and getattr(fn, "_bn_live_capable", False):
            params = meta.get("params") or {}
            action = str(params.get("action") or "start").strip().lower()
            if action != "stop":
                found.add(node_type)
    return sorted(found)


def classify(workflow: Mapping[str, Any]) -> str:
    """A graph holding a live service is a ``service``; anything else a ``job``."""
    return KIND_SERVICE if live_node_types(workflow) else KIND_JOB


def resolve_entrypoint(workflow: Mapping[str, Any]) -> dict[str, str]:
    """Pick the node whose cook pulls the whole graph.

    ``workflow.infer_entrypoint`` requires an explicit entrypoint or exactly
    one ``Output`` node, which a publisher graph typically has neither of --
    the flagship "publish a camera and leave it running" case would be
    undeployable. Fall back to the graph's sink nodes, preferring a live one.
    """
    entrypoint = workflow.get("entrypoint")
    if isinstance(entrypoint, Mapping):
        node_id = entrypoint.get("node_id")
        port = entrypoint.get("port")
        if isinstance(node_id, str) and isinstance(port, str) and node_id:
            return {"node_id": node_id, "port": port}

    node_meta = workflow.get("node_meta") or {}
    if not node_meta:
        raise WorkflowRunError("Cannot deploy an empty graph.")
    edges = workflow.get("edges") or []

    outputs = [nid for nid, meta in node_meta.items()
               if isinstance(meta, Mapping) and meta.get("type") == "Output"]
    if len(outputs) == 1:
        return {"node_id": outputs[0], "port": "value"}

    consumed = {str(edge.get("from")) for edge in edges if isinstance(edge, Mapping)}
    sinks = [nid for nid in node_meta if nid not in consumed]
    if not sinks:
        # Every node feeds another one: a cycle, or a graph whose only
        # terminal is inside a loop. Nothing sensible to cook.
        raise WorkflowRunError(
            "Cannot infer what to deploy: every node feeds another node. "
            "Add an Output node or set an explicit entrypoint."
        )

    def first_port(node_id: str) -> str:
        meta = node_meta.get(node_id) or {}
        ports = [str(p) for p in (meta.get("outputs") or []) if str(p)]
        return ports[0] if ports else "report"

    if len(sinks) == 1:
        return {"node_id": sinks[0], "port": first_port(sinks[0])}

    live_sinks = [
        nid for nid in sinks
        if getattr(_NODE_REGISTRY.get(str((node_meta.get(nid) or {}).get("type") or "")), "_bn_live_capable", False)
    ]
    if len(live_sinks) == 1:
        return {"node_id": live_sinks[0], "port": first_port(live_sinks[0])}

    ambiguous = ", ".join(sorted(live_sinks or sinks)[:6])
    raise WorkflowRunError(
        f"Cannot infer what to deploy: {len(live_sinks or sinks)} end nodes ({ambiguous}). "
        "Add an Output node, or set an explicit entrypoint on the workflow."
    )


def _snapshot_hash(workflow: Mapping[str, Any], lock: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"workflow": workflow, "packages": lock},
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _package_lock() -> dict[str, Any]:
    """Pin the package versions this snapshot was built against.

    Read-only: never write the lockfile as a side effect of deploying.
    """
    try:
        from .packages import package_lock_path

        path = package_lock_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("packages") if isinstance(data.get("packages"), dict) else data
    except Exception:
        pass
    return {}


class DeploymentError(RuntimeError):
    """Raised for a deployment request that cannot be satisfied."""


class DeploymentStore:
    """One directory per deployment under ``root``.

    Layout::

        <root>/<id>/deployment.json   record
        <root>/<id>/snapshot.json     frozen workflow
        <root>/<id>/graph.py          generated standalone script
        <root>/<id>/deployment.log    captured output
    """

    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # Popen handles for deployments this process started. Absent after a
        # restart, which is why liveness is always re-derived from the pid.
        self._procs: dict[str, subprocess.Popen] = {}

    # ── paths ──────────────────────────────────────────────────────────────

    def _dir(self, deployment_id: str) -> Path:
        return self.root / deployment_id

    def _record_path(self, deployment_id: str) -> Path:
        return self._dir(deployment_id) / _RECORD_NAME

    def script_path(self, deployment_id: str) -> Path:
        return self._dir(deployment_id) / _SCRIPT_NAME

    def log_path(self, deployment_id: str) -> Path:
        return self._dir(deployment_id) / _LOG_NAME

    # ── record io ──────────────────────────────────────────────────────────

    def _read(self, deployment_id: str) -> dict[str, Any] | None:
        path = self._record_path(deployment_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write(self, record: Mapping[str, Any]) -> dict[str, Any]:
        data = dict(record)
        path = self._record_path(str(data["id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return data

    # ── lifecycle ──────────────────────────────────────────────────────────

    def create(
        self,
        workflow: Mapping[str, Any],
        *,
        name: str = "",
        target: str = TARGET_LOCAL_PROCESS,
        autostart: bool = True,
    ) -> dict[str, Any]:
        """Freeze ``workflow`` into a snapshot and (by default) start it."""
        if target != TARGET_LOCAL_PROCESS:
            raise DeploymentError(
                f"Unsupported deployment target '{target}'. Only '{TARGET_LOCAL_PROCESS}' is available."
            )

        snapshot = json.loads(json.dumps(dict(workflow), default=str))
        display = str(name or snapshot.get("name") or "Graph").strip() or "Graph"
        snapshot["name"] = display

        # Both steps reject graphs that are valid documents but not runnable
        # as-is. That is a request the caller can fix in the editor, so it
        # must surface as a DeploymentError (HTTP 400) carrying the reason,
        # never as an unhandled WorkflowRunError.
        try:
            snapshot["entrypoint"] = resolve_entrypoint(snapshot)
            script = export_workflow_python(snapshot)
        except WorkflowRunError as exc:
            raise DeploymentError(f"Graph cannot be deployed: {exc}") from exc

        lock = _package_lock()
        kind = classify(snapshot)
        deployment_id = f"{_slug(display)}-{uuid.uuid4().hex[:8]}"

        directory = self._dir(deployment_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / _SNAPSHOT_NAME).write_text(
            json.dumps(snapshot, indent=2, default=str) + "\n", encoding="utf-8"
        )
        self.script_path(deployment_id).write_text(script, encoding="utf-8")

        record = {
            "schema_version": SCHEMA_VERSION,
            "id": deployment_id,
            "name": display,
            "kind": kind,
            "target": target,
            "state": STATE_STOPPED,
            "snapshot_hash": _snapshot_hash(snapshot, lock),
            "entrypoint": snapshot["entrypoint"],
            "node_count": len(snapshot.get("node_meta") or {}),
            "live_node_types": live_node_types(snapshot),
            "packages": lock,
            "created_at": _iso_now(),
            "started_at": None,
            "stopped_at": None,
            "pid": None,
            "exit_code": None,
            "error": "",
        }
        with self._lock:
            self._write(record)
            if autostart:
                return self._start_locked(deployment_id)
            return self._reconcile(record)

    def start(self, deployment_id: str) -> dict[str, Any]:
        with self._lock:
            return self._start_locked(deployment_id)

    def _start_locked(self, deployment_id: str) -> dict[str, Any]:
        record = self._read(deployment_id)
        if record is None:
            raise DeploymentError(f"Unknown deployment '{deployment_id}'.")
        current = self._reconcile(record)
        if current.get("state") == STATE_RUNNING:
            return current

        script = self.script_path(deployment_id)
        if not script.exists():
            raise DeploymentError(f"Deployment '{deployment_id}' has no generated script.")

        env = dict(os.environ)
        # The generated script calls run_graph_live(), which streams run
        # events to the editor when BLACKNODE_SYNC_URL is set -- and the
        # editor opens a tab per synced run. A deployment is not an editor
        # run, so it must not do that. Phase 2 adds a dedicated reporting
        # channel for deployments.
        env.pop("BLACKNODE_SYNC_URL", None)
        env.setdefault("BLACKNODE_HOME", str(_repo_root()))
        env["BLACKNODE_DEPLOYMENT_ID"] = deployment_id
        env["PYTHONUNBUFFERED"] = "1"

        log = self.log_path(deployment_id)
        handle = log.open("ab")
        try:
            handle.write(
                f"\n=== {_iso_now()} starting {deployment_id} ({record.get('kind')}) ===\n".encode("utf-8")
            )
            handle.flush()
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(self._dir(deployment_id)),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                **_spawn_kwargs(),
            )
        except Exception as exc:
            handle.close()
            record.update({
                "state": STATE_FAILED,
                "error": f"Could not start deployment: {type(exc).__name__}: {exc}",
                "stopped_at": _iso_now(),
            })
            return self._write(record)
        finally:
            # The child holds its own inherited copy of the descriptor.
            try:
                handle.close()
            except OSError:
                pass

        self._procs[deployment_id] = proc
        record.update({
            "state": STATE_RUNNING,
            "pid": proc.pid,
            "started_at": _iso_now(),
            "stopped_at": None,
            "exit_code": None,
            "error": "",
        })
        return self._write(record)

    def stop(self, deployment_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._read(deployment_id)
            if record is None:
                raise DeploymentError(f"Unknown deployment '{deployment_id}'.")
            pid = record.get("pid")
            if isinstance(pid, int):
                _terminate_pid(pid)
            proc = self._procs.pop(deployment_id, None)
            if proc is not None:
                try:
                    proc.wait(timeout=1)
                except Exception:
                    pass
            record.update({
                "state": STATE_STOPPED,
                "stopped_at": _iso_now(),
                "pid": None,
                "error": "",
            })
            return self._write(record)

    def delete(self, deployment_id: str) -> bool:
        with self._lock:
            if self._read(deployment_id) is None:
                return False
            try:
                self.stop(deployment_id)
            except DeploymentError:
                pass
            self._procs.pop(deployment_id, None)
            shutil.rmtree(self._dir(deployment_id), ignore_errors=True)
            return not self._dir(deployment_id).exists()

    # ── reads ──────────────────────────────────────────────────────────────

    def _reconcile(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Refresh a record against the OS before returning it.

        A record saying ``running`` only means nobody has looked since it
        started. The process may have finished or crashed, and after an
        editor-server restart there is no Popen to ask, so liveness comes
        from the pid.
        """
        data = dict(record)
        if data.get("state") != STATE_RUNNING:
            return data
        pid = data.get("pid")
        if isinstance(pid, int) and process_alive(pid):
            return data

        deployment_id = str(data.get("id") or "")
        proc = self._procs.pop(deployment_id, None)
        exit_code = None
        if proc is not None:
            exit_code = proc.poll()
        data["pid"] = None
        data["exit_code"] = exit_code
        data["stopped_at"] = _iso_now()
        if data.get("kind") == KIND_JOB and (exit_code is None or exit_code == 0):
            # A job ending is the expected outcome, not a fault.
            data["state"] = STATE_EXITED
        elif exit_code in (None, 0):
            data["state"] = STATE_FAILED
            data["error"] = "Service stopped on its own. Check the log."
        else:
            data["state"] = STATE_FAILED
            data["error"] = f"Exited with code {exit_code}. Check the log."
        return self._write(data)

    def get(self, deployment_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read(deployment_id)
            if record is None:
                return None
            return self._reconcile(record)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            records: list[dict[str, Any]] = []
            for directory in self.root.iterdir() if self.root.exists() else []:
                if not directory.is_dir():
                    continue
                record = self._read(directory.name)
                if record is not None:
                    records.append(self._reconcile(record))
        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records

    def snapshot(self, deployment_id: str) -> dict[str, Any] | None:
        path = self._dir(deployment_id) / _SNAPSHOT_NAME
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def logs(self, deployment_id: str, *, limit_bytes: int = 20000) -> str:
        path = self.log_path(deployment_id)
        if not path.exists():
            return ""
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                if size > limit_bytes:
                    handle.seek(size - limit_bytes)
                data = handle.read()
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")

    def stop_all(self) -> int:
        stopped = 0
        for record in self.list():
            if record.get("state") == STATE_RUNNING:
                try:
                    self.stop(str(record["id"]))
                    stopped += 1
                except DeploymentError:
                    continue
        return stopped
