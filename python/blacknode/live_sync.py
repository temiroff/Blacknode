from __future__ import annotations

import json
import os
import time
import traceback
import urllib.request
from typing import Any

from .node import _NODE_REGISTRY


def run_graph_live(
    graph,
    node_id: str,
    port: str = "output",
    *,
    workflow: dict[str, Any] | None = None,
    editor_url: str | None = None,
) -> Any:
    sync = LiveSyncClient(editor_url or os.environ.get("BLACKNODE_SYNC_URL", ""))
    if not sync.enabled:
        graph._cache.clear()
        graph._dirty = set(graph._nodes)
        return graph._cook(node_id, port)

    node_type = graph._nodes.get(node_id, {}).get("type", "Graph")
    run_id = sync.begin(node_id=node_id, port=port, node_type=node_type, workflow=workflow)
    graph._cache.clear()
    graph._dirty = set(graph._nodes)
    try:
        value = _cook_live(graph, node_id, port, sync, run_id)
    except Exception as exc:
        error = traceback.format_exc()
        sync.event(run_id, {"type": "done", "port": port, "error": error})
        sync.finish(run_id, status="error", error=str(exc))
        raise
    sync.event(run_id, {"type": "done", "port": port, "value": value})
    sync.finish(run_id, status="success", value=value)
    return value


class LiveSyncClient:
    def __init__(self, editor_url: str):
        self.editor_url = editor_url.rstrip("/")
        self.enabled = bool(self.editor_url)

    def begin(
        self,
        *,
        node_id: str,
        port: str,
        node_type: str,
        workflow: dict[str, Any] | None = None,
    ) -> str:
        payload = self._post("/sync/runs", {
            "node_id": node_id,
            "port": port,
            "node_type": node_type,
            "workflow": workflow,
        })
        return str(payload["run_id"])

    def event(self, run_id: str, event: dict[str, Any]) -> None:
        stamped = {"ts": time.time(), **event}
        self._post("/sync/events", {"run_id": run_id, "event": stamped})

    def finish(self, run_id: str, *, status: str, value: Any = None, error: str | None = None) -> None:
        self._post(f"/sync/runs/{run_id}/finish", {"status": status, "value": value, "error": error})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, default=str).encode("utf-8")
        request = urllib.request.Request(
            f"{self.editor_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


class _RunLogger:
    def __init__(self, sync: LiveSyncClient, run_id: str):
        self.sync = sync
        self.run_id = run_id

    def model_call(self, *, node_id, model, provider=None, action="complete", tool_count=None):
        event: dict[str, Any] = {
            "type": "model_call",
            "node_id": node_id,
            "model": model,
            "action": action,
        }
        if provider:
            event["provider"] = provider
        if tool_count is not None:
            event["tool_count"] = tool_count
        self.sync.event(self.run_id, event)

    def tool_call(self, *, node_id, name, arguments=None):
        self.sync.event(self.run_id, {
            "type": "tool_call",
            "node_id": node_id,
            "name": name,
            "arguments": dict(arguments or {}),
        })


def _cook_live(graph, node_id: str, port: str, sync: LiveSyncClient, run_id: str) -> Any:
    cache_key = (node_id, port)
    if node_id not in graph._dirty and cache_key in graph._cache:
        value = graph._cache[cache_key]
        sync.event(run_id, {"type": "success", "node_id": node_id, "port": port, "value": value, "cached": True})
        return value

    node_def = graph._nodes[node_id]
    ctx = dict(node_def["params"])
    for edge in graph._edges:
        if edge["to"] == node_id:
            ctx[edge["to_port"]] = _cook_live(graph, edge["from"], edge["from_port"], sync, run_id)

    sync.event(run_id, {"type": "start", "node_id": node_id, "node_type": node_def["type"], "port": port})
    try:
        if node_def["type"] == "Subnet":
            result = graph._cook_subnet(node_id, port, ctx)
        else:
            fn = _NODE_REGISTRY[node_def["type"]]
            ctx["__graph__"] = graph
            ctx["__node_id__"] = node_id
            ctx["__run_logger__"] = _RunLogger(sync, run_id)
            result = fn(ctx)
        if not isinstance(result, dict):
            result = {"output": result}
        for key, value in result.items():
            graph._cache[(node_id, key)] = value
        graph._dirty.discard(node_id)
        if cache_key not in graph._cache:
            raise KeyError(f"Node '{node_def['type']}' did not produce port '{port}'.")
        value = graph._cache[cache_key]
        sync.event(run_id, {
            "type": "success",
            "node_id": node_id,
            "node_type": node_def["type"],
            "port": port,
            "value": value,
            "outputs": result,
        })
        return value
    except Exception:
        sync.event(run_id, {
            "type": "error",
            "node_id": node_id,
            "node_type": node_def["type"],
            "port": port,
            "error": traceback.format_exc(),
        })
        raise
