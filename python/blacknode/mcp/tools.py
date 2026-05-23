"""Pure-Python implementations of the Blacknode MCP tool surface.

These functions take dicts in and return dicts out, with no MCP runtime
dependency. ``server.py`` wraps each one as a FastMCP tool. Keeping the logic
here means tests can exercise the tool surface without installing ``mcp``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..node import _NODE_REGISTRY
from ..workflow import (
    SUBGRAPH_NODE_TYPES,
    WORKFLOW_KIND,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowRunError,
    export_workflow_python,
    load_workflow,
    ports_compatible,
    run_workflow,
    validate_workflow,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _REPO_ROOT / "templates"

_CATEGORY_BY_MODULE = {
    "blacknode.nodes.values": "Values",
    "blacknode.nodes.ai": "AI",
    "blacknode.nodes.api": "API",
    "blacknode.nodes.core": "Core",
    "blacknode.nodes.database": "Database",
    "blacknode.nodes.flow": "Flow",
    "blacknode.nodes.io": "IO",
    "blacknode.nodes.math": "Math",
    "blacknode.nodes.nvidia": "NVIDIA",
    "blacknode.nodes.rag": "RAG",
    "blacknode.nodes.routing": "Routing",
    "blacknode.nodes.search": "Search",
    "blacknode.nodes.subnet": "Subnet",
}


# ── Public tool functions ─────────────────────────────────────────────────────

def list_nodes() -> dict[str, Any]:
    """Return every registered node type with its category and port schema."""
    nodes = [_node_schema(name, fn) for name, fn in sorted(_NODE_REGISTRY.items())]
    by_category: dict[str, list[str]] = {}
    for entry in nodes:
        by_category.setdefault(entry["category"], []).append(entry["type"])
    return {"nodes": nodes, "by_category": by_category, "count": len(nodes)}


def get_node_schema(type_name: str) -> dict[str, Any]:
    """Return the input/output port schema for one node type."""
    if type_name in SUBGRAPH_NODE_TYPES:
        return {
            "type": type_name,
            "category": "Subnet",
            "advanced": True,
            "note": (
                f"{type_name} carries a nested subgraph. Build it in the visual "
                "editor — the MCP surface only adds flat nodes."
            ),
        }
    fn = _NODE_REGISTRY.get(type_name)
    if fn is None:
        raise ValueError(f"Unknown node type '{type_name}'")
    return _node_schema(type_name, fn)


def list_templates() -> dict[str, Any]:
    """Return shipped workflow templates from the repo ``templates/`` folder."""
    items: list[dict[str, Any]] = []
    if _TEMPLATES_DIR.exists():
        for path in sorted(_TEMPLATES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append({
                "name": data.get("name") or path.stem,
                "path": str(path),
                "description": (data.get("metadata") or {}).get("description", ""),
                "node_count": len(data.get("node_meta") or {}),
            })
    return {"templates": items, "count": len(items)}


def load_template_workflow(template: str) -> dict[str, Any]:
    """Load a shipped template workflow by slug, relative path, or absolute path."""
    _path, workflow = _load_template_workflow(template)
    return workflow


def load_workflow_tool(path: str) -> dict[str, Any]:
    """Read a workflow JSON file and return its canonical dict form."""
    return load_workflow(Path(path))


def save_workflow_tool(
    workflow: Mapping[str, Any],
    path: str,
    *,
    validate: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate and save a workflow JSON file to disk."""
    workflow_dict = _copy_workflow(workflow)
    report = validate_workflow(workflow_dict).to_dict() if validate else None
    if report is not None and not report.get("ok"):
        raise ValueError(f"Workflow is invalid: {report}")

    target = Path(path).expanduser()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Workflow file already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    body = json.dumps(workflow_dict, indent=2) + "\n"
    target.write_text(body, encoding="utf-8")
    return {
        "ok": True,
        "path": str(target),
        "bytes": len(body.encode("utf-8")),
        "validation": report,
    }


def create_workflow(name: str = "Untitled", description: str = "") -> dict[str, Any]:
    """Build an empty workflow that already contains an Output node."""
    out_id = "out"
    metadata: dict[str, Any] = {}
    if description:
        metadata["description"] = description
    workflow: dict[str, Any] = {
        "kind": WORKFLOW_KIND,
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "name": name,
        "entrypoint": {"node_id": out_id, "port": "value"},
        "node_meta": {
            out_id: _build_node_meta(out_id, "Output", params={}, pos=(400.0, 200.0)),
        },
        "edges": [],
    }
    if metadata:
        workflow["metadata"] = metadata
    return workflow


def add_node(
    workflow: Mapping[str, Any],
    type_name: str,
    *,
    params: Mapping[str, Any] | None = None,
    pos: tuple[float, float] | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Add a node to a workflow and return the updated workflow + validation."""
    if type_name in SUBGRAPH_NODE_TYPES:
        raise ValueError(
            f"{type_name} requires a nested subgraph and cannot be added via MCP. "
            "Build subnets in the visual editor instead."
        )
    if type_name not in _NODE_REGISTRY:
        raise ValueError(f"Unknown node type '{type_name}'")

    new_workflow = _copy_workflow(workflow)
    node_meta = new_workflow.setdefault("node_meta", {})
    new_id = node_id or _unique_id(node_meta, type_name)
    if new_id in node_meta:
        raise ValueError(f"Node id '{new_id}' already exists")
    node_meta[new_id] = _build_node_meta(
        new_id,
        type_name,
        params=dict(params or {}),
        pos=pos or _next_pos(node_meta),
    )
    return {
        "workflow": new_workflow,
        "node_id": new_id,
        "validation": _validate_summary(new_workflow),
    }


def connect_nodes(
    workflow: Mapping[str, Any],
    from_node: str,
    from_port: str,
    to_node: str,
    to_port: str,
) -> dict[str, Any]:
    """Add a typed edge between two existing nodes."""
    new_workflow = _copy_workflow(workflow)
    node_meta = new_workflow.get("node_meta") or {}
    source = node_meta.get(from_node)
    target = node_meta.get(to_node)
    if source is None:
        raise ValueError(f"Source node '{from_node}' does not exist")
    if target is None:
        raise ValueError(f"Target node '{to_node}' does not exist")

    source_outputs = list(source.get("outputs", []))
    target_inputs = list(target.get("inputs", []))
    if from_port not in source_outputs:
        raise ValueError(
            f"Node '{from_node}' ({source.get('type')}) has no output port "
            f"'{from_port}'. Available outputs: {source_outputs}"
        )
    if to_port not in target_inputs:
        raise ValueError(
            f"Node '{to_node}' ({target.get('type')}) has no input port "
            f"'{to_port}'. Available inputs: {target_inputs}"
        )

    from_type = str((source.get("output_types") or {}).get(from_port, "Any"))
    to_type = str((target.get("input_types") or {}).get(to_port, "Any"))
    if not ports_compatible(from_type, to_type):
        raise ValueError(
            f"Incompatible port types: '{from_node}.{from_port}' is {from_type}, "
            f"'{to_node}.{to_port}' is {to_type}"
        )

    new_workflow.setdefault("edges", []).append({
        "from": from_node,
        "from_port": from_port,
        "to": to_node,
        "to_port": to_port,
    })
    return {"workflow": new_workflow, "validation": _validate_summary(new_workflow)}


def validate_workflow_tool(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Run full schema + port-type validation against the workflow schema."""
    return validate_workflow(workflow).to_dict()


def run_workflow_tool(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the workflow and return the cooked value plus run event log."""
    try:
        return run_workflow(workflow)
    except WorkflowRunError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "run_id": getattr(exc, "run_id", None),
            "events": getattr(exc, "events", []),
        }


def export_python_tool(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Export the workflow as a standalone Python script."""
    return {"source": export_workflow_python(workflow)}


def create_editor_workflow_tab(
    name: str = "Untitled",
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Queue a new workflow tab in a running Blacknode visual editor."""
    base_url, result = _post_editor_action(
        "/editor/actions/workflow-tab",
        {"name": name or "Untitled"},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will create the tab on its next action poll.",
    }


def open_workflow_in_editor_tab(
    workflow: Mapping[str, Any],
    name: str | None = None,
    *,
    editor_url: str | None = None,
    organize: bool = True,
) -> dict[str, Any]:
    """Queue a populated workflow tab in a running Blacknode visual editor."""
    workflow_dict = _copy_workflow(workflow)
    report = validate_workflow(workflow_dict).to_dict()
    if not report.get("ok"):
        raise ValueError(f"Workflow is invalid: {report}")

    tab_name = name or str(workflow_dict.get("name") or "Untitled")
    base_url, result = _post_editor_action(
        "/editor/actions/open-workflow-tab",
        {"name": tab_name, "workflow": workflow_dict, "organize": organize},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "validation": report,
        "note": "The open Blacknode editor will open the populated tab on its next action poll.",
    }


def run_template_in_editor(
    template: str,
    name: str | None = None,
    *,
    editor_url: str | None = None,
    organize: bool = True,
    cook: bool = False,
    cook_node_id: str = "out",
    cook_port: str = "value",
) -> dict[str, Any]:
    """Load a template, open it in the running editor, and optionally cook it."""
    path, workflow = _load_template_workflow(template)
    report = validate_workflow(workflow).to_dict()
    if not report.get("ok"):
        raise ValueError(f"Template workflow is invalid: {report}")

    open_result = open_workflow_in_editor_tab(
        workflow=workflow,
        name=name or str(workflow.get("name") or path.stem),
        editor_url=editor_url,
        organize=organize,
    )
    result: dict[str, Any] = {
        "ok": bool(open_result.get("ok")),
        "template": {
            "name": workflow.get("name") or path.stem,
            "path": str(path),
        },
        "editor_url": open_result.get("editor_url"),
        "validation": report,
        "open": open_result,
        "cook": None,
        "note": "The open Blacknode editor will load the template on its next action poll.",
    }
    if cook:
        cook_result = cook_editor_node(
            node_id=cook_node_id,
            port=cook_port,
            editor_url=editor_url,
        )
        result["cook"] = cook_result
        result["ok"] = bool(result["ok"] and cook_result.get("ok"))
        result["note"] = (
            "The open Blacknode editor will load the template, then cook the requested node "
            "on subsequent action polls."
        )
    return result


def cook_editor_node(
    node_id: str = "out",
    port: str = "value",
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Queue a node cook in a running Blacknode visual editor."""
    base_url, result = _post_editor_action(
        "/editor/actions/cook-node",
        {"node_id": node_id, "port": port},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will cook the node on its next action poll.",
    }


def get_editor_graph(*, editor_url: str | None = None) -> dict[str, Any]:
    """Return the graph currently loaded in a running Blacknode editor backend."""
    base_url, graph = _editor_request_json("GET", "/graph", editor_url=editor_url)
    _, validation = _editor_request_json("GET", "/validate", editor_url=editor_url)
    nodes = graph.get("nodes", []) if isinstance(graph, Mapping) else []
    edges = graph.get("edges", []) if isinstance(graph, Mapping) else []
    return {
        "ok": True,
        "editor_url": base_url,
        "graph": graph,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
        "validation": validation,
    }


def save_editor_workflow(
    name: str = "Untitled",
    previous_slug: str | None = None,
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Save the graph currently loaded in a running Blacknode editor backend."""
    clean_name = name.strip() or "Untitled"
    base_url, result = _editor_request_json(
        "POST",
        "/workflows",
        {"name": clean_name, "previous_slug": previous_slug},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "name": clean_name,
        "slug": result.get("slug"),
        "result": result,
        "note": "Saved the graph currently loaded in the Blacknode editor backend.",
    }


def list_saved_workflows(*, editor_url: str | None = None) -> dict[str, Any]:
    """List workflows saved by a running Blacknode editor backend."""
    base_url, workflows = _editor_request_json("GET", "/workflows", editor_url=editor_url)
    if not isinstance(workflows, list):
        raise RuntimeError(f"Blacknode editor backend returned unexpected workflows payload: {workflows!r}")
    return {
        "ok": True,
        "editor_url": base_url,
        "workflows": workflows,
        "count": len(workflows),
    }


def list_recent_runs(
    limit: int = 20,
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """List recent run summaries from a running Blacknode editor backend."""
    clean_limit = max(1, min(int(limit), 500))
    base_url, result = _editor_request_json("GET", f"/runs?limit={clean_limit}", editor_url=editor_url)
    if not isinstance(result, Mapping) or not isinstance(result.get("runs"), list):
        raise RuntimeError(f"Blacknode editor backend returned unexpected runs payload: {result!r}")
    runs = result["runs"]
    return {
        "ok": True,
        "editor_url": base_url,
        "runs": runs,
        "count": len(runs),
    }


def get_run(
    run_id: str,
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Return a full run record, including events, from a running editor backend."""
    clean_run_id = run_id.strip()
    if not clean_run_id:
        raise ValueError("Run id must be a non-empty string")
    base_url, result = _editor_request_json("GET", f"/runs/{clean_run_id}", editor_url=editor_url)
    if not isinstance(result, Mapping):
        raise RuntimeError(f"Blacknode editor backend returned unexpected run payload: {result!r}")
    return {
        "ok": True,
        "editor_url": base_url,
        "run": dict(result),
    }


def load_saved_workflow_in_editor(
    slug: str,
    name: str | None = None,
    *,
    editor_url: str | None = None,
    organize: bool = True,
) -> dict[str, Any]:
    """Queue a saved workflow to open as a new tab in a running Blacknode editor."""
    base_url, result = _post_editor_action(
        "/editor/actions/load-saved-workflow-tab",
        {"slug": slug, "name": name, "organize": organize},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will load the saved workflow on its next action poll.",
    }


def organize_editor_graph(*, editor_url: str | None = None) -> dict[str, Any]:
    """Queue the running Blacknode editor to organize and fit the current graph."""
    base_url, result = _post_editor_action(
        "/editor/actions/organize-graph",
        {},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will organize the current graph on its next action poll.",
    }


def rename_editor_tab(
    name: str,
    *,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Queue the running Blacknode editor to rename its active workflow tab."""
    base_url, result = _post_editor_action(
        "/editor/actions/rename-tab",
        {"name": name},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will rename the active tab on its next action poll.",
    }


def close_editor_tab(*, editor_url: str | None = None) -> dict[str, Any]:
    """Queue the running Blacknode editor to close its active workflow tab."""
    base_url, result = _post_editor_action(
        "/editor/actions/close-tab",
        {},
        editor_url=editor_url,
    )
    return {
        "ok": bool(result.get("ok", True)),
        "editor_url": base_url,
        "action": result.get("action", result),
        "note": "The open Blacknode editor will close the active tab on its next action poll.",
    }


# ── Internals ─────────────────────────────────────────────────────────────────

def _post_editor_action(
    path: str,
    payload_dict: Mapping[str, Any],
    *,
    editor_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    return _editor_request_json("POST", path, payload_dict, editor_url=editor_url)


def _editor_request_json(
    method: str,
    path: str,
    payload_dict: Mapping[str, Any] | None = None,
    *,
    editor_url: str | None = None,
) -> tuple[str, Any]:
    base_url = (editor_url or os.environ.get("BLACKNODE_EDITOR_URL") or "http://127.0.0.1:7777").rstrip("/")
    payload = json.dumps(payload_dict).encode("utf-8") if payload_dict is not None else None
    req = urllib_request.Request(
        f"{base_url}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method=method,
    )

    try:
        with urllib_request.urlopen(req, timeout=3) as res:
            body = res.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Blacknode editor backend rejected the request: HTTP {exc.code} {detail}"
        ) from exc
    except (OSError, urllib_error.URLError) as exc:
        raise RuntimeError(
            f"Could not reach Blacknode editor backend at {base_url}. "
            "Start the editor backend with: cd editor-server && python server.py"
        ) from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Blacknode editor backend returned non-JSON: {body!r}") from exc
    return base_url, result


def _load_template_workflow(template: str) -> tuple[Path, dict[str, Any]]:
    path = _resolve_template_path(template)
    return path, load_workflow(path)


def _resolve_template_path(template: str) -> Path:
    clean = template.strip()
    if not clean:
        raise ValueError("Template must be a slug or path")

    raw = Path(clean)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
        if raw.suffix.lower() != ".json":
            candidates.append(raw.with_suffix(".json"))
    else:
        candidates.append(_REPO_ROOT / raw)
        candidates.append(_TEMPLATES_DIR / raw)
        if raw.suffix.lower() != ".json":
            candidates.append((_REPO_ROOT / raw).with_suffix(".json"))
            candidates.append((_TEMPLATES_DIR / raw).with_suffix(".json"))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Template '{template}' not found. Searched: {searched}")


def _node_schema(name: str, fn: Any) -> dict[str, Any]:
    inputs = list(getattr(fn, "_bn_inputs", []))
    outputs = list(getattr(fn, "_bn_outputs", []))
    input_types = dict(getattr(fn, "_bn_input_types", {}))
    output_types = dict(getattr(fn, "_bn_output_types", {}))
    doc = (fn.__doc__ or "").strip()
    summary = doc.split("\n", 1)[0] if doc else ""
    return {
        "type": name,
        "category": getattr(fn, "_bn_category", None) or _CATEGORY_BY_MODULE.get(getattr(fn, "__module__", ""), "Other"),
        "inputs": [{"name": p, "type": input_types.get(p, "Any")} for p in inputs],
        "outputs": [{"name": p, "type": output_types.get(p, "Any")} for p in outputs],
        "input_defaults": dict(getattr(fn, "_bn_input_defaults", {})),
        "doc": getattr(fn, "_bn_description", None) or summary,
        "source": getattr(fn, "_bn_source_path", ""),
    }


def _build_node_meta(
    node_id: str,
    type_name: str,
    *,
    params: dict[str, Any],
    pos: tuple[float, float],
) -> dict[str, Any]:
    fn = _NODE_REGISTRY[type_name]
    return {
        "id": node_id,
        "type": type_name,
        "params": dict(params),
        "pos": [float(pos[0]), float(pos[1])],
        "inputs": list(getattr(fn, "_bn_inputs", [])),
        "outputs": list(getattr(fn, "_bn_outputs", [])),
        "input_types": dict(getattr(fn, "_bn_input_types", {})),
        "output_types": dict(getattr(fn, "_bn_output_types", {})),
        "input_defaults": dict(getattr(fn, "_bn_input_defaults", {})),
    }


def _copy_workflow(workflow: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(workflow)))


def _unique_id(node_meta: Mapping[str, Any], type_name: str) -> str:
    base = type_name.lower()
    candidate = base
    suffix = 2
    while candidate in node_meta:
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def _next_pos(node_meta: Mapping[str, Any]) -> tuple[float, float]:
    if not node_meta:
        return (60.0, 60.0)
    xs = [meta.get("pos", [0, 0])[0] for meta in node_meta.values() if isinstance(meta, Mapping)]
    return (float(max(xs, default=0.0)) + 200.0, 120.0)


def _validate_summary(workflow: Mapping[str, Any]) -> dict[str, Any]:
    return validate_workflow(workflow).to_dict()
