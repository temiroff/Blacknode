"""Pure-Python implementations of the Blacknode MCP tool surface.

These functions take dicts in and return dicts out, with no MCP runtime
dependency. ``server.py`` wraps each one as a FastMCP tool. Keeping the logic
here means tests can exercise the tool surface without installing ``mcp``.
"""
from __future__ import annotations

import ast
import logging
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request
from datetime import datetime, timezone

from ..learned import registry as learned_registry
from ..learned.manifest import ALLOWED_PORT_TYPES, PORT_RE, validate_manifest
from ..node import _NODE_REGISTRY
from ..sandbox.static import check_safe
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
_LOGGER = logging.getLogger(__name__)
_LEARNED_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_LEARNED_CONSENT_ENV = "BLACKNODE_LEARNED_NODES_CONSENT"
_LEARNED_CONSENT_FILE = "learned-nodes-consent.json"
_ALLOWED_PORT_TYPES_DISPLAY = "Text, Int, Float, Bool, List, Dict, Any"

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


class BlacknodeMCPError(ValueError):
    """MCP-facing error with an actionable suggestion in the message."""

    def __init__(
        self,
        code: str,
        message: str,
        suggestion: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.suggestion = suggestion
        self.details = dict(details or {})
        super().__init__(_format_mcp_error(code, message, suggestion, self.details))


# ── Public tool functions ─────────────────────────────────────────────────────

def list_nodes() -> dict[str, Any]:
    """Return every registered node type with its category and port schema."""
    learned_registry.sync_with_disk()
    nodes = [_node_schema(name, fn) for name, fn in sorted(_NODE_REGISTRY.items())]
    by_category: dict[str, list[str]] = {}
    for entry in nodes:
        by_category.setdefault(entry["category"], []).append(entry["type"])
    return {"nodes": nodes, "by_category": by_category, "count": len(nodes)}


def get_node_schema(type_name: str) -> dict[str, Any]:
    """Return the input/output port schema for one node type."""
    learned_registry.sync_with_disk()
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
    learned_registry.sync_with_disk()
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
        raise BlacknodeMCPError(
            "missing_source_node",
            f"Source node '{from_node}' does not exist.",
            _node_lookup_suggestion(node_meta, from_node),
            details={"from_node": from_node, "available_nodes": _node_refs(node_meta)},
        )
    if target is None:
        raise BlacknodeMCPError(
            "missing_target_node",
            f"Target node '{to_node}' does not exist.",
            _node_lookup_suggestion(node_meta, to_node),
            details={"to_node": to_node, "available_nodes": _node_refs(node_meta)},
        )

    source_outputs = list(source.get("outputs", []))
    target_inputs = list(target.get("inputs", []))
    if from_port not in source_outputs:
        raise BlacknodeMCPError(
            "invalid_source_port",
            f"Node '{from_node}' ({source.get('type')}) has no output port "
            f"'{from_port}'. Available outputs: {source_outputs}.",
            _port_lookup_suggestion(source, from_port, direction="output"),
            details={"node": from_node, "requested_port": from_port, "available_outputs": source_outputs},
        )
    if to_port not in target_inputs:
        raise BlacknodeMCPError(
            "invalid_target_port",
            f"Node '{to_node}' ({target.get('type')}) has no input port "
            f"'{to_port}'. Available inputs: {target_inputs}.",
            _port_lookup_suggestion(target, to_port, direction="input"),
            details={"node": to_node, "requested_port": to_port, "available_inputs": target_inputs},
        )

    from_type = str((source.get("output_types") or {}).get(from_port, "Any"))
    to_type = str((target.get("input_types") or {}).get(to_port, "Any"))
    if not ports_compatible(from_type, to_type):
        raise BlacknodeMCPError(
            "incompatible_port_types",
            f"Incompatible port types: '{from_node}.{from_port}' is {from_type}, "
            f"'{to_node}.{to_port}' is {to_type}.",
            _type_compatibility_suggestion(source, target, from_type, to_type),
            details={
                "from": f"{from_node}.{from_port}",
                "from_type": from_type,
                "to": f"{to_node}.{to_port}",
                "to_type": to_type,
            },
        )

    new_workflow.setdefault("edges", []).append({
        "from": from_node,
        "from_port": from_port,
        "to": to_node,
        "to_port": to_port,
    })
    report = _validate_summary(new_workflow)
    if not report.get("ok"):
        issue = (report.get("errors") or [{}])[0]
        raise BlacknodeMCPError(
            str(issue.get("code") or "invalid_connection"),
            f"Connection would make the workflow invalid: {issue.get('message') or report}",
            str(issue.get("suggestion") or "Inspect validate_workflow output, remove the bad edge, and reconnect using compatible ports."),
            details={"validation": report},
        )
    return {"workflow": new_workflow, "validation": report}


def validate_workflow_tool(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Run full schema + port-type validation against the workflow schema."""
    learned_registry.sync_with_disk()
    return _validation_with_suggestions(workflow)


def run_workflow_tool(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the workflow and return the cooked value plus run event log."""
    learned_registry.sync_with_disk()
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


def create_node_type(
    name: str,
    description: str,
    inputs: list[str],
    outputs: list[str],
    code: str,
    requires_network: bool = False,
) -> dict[str, Any]:
    """
    Create a new permanent learned Blacknode node type.

    Learned node source is written to disk, registered into the normal node
    registry, and executed only through the Docker-backed learned-node wrapper.
    """
    learned_registry.sync_with_disk()
    consent = _ensure_learned_nodes_consent()
    if consent is not None:
        return consent

    validation = _validate_create_node_type_inputs(
        name=name,
        description=description,
        inputs=inputs,
        outputs=outputs,
        code=code,
    )
    if validation is not None:
        return validation

    base = learned_registry.learned_dir()
    node_dir = base / name
    manifest = {
        "name": name,
        "description": description,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "permissions": {"network": bool(requires_network)},
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "created_by": "claude-via-mcp",
        "schema_version": 1,
    }
    validate_manifest(manifest)

    try:
        node_dir.mkdir(parents=True, exist_ok=False)
        (node_dir / "node.py").write_text(code, encoding="utf-8")
        (node_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        learned_registry.register_one(name, learned_dir=base)
    except Exception as exc:
        if node_dir.exists():
            shutil.rmtree(node_dir)
        learned_registry.unregister_one(name)
        return {"status": "rejected", "reason": f"Failed to create learned node: {exc}"}

    _notify_learned_node_event("learned_node_added", name)
    return {"status": "created", "node_type": name, "path": str(node_dir)}


def list_learned_nodes() -> dict[str, Any]:
    """List learned nodes currently present on disk."""
    learned_registry.sync_with_disk()
    nodes: list[dict[str, Any]] = []
    base = learned_registry.learned_dir()
    if base.exists():
        for manifest_path in sorted(base.glob("*/manifest.json")):
            try:
                manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")), path=manifest_path)
            except Exception as exc:
                _LOGGER.warning("Skipping invalid learned node manifest %s: %s", manifest_path, exc)
                continue
            nodes.append({
                "name": manifest.name,
                "description": manifest.description,
                "inputs": list(manifest.inputs),
                "outputs": list(manifest.outputs),
                "permissions": dict(manifest.permissions),
                "created_at": manifest.created_at,
            })
    return {"nodes": nodes, "count": len(nodes)}


def delete_learned_node(name: str, confirm: bool = False, *, notify_editor: bool = True) -> dict[str, Any]:
    """Remove one learned node from disk and unregister it."""
    learned_registry.sync_with_disk()
    if not confirm:
        return {
            "status": "rejected",
            "reason": "delete_learned_node requires confirm=True",
        }
    if not _is_valid_learned_name(name):
        return {"status": "rejected", "reason": "Invalid learned node name"}

    fn = _NODE_REGISTRY.get(name)
    if fn is not None and getattr(fn, "_bn_source", None) != "learned":
        return {"status": "rejected", "reason": f"'{name}' is a built-in node and cannot be deleted"}

    node_dir = learned_registry.learned_dir() / name
    if not node_dir.exists():
        return {"status": "not_found", "node_type": name}

    learned_registry.unregister_one(name)
    shutil.rmtree(node_dir)
    if notify_editor:
        _notify_learned_node_event("learned_node_deleted", name)
    return {"status": "deleted", "node_type": name}


def get_learned_node_source(name: str) -> dict[str, Any]:
    """Return the Python source for one learned node."""
    if not _is_valid_learned_name(name):
        return {"status": "rejected", "reason": "Invalid learned node name"}

    source_path = learned_registry.learned_dir() / name / "node.py"
    if not source_path.is_file():
        return {"status": "not_found", "node_type": name}
    return {
        "status": "ok",
        "node_type": name,
        "path": str(source_path),
        "source": source_path.read_text(encoding="utf-8"),
    }


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


def _validate_create_node_type_inputs(
    *,
    name: str,
    description: str,
    inputs: list[str],
    outputs: list[str],
    code: str,
) -> dict[str, Any] | None:
    if not _is_valid_learned_name(name):
        return {
            "status": "rejected",
            "reason": "name must match ^[A-Z][A-Za-z0-9]*$ and be 3-40 characters",
        }
    if name in _NODE_REGISTRY:
        return {"status": "rejected", "reason": f"Node type '{name}' already exists"}
    if (learned_registry.learned_dir() / name).exists():
        return {"status": "rejected", "reason": f"Learned node '{name}' already exists on disk"}

    if not isinstance(description, str) or not (10 <= len(description) <= 200):
        return {"status": "rejected", "reason": "description must be 10-200 characters"}

    port_error = _validate_port_declarations(inputs, "inputs", allow_empty=True)
    if port_error is not None:
        return port_error
    port_error = _validate_port_declarations(outputs, "outputs", allow_empty=False)
    if port_error is not None:
        return port_error

    static_result = check_safe(code)
    if not static_result.safe:
        return {"status": "rejected", "reason": static_result.reason}

    run_error = _validate_run_function_signature(code, _port_names(inputs))
    if run_error is not None:
        return run_error

    return None


def _validate_port_declarations(
    ports: Any,
    field: str,
    *,
    allow_empty: bool,
) -> dict[str, Any] | None:
    if not isinstance(ports, list):
        return {"status": "rejected", "reason": f"{field} must be a list"}
    if not ports and not allow_empty:
        return {"status": "rejected", "reason": f"{field} must declare at least one port"}
    names: set[str] = set()
    for port in ports:
        if not isinstance(port, str) or not PORT_RE.match(port):
            return {
                "status": "rejected",
                "reason": f"{field} entries must match 'name:Type'",
            }
        port_name, port_type = port.split(":", 1)
        if port_name in names:
            return {"status": "rejected", "reason": f"duplicate {field} port '{port_name}'"}
        if port_type not in ALLOWED_PORT_TYPES:
            return {
                "status": "rejected",
                "reason": f"Port type '{port_type}' not in allowed set: {_ALLOWED_PORT_TYPES_DISPLAY}",
            }
        names.add(port_name)
    return None


def _validate_run_function_signature(code: str, expected_params: list[str]) -> dict[str, Any] | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"status": "rejected", "reason": f"Syntax error: {exc.msg} at line {exc.lineno}"}

    run_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    ]
    if not run_functions:
        return {"status": "rejected", "reason": "Generated node must define def run(...)"}

    args = run_functions[0].args
    if args.vararg is not None or args.kwarg is not None:
        return {"status": "rejected", "reason": "run parameters must match input ports exactly"}

    actual_params = [
        *(arg.arg for arg in args.posonlyargs),
        *(arg.arg for arg in args.args),
        *(arg.arg for arg in args.kwonlyargs),
    ]
    if actual_params != expected_params:
        return {
            "status": "rejected",
            "reason": (
                "run parameters must match input ports exactly: "
                f"expected {expected_params}, got {actual_params}"
            ),
        }
    return None


def _ensure_learned_nodes_consent() -> dict[str, Any] | None:
    consent_file = _learned_consent_file()
    if consent_file.is_file():
        return None

    raw = os.environ.get(_LEARNED_CONSENT_ENV)
    if raw is None:
        consent_file = _learned_consent_file()
        return {
            "status": "rejected",
            "reason": (
                "Learned nodes let MCP-connected agents create new permanent Python node "
                "code that will execute on your machine in a Docker sandbox. To opt in, "
                "set BLACKNODE_LEARNED_NODES_CONSENT=1 and call create_node_type again. "
                f"On opt-in, consent is saved to {consent_file}; delete that file to revoke it."
            ),
        }
    if not _truthy(raw):
        return {
            "status": "rejected",
            "reason": "BLACKNODE_LEARNED_NODES_CONSENT must be set to 1/true/yes to enable learned nodes",
        }

    consent_file.parent.mkdir(parents=True, exist_ok=True)
    consent_file.write_text(
        json.dumps({
            "accepted": True,
            "accepted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": _LEARNED_CONSENT_ENV,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return None


def _learned_consent_file() -> Path:
    config_dir = os.environ.get("BLACKNODE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir).expanduser().resolve() / _LEARNED_CONSENT_FILE
    return Path.home() / ".blacknode" / _LEARNED_CONSENT_FILE


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_valid_learned_name(name: str) -> bool:
    return isinstance(name, str) and 3 <= len(name) <= 40 and bool(_LEARNED_NAME_RE.match(name))


def _port_names(ports: list[str]) -> list[str]:
    return [port.split(":", 1)[0] for port in ports]


def _notify_learned_node_event(event_type: str, name: str) -> None:
    base_url = (os.environ.get("BLACKNODE_EDITOR_URL") or "http://127.0.0.1:7777").rstrip("/")
    payload = json.dumps({"name": name}).encode("utf-8")
    path = "/internal/learned-node-deleted" if event_type == "learned_node_deleted" else "/internal/learned-node-added"
    req = urllib_request.Request(
        f"{base_url}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=1):
            pass
    except Exception as exc:
        _LOGGER.info("Could not notify editor about %s for %s: %s", event_type, name, exc)


def _notify_learned_node_added(name: str) -> None:
    _notify_learned_node_event("learned_node_added", name)


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


def _format_mcp_error(
    code: str,
    message: str,
    suggestion: str,
    details: Mapping[str, Any],
) -> str:
    detail_text = f" Details: {json.dumps(details, default=str)}" if details else ""
    return f"[{code}] {message} Suggestion: {suggestion}{detail_text}"


def _node_refs(node_meta: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for node_id, meta in node_meta.items():
        node_type = meta.get("type") if isinstance(meta, Mapping) else "Unknown"
        refs.append(f"{node_id}({node_type})")
    return refs


def _node_lookup_suggestion(node_meta: Mapping[str, Any], requested: str) -> str:
    closest = _closest_string(requested, [str(node_id) for node_id in node_meta])
    if closest:
        return f"Use existing node id '{closest}', or call add_node first and pass the returned node_id."
    return "Call add_node first and pass the returned node_id into connect_nodes."


def _port_lookup_suggestion(meta: Mapping[str, Any], requested: str, *, direction: str) -> str:
    key = "outputs" if direction == "output" else "inputs"
    ports = [str(port) for port in meta.get(key, [])]
    closest = _closest_string(requested, ports)
    if closest:
        return f"Use port '{closest}', or call get_node_schema('{meta.get('type')}') before connecting."
    if ports:
        return f"Use one of {ports}, or call get_node_schema('{meta.get('type')}') before connecting."
    return f"This node has no {direction} ports. Choose a different node or add an adapter node."


def _type_compatibility_suggestion(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    from_type: str,
    to_type: str,
) -> str:
    compatible_inputs = [
        port
        for port, port_type in (target.get("input_types") or {}).items()
        if ports_compatible(from_type, str(port_type))
    ]
    if compatible_inputs:
        return f"Connect to one of the compatible inputs on {target.get('type')}: {compatible_inputs}."

    source_type = source.get("type")
    target_type = target.get("type")
    if from_type != "Text" and to_type == "Text":
        return "Convert the value to Text first, for example with JSONDump for Dict/List data or a custom PythonFn adapter."
    if from_type == "Text" and to_type in {"Dict", "List"}:
        return "Parse the Text first with JSONParse or add a PythonFn adapter that returns the required structured type."
    if to_type == "Bool":
        return "Use a Bool-producing node or add a PythonFn predicate before Branch/Gate-style control nodes."
    return (
        f"Do not connect {source_type} {from_type} output directly to {target_type} {to_type} input. "
        "Call list_nodes/get_node_schema and insert a converter, router, or node with an Any-compatible input."
    )


def _validation_with_suggestions(workflow: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_workflow(workflow).to_dict()
    node_meta = workflow.get("node_meta") if isinstance(workflow, Mapping) else {}
    nodes = node_meta if isinstance(node_meta, Mapping) else {}
    for issue in report.get("errors", []):
        if isinstance(issue, dict):
            issue.setdefault("suggestion", _suggestion_for_issue(issue, nodes))
    for issue in report.get("warnings", []):
        if isinstance(issue, dict):
            issue.setdefault("suggestion", _suggestion_for_issue(issue, nodes))
    return report


def _suggestion_for_issue(issue: Mapping[str, Any], nodes: Mapping[str, Any]) -> str:
    code = str(issue.get("code") or "")
    path = str(issue.get("path") or "")
    if code in {"missing_source_node", "missing_target_node", "missing_entrypoint_node"}:
        return f"Use an existing node id. Available nodes: {_node_refs(nodes)}."
    if code in {"invalid_source_port", "invalid_target_port", "invalid_entrypoint_port"}:
        node_id = _node_id_from_issue_path(path)
        if node_id and node_id in nodes and isinstance(nodes[node_id], Mapping):
            meta = nodes[node_id]
            return f"Call get_node_schema('{meta.get('type')}') and use one of inputs={meta.get('inputs', [])}, outputs={meta.get('outputs', [])}."
        return "Call get_node_schema for the node type and use a real input/output port."
    if code == "incompatible_port_types":
        return "Insert a converter node or reconnect to a port whose type is compatible. Text can flow to Text/Any; structured data usually needs JSONParse/JSONDump or PythonFn."
    if code == "cycle_detected":
        return "Remove the back-edge. Blacknode workflows are DAGs: data should flow toward Output/SubnetOutput nodes only."
    if code in {"missing_output_node", "missing_subgraph_output_node"}:
        return "Add an Output/SubnetOutput node or set an explicit entrypoint."
    if code == "runtime_status_in_workflow":
        return "Remove cookResult, cookError, cooking, and cookPort before saving or sending workflow JSON."
    return "Fix the field named by path, then call validate_workflow again before running or exporting."


def _node_id_from_issue_path(path: str) -> str | None:
    marker = ".node_meta."
    if marker not in path:
        return None
    tail = path.split(marker, 1)[1]
    return tail.split(".", 1)[0]


def _closest_string(value: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    value_lower = value.lower()
    for candidate in candidates:
        if candidate.lower() == value_lower:
            return candidate
    for candidate in candidates:
        candidate_lower = candidate.lower()
        if value_lower in candidate_lower or candidate_lower in value_lower:
            return candidate
    return candidates[0] if len(candidates) == 1 else None


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
    return _validation_with_suggestions(workflow)
