"""Blacknode editor backend — FastAPI server the React editor talks to."""
from __future__ import annotations
import uuid, os, sys, json, threading, re, queue, io, contextlib, time, subprocess, importlib, signal
from datetime import datetime
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import blacknode as bn
import blacknode.integrations  # noqa: F401  registers chat drivers (slack/telegram)
from blacknode.discovery import discover_node_modules, load_node_file
from blacknode.integrations import registry as driver_registry
from blacknode.exporters import export_workflow as export_framework_workflow
from blacknode.exporters import list_export_targets
from blacknode.learned import registry as learned_registry
from blacknode.mcp import tools as mcp_tools
from blacknode.node import _NODE_REGISTRY
from blacknode.nodes import ai as ai_nodes
from blacknode.packages import discover_packages as discover_bn_packages
from blacknode.packages import installed_packages, package_category_colors, package_template_dirs
from blacknode.python_importer import import_workflow_python
from blacknode.workflow import validate_graph as validate_bn_graph
from blacknode.workflow import validate_workflow as validate_bn_workflow

from run_store import RunStore

app = FastAPI(title="Blacknode Editor Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Persistence ───────────────────────────────────────────────────────────────

_SAVE_PATH      = os.path.join(os.path.dirname(__file__), "blacknode_graph.json")
_WORKFLOWS_DIR  = os.path.join(os.path.dirname(__file__), "..", "workflows")
_TEMPLATES_DIR  = os.path.join(os.path.dirname(__file__), "..", "templates")
_CUSTOM_NODES_DIR = os.path.join(os.path.dirname(__file__), "..", "custom-nodes")
_RUNS_DIR       = os.path.join(os.path.dirname(__file__), "runs")
_run_store      = RunStore(_RUNS_DIR)
_save_timer: threading.Timer | None = None
_SUBGRAPH_NODE_TYPES = {"Subnet", "SubnetAsTool", "VisualAgentLoop"}
_TOOLBOX_NODE_TYPES = {"ToolBox"}
_DYNAMIC_PORT_TYPES = {*_SUBGRAPH_NODE_TYPES, "SubnetInput", "SubnetOutput", *_TOOLBOX_NODE_TYPES}
_WORKFLOW_KIND = "blacknode.workflow"
_WORKFLOW_SCHEMA_VERSION = 1
_SECRET_FIELD_RE = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.I)


def _migrate_legacy_node_meta(meta: dict) -> bool:
    changed = False
    if meta.get("type") == "LoadImage":
        params = meta.setdefault("params", {})
        defaults = meta.setdefault("input_defaults", {})
        if params.get("max_size") == 768 and defaults.get("max_size") == 768:
            params["max_size"] = 0
            changed = True
        if defaults.get("max_size") == 768:
            defaults["max_size"] = 0
            changed = True

    subgraph = meta.get("subgraph")
    if isinstance(subgraph, dict):
        inner_meta = subgraph.get("node_meta")
        if isinstance(inner_meta, dict):
            for child in inner_meta.values():
                if isinstance(child, dict):
                    changed = _migrate_legacy_node_meta(child) or changed
    return changed


def _save_now() -> None:
    try:
        with open(_SAVE_PATH, "w") as f:
            json.dump({"node_meta": _session.node_meta,
                       "edges":     _session.graph._edges}, f, indent=2)
    except Exception as e:
        print(f"[blacknode] save error: {e}")


def _save(debounce: float = 0.0) -> None:
    """Write graph to disk. Pass debounce > 0 to coalesce rapid calls (e.g. node drag)."""
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
    if debounce > 0:
        _save_timer = threading.Timer(debounce, _save_now)
        _save_timer.daemon = True
        _save_timer.start()
    else:
        _save_now()


def _load() -> None:
    if not os.path.exists(_SAVE_PATH):
        return
    try:
        with open(_SAVE_PATH) as f:
            data = json.load(f)
        meta_map: dict = data.get("node_meta", {})
        edges:    list = data.get("edges",     [])
        # only restore nodes whose type is still registered
        migrated = False
        for node_id, meta in meta_map.items():
            if meta["type"] not in _NODE_REGISTRY and meta["type"] not in _SUBGRAPH_NODE_TYPES:
                continue
            migrated = _migrate_legacy_node_meta(meta) or migrated
            if meta["type"] in _SUBGRAPH_NODE_TYPES:
                _sync_subgraph_node_ports(meta)
            elif meta["type"] in _TOOLBOX_NODE_TYPES:
                _sync_toolbox_ports(meta, edges)
            _session.node_meta[node_id] = meta
            node_entry = {
                "type":   meta["type"],
                "params": dict(meta.get("params", {})),
            }
            if meta["type"] in _SUBGRAPH_NODE_TYPES:
                node_entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
            _session.graph._nodes[node_id] = node_entry
            _session.graph._dirty.add(node_id)
        _session.graph._edges = [
            e for e in edges
            if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
        ]
        print(f"[blacknode] Loaded {len(_session.node_meta)} nodes, "
              f"{len(_session.graph._edges)} edges from {_SAVE_PATH}")
        if migrated:
            _save()
    except Exception as e:
        print(f"[blacknode] Could not load saved graph: {e}")


# ── In-memory state ───────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.graph = bn.Graph()
        self.node_meta: dict[str, dict] = {}

_session = Session()


# ── Schema models ─────────────────────────────────────────────────────────────

class AddNodeReq(BaseModel):
    type_name: str
    params: dict[str, Any] = {}
    pos: tuple[float, float] = (0.0, 0.0)

class ConnectReq(BaseModel):
    from_id: str
    from_port: str
    to_id: str
    to_port: str

class UpdateParamReq(BaseModel):
    key: str
    value: Any

class UpdatePortsReq(BaseModel):
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    input_types: dict[str, str] | None = None
    output_types: dict[str, str] | None = None
    input_defaults: dict[str, Any] | None = None
    multi_input_ports: list[str] | None = None

class CookReq(BaseModel):
    node_id: str
    port: str = "output"

class CookTargetReq(BaseModel):
    node_id: str
    port: str = "output"

class CookGraphReq(BaseModel):
    targets: list[CookTargetReq]

class SetGraphReq(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

class ExecNodeReq(BaseModel):
    code: str

class SaveCustomNodeReq(BaseModel):
    filename: str = "custom_node.py"
    code: str

class SetApiKeyReq(BaseModel):
    provider: str
    key: str

class SaveWorkflowReq(BaseModel):
    name: str
    previous_slug: str | None = None

class RenameWorkflowReq(BaseModel):
    name: str

class NewWorkflowTabReq(BaseModel):
    name: str = "Untitled"

class OpenWorkflowTabReq(BaseModel):
    name: str | None = None
    workflow: dict[str, Any]
    organize: bool = True

class CookEditorNodeReq(BaseModel):
    node_id: str
    port: str = "value"

class LoadSavedWorkflowTabReq(BaseModel):
    slug: str
    name: str | None = None
    organize: bool = True

class RenameEditorTabReq(BaseModel):
    name: str

class LearnedNodeEventReq(BaseModel):
    name: str

class UpdateSubgraphReq(BaseModel):
    node_meta: dict[str, Any] = {}
    edges: list[dict[str, Any]] = []

class CollapseSubnetReq(BaseModel):
    node_ids: list[str]
    label: str = "Subnet"

class FrameworkExportReq(BaseModel):
    target: str
    workflow: dict[str, Any] | None = None

class ExportWorkflowReq(BaseModel):
    workflow: dict[str, Any] | None = None

class ImportPythonReq(BaseModel):
    code: str
    name: str = "Imported Python Workflow"

class SyncRunReq(BaseModel):
    node_id: str
    port: str = "output"
    node_type: str = "ExternalPython"
    workflow: dict[str, Any] | None = None

class SyncEventReq(BaseModel):
    run_id: str
    event: dict[str, Any]

class SyncFinishReq(BaseModel):
    status: str = "success"
    value: Any = None
    error: str | None = None

_PROVIDER_ENV: dict[str, str] = {
    "Anthropic":     "ANTHROPIC_API_KEY",
    "OpenAI":        "OPENAI_API_KEY",
    "NVIDIA NIM":    "NVIDIA_API_KEY",
    "Ollama (local)": "",
}

_KEYS_PATH = os.path.join(os.path.dirname(__file__), "api_keys.json")
_api_keys: dict[str, str] = {}
_editor_action_queue: list[dict[str, Any]] = []
_editor_action_lock = threading.Lock()
_learned_node_event_subscribers: list[queue.Queue] = []
_learned_node_event_lock = threading.Lock()
_active_cook_lock = threading.Lock()
_active_cook_stop: threading.Event | None = None


class _CookStopped(Exception):
    pass


def _prepare_cook() -> threading.Event:
    global _active_cook_stop
    with _active_cook_lock:
        if _active_cook_stop is not None:
            _active_cook_stop.set()
        _active_cook_stop = threading.Event()
        return _active_cook_stop


def _stop_active_cook() -> None:
    with _active_cook_lock:
        if _active_cook_stop is not None:
            _active_cook_stop.set()


def _raise_if_stopped(stop_event: threading.Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise _CookStopped("stopped")


def _load_api_keys() -> None:
    global _api_keys
    if not os.path.exists(_KEYS_PATH):
        return
    try:
        with open(_KEYS_PATH) as f:
            _api_keys = json.load(f)
        for provider, key in _api_keys.items():
            env_var = _PROVIDER_ENV.get(provider)
            if env_var and key:
                os.environ[env_var] = key
        loaded = [p for p, k in _api_keys.items() if k]
        if loaded:
            print(f"[blacknode] Loaded API keys for: {', '.join(loaded)}")
    except Exception as e:
        print(f"[blacknode] Could not load api_keys.json: {e}")


def _save_api_keys() -> None:
    try:
        with open(_KEYS_PATH, "w") as f:
            json.dump(_api_keys, f, indent=2)
    except Exception as e:
        print(f"[blacknode] Could not save api_keys.json: {e}")


def _api_key_status() -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for provider, env_var in _PROVIDER_ENV.items():
        saved = bool(_api_keys.get(provider))
        environment = bool(env_var and os.environ.get(env_var))
        source = "saved" if saved else "environment" if environment else "missing"
        status[provider] = {
            "configured": saved or environment or not env_var,
            "source": source if env_var else "local",
            "env_var": env_var,
        }
    return status


_load_api_keys()

# ── Custom model persistence ──────────────────────────────────────────────────

_CUSTOM_MODELS_PATH = os.path.join(os.path.dirname(__file__), "custom_models.json")
_custom_models: list[str] = []


def _load_custom_models() -> None:
    global _custom_models
    if not os.path.exists(_CUSTOM_MODELS_PATH):
        return
    try:
        with open(_CUSTOM_MODELS_PATH) as f:
            _custom_models = json.load(f)
    except Exception as e:
        print(f"[blacknode] Could not load custom_models.json: {e}")


def _save_custom_models() -> None:
    try:
        with open(_CUSTOM_MODELS_PATH, "w") as f:
            json.dump(_custom_models, f, indent=2)
    except Exception as e:
        print(f"[blacknode] Could not save custom_models.json: {e}")


class AddCustomModelReq(BaseModel):
    value: str


_load_custom_models()


def _toolbox_port_sort_key(port: str) -> tuple[int, str]:
    match = re.fullmatch(r"tool_(\d+)", str(port))
    return (int(match.group(1)), str(port)) if match else (999_999, str(port))


def _sync_toolbox_ports(toolbox_meta: dict, edges: list[dict] | None = None) -> None:
    """Keep ToolBox metadata dynamic and remove disconnected tool slots."""
    fn = _NODE_REGISTRY.get("ToolBox")
    inputs = [
        str(port)
        for port in list(toolbox_meta.get("inputs") or [])
        if str(port).startswith("tool_")
    ]
    if edges is not None:
        connected = sorted({
            str(e.get("to_port"))
            for e in edges
            if e.get("to") == toolbox_meta.get("id") and str(e.get("to_port", "")).startswith("tool_")
        }, key=_toolbox_port_sort_key)
        inputs = connected

    input_types = dict(toolbox_meta.get("input_types", {}))
    toolbox_meta["inputs"] = inputs
    toolbox_meta["input_types"] = {port: input_types.get(port, "Fn") for port in inputs}
    toolbox_meta["outputs"] = getattr(fn, "_bn_outputs", ["tools"])
    toolbox_meta["output_types"] = getattr(fn, "_bn_output_types", {"tools": "List"})
    toolbox_meta["input_defaults"] = {}


def _default_visual_agent_loop_subgraph() -> dict:
    node_meta = {
        "loop_in": {
            "id": "loop_in", "type": "SubnetInput", "params": {},
            "pos": [40, 220],
            "inputs": [],
            "outputs": ["prompt", "system", "model", "tools", "max_tokens", "max_iter"],
            "input_types": {},
            "output_types": {
                "prompt": "Text",
                "system": "Text",
                "model": "Model",
                "tools": "List",
                "max_tokens": "Int",
                "max_iter": "Int",
            },
            "input_defaults": {},
        },
        "messages": {
            "id": "messages", "type": "AgentMessages", "params": {},
            "pos": [300, 120],
            "inputs": ["prompt"],
            "outputs": ["messages"],
            "input_types": {"prompt": "Text"},
            "output_types": {"messages": "List"},
            "input_defaults": {},
        },
        "chat": {
            "id": "chat", "type": "AgentChatStep", "params": {},
            "pos": [560, 100],
            "inputs": ["messages", "system", "model", "tools", "max_tokens"],
            "outputs": ["assistant_text", "tool_calls", "stop_reason", "step"],
            "input_types": {
                "messages": "List",
                "system": "Text",
                "model": "Model",
                "tools": "List",
                "max_tokens": "Int",
            },
            "output_types": {
                "assistant_text": "Text",
                "tool_calls": "List",
                "stop_reason": "Text",
                "step": "Dict",
            },
            "input_defaults": {"model": "claude-sonnet-4-6", "max_tokens": 1024},
        },
        "iteration": {
            "id": "iteration", "type": "AgentIteration", "params": {"start": 1},
            "pos": [560, 360],
            "inputs": ["start"],
            "outputs": ["iteration"],
            "input_types": {"start": "Int"},
            "output_types": {"iteration": "Int"},
            "input_defaults": {"start": 1},
        },
        "dispatch": {
            "id": "dispatch", "type": "ToolDispatch", "params": {},
            "pos": [840, 80],
            "inputs": ["tool_calls", "tools"],
            "outputs": ["tool_results", "steps"],
            "input_types": {"tool_calls": "List", "tools": "List"},
            "output_types": {"tool_results": "List", "steps": "List"},
            "input_defaults": {},
        },
        "stop": {
            "id": "stop", "type": "AgentStopCheck", "params": {},
            "pos": [840, 330],
            "inputs": ["stop_reason", "tool_calls", "iteration", "max_iter"],
            "outputs": ["continue", "done", "reason"],
            "input_types": {
                "stop_reason": "Text",
                "tool_calls": "List",
                "iteration": "Int",
                "max_iter": "Int",
            },
            "output_types": {"continue": "Bool", "done": "Bool", "reason": "Text"},
            "input_defaults": {"iteration": 1, "max_iter": 5},
        },
        "append": {
            "id": "append", "type": "AgentAppendMessages", "params": {},
            "pos": [1120, 120],
            "inputs": ["messages", "model", "assistant_text", "tool_calls", "tool_results"],
            "outputs": ["messages"],
            "input_types": {
                "messages": "List",
                "model": "Model",
                "assistant_text": "Text",
                "tool_calls": "List",
                "tool_results": "List",
            },
            "output_types": {"messages": "List"},
            "input_defaults": {"model": "claude-sonnet-4-6"},
        },
        "final": {
            "id": "final", "type": "AgentFinalAnswer", "params": {},
            "pos": [1400, 150],
            "inputs": ["messages", "system", "model", "max_tokens", "assistant_text", "stop_reason", "reason", "tool_calls"],
            "outputs": ["result", "step"],
            "input_types": {
                "messages": "List",
                "system": "Text",
                "model": "Model",
                "max_tokens": "Int",
                "assistant_text": "Text",
                "stop_reason": "Text",
                "reason": "Text",
                "tool_calls": "List",
            },
            "output_types": {"result": "Text", "step": "Dict"},
            "input_defaults": {"model": "claude-sonnet-4-6", "max_tokens": 1024},
        },
        "loop_out": {
            "id": "loop_out", "type": "SubnetOutput", "params": {},
            "pos": [1680, 180],
            "inputs": ["result", "steps"],
            "outputs": [],
            "input_types": {"result": "Text", "steps": "List"},
            "output_types": {},
            "input_defaults": {},
        },
    }
    edges = [
        {"from": "loop_in", "from_port": "prompt", "to": "messages", "to_port": "prompt"},
        {"from": "messages", "from_port": "messages", "to": "chat", "to_port": "messages"},
        {"from": "loop_in", "from_port": "system", "to": "chat", "to_port": "system"},
        {"from": "loop_in", "from_port": "model", "to": "chat", "to_port": "model"},
        {"from": "loop_in", "from_port": "tools", "to": "chat", "to_port": "tools"},
        {"from": "loop_in", "from_port": "max_tokens", "to": "chat", "to_port": "max_tokens"},
        {"from": "chat", "from_port": "tool_calls", "to": "dispatch", "to_port": "tool_calls"},
        {"from": "loop_in", "from_port": "tools", "to": "dispatch", "to_port": "tools"},
        {"from": "messages", "from_port": "messages", "to": "append", "to_port": "messages"},
        {"from": "loop_in", "from_port": "model", "to": "append", "to_port": "model"},
        {"from": "chat", "from_port": "assistant_text", "to": "append", "to_port": "assistant_text"},
        {"from": "chat", "from_port": "tool_calls", "to": "append", "to_port": "tool_calls"},
        {"from": "dispatch", "from_port": "tool_results", "to": "append", "to_port": "tool_results"},
        {"from": "chat", "from_port": "stop_reason", "to": "stop", "to_port": "stop_reason"},
        {"from": "chat", "from_port": "tool_calls", "to": "stop", "to_port": "tool_calls"},
        {"from": "iteration", "from_port": "iteration", "to": "stop", "to_port": "iteration"},
        {"from": "loop_in", "from_port": "max_iter", "to": "stop", "to_port": "max_iter"},
        {"from": "append", "from_port": "messages", "to": "final", "to_port": "messages"},
        {"from": "loop_in", "from_port": "system", "to": "final", "to_port": "system"},
        {"from": "loop_in", "from_port": "model", "to": "final", "to_port": "model"},
        {"from": "loop_in", "from_port": "max_tokens", "to": "final", "to_port": "max_tokens"},
        {"from": "chat", "from_port": "assistant_text", "to": "final", "to_port": "assistant_text"},
        {"from": "chat", "from_port": "stop_reason", "to": "final", "to_port": "stop_reason"},
        {"from": "chat", "from_port": "tool_calls", "to": "final", "to_port": "tool_calls"},
        {"from": "stop", "from_port": "reason", "to": "final", "to_port": "reason"},
        {"from": "final", "from_port": "result", "to": "loop_out", "to_port": "result"},
        {"from": "dispatch", "from_port": "steps", "to": "loop_out", "to_port": "steps"},
    ]
    return {"node_meta": node_meta, "edges": edges}


def _ensure_edge(edges: list[dict], from_id: str, from_port: str, to_id: str, to_port: str) -> None:
    if not any(
        e.get("from") == from_id
        and e.get("from_port") == from_port
        and e.get("to") == to_id
        and e.get("to_port") == to_port
        for e in edges
    ):
        edges.append({"from": from_id, "from_port": from_port, "to": to_id, "to_port": to_port})


def _migrate_visual_agent_loop_subgraph(subnet_meta: dict) -> None:
    subgraph = subnet_meta.setdefault("subgraph", {"node_meta": {}, "edges": []})
    inner_meta = subgraph.setdefault("node_meta", {})
    edges = subgraph.setdefault("edges", [])

    if "iter_one" in inner_meta and "iteration" not in inner_meta:
        old = inner_meta.pop("iter_one")
        inner_meta["iteration"] = {
            **old,
            "id": "iteration",
            "type": "AgentIteration",
            "params": {"start": old.get("params", {}).get("value", 1)},
            "inputs": ["start"],
            "outputs": ["iteration"],
            "input_types": {"start": "Int"},
            "output_types": {"iteration": "Int"},
            "input_defaults": {"start": 1},
        }
        for edge in edges:
            if edge.get("from") == "iter_one":
                edge["from"] = "iteration"
            if edge.get("from") == "iteration" and edge.get("from_port") == "value":
                edge["from_port"] = "iteration"

    final = inner_meta.get("final")
    if final:
        final["inputs"] = ["messages", "system", "model", "max_tokens", "assistant_text", "stop_reason", "reason", "tool_calls"]
        final["input_types"] = {
            **final.get("input_types", {}),
            "messages": "List",
            "system": "Text",
            "model": "Model",
            "max_tokens": "Int",
            "assistant_text": "Text",
            "stop_reason": "Text",
            "reason": "Text",
            "tool_calls": "List",
        }
        final["input_defaults"] = {**final.get("input_defaults", {}), "model": "claude-sonnet-4-6", "max_tokens": 1024}

    _ensure_edge(edges, "chat", "assistant_text", "append", "assistant_text")
    _ensure_edge(edges, "iteration", "iteration", "stop", "iteration")
    _ensure_edge(edges, "chat", "assistant_text", "final", "assistant_text")
    _ensure_edge(edges, "chat", "stop_reason", "final", "stop_reason")
    _ensure_edge(edges, "chat", "tool_calls", "final", "tool_calls")
    _ensure_edge(edges, "stop", "reason", "final", "reason")


def _sync_subgraph_node_ports(subnet_meta: dict) -> None:
    """Rebuild a Subnet node's inputs/outputs from its single boundary nodes.

    SubnetInput outputs  → outer Subnet inputs
    SubnetOutput inputs  → outer Subnet outputs
    """
    subnet_meta.setdefault("subgraph", {"node_meta": {}, "edges": []})
    if subnet_meta.get("type") == "SubnetAsTool":
        params = subnet_meta.setdefault("params", {})
        params["name"] = params.get("name") or params.get("subnet_label") or params.get("label") or "tool"
        params.setdefault("description", "")
        fn = _NODE_REGISTRY.get("SubnetAsTool")
        subnet_meta["inputs"]         = getattr(fn, "_bn_inputs", ["name", "description"])
        subnet_meta["outputs"]        = getattr(fn, "_bn_outputs", ["fn"])
        subnet_meta["input_types"]    = getattr(fn, "_bn_input_types", {"name": "Text", "description": "Text"})
        subnet_meta["output_types"]   = getattr(fn, "_bn_output_types", {"fn": "Fn"})
        subnet_meta["input_defaults"] = getattr(fn, "_bn_input_defaults", {"name": "tool"})
        return

    if subnet_meta.get("type") == "VisualAgentLoop":
        if not subnet_meta.get("subgraph", {}).get("node_meta"):
            subnet_meta["subgraph"] = _default_visual_agent_loop_subgraph()
        else:
            _migrate_visual_agent_loop_subgraph(subnet_meta)
        fn = _NODE_REGISTRY.get("VisualAgentLoop")
        subnet_meta["inputs"]         = getattr(fn, "_bn_inputs", [])
        subnet_meta["outputs"]        = getattr(fn, "_bn_outputs", ["result", "steps"])
        subnet_meta["input_types"]    = getattr(fn, "_bn_input_types", {})
        subnet_meta["output_types"]   = getattr(fn, "_bn_output_types", {})
        subnet_meta["input_defaults"] = getattr(fn, "_bn_input_defaults", {})
        return

    subgraph = subnet_meta.get("subgraph", {})
    inner_meta = subgraph.get("node_meta", {})
    inputs, outputs = [], []
    in_types: dict[str, str] = {}
    out_types: dict[str, str] = {}
    for m in inner_meta.values():
        if m["type"] == "SubnetInput":
            for port in m.get("outputs", []):
                if port not in inputs:
                    inputs.append(port)
                    in_types[port] = m.get("output_types", {}).get(port, "Any")
        elif m["type"] == "SubnetOutput":
            for port in m.get("inputs", []):
                if port not in outputs:
                    outputs.append(port)
                    out_types[port] = m.get("input_types", {}).get(port, "Any")
    subnet_meta["inputs"]         = inputs
    subnet_meta["outputs"]        = outputs
    subnet_meta["input_types"]    = in_types
    subnet_meta["output_types"]   = out_types
    subnet_meta["input_defaults"] = {}


def _meta_fingerprint(meta: dict) -> str:
    fields = {
        "params": meta.get("params", {}),
        "inputs": meta.get("inputs", []),
        "outputs": meta.get("outputs", []),
        "input_types": meta.get("input_types", {}),
        "output_types": meta.get("output_types", {}),
        "input_defaults": meta.get("input_defaults", {}),
        "subgraph": meta.get("subgraph", None),
    }
    return json.dumps(fields, sort_keys=True, default=str)


def _sync_dynamic_node_meta(meta: dict, edges: list[dict] | None = None) -> bool:
    """Refresh dynamic node metadata and mirror it into the runtime graph entry."""
    before = _meta_fingerprint(meta)
    if meta.get("type") in _SUBGRAPH_NODE_TYPES:
        _sync_subgraph_node_ports(meta)
    elif meta.get("type") in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta, edges)
    changed = before != _meta_fingerprint(meta)

    node_id = meta.get("id")
    if node_id in _session.graph._nodes:
        entry = _session.graph._nodes[node_id]
        entry["type"] = meta.get("type")
        entry["params"] = dict(meta.get("params", {}))
        if meta.get("type") in _SUBGRAPH_NODE_TYPES:
            entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
    return changed


def _enqueue_editor_action(action_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    action = {
        "id": str(uuid.uuid4()),
        "type": action_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "payload": payload or {},
    }
    with _editor_action_lock:
        _editor_action_queue.append(action)
        del _editor_action_queue[:-100]
    return action


def _broadcast_learned_node_event(event_type: str, name: str) -> dict[str, Any]:
    event = {
        "type": event_type,
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _learned_node_event_lock:
        subscribers = list(_learned_node_event_subscribers)
    for subscriber in subscribers:
        subscriber.put(event)
    return event


_load()   # restore last session on startup


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/node-types")
def list_node_types():
    return sorted(_NODE_REGISTRY.keys())


def _category_for_node(fn: Any) -> str:
    module = getattr(fn, "__module__", "")
    module_categories = {
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
    return getattr(fn, "_bn_category", None) or module_categories.get(module, "Custom")


def _node_def_payload(name: str, fn: Any) -> dict[str, Any]:
    doc = (getattr(fn, "_bn_description", None) or fn.__doc__ or "").strip()
    category = _category_for_node(fn)
    return {
        "type": name,
        "category": category,
        "color": package_category_colors().get(category, ""),
        "package": getattr(fn, "_bn_package", ""),
        "inputs": getattr(fn, "_bn_inputs", []),
        "outputs": getattr(fn, "_bn_outputs", ["output"]),
        "input_types": getattr(fn, "_bn_input_types", {}),
        "output_types": getattr(fn, "_bn_output_types", {}),
        "input_defaults": getattr(fn, "_bn_input_defaults", {}),
        "input_choices": getattr(fn, "_bn_input_choices", {}),
        "doc": doc.split("\n", 1)[0] if doc else "",
        "source": getattr(fn, "_bn_source_path", ""),
    }


@app.get("/node-defs")
def list_node_defs():
    return {
        name: _node_def_payload(name, fn)
        for name, fn in sorted(_NODE_REGISTRY.items())
    }

@app.get("/graph")
def get_graph():
    """Return nodes with types always read fresh from registry."""
    nodes = []
    for meta in _session.node_meta.values():
        fn = _NODE_REGISTRY.get(meta["type"])
        _sync_dynamic_node_meta(meta, _session.graph._edges)
        if meta["type"] in _DYNAMIC_PORT_TYPES or fn is None:
            nodes.append({**meta})
        else:
            nodes.append({
                **meta,
                "inputs":         getattr(fn, "_bn_inputs",         meta.get("inputs",         [])),
                "outputs":        getattr(fn, "_bn_outputs",        meta.get("outputs",        [])),
                "input_types":    getattr(fn, "_bn_input_types",    meta.get("input_types",    {})),
                "output_types":   getattr(fn, "_bn_output_types",   meta.get("output_types",   {})),
                "input_defaults": getattr(fn, "_bn_input_defaults", meta.get("input_defaults", {})),
            })
    return {"nodes": nodes, "edges": _session.graph._edges}


@app.post("/graph")
def set_graph(req: SetGraphReq):
    _restore_session_from_nodes(req.nodes, req.edges)
    _save()
    return get_graph()


@app.post("/nodes")
def add_node(req: AddNodeReq):
    if req.type_name in _SUBGRAPH_NODE_TYPES:
        node_id = str(__import__('uuid').uuid4())
        if req.type_name == "Subnet":
            params = {"label": req.params.get("label", "Subnet")}
        elif req.type_name == "SubnetAsTool":
            params = {
                "name": req.params.get("name") or req.params.get("subnet_label") or "tool",
                "description": req.params.get("description", ""),
            }
        else:
            params = dict(req.params)
        meta: dict[str, Any] = {
            "id":           node_id,
            "type":         req.type_name,
            "params":       params,
            "pos":          list(req.pos),
            "inputs":       [],
            "outputs":      [],
            "input_types":  {},
            "output_types": {},
            "input_defaults": {},
            "subgraph":     {"node_meta": {}, "edges": []},
        }
        _sync_subgraph_node_ports(meta)
        _session.node_meta[node_id] = meta
        _session.graph._nodes[node_id] = {
            "type": req.type_name,
            "params": meta["params"],
            "subgraph": meta["subgraph"],
        }
        _session.graph._dirty.add(node_id)
        _save()
        return meta
    if req.type_name not in _NODE_REGISTRY:
        raise HTTPException(400, f"Unknown node type '{req.type_name}'")
    proxy = _session.graph.node(req.type_name, **req.params)
    fn = _NODE_REGISTRY[req.type_name]
    meta = {
        "id":           proxy._id,
        "type":         req.type_name,
        "params":       req.params,
        "pos":          list(req.pos),
        "inputs":         getattr(fn, "_bn_inputs",         []),
        "outputs":        getattr(fn, "_bn_outputs",        ["output"]),
        "input_types":    getattr(fn, "_bn_input_types",    {}),
        "output_types":   getattr(fn, "_bn_output_types",   {}),
        "input_defaults": getattr(fn, "_bn_input_defaults", {}),
    }
    if req.type_name in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta)
    _session.node_meta[proxy._id] = meta
    _save()
    return meta


@app.delete("/nodes/{node_id}")
def remove_node(node_id: str):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    del _session.node_meta[node_id]
    _session.graph._edges = [
        e for e in _session.graph._edges
        if e["from"] != node_id and e["to"] != node_id
    ]
    _session.graph._nodes.pop(node_id, None)
    _session.graph._dirty.discard(node_id)
    _save()
    return {"ok": True}


@app.patch("/nodes/{node_id}/params")
def update_param(node_id: str, req: UpdateParamReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    _session.node_meta[node_id]["params"][req.key] = req.value
    _session.graph._nodes[node_id]["params"][req.key] = req.value
    _session.graph._mark_dirty(node_id)
    _save()
    return _session.node_meta[node_id]


@app.patch("/nodes/{node_id}/ports")
def update_ports(node_id: str, req: UpdatePortsReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    meta = _session.node_meta[node_id]
    if meta["type"] not in _TOOLBOX_NODE_TYPES:
        raise HTTPException(400, "Only ToolBox supports editable root ports")

    if req.inputs is not None:
        meta["inputs"] = req.inputs
    if req.outputs is not None:
        meta["outputs"] = req.outputs
    if req.input_types is not None:
        meta["input_types"] = req.input_types
    if req.output_types is not None:
        meta["output_types"] = req.output_types
    if req.input_defaults is not None:
        meta["input_defaults"] = req.input_defaults
    if req.multi_input_ports is not None:
        meta["multi_input_ports"] = req.multi_input_ports

    _sync_toolbox_ports(meta)
    _session.graph._mark_dirty(node_id)
    _save()
    return meta


@app.patch("/nodes/{node_id}/pos")
def update_pos(node_id: str, pos: list[float]):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    _session.node_meta[node_id]["pos"] = pos
    _save(debounce=0.8)   # coalesce rapid drag updates
    return {"ok": True}


@app.post("/edges")
def connect(req: ConnectReq):
    try:
        _session.graph._add_edge(req.from_id, req.from_port, req.to_id, req.to_port)
    except Exception as e:
        raise HTTPException(400, str(e))
    meta = _session.node_meta.get(req.to_id)
    if meta and meta.get("type") in _TOOLBOX_NODE_TYPES and req.to_port.startswith("tool_"):
        inputs = list(meta.get("inputs", []))
        if req.to_port not in inputs:
            meta["inputs"] = [*inputs, req.to_port]
            meta["input_types"] = {**meta.get("input_types", {}), req.to_port: "Fn"}
        _sync_toolbox_ports(meta)
    _save()
    return {"ok": True}


@app.delete("/edges")
def disconnect(from_id: str, from_port: str, to_id: str, to_port: str):
    _session.graph._edges = [
        e for e in _session.graph._edges
        if not (e["from"] == from_id and e["from_port"] == from_port
                and e["to"] == to_id and e["to_port"] == to_port)
    ]
    meta = _session.node_meta.get(to_id)
    if meta and meta.get("type") in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta, _session.graph._edges)
    _save()
    return {"ok": True}


@app.patch("/nodes/{node_id}/subgraph")
def update_subgraph(node_id: str, req: UpdateSubgraphReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if _session.node_meta[node_id]["type"] not in _SUBGRAPH_NODE_TYPES:
        raise HTTPException(400, "Node does not own a subgraph")
    subgraph = {"node_meta": req.node_meta, "edges": req.edges}
    _session.node_meta[node_id]["subgraph"] = subgraph
    _session.graph._nodes[node_id]["subgraph"] = subgraph
    _sync_subgraph_node_ports(_session.node_meta[node_id])
    _session.graph._mark_dirty(node_id)
    _save()
    return _session.node_meta[node_id]


@app.get("/nodes/{node_id}/subgraph")
def get_subgraph(node_id: str):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if _sync_dynamic_node_meta(_session.node_meta[node_id], _session.graph._edges):
        _save()
    return _session.node_meta[node_id].get("subgraph", {"node_meta": {}, "edges": []})


@app.post("/subnets")
def collapse_to_subnet(req: CollapseSubnetReq):
    """Collapse selected nodes into a Subnet node."""
    import uuid as _uuid
    node_ids = set(req.node_ids)
    for nid in node_ids:
        if nid not in _session.node_meta:
            raise HTTPException(404, f"Node {nid} not found")

    # Compute bounding box centre for subnet position
    positions = [_session.node_meta[nid]["pos"] for nid in node_ids]
    cx = sum(p[0] for p in positions) / len(positions)
    cy = sum(p[1] for p in positions) / len(positions)

    # Classify edges as internal or crossing
    all_edges = _session.graph._edges
    internal_edges = [e for e in all_edges if e["from"] in node_ids and e["to"] in node_ids]
    entering_edges  = [e for e in all_edges if e["from"] not in node_ids and e["to"] in node_ids]
    exiting_edges   = [e for e in all_edges if e["from"] in node_ids and e["to"] not in node_ids]

    # Build inner node_meta for collapsed nodes
    inner_meta: dict[str, dict] = {}
    for nid in node_ids:
        inner_meta[nid] = dict(_session.node_meta[nid])

    new_inner_nodes: dict[str, dict] = {}
    new_inner_edges: list[dict] = []

    min_x = min(inner_meta[nid]["pos"][0] for nid in node_ids)
    max_x = max(inner_meta[nid]["pos"][0] for nid in node_ids)
    avg_y = sum(inner_meta[nid]["pos"][1] for nid in node_ids) / len(node_ids)

    # ONE SubnetInput node with one output per unique entering target port
    entry_ports: list[str] = []
    seen_entry_ports: set[str] = set()
    subnet_inputs: list[dict] = []

    for e in entering_edges:
        p = e["to_port"]
        if p in seen_entry_ports:
            p = f"{e['to'][:6]}_{e['to_port']}"
        seen_entry_ports.add(p)
        entry_ports.append(p)
        subnet_inputs.append({"port_name": p, "from_id": e["from"], "from_port": e["from_port"]})

    if entry_ports:
        inp_id = str(_uuid.uuid4())
        new_inner_nodes[inp_id] = {
            "id": inp_id, "type": "SubnetInput", "params": {},
            "pos": [min_x - 220, avg_y],
            "inputs": [], "outputs": entry_ports,
            "input_types": {}, "output_types": {p: "Any" for p in entry_ports},
            "input_defaults": {},
        }
        for i, e in enumerate(entering_edges):
            new_inner_edges.append({
                "from": inp_id, "from_port": entry_ports[i],
                "to": e["to"], "to_port": e["to_port"],
            })

    # ONE SubnetOutput node with one input per unique exiting source port
    exit_ports: list[str] = []
    seen_exit_ports: set[str] = set()
    subnet_outputs: list[dict] = []

    for e in exiting_edges:
        p = e["from_port"]
        if p in seen_exit_ports:
            p = f"{e['from'][:6]}_{e['from_port']}"
        seen_exit_ports.add(p)
        exit_ports.append(p)
        subnet_outputs.append({"port_name": p, "to_id": e["to"], "to_port": e["to_port"]})

    if exit_ports:
        out_id = str(_uuid.uuid4())
        new_inner_nodes[out_id] = {
            "id": out_id, "type": "SubnetOutput", "params": {},
            "pos": [max_x + 220, avg_y],
            "inputs": exit_ports, "outputs": [],
            "input_types": {p: "Any" for p in exit_ports}, "output_types": {},
            "input_defaults": {},
        }
        for i, e in enumerate(exiting_edges):
            new_inner_edges.append({
                "from": e["from"], "from_port": e["from_port"],
                "to": out_id, "to_port": exit_ports[i],
            })

    # Build complete inner meta
    all_inner_meta = {**inner_meta, **new_inner_nodes}
    all_inner_edges = internal_edges + new_inner_edges

    # Create the Subnet node
    subnet_id = str(_uuid.uuid4())
    subnet_meta: dict[str, Any] = {
        "id":       subnet_id,
        "type":     "Subnet",
        "params":   {"label": req.label},
        "pos":      [cx, cy],
        "inputs":   [],
        "outputs":  [],
        "input_types": {},
        "output_types": {},
        "input_defaults": {},
        "subgraph": {"node_meta": all_inner_meta, "edges": all_inner_edges},
    }
    _sync_subgraph_node_ports(subnet_meta)

    # Remove collapsed nodes from session
    for nid in node_ids:
        del _session.node_meta[nid]
        _session.graph._nodes.pop(nid, None)
        _session.graph._dirty.discard(nid)

    # Remove all edges involving collapsed nodes
    _session.graph._edges = [
        e for e in _session.graph._edges
        if e["from"] not in node_ids and e["to"] not in node_ids
    ]

    # Add subnet node to session
    _session.node_meta[subnet_id] = subnet_meta
    _session.graph._nodes[subnet_id] = {
        "type": "Subnet",
        "params": subnet_meta["params"],
        "subgraph": subnet_meta["subgraph"],
    }
    _session.graph._dirty.add(subnet_id)

    # Rewire external edges through the subnet
    for inp_info in subnet_inputs:
        _session.graph._edges.append({
            "from": inp_info["from_id"],
            "from_port": inp_info["from_port"],
            "to": subnet_id,
            "to_port": inp_info["port_name"],
        })
    for out_info in subnet_outputs:
        _session.graph._edges.append({
            "from": subnet_id,
            "from_port": out_info["port_name"],
            "to": out_info["to_id"],
            "to_port": out_info["to_port"],
        })

    _save()
    return {"subnet": subnet_meta, "removed_node_ids": list(node_ids)}


@app.post("/cook")
def cook(req: CookReq):
    import traceback
    if req.node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if req.node_id not in _session.graph._nodes:
        raise HTTPException(500, f"Node {req.node_id} missing from graph (try resetting)")
    node_type = _session.node_meta[req.node_id]["type"]
    workflow = _run_workflow_snapshot(req.node_id, req.port)
    run_id = _run_store.begin(node_id=req.node_id, port=req.port, node_type=node_type, workflow=workflow)
    try:
        _begin_fresh_cook()
        _run_store.record_event(run_id, {"type": "start", "node_id": req.node_id, "port": req.port})
        proxy  = bn.NodeProxy(_session.graph, req.node_id, node_type, {})
        result = _session.graph.cook(proxy, req.port)
        _run_store.record_event(run_id, _event_for_storage({
            "type": "success", "node_id": req.node_id, "port": req.port, "value": result,
        }))
        _run_store.record_event(run_id, _event_for_storage({"type": "done", "port": req.port, "value": result}))
        _run_store.finalize_success(run_id, value=_event_value(result))
        return {"value": result, "port": req.port, "run_id": run_id}
    except Exception as exc:
        trace = traceback.format_exc()
        _run_store.record_event(run_id, {
            "type": "error", "node_id": req.node_id, "port": req.port, "error": trace,
        })
        _run_store.finalize_error(run_id, error=str(exc))
        raise HTTPException(500, trace)


def _json_line(payload: dict) -> str:
    return json.dumps(payload, default=str) + "\n"


_RUNTIME_STATUS_KEYS = ("cookResult", "cookError", "cooking", "cookPort")


def _status_value(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _is_image_data_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("data:image/")


def _event_value(value: Any) -> Any:
    if _is_image_data_url(value):
        return f"[image data URL, {len(value)} chars]"
    if isinstance(value, list):
        return [_event_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _event_value(item) for key, item in value.items()}
    return value


def _event_outputs(outputs: Any) -> Any:
    if isinstance(outputs, dict):
        return {key: _event_value(value) for key, value in outputs.items()}
    return _event_value(outputs)


def _event_for_storage(event: dict[str, Any]) -> dict[str, Any]:
    stored = dict(event)
    if "value" in stored:
        stored["value"] = _event_value(stored["value"])
    if "outputs" in stored:
        stored["outputs"] = _event_outputs(stored["outputs"])
    return stored


def _clear_runtime_status(meta: dict) -> None:
    for key in _RUNTIME_STATUS_KEYS:
        meta.pop(key, None)


def _record_node_success(meta_map: dict[str, dict], node_id: str, port: str, value: Any) -> None:
    meta = meta_map.get(node_id)
    if not meta:
        return
    _clear_runtime_status(meta)
    meta["cookResult"] = _status_value(value)
    meta["cookPort"] = port
    meta["cooking"] = False


def _record_node_error(meta_map: dict[str, dict], node_id: str, port: str, error: str) -> None:
    meta = meta_map.get(node_id)
    if not meta:
        return
    _clear_runtime_status(meta)
    meta["cookError"] = str(error)
    meta["cookPort"] = port
    meta["cooking"] = False


def _node_cached_outputs(cache: dict[tuple, Any], node_id: str, fallback_port: str, fallback_value: Any) -> Any:
    outputs = {
        str(port): _status_value(value)
        for (nid, port), value in cache.items()
        if nid == node_id
    }
    return outputs if len(outputs) > 1 else fallback_value


def _clear_runtime_status_tree(meta_map: dict[str, dict]) -> None:
    for meta in meta_map.values():
        _clear_runtime_status(meta)
        subgraph = meta.get("subgraph")
        if isinstance(subgraph, dict):
            inner_meta = subgraph.get("node_meta")
            if isinstance(inner_meta, dict):
                _clear_runtime_status_tree(inner_meta)


def _begin_fresh_cook(clear_status: bool = True) -> None:
    """Make every user-triggered cook execute from scratch.

    The graph still uses its cache inside a single cook so one upstream node
    can feed multiple downstream ports without running twice.
    """
    _session.graph._cache.clear()
    _session.graph._dirty = set(_session.graph._nodes)
    if clear_status:
        _clear_runtime_status_tree(_session.node_meta)


def _subgraph_output_node_id(subgraph: dict) -> str:
    for nid, meta in subgraph.get("node_meta", {}).items():
        if meta.get("type") == "SubnetOutput":
            return nid
    raise KeyError("Subgraph has no SubnetOutput node")


def _subgraph_output_has_status(subnet_id: str, port: str) -> bool:
    subgraph = _session.node_meta[subnet_id].get("subgraph", {})
    try:
        output_id = _subgraph_output_node_id(subgraph)
    except KeyError:
        return False
    meta = subgraph.get("node_meta", {}).get(output_id, {})
    return meta.get("cookPort") == port and ("cookResult" in meta or "cookError" in meta)


def _cook_subgraph_streamed_value(subnet_id: str, port: str):
    output_id = _subgraph_output_node_id(_session.node_meta[subnet_id].get("subgraph", {}))
    final_value: Any = None
    final_error: str | None = None
    saw_done = False

    for line in _subgraph_cook_trace(subnet_id, output_id, port):
        yield line
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "done":
            saw_done = True
            final_value = event.get("value")
            final_error = event.get("error")

    if final_error:
        raise RuntimeError(final_error)
    if not saw_done:
        raise RuntimeError("Subgraph cook did not complete")
    return final_value


def _visual_node_id(inner_meta: dict[str, dict], preferred: str, type_name: str) -> str | None:
    if preferred in inner_meta:
        return preferred
    for node_id, meta in inner_meta.items():
        if meta.get("type") == type_name:
            return node_id
    return None


def _visual_emit_success(inner_meta: dict[str, dict], node_id: str | None, port: str, value: Any, outputs: dict | None = None):
    if not node_id:
        return
    status_value = outputs if outputs is not None else value
    _record_node_success(inner_meta, node_id, port, status_value)
    yield _json_line({
        "type": "success",
        "node_id": node_id,
        "port": port,
        "value": status_value,
        "outputs": outputs if outputs is not None else {port: value},
    })


def _visual_emit_start(node_id: str | None, port: str, inner_meta: dict[str, dict] | None = None):
    if not node_id:
        return
    payload: dict[str, Any] = {"type": "start", "node_id": node_id, "port": port}
    if inner_meta and node_id in inner_meta:
        payload["node_type"] = str(inner_meta[node_id].get("type", ""))
    yield _json_line(payload)


def _visual_emit_error(inner_meta: dict[str, dict], node_id: str | None, port: str, error: str):
    if not node_id:
        return
    _record_node_error(inner_meta, node_id, port, error)
    payload: dict[str, Any] = {"type": "error", "node_id": node_id, "port": port, "error": error}
    if node_id in inner_meta:
        payload["node_type"] = str(inner_meta[node_id].get("type", ""))
    yield _json_line(payload)


def _cook_visual_agent_loop_streamed_value(subnet_id: str, port: str, outer_ctx: dict):
    import traceback

    subgraph = _session.node_meta[subnet_id].get("subgraph", {})
    inner_meta = subgraph.get("node_meta", {})
    _migrate_visual_agent_loop_subgraph(_session.node_meta[subnet_id])

    loop_in_id = _visual_node_id(inner_meta, "loop_in", "SubnetInput")
    messages_id = _visual_node_id(inner_meta, "messages", "AgentMessages")
    chat_id = _visual_node_id(inner_meta, "chat", "AgentChatStep")
    iteration_id = _visual_node_id(inner_meta, "iteration", "AgentIteration") or _visual_node_id(inner_meta, "iter_one", "Int")
    stop_id = _visual_node_id(inner_meta, "stop", "AgentStopCheck")
    dispatch_id = _visual_node_id(inner_meta, "dispatch", "ToolDispatch")
    append_id = _visual_node_id(inner_meta, "append", "AgentAppendMessages")
    final_id = _visual_node_id(inner_meta, "final", "AgentFinalAnswer")
    loop_out_id = _visual_node_id(inner_meta, "loop_out", "SubnetOutput")

    model = outer_ctx.get("model", "claude-sonnet-4-6")
    system = outer_ctx.get("system", "You are a helpful agent. Use the available tools.")
    prompt = outer_ctx.get("prompt", "")
    tools = outer_ctx.get("tools") or []
    max_tokens = ai_nodes._max_tokens_for_model(model, outer_ctx.get("max_tokens"))
    max_iter = max(1, ai_nodes._int_value(outer_ctx.get("max_iter"), 5))

    injected = {
        "prompt": prompt,
        "system": system,
        "model": model,
        "tools": tools,
        "max_tokens": max_tokens,
        "max_iter": max_iter,
    }
    yield from _visual_emit_success(inner_meta, loop_in_id, "inputs", injected, injected)

    messages: list[dict] = [{"role": "user", "content": prompt}]
    yield from _visual_emit_success(inner_meta, messages_id, "messages", messages, {"messages": messages})

    steps: list[dict] = []
    final_result = ""
    final_step: dict = {"role": "assistant", "text": "", "tool_calls": []}

    for iteration in range(1, max_iter + 1):
        yield from _visual_emit_success(
            inner_meta,
            iteration_id,
            "iteration",
            iteration,
            {"iteration": iteration},
        )

        try:
            yield from _visual_emit_start(chat_id, "step")
            _, resp, chat_step = ai_nodes._chat_step(
                messages,
                model=model,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                provider_name=outer_ctx.get("provider"),
                base_url=outer_ctx.get("base_url"),
                api_key=outer_ctx.get("api_key"),
            )
        except Exception as exc:
            error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
            yield from _visual_emit_error(inner_meta, chat_id, "step", error)
            raise

        chat_outputs = {
            "assistant_text": resp.text,
            "tool_calls": chat_step["tool_calls"],
            "stop_reason": resp.stop_reason,
            "step": chat_step,
        }
        yield from _visual_emit_success(inner_meta, chat_id, "step", chat_step, chat_outputs)
        steps.append({
            "role": "assistant",
            "text": resp.text,
            "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls],
        })

        stop_outputs = ai_nodes.agent_stop_check({
            "stop_reason": resp.stop_reason,
            "tool_calls": chat_step["tool_calls"],
            "iteration": iteration,
            "max_iter": max_iter,
        })
        yield from _visual_emit_success(inner_meta, stop_id, "reason", stop_outputs["reason"], stop_outputs)

        if stop_outputs["reason"] == "final":
            final_result = resp.text
            final_step = {"role": "assistant", "text": final_result, "tool_calls": [], "reason": "final"}
            yield from _visual_emit_success(inner_meta, final_id, "result", final_result, {"result": final_result, "step": final_step})
            break

        tool_call_dicts = [ai_nodes._tool_call_dict(tc) for tc in resp.tool_calls]
        yield from _visual_emit_start(dispatch_id, "steps")
        tool_results, tool_steps = ai_nodes._dispatch_tools(tool_call_dicts, tools)
        dispatch_outputs = {
            "tool_results": [ai_nodes._tool_result_dict(r) for r in tool_results],
            "steps": tool_steps,
        }
        yield from _visual_emit_success(inner_meta, dispatch_id, "steps", tool_steps, dispatch_outputs)
        steps.extend(tool_steps)

        messages = ai_nodes._append_tool_messages(
            messages,
            model=model,
            assistant_text=resp.text,
            tool_calls=tool_call_dicts,
            tool_results=[ai_nodes._tool_result_dict(r) for r in tool_results],
            provider_name=outer_ctx.get("provider"),
            base_url=outer_ctx.get("base_url"),
            api_key=outer_ctx.get("api_key"),
        )
        yield from _visual_emit_success(inner_meta, append_id, "messages", messages, {"messages": messages})

        if stop_outputs["reason"] == "max_iter":
            try:
                yield from _visual_emit_start(final_id, "result")
                final_outputs = ai_nodes.agent_final_answer({
                    "messages": messages,
                    "system": system,
                    "model": model,
                    "max_tokens": max_tokens,
                    "assistant_text": resp.text,
                    "stop_reason": resp.stop_reason,
                    "reason": "max_iter",
                    "tool_calls": chat_step["tool_calls"],
                    "provider": outer_ctx.get("provider"),
                    "base_url": outer_ctx.get("base_url"),
                    "api_key": outer_ctx.get("api_key"),
                })
            except Exception as exc:
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                yield from _visual_emit_error(inner_meta, final_id, "result", error)
                raise
            final_result = final_outputs.get("result", "")
            final_step = final_outputs.get("step", {})
            steps.append(final_step)
            yield from _visual_emit_success(inner_meta, final_id, "result", final_result, final_outputs)
            break

    loop_outputs = {"result": final_result, "steps": steps}
    yield from _visual_emit_success(inner_meta, loop_out_id, port, loop_outputs.get(port), loop_outputs)
    return loop_outputs.get(port)


def _refresh_subgraph_status_if_needed(subnet_id: str, port: str):
    if _subgraph_output_has_status(subnet_id, port):
        return
    if _session.node_meta[subnet_id].get("type") == "VisualAgentLoop":
        outer_ctx = dict(_session.graph._nodes.get(subnet_id, {}).get("params", {}))
        for edge in _session.graph._edges:
            if edge["to"] == subnet_id and (edge["from"], edge["from_port"]) in _session.graph._cache:
                outer_ctx[edge["to_port"]] = _session.graph._cache[(edge["from"], edge["from_port"])]
        value = yield from _cook_visual_agent_loop_streamed_value(subnet_id, port, outer_ctx)
    else:
        value = yield from _cook_subgraph_streamed_value(subnet_id, port)
    _session.graph._cache[(subnet_id, port)] = value
    _session.graph._dirty.discard(subnet_id)


def _lookup_node_type(node_id: str | None) -> str:
    if not isinstance(node_id, str):
        return ""
    meta = _session.node_meta.get(node_id)
    if isinstance(meta, dict):
        return str(meta.get("type", ""))
    return ""


def _node_event(payload: dict[str, Any]) -> str:
    """Build an ndjson event line, auto-filling node_type when a node_id is set."""
    if "node_id" in payload and "node_type" not in payload:
        node_type = _lookup_node_type(payload["node_id"])
        if node_type:
            payload = {**payload, "node_type": node_type}
    return _json_line(payload)


def _cook_target_batch_trace(cook_one, targets: list[tuple[str, str]]):
    """Cook every requested terminal while sharing the current graph cache."""
    import traceback

    if len(targets) == 1:
        node_id, port = targets[0]
        try:
            final_value = yield from cook_one(node_id, port)
            yield _json_line({"type": "done", "port": port, "value": _event_value(final_value)})
        except _CookStopped:
            yield _json_line({"type": "done", "port": port, "error": "stopped"})
        except Exception:
            yield _json_line({"type": "done", "port": port, "error": traceback.format_exc()})
        return

    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    target_status: list[dict[str, str]] = []
    try:
        for node_id, port in targets:
            key = f"{node_id}.{port}"
            try:
                values[key] = yield from cook_one(node_id, port)
                target_status.append({"node_id": node_id, "port": port, "status": "success"})
            except _CookStopped:
                raise
            except Exception:
                errors[key] = traceback.format_exc()
                target_status.append({"node_id": node_id, "port": port, "status": "error"})

        done: dict[str, Any] = {
            "type": "done",
            "port": "leaves",
            "value": _event_value(values),
            "targets": target_status,
        }
        if errors:
            done["error"] = "\n\n".join(
                f"{key}:\n{error}" for key, error in errors.items()
            )
        yield _json_line(done)
    except _CookStopped:
        yield _json_line({
            "type": "done",
            "port": "leaves",
            "value": _event_value(values),
            "targets": target_status,
            "error": "stopped",
        })


class _CookStreamLogger:
    """RunLogger-shaped adapter that forwards model/tool events into the cook stream.

    The AI nodes call ``ctx['__run_logger__'].model_call(...)`` and
    ``.tool_call(...)``. The CLI runtime gives them a real RunLogger; the editor
    cook path used to drop those events on the floor. This adapter queues them
    so ``_cook_trace`` can yield them as ndjson lines, which means both the live
    frontend and the persistent RunStore see them.
    """

    def __init__(self):
        self._pending: list[dict[str, Any]] = []

    def drain(self) -> list[dict[str, Any]]:
        pending, self._pending = self._pending, []
        return pending

    def model_call(self, *, node_id, model, provider=None, action="complete", tool_count=None):
        event: dict[str, Any] = {
            "type": "model_call",
            "node_id": node_id,
            "node_type": _lookup_node_type(node_id),
            "model": model,
            "action": action,
        }
        if provider:
            event["provider"] = provider
        if tool_count is not None:
            event["tool_count"] = tool_count
        self._pending.append(event)

    def tool_call(self, *, node_id, name, arguments=None):
        self._pending.append({
            "type": "tool_call",
            "node_id": node_id,
            "node_type": _lookup_node_type(node_id),
            "name": name,
            "arguments": dict(arguments or {}),
        })


def _cook_trace(
    node_id: str,
    port: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
):
    import traceback
    emitted_cached: set[tuple[str, str]] = set()
    logger = _CookStreamLogger()

    def drain_logger():
        for event in logger.drain():
            yield _json_line(event)

    def emit_cached_success(current_id: str, current_port: str):
        cache_key = (current_id, current_port)
        if cache_key in emitted_cached or cache_key not in _session.graph._cache:
            return
        emitted_cached.add(cache_key)
        yield _node_event({
            "type": "success",
            "node_id": current_id,
            "port": current_port,
            "value": _session.graph._cache[cache_key],
            "cached": True,
        })

    def emit_cached_upstream(current_id: str, visiting: set[str] | None = None):
        if visiting is None:
            visiting = set()
        if current_id in visiting:
            return
        visiting.add(current_id)
        for edge in _session.graph._edges:
            if edge["to"] == current_id:
                yield from emit_cached_upstream(edge["from"], visiting)
                source_def = _session.graph._nodes.get(edge["from"])
                if source_def and source_def.get("type") in {"Subnet", "VisualAgentLoop"}:
                    yield from _refresh_subgraph_status_if_needed(edge["from"], edge["from_port"])
                yield from emit_cached_success(edge["from"], edge["from_port"])
        visiting.remove(current_id)

    def cook_one(current_id: str, current_port: str):
        _raise_if_stopped(stop_event)
        if current_id not in _session.node_meta:
            raise KeyError(f"Node {current_id} not found")
        if current_id not in _session.graph._nodes:
            raise KeyError(f"Node {current_id} missing from graph")

        node_def = _session.graph._nodes[current_id]
        cache_key = (current_id, current_port)
        if (
            node_def["type"] not in {"Subnet", "VisualAgentLoop"}
            and current_id not in _session.graph._dirty
            and cache_key in _session.graph._cache
        ):
            value = _session.graph._cache[cache_key]
            yield from emit_cached_upstream(current_id)
            yield from emit_cached_success(current_id, current_port)
            return value

        ctx = dict(node_def["params"])

        for edge in _session.graph._edges:
            if edge["to"] == current_id:
                val = yield from cook_one(edge["from"], edge["from_port"])
                _raise_if_stopped(stop_event)
                ctx[edge["to_port"]] = val

        try:
            if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                _raise_if_stopped(stop_event)
                yield _node_event({"type": "start", "node_id": current_id, "port": current_port})
                try:
                    if node_def["type"] == "VisualAgentLoop":
                        value = yield from _cook_visual_agent_loop_streamed_value(current_id, current_port, ctx)
                    else:
                        value = yield from _cook_subgraph_streamed_value(current_id, current_port)
                    _raise_if_stopped(stop_event)
                    result = {current_port: value}
                    _session.graph._cache[(current_id, current_port)] = value
                    _session.graph._dirty.discard(current_id)
                    yield _node_event({
                        "type": "success",
                        "node_id": current_id,
                        "port": current_port,
                        "value": value,
                        "outputs": _event_outputs(result),
                    })
                    return value
                except Exception as exc:
                    yield _node_event({"type": "error", "node_id": current_id, "port": current_port, "error": str(exc)})
                    raise

            yield _node_event({
                "type": "start",
                "node_id": current_id,
                "port": current_port,
            })

            fn = _NODE_REGISTRY[node_def["type"]]
            ctx["__graph__"] = _session.graph
            ctx["__node_id__"] = current_id
            ctx["__run_logger__"] = logger
            _out_buf, _err_buf = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(_out_buf), contextlib.redirect_stderr(_err_buf):
                    result = fn(ctx)
            finally:
                yield from drain_logger()
                for _stream, _buf in (("stdout", _out_buf), ("stderr", _err_buf)):
                    _text = _buf.getvalue()
                    if _text.strip():
                        yield _node_event({
                            "type": "log",
                            "node_id": current_id,
                            "stream": _stream,
                            "text": _text,
                        })
            _raise_if_stopped(stop_event)
            if not isinstance(result, dict):
                result = {"output": result}

            for key, value in result.items():
                _session.graph._cache[(current_id, key)] = value
            _session.graph._dirty.discard(current_id)

            if cache_key not in _session.graph._cache:
                raise KeyError(
                    f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                    f"Available: {[key for (nid, key) in _session.graph._cache if nid == current_id]}"
                )

            value = _session.graph._cache[cache_key]
            yield _node_event({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": value,
                "outputs": _event_outputs(result),
            })
            return value
        except Exception as exc:
            yield from drain_logger()
            error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
            yield _node_event({
                "type": "error",
                "node_id": current_id,
                "port": current_port,
                "error": error,
            })
            raise

    yield from _cook_target_batch_trace(cook_one, targets or [(node_id, port)])


def _captured_cook_trace(
    node_id: str,
    port: str,
    run_id: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
):
    """Wrap _cook_trace so every emitted event is also persisted to the run store."""
    final_value: Any = None
    final_error: str | None = None
    try:
        for line in _cook_trace(node_id, port, stop_event, targets=targets):
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                event = None
            if isinstance(event, dict):
                stored_event = _event_for_storage(event)
                _run_store.record_event(run_id, stored_event)
                if stored_event.get("type") == "done":
                    if stored_event.get("error"):
                        final_error = stored_event.get("error")
                    elif "value" in event:
                        final_value = stored_event.get("value")
                elif stored_event.get("type") == "error" and final_error is None:
                    final_error = stored_event.get("error")
            yield line
    finally:
        if final_error is not None:
            _run_store.finalize_error(run_id, error=final_error)
        else:
            _run_store.finalize_success(run_id, value=final_value)


def _stream_in_worker(lines_factory, stop_event: threading.Event, port: str):
    import traceback

    out_q: queue.Queue[str | None] = queue.Queue()

    def run_worker() -> None:
        try:
            for line in lines_factory():
                if stop_event.is_set():
                    break
                out_q.put(line)
        except _CookStopped:
            out_q.put(_json_line({"type": "done", "port": port, "error": "stopped"}))
        except Exception:
            out_q.put(_json_line({"type": "done", "port": port, "error": traceback.format_exc()}))
        finally:
            out_q.put(None)

    worker = threading.Thread(target=run_worker, name=f"blacknode-cook-{port}", daemon=True)
    worker.start()

    while True:
        if stop_event.is_set():
            yield _json_line({"type": "done", "port": port, "error": "stopped"})
            break
        try:
            line = out_q.get(timeout=0.25)
        except queue.Empty:
            continue
        if line is None:
            break
        yield line


@app.post("/cook-stream")
def cook_stream(req: CookReq):
    node_type = _session.node_meta.get(req.node_id, {}).get("type", "")
    workflow = _run_workflow_snapshot(req.node_id, req.port)
    run_id = _run_store.begin(node_id=req.node_id, port=req.port, node_type=node_type, workflow=workflow)
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    headers = {"X-Blacknode-Run-Id": run_id}
    return StreamingResponse(
        _stream_in_worker(
            lambda: _captured_cook_trace(req.node_id, req.port, run_id, stop_event),
            stop_event,
            req.port,
        ),
        media_type="application/x-ndjson",
        headers=headers,
    )


def _graph_cook_targets(req: CookGraphReq) -> list[tuple[str, str]]:
    if not req.targets:
        raise HTTPException(400, "Graph run requires at least one terminal target")
    if len(req.targets) > 256:
        raise HTTPException(400, "Graph run supports at most 256 terminal targets")

    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target in req.targets:
        item = (target.node_id.strip(), target.port.strip())
        if not item[0] or not item[1]:
            raise HTTPException(400, "Each graph run target needs a node_id and port")
        if item not in seen:
            seen.add(item)
            targets.append(item)
    return targets


@app.post("/cook-graph-stream")
def cook_graph_stream(req: CookGraphReq):
    targets = _graph_cook_targets(req)
    workflow = _run_graph_workflow_snapshot(targets)
    run_id = _run_store.begin(
        node_id="__graph__",
        port="leaves",
        node_type="Graph",
        workflow=workflow,
    )
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    headers = {"X-Blacknode-Run-Id": run_id}
    first_node, first_port = targets[0]
    return StreamingResponse(
        _stream_in_worker(
            lambda: _captured_cook_trace(
                first_node,
                first_port,
                run_id,
                stop_event,
                targets=targets,
            ),
            stop_event,
            "leaves",
        ),
        media_type="application/x-ndjson",
        headers=headers,
    )


@app.post("/cook/stop")
def stop_cook():
    _stop_active_cook()
    _begin_fresh_cook()
    return {"ok": True}


@app.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": _run_store.list_runs(limit=max(1, min(limit, 500)))}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    record = _run_store.get_run(run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    return record


@app.delete("/runs/{run_id}")
def delete_run(run_id: str):
    if not _run_store.delete_run(run_id):
        raise HTTPException(404, "Run not found")
    return {"ok": True, "run_id": run_id}


@app.delete("/runs")
def clear_runs():
    return {"ok": True, "removed": _run_store.clear()}


@app.post("/sync/runs")
def sync_begin_run(req: SyncRunReq):
    workflow = req.workflow
    if isinstance(workflow, dict):
        _ensure_workflow_header(workflow)
        _enqueue_editor_action(
            "open_workflow_tab",
            {
                "name": str(workflow.get("name") or "Python Live Sync"),
                "workflow": workflow,
                "organize": False,
            },
        )
    run_id = _run_store.begin(
        node_id=req.node_id,
        port=req.port,
        node_type=req.node_type,
        workflow=workflow,
    )
    record = _run_store.snapshot(run_id)
    if record is not None:
        _enqueue_sync_run_update(record, playing=True)
    return {"ok": True, "run_id": run_id}


@app.post("/sync/events")
def sync_record_event(req: SyncEventReq):
    _run_store.record_event(req.run_id, req.event)
    record = _run_store.snapshot(req.run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    _enqueue_sync_run_update(record, playing=True)
    events = record.get("events") or []
    return {"ok": True, "run_id": req.run_id, "cursor": len(events) - 1}


@app.post("/sync/runs/{run_id}/finish")
def sync_finish_run(run_id: str, req: SyncFinishReq):
    if req.status == "error" or req.error:
        record = _run_store.finalize_error(run_id, error=req.error or "External Python run failed")
    else:
        record = _run_store.finalize_success(run_id, value=req.value)
    if record is None:
        raise HTTPException(404, "Run not found")
    _enqueue_sync_run_update(record, playing=False)
    return {"ok": True, "run": record}


@app.get("/sync/runs/{run_id}")
def sync_get_run(run_id: str):
    record = _run_store.snapshot(run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    return record


@app.get("/mcp/status")
def mcp_status():
    import importlib.util
    import shutil
    mcp_installed = importlib.util.find_spec("mcp") is not None
    cli_path = shutil.which("blacknode")
    return {
        "mcp_installed": mcp_installed,
        "blacknode_cli": cli_path,
        "install_command": "pip install -e \".[mcp]\"",
        "launch_command": "blacknode mcp",
    }


@app.post("/editor/actions/workflow-tab")
def queue_new_workflow_tab(req: NewWorkflowTabReq):
    name = req.name.strip() or "Untitled"
    action = _enqueue_editor_action("new_workflow_tab", {"name": name})
    return {"ok": True, "action": action}


@app.post("/editor/actions/open-workflow-tab")
def queue_open_workflow_tab(req: OpenWorkflowTabReq):
    workflow = req.workflow
    _ensure_workflow_header(workflow)
    report = validate_bn_workflow(workflow)
    if not report.ok:
        raise HTTPException(400, report.to_dict())
    name = (req.name or workflow.get("name") or "Untitled").strip() or "Untitled"
    action = _enqueue_editor_action("open_workflow_tab", {
        "name": name,
        "workflow": workflow,
        "organize": req.organize,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/cook-node")
def queue_cook_node(req: CookEditorNodeReq):
    node_id = req.node_id.strip()
    port = req.port.strip() or "value"
    if node_id not in _session.node_meta:
        raise HTTPException(404, f"Node '{node_id}' not found")
    action = _enqueue_editor_action("cook_node", {
        "node_id": node_id,
        "port": port,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/load-saved-workflow-tab")
def queue_load_saved_workflow_tab(req: LoadSavedWorkflowTabReq):
    slug = req.slug.strip()
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    name = (req.name or data.get("name") or slug).strip() or slug
    action = _enqueue_editor_action("load_saved_workflow_tab", {
        "slug": slug,
        "name": name,
        "organize": req.organize,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/organize-graph")
def queue_organize_graph():
    action = _enqueue_editor_action("organize_graph")
    return {"ok": True, "action": action}


@app.post("/editor/actions/rename-tab")
def queue_rename_tab(req: RenameEditorTabReq):
    name = req.name.strip() or "Untitled"
    action = _enqueue_editor_action("rename_tab", {"name": name})
    return {"ok": True, "action": action}


@app.post("/editor/actions/close-tab")
def queue_close_tab():
    action = _enqueue_editor_action("close_tab")
    return {"ok": True, "action": action}


@app.get("/editor/actions")
def consume_editor_actions():
    with _editor_action_lock:
        actions = list(_editor_action_queue)
        _editor_action_queue.clear()
    return {"actions": actions}


@app.get("/learned-nodes")
def list_learned_nodes():
    return mcp_tools.list_learned_nodes()


@app.get("/learned-nodes/{name}/source")
def get_learned_node_source(name: str):
    result = mcp_tools.get_learned_node_source(name)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Invalid learned node name"))
    return result


@app.delete("/learned-nodes/{name}")
def delete_learned_node(name: str):
    result = mcp_tools.delete_learned_node(name, confirm=True, notify_editor=False)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Could not delete learned node"))
    _broadcast_learned_node_event("learned_node_deleted", name)
    return result


@app.post("/learned-nodes/{name}/promote")
def promote_learned_node(name: str):
    result = mcp_tools.promote_learned_node(name, notify_editor=False)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Could not promote learned node"))
    _broadcast_learned_node_event("learned_node_deleted", name)
    return result


@app.get("/learned-nodes/events")
def learned_nodes_events():
    def event_generator():
        subscriber: queue.Queue = queue.Queue()
        with _learned_node_event_lock:
            _learned_node_event_subscribers.append(subscriber)
        try:
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            with _learned_node_event_lock:
                if subscriber in _learned_node_event_subscribers:
                    _learned_node_event_subscribers.remove(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/internal/learned-node-added")
def internal_learned_node_added(req: LearnedNodeEventReq):
    name = req.name.strip()
    try:
        learned_registry.register_one(name)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    event = _broadcast_learned_node_event("learned_node_added", name)
    return {"ok": True, "event": event}


@app.post("/internal/learned-node-deleted")
def internal_learned_node_deleted(req: LearnedNodeEventReq):
    name = req.name.strip()
    learned_registry.unregister_one(name)
    event = _broadcast_learned_node_event("learned_node_deleted", name)
    return {"ok": True, "event": event}


def _subgraph_cook_trace(
    subnet_id: str,
    node_id: str,
    port: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
):
    import traceback

    logger = _CookStreamLogger()
    resolved_targets = targets or [(node_id, port)]

    def drain_logger():
        for event in logger.drain():
            yield _json_line(event)

    try:
        if subnet_id not in _session.node_meta:
            raise KeyError(f"Subnet node {subnet_id} not found")
        subgraph = _session.node_meta[subnet_id].get("subgraph", {})
        inner_meta = subgraph.get("node_meta", {})
        inner_edges = subgraph.get("edges", [])
        for target_id, _target_port in resolved_targets:
            if target_id not in inner_meta:
                raise KeyError(f"Node {target_id} not found inside subnet")

        inner = bn.Graph.__new__(bn.Graph)
        inner._edges = inner_edges
        inner._cache = {}
        inner._dirty = set(inner_meta.keys())
        inner._nodes = {}
        for nid, meta in inner_meta.items():
            entry = {"type": meta["type"], "params": dict(meta.get("params", {}))}
            if "subgraph" in meta:
                entry["subgraph"] = meta["subgraph"]
            inner._nodes[nid] = entry

        emitted_outer_cached: set[tuple[str, str]] = set()

        def emit_outer_cached_success(current_id: str, current_port: str):
            cache_key = (current_id, current_port)
            if cache_key in emitted_outer_cached or cache_key not in _session.graph._cache:
                return
            emitted_outer_cached.add(cache_key)
            yield _node_event({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": _session.graph._cache[cache_key],
                "cached": True,
            })

        def emit_outer_cached_upstream(current_id: str, visiting: set[str] | None = None):
            if visiting is None:
                visiting = set()
            if current_id in visiting:
                return
            visiting.add(current_id)
            for edge in _session.graph._edges:
                if edge["to"] == current_id:
                    yield from emit_outer_cached_upstream(edge["from"], visiting)
                    yield from emit_outer_cached_success(edge["from"], edge["from_port"])
            visiting.remove(current_id)

        def cook_outer_one(current_id: str, current_port: str):
            _raise_if_stopped(stop_event)
            if current_id not in _session.node_meta:
                raise KeyError(f"Node {current_id} not found")
            if current_id not in _session.graph._nodes:
                raise KeyError(f"Node {current_id} missing from graph")

            cache_key = (current_id, current_port)
            if current_id not in _session.graph._dirty and cache_key in _session.graph._cache:
                value = _session.graph._cache[cache_key]
                yield from emit_outer_cached_upstream(current_id)
                yield from emit_outer_cached_success(current_id, current_port)
                return value

            node_def = _session.graph._nodes[current_id]
            ctx = dict(node_def["params"])

            for edge in _session.graph._edges:
                if edge["to"] == current_id:
                    val = yield from cook_outer_one(edge["from"], edge["from_port"])
                    _raise_if_stopped(stop_event)
                    ctx[edge["to_port"]] = val

            try:
                yield _json_line({"type": "start", "node_id": current_id, "port": current_port})
                if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                    result = _session.graph._cook_subnet(current_id, current_port, ctx)
                else:
                    fn = _NODE_REGISTRY[node_def["type"]]
                    ctx["__graph__"] = _session.graph
                    ctx["__node_id__"] = current_id
                    ctx["__run_logger__"] = logger
                    try:
                        result = fn(ctx)
                    finally:
                        yield from drain_logger()
                    if not isinstance(result, dict):
                        result = {"output": result}
                _raise_if_stopped(stop_event)

                for key, value in result.items():
                    _session.graph._cache[(current_id, key)] = value
                _session.graph._dirty.discard(current_id)

                if cache_key not in _session.graph._cache:
                    raise KeyError(
                        f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                        f"Available: {[key for (nid, key) in _session.graph._cache if nid == current_id]}"
                    )

                value = _session.graph._cache[cache_key]
                yield _node_event({
                    "type": "success",
                    "node_id": current_id,
                    "port": current_port,
                    "value": value,
                    "outputs": _event_outputs(result),
                })
                return value
            except Exception as exc:
                yield from drain_logger()
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                yield _node_event({
                    "type": "error",
                    "node_id": current_id,
                    "port": current_port,
                    "error": error,
                })
                raise

        outer_ctx = dict(_session.graph._nodes.get(subnet_id, {}).get("params", {}))
        for edge in _session.graph._edges:
            if edge["to"] == subnet_id:
                outer_ctx[edge["to_port"]] = yield from cook_outer_one(edge["from"], edge["from_port"])

        for nid, meta in inner_meta.items():
            if meta["type"] == "SubnetInput":
                injected: dict[str, Any] = {}
                for out_port in meta.get("outputs", []):
                    injected[out_port] = outer_ctx.get(out_port)
                    inner._cache[(nid, out_port)] = injected[out_port]
                inner._dirty.discard(nid)
                _record_node_success(inner_meta, nid, "inputs", injected)
                yield _json_line({
                    "type": "success",
                    "node_id": nid,
                    "port": "inputs",
                    "value": injected,
                    "outputs": _event_outputs(injected),
                })

        emitted_inner_cached: set[tuple[str, str]] = set()

        def emit_inner_cached_success(current_id: str, current_port: str):
            cache_key = (current_id, current_port)
            if cache_key in emitted_inner_cached or cache_key not in inner._cache:
                return
            emitted_inner_cached.add(cache_key)
            value = inner._cache[cache_key]
            _record_node_success(
                inner_meta,
                current_id,
                current_port,
                _node_cached_outputs(inner._cache, current_id, current_port, value),
            )
            yield _json_line({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": value,
                "cached": True,
            })

        def emit_inner_cached_upstream(current_id: str, visiting: set[str] | None = None):
            if visiting is None:
                visiting = set()
            if current_id in visiting:
                return
            visiting.add(current_id)
            for edge in inner._edges:
                if edge["to"] == current_id:
                    yield from emit_inner_cached_upstream(edge["from"], visiting)
                    yield from emit_inner_cached_success(edge["from"], edge["from_port"])
            visiting.remove(current_id)

        def cook_one(current_id: str, current_port: str):
            _raise_if_stopped(stop_event)
            if current_id not in inner_meta:
                raise KeyError(f"Node {current_id} not found inside subnet")
            if current_id not in inner._nodes:
                raise KeyError(f"Node {current_id} missing from inner graph")

            cache_key = (current_id, current_port)
            if current_id not in inner._dirty and cache_key in inner._cache:
                value = inner._cache[cache_key]
                yield from emit_inner_cached_upstream(current_id)
                yield from emit_inner_cached_success(current_id, current_port)
                _record_node_success(
                    inner_meta,
                    current_id,
                    current_port,
                    _node_cached_outputs(inner._cache, current_id, current_port, value),
                )
                return value

            node_def = inner._nodes[current_id]
            ctx = dict(node_def["params"])

            for edge in inner._edges:
                if edge["to"] == current_id:
                    val = yield from cook_one(edge["from"], edge["from_port"])
                    _raise_if_stopped(stop_event)
                    ctx[edge["to_port"]] = val

            try:
                node_type = node_def["type"]
                yield _json_line({"type": "start", "node_id": current_id, "port": current_port, "node_type": node_type})
                if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                    result = inner._cook_subnet(current_id, current_port, ctx)
                else:
                    fn = _NODE_REGISTRY[node_def["type"]]
                    ctx["__graph__"] = inner
                    ctx["__node_id__"] = current_id
                    result = fn(ctx)
                    if not isinstance(result, dict):
                        result = {"output": result}
                _raise_if_stopped(stop_event)

                for key, value in result.items():
                    inner._cache[(current_id, key)] = value
                inner._dirty.discard(current_id)

                if cache_key not in inner._cache:
                    raise KeyError(
                        f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                        f"Available: {[key for (nid, key) in inner._cache if nid == current_id]}"
                    )

                value = inner._cache[cache_key]
                _record_node_success(
                    inner_meta,
                    current_id,
                    current_port,
                    result if len(result) > 1 else value,
                )
                yield _json_line({
                    "type": "success",
                    "node_id": current_id,
                    "port": current_port,
                    "value": value,
                    "outputs": _event_outputs(result),
                })
                return value
            except Exception as exc:
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                _record_node_error(inner_meta, current_id, current_port, error)
                yield _json_line({
                    "type": "error",
                    "node_id": current_id,
                    "port": current_port,
                    "error": error,
                })
                raise

        yield from _cook_target_batch_trace(cook_one, resolved_targets)
    except _CookStopped:
        yield _json_line({"type": "done", "port": "leaves" if len(resolved_targets) > 1 else port, "error": "stopped"})
    except Exception:
        yield _json_line({"type": "done", "port": "leaves" if len(resolved_targets) > 1 else port, "error": traceback.format_exc()})


@app.post("/nodes/{subnet_id}/cook-stream")
def cook_subgraph_stream(subnet_id: str, req: CookReq):
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    return StreamingResponse(
        _stream_in_worker(
            lambda: _subgraph_cook_trace(subnet_id, req.node_id, req.port, stop_event),
            stop_event,
            req.port,
        ),
        media_type="application/x-ndjson",
    )


@app.post("/nodes/{subnet_id}/cook-graph-stream")
def cook_subgraph_graph_stream(subnet_id: str, req: CookGraphReq):
    targets = _graph_cook_targets(req)
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    first_node, first_port = targets[0]
    return StreamingResponse(
        _stream_in_worker(
            lambda: _subgraph_cook_trace(
                subnet_id,
                first_node,
                first_port,
                stop_event,
                targets=targets,
            ),
            stop_event,
            "leaves",
        ),
        media_type="application/x-ndjson",
    )


@app.get("/settings/api-keys")
def get_api_keys():
    return _api_keys


@app.get("/settings/api-key-status")
def get_api_key_status():
    """Return credential availability without exposing secret values."""
    return _api_key_status()


@app.post("/settings/api-key")
def set_api_key(req: SetApiKeyReq):
    env_var = _PROVIDER_ENV.get(req.provider)
    if env_var is not None:
        if req.key:
            os.environ[env_var] = req.key
        elif env_var in os.environ:
            del os.environ[env_var]
    changed = _api_keys.get(req.provider) != req.key
    _api_keys[req.provider] = req.key
    _save_api_keys()
    # If this is a bot token and that driver is running, restart it so the new
    # token takes effect (a running bot reads its token only at startup).
    restarted = _restart_running_driver_for(req.provider) if changed else None
    return {
        "ok": True,
        "restarted": restarted,
        "credential": _api_key_status().get(req.provider),
    }


# ── Driver status bridge ──────────────────────────────────────────────────
# Running drivers (blacknode slack/telegram, separate processes) POST heartbeats
# here so the canvas can show a truthful live/offline badge on trigger nodes.
_driver_status: dict[str, dict] = {}
_DRIVER_STALE_S = 15.0  # no heartbeat within this window → considered offline


class DriverStatusReq(BaseModel):
    name: str
    workflow: str = ""
    label: str = ""
    state: str = "listening"
    processed: int = 0
    pid: int = 0
    ts: float = 0.0


@app.post("/drivers/status")
def post_driver_status(req: DriverStatusReq):
    _driver_status[req.name] = {
        "name": req.name,
        "workflow": req.workflow,
        "label": req.label,
        "state": req.state,
        "processed": req.processed,
        "pid": req.pid,
        "ts": req.ts,
        "received": time.time(),
    }
    return {"ok": True}


@app.get("/drivers/status")
def get_driver_status():
    now = time.time()
    out: dict[str, dict] = {}
    for name, st in _driver_status.items():
        live = (now - st.get("received", 0.0)) < _DRIVER_STALE_S
        out[name] = {**st, "live": live and st.get("state") != "stopped"}
    return out


@app.get("/drivers")
def list_drivers():
    """Readiness of each registered driver: ready / needs env / needs install."""
    return [driver_registry.driver_status(s) for s in driver_registry.list_drivers()]


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Driver subprocesses started from the editor (name -> Popen). Launched with the
# server's own interpreter, so they inherit the env the Install button uses.
_driver_procs: dict[str, "subprocess.Popen"] = {}
import collections
_driver_logs: dict[str, "collections.deque[str]"] = {}
_RUNTIME_KEYS = {"cookResult", "cookError", "cooking", "cookPort"}


def _drain_driver_output(name: str, proc: "subprocess.Popen") -> None:
    buf = _driver_logs[name]
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            buf.append(line.rstrip("\n"))
    except Exception:
        pass
    buf.append(f"[process exited, code {proc.poll()}]")


def _current_workflow() -> tuple[dict, dict | None]:
    """Build a runnable workflow from the live editor graph + pick an entrypoint."""
    node_meta = {
        nid: {k: v for k, v in meta.items() if k not in _RUNTIME_KEYS}
        for nid, meta in _session.node_meta.items()
    }
    entry = None
    for nid, meta in node_meta.items():
        if meta.get("type") in ("SlackReply", "TelegramReply"):
            entry = {"node_id": nid, "port": "text"}
            break
    if entry is None:
        for nid, meta in node_meta.items():
            if meta.get("type") == "Output":
                entry = {"node_id": nid, "port": "value"}
                break
    wf = {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Editor graph",
        "node_meta": node_meta,
        "edges": [dict(e) for e in _session.graph._edges],
        "entrypoint": entry,
    }
    return wf, entry


def _driver_running(name: str) -> bool:
    proc = _driver_procs.get(name)
    return proc is not None and proc.poll() is None


def _terminate_driver_process(proc: "subprocess.Popen") -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=3)
    except Exception:
        pass


def _stop_driver_proc(name: str) -> None:
    proc = _driver_procs.pop(name, None)
    if proc is not None:
        _terminate_driver_process(proc)
    _driver_status.pop(name, None)  # flip the badge offline immediately


def _spawn_driver(name: str) -> tuple[bool, str]:
    """Launch a driver subprocess on the current graph. Returns (ok, detail)."""
    spec = driver_registry.get_driver(name)
    if spec is None:
        return False, f"Unknown driver '{name}'"
    if not driver_registry.packages_installed(spec):
        return False, f"{spec.required_extra} is not installed — install it first."
    missing = driver_registry.missing_env(spec)
    if missing:
        return False, f"Set {', '.join(missing)} on the node first."
    if _driver_running(name):
        return True, "already running"
    wf, entry = _current_workflow()
    if entry is None:
        return False, "Graph needs a reply node (or Output) to drive."
    if not validate_bn_workflow(wf).ok:
        return False, "Graph is invalid; fix errors before starting."
    path = os.path.join(os.path.dirname(__file__), f".driver-{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2)
    # Tell the bot where the editor is, so each message cooks through live-sync
    # and the real run animates on the canvas (BLACKNODE_SYNC_URL), and so its
    # heartbeat reaches us (BLACKNODE_EDITOR_URL).
    env = dict(os.environ)
    env["BLACKNODE_SYNC_URL"] = "http://127.0.0.1:7777"
    env["BLACKNODE_EDITOR_URL"] = "http://127.0.0.1:7777"
    env["PYTHONIOENCODING"] = "utf-8"  # bot logs may contain unicode/emoji (Windows)
    process_group: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "blacknode.cli", name, path],
        cwd=_REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace", env=env,
        **process_group,
    )
    _driver_procs[name] = proc
    _driver_logs[name] = collections.deque(maxlen=300)
    threading.Thread(target=_drain_driver_output, args=(name, proc), daemon=True).start()
    return True, str(proc.pid)


def _restart_running_driver_for(provider: str) -> str | None:
    """If ``provider`` is a token for a *running* driver, restart it so the new
    value takes effect. Returns the restarted driver name, or None."""
    for spec in driver_registry.list_drivers():
        if provider in spec.required_env:
            if _driver_running(spec.name):
                _stop_driver_proc(spec.name)
                ok, _ = _spawn_driver(spec.name)
                return spec.name if ok else None
            return None
    return None


@app.post("/drivers/{name}/start")
def start_driver(name: str):
    ok, detail = _spawn_driver(name)
    if not ok:
        raise HTTPException(status_code=404 if detail.startswith("Unknown") else 400, detail=detail)
    return {"ok": True, "detail": detail}


@app.get("/drivers/{name}/logs")
def driver_logs(name: str):
    return {"running": _driver_running(name), "lines": list(_driver_logs.get(name, []))}


@app.get("/drivers/workflow")
def driver_current_workflow():
    """The live editor graph, so a running bot cooks the current shape per message."""
    wf, _ = _current_workflow()
    return wf


@app.post("/drivers/{name}/stop")
def stop_driver(name: str):
    _stop_driver_proc(name)
    return {"ok": True}


import atexit


@atexit.register
def _stop_all_drivers() -> None:
    for proc in list(_driver_procs.values()):
        _terminate_driver_process(proc)


@app.post("/drivers/{name}/install")
def install_driver(name: str):
    """Install a registered driver's optional extra (pip install -e .[extra])."""
    spec = driver_registry.get_driver(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown driver '{name}'")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f".[{spec.required_extra}]"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pip install timed out")
    importlib.invalidate_caches()  # so the next readiness check sees the new package
    log = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "log": log,
        "status": driver_registry.driver_status(spec),
    }


@app.get("/settings/custom-models")
def get_custom_models():
    return _custom_models


@app.post("/settings/custom-models")
def add_custom_model(req: AddCustomModelReq):
    if req.value and req.value not in _custom_models:
        _custom_models.append(req.value)
        _save_custom_models()
    return {"ok": True}


@app.delete("/settings/custom-models")
def remove_custom_model(value: str):
    if value in _custom_models:
        _custom_models.remove(value)
        _save_custom_models()
    return {"ok": True}


def _custom_node_globals() -> dict[str, Any]:
    return {
        "Any": bn.Any,
        "Bool": bn.Bool,
        "Dict": bn.Dict,
        "Embedding": bn.Embedding,
        "Float": bn.Float,
        "Fn": bn.Fn,
        "Int": bn.Int,
        "List": bn.List,
        "Model": bn.Model,
        "Number": bn.Number,
        "Text": bn.Text,
        "blacknode": bn,
        "bn": bn,
        "node": bn.node,
        "__builtins__": __builtins__,
    }


@app.post("/exec-node")
def exec_node(req: ExecNodeReq):
    import traceback
    before = set(_NODE_REGISTRY.keys())
    globs: dict = _custom_node_globals()
    try:
        exec(compile(req.code, "<custom>", "exec"), globs)
        new_types = sorted(set(_NODE_REGISTRY.keys()) - before)
        return {"ok": True, "new_types": new_types}
    except Exception:
        raise HTTPException(400, traceback.format_exc())


@app.get("/custom-nodes")
def list_custom_nodes():
    custom_dir = Path(_CUSTOM_NODES_DIR).resolve()
    files = []
    if custom_dir.exists():
        files = [str(path.relative_to(custom_dir)) for path in sorted(custom_dir.rglob("*.py")) if not path.name.startswith("_")]
    registered = [
        _node_def_payload(name, fn)
        for name, fn in sorted(_NODE_REGISTRY.items())
        if getattr(fn, "_bn_source_path", "")
    ]
    return {"directory": str(custom_dir), "files": files, "registered": registered}


@app.get("/packages")
def list_packages():
    return {"packages": [info.to_dict() for info in installed_packages()]}


@app.post("/packages/reload")
def reload_packages():
    report = discover_bn_packages()
    return {"ok": not report["failed"], **report}


@app.post("/custom-nodes/reload")
def reload_custom_nodes():
    report = discover_node_modules()
    if report.get("failed"):
        return {"ok": False, **report}
    return {"ok": True, **report}


@app.post("/custom-nodes")
def save_custom_node(req: SaveCustomNodeReq):
    import traceback

    try:
        compile(req.code, "<custom-node>", "exec")
    except Exception:
        raise HTTPException(400, traceback.format_exc())

    filename = _safe_custom_node_filename(req.filename)
    custom_dir = Path(_CUSTOM_NODES_DIR).resolve()
    custom_dir.mkdir(parents=True, exist_ok=True)
    path = (custom_dir / filename).resolve()
    if custom_dir not in path.parents and path != custom_dir:
        raise HTTPException(400, "Invalid custom node path")

    path.write_text(req.code, encoding="utf-8")
    result = load_node_file(path)
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "Could not load custom node"))
    return {"ok": True, "path": str(path), "new_types": result["new_types"]}


def _safe_custom_node_filename(filename: str) -> str:
    raw = Path(filename or "custom_node").name.strip()
    if raw.lower().endswith(".py"):
        raw = raw[:-3]
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw)
    stem = stem.strip("._-") or "custom_node"
    return f"{stem}.py"


@app.post("/reset")
def reset():
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    _save()
    return {"ok": True}


# ── Workflow persistence ──────────────────────────────────────────────────────

def _portable_subgraph(subgraph: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_meta": _portable_node_meta(subgraph.get("node_meta", {})),
        "edges": [dict(edge) for edge in subgraph.get("edges", [])],
    }


def _portable_node_meta(node_meta: dict[str, dict]) -> dict[str, dict]:
    portable: dict[str, dict] = {}
    for node_id, meta in node_meta.items():
        clean = {
            key: value
            for key, value in meta.items()
            if key not in _RUNTIME_STATUS_KEYS
        }
        if isinstance(clean.get("subgraph"), dict):
            clean["subgraph"] = _portable_subgraph(clean["subgraph"])
        portable[node_id] = clean
    return portable


def _workflow_payload(
    name: str,
    *,
    entrypoint: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": _WORKFLOW_KIND,
        "schema_version": _WORKFLOW_SCHEMA_VERSION,
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "node_meta": _portable_node_meta(_session.node_meta),
        "edges": [dict(edge) for edge in _session.graph._edges],
    }
    if entrypoint is not None:
        payload["entrypoint"] = dict(entrypoint)
    if metadata is not None:
        payload["metadata"] = dict(metadata)
    return payload


def _workflow_for_export(workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(workflow) if workflow is not None else _workflow_payload(
        "Current Graph",
        metadata={"source": "editor"},
    )
    _ensure_workflow_header(data)
    return data


def _export_framework_payload(target: str, workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return export_framework_workflow(_workflow_for_export(workflow), target)
    except Exception as exc:
        raise HTTPException(400, str(exc))


def _enqueue_sync_run_update(record: dict[str, Any], *, playing: bool) -> None:
    events = record.get("events") if isinstance(record.get("events"), list) else []
    cursor = len(events) - 1
    _enqueue_editor_action(
        "sync_run_event",
        {
            "record": _redact_run_snapshot_secrets(record),
            "cursor": cursor,
            "playing": playing,
        },
    )


def _redact_run_snapshot_secrets(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            item_key: _redact_run_snapshot_secrets(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_run_snapshot_secrets(item) for item in value]
    if key and _SECRET_FIELD_RE.search(key) and value not in (None, ""):
        return "[redacted]"
    return value


def _run_workflow_snapshot(node_id: str, port: str) -> dict[str, Any]:
    node_type = _session.node_meta.get(node_id, {}).get("type", "Graph")
    workflow = _workflow_payload(
        f"Run: {node_type}.{port}",
        entrypoint={"node_id": node_id, "port": port},
        metadata={"source": "run_history"},
    )
    return _redact_run_snapshot_secrets(workflow)


def _run_graph_workflow_snapshot(targets: list[tuple[str, str]]) -> dict[str, Any]:
    workflow = _workflow_payload(
        f"Run Graph: {len(targets)} terminal node{'s' if len(targets) != 1 else ''}",
        metadata={
            "source": "run_history",
            "run_scope": "terminal_nodes",
            "targets": [
                {"node_id": node_id, "port": port}
                for node_id, port in targets
            ],
        },
    )
    return _redact_run_snapshot_secrets(workflow)


def _ensure_workflow_header(data: dict[str, Any]) -> None:
    data.setdefault("kind", _WORKFLOW_KIND)
    data.setdefault("schema_version", _WORKFLOW_SCHEMA_VERSION)


def _slug(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip())[:60] or "workflow"

def _workflow_path(slug: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug):
        raise HTTPException(400, "Invalid workflow slug")
    return os.path.join(_WORKFLOWS_DIR, f"{slug}.json")


def _template_dirs() -> list[str]:
    # Root templates first so they win slug collisions with package templates.
    return [_TEMPLATES_DIR, *package_template_dirs()]


def _template_path(slug: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug):
        raise HTTPException(400, "Invalid template slug")
    for templates_dir in _template_dirs():
        path = os.path.join(templates_dir, f"{slug}.json")
        if os.path.exists(path):
            return path
    return os.path.join(_TEMPLATES_DIR, f"{slug}.json")


def _read_workflow_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise HTTPException(400, "Workflow file must contain a JSON object")
    _ensure_workflow_header(data)
    return data


def _workflow_summary(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return {
        "slug": slug,
        "name": data.get("name", slug),
        "saved_at": data.get("saved_at", ""),
        "description": metadata.get("description", ""),
        "color": metadata.get("color", "#6366f1"),
        "node_count": len(data.get("node_meta", {}) or {}),
    }


def _unique_workflow_slug(base_slug: str) -> str:
    slug = base_slug
    i = 2
    while os.path.exists(_workflow_path(slug)):
        suffix = f"_{i}"
        slug = f"{base_slug[:60 - len(suffix)]}{suffix}"
        i += 1
    return slug

def _save_workflow(name: str, previous_slug: str | None = None):
    os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
    clean_name = name.strip() or "Untitled"
    slug = _slug(clean_name)
    data = _workflow_payload(clean_name)
    with open(_workflow_path(slug), "w") as f:
        json.dump(data, f, indent=2)
    if previous_slug and previous_slug != slug:
        old_path = _workflow_path(previous_slug)
        if os.path.exists(old_path):
            os.remove(old_path)
    return {"ok": True, "slug": slug}

def _restore_session(node_meta: dict, edges: list):
    """Replace current session with the given node_meta + edges."""
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    for node_id, meta in node_meta.items():
        if meta["type"] not in _NODE_REGISTRY and meta["type"] not in _SUBGRAPH_NODE_TYPES:
            continue
        _migrate_legacy_node_meta(meta)
        if meta["type"] in _SUBGRAPH_NODE_TYPES:
            _sync_subgraph_node_ports(meta)
        elif meta["type"] in _TOOLBOX_NODE_TYPES:
            _sync_toolbox_ports(meta, edges)
        _session.node_meta[node_id] = meta
        node_entry = {
            "type":   meta["type"],
            "params": dict(meta.get("params", {})),
        }
        if meta["type"] in _SUBGRAPH_NODE_TYPES:
            node_entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
        _session.graph._nodes[node_id] = node_entry
        _session.graph._dirty.add(node_id)
    _session.graph._edges = [
        e for e in edges
        if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
    ]


def _restore_session_from_nodes(nodes: list[dict], edges: list):
    _restore_session({node["id"]: node for node in nodes if "id" in node}, edges)


def _node_pos(meta: dict) -> tuple[float, float]:
    pos = meta.get("pos", [0, 0])
    try:
        return float(pos[0]), float(pos[1])
    except Exception:
        return 0.0, 0.0


def _insert_workflow(node_meta: dict, edges: list):
    valid_nodes = [
        meta for meta in node_meta.values()
        if meta.get("type") in _NODE_REGISTRY or meta.get("type") in _SUBGRAPH_NODE_TYPES
    ]
    if not valid_nodes:
        return

    current_positions = [_node_pos(meta) for meta in _session.node_meta.values()]
    import_positions = [_node_pos(meta) for meta in valid_nodes]
    if current_positions:
        offset_x = max(x for x, _ in current_positions) - min(x for x, _ in import_positions) + 360
        offset_y = 0
    else:
        offset_x = 0
        offset_y = 0

    id_map: dict[str, str] = {}
    for meta in valid_nodes:
        old_id = meta["id"]
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id
        x, y = _node_pos(meta)
        next_meta = {
            **meta,
            "id": new_id,
            "params": dict(meta.get("params", {})),
            "pos": [x + offset_x, y + offset_y],
        }
        _migrate_legacy_node_meta(next_meta)
        if next_meta["type"] in _SUBGRAPH_NODE_TYPES:
            _sync_subgraph_node_ports(next_meta)
        elif next_meta["type"] in _TOOLBOX_NODE_TYPES:
            old_id_meta = {**next_meta, "id": old_id}
            _sync_toolbox_ports(old_id_meta, edges)
            next_meta.update({
                "inputs": old_id_meta["inputs"],
                "outputs": old_id_meta["outputs"],
                "input_types": old_id_meta["input_types"],
                "output_types": old_id_meta["output_types"],
                "input_defaults": old_id_meta["input_defaults"],
            })
        _session.node_meta[new_id] = next_meta
        _session.graph._nodes[new_id] = {
            "type": next_meta["type"],
            "params": dict(next_meta.get("params", {})),
        }
        if next_meta["type"] in _SUBGRAPH_NODE_TYPES:
            _session.graph._nodes[new_id]["subgraph"] = next_meta.get("subgraph", {"node_meta": {}, "edges": []})
        _session.graph._dirty.add(new_id)

    for edge in edges:
        from_id = id_map.get(edge.get("from"))
        to_id = id_map.get(edge.get("to"))
        if not from_id or not to_id:
            continue
        _session.graph._edges.append({
            "from": from_id,
            "from_port": edge.get("from_port", "output"),
            "to": to_id,
            "to_port": edge.get("to_port", "input"),
        })


@app.get("/workflows")
def list_workflows():
    os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
    result = []
    for fname in sorted(os.listdir(_WORKFLOWS_DIR)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_WORKFLOWS_DIR, fname)) as f:
                data = json.load(f)
            result.append({
                "slug":     fname[:-5],
                "name":     data.get("name", fname[:-5]),
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


@app.get("/templates")
def list_templates():
    result = []
    seen: set[str] = set()
    for templates_dir in _template_dirs():
        if not os.path.isdir(templates_dir):
            continue
        for fname in sorted(os.listdir(templates_dir)):
            if not fname.endswith(".json"):
                continue
            slug = fname[:-5]
            if slug in seen:
                continue
            try:
                data = _read_workflow_file(os.path.join(templates_dir, fname))
                result.append(_workflow_summary(slug, data))
                seen.add(slug)
            except Exception:
                pass
    return result


@app.get("/templates/{slug}/validate")
def validate_template(slug: str):
    path = _template_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Template '{slug}' not found")
    return validate_bn_workflow(_read_workflow_file(path)).to_dict()


@app.post("/templates/{slug}/load")
def load_template(slug: str):
    path = _template_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Template '{slug}' not found")
    data = _read_workflow_file(path)
    report = validate_bn_workflow(data)
    if not report.ok:
        raise HTTPException(400, report.to_dict())
    _restore_session(data.get("node_meta", {}), data.get("edges", []))
    _save()
    return get_graph()


@app.get("/validate")
def validate_current_workflow():
    report = validate_bn_graph(
        _portable_node_meta(_session.node_meta),
        [dict(edge) for edge in _session.graph._edges],
    )
    return report.to_dict()


@app.get("/export/frameworks")
def export_frameworks():
    return {"targets": list_export_targets()}


@app.post("/export/framework")
def export_framework(req: FrameworkExportReq):
    return _export_framework_payload(req.target, req.workflow)


@app.post("/export/langgraph")
def export_langgraph(req: ExportWorkflowReq | None = None):
    return _export_framework_payload("langgraph", req.workflow if req else None)


@app.post("/import/python")
@app.post("/api/workflows/current/import-python")
def import_python_workflow(req: ImportPythonReq):
    try:
        workflow = import_workflow_python(req.code, name=req.name.strip() or "Imported Python Workflow")
        _ensure_workflow_header(workflow)
        validation = validate_bn_workflow(workflow).to_dict()
    except SyntaxError as exc:
        raise HTTPException(400, f"Python parse error: {exc}")
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"workflow": workflow, "validation": validation}


@app.get("/api/workflows/current")
def api_current_workflow():
    workflow = _workflow_for_export()
    return {"workflow": workflow, "validation": validate_current_workflow()}


@app.post("/api/workflows/current/nodes")
def api_create_node(req: AddNodeReq):
    return add_node(req)


@app.post("/api/workflows/current/edges")
def api_connect_node(req: ConnectReq):
    return connect(req)


@app.get("/api/workflows/current/validate")
def api_validate_current_workflow():
    return validate_current_workflow()


@app.post("/api/workflows/current/run")
def api_run_current_workflow(req: CookReq):
    return cook(req)


@app.post("/api/workflows/current/export")
def api_export_current_workflow(req: FrameworkExportReq):
    return _export_framework_payload(req.target, req.workflow)


@app.websocket("/api/workflows/current/ws")
@app.websocket("/ws/workflows/current")
async def workflow_socket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "state", **api_current_workflow()})
    try:
        while True:
            message = await websocket.receive_json()
            action = str(message.get("action") or "get_state")
            if action == "get_state":
                await websocket.send_json({"type": "state", **api_current_workflow()})
            elif action == "validate":
                await websocket.send_json({"type": "validation", "validation": validate_current_workflow()})
            elif action == "export":
                target = str(message.get("target") or "langgraph")
                await websocket.send_json({"type": "export", **_export_framework_payload(target, message.get("workflow"))})
            else:
                await websocket.send_json({"type": "error", "error": f"Unknown action '{action}'"})
    except WebSocketDisconnect:
        return


@app.get("/workflows/{slug}/validate")
def validate_saved_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    return validate_bn_workflow(data).to_dict()


@app.post("/workflows")
def save_workflow(req: SaveWorkflowReq):
    return _save_workflow(req.name, req.previous_slug)


@app.post("/workflows/{name}")
def save_workflow_legacy(name: str):
    return _save_workflow(name)


@app.patch("/workflows/{slug}")
def rename_workflow(slug: str, req: RenameWorkflowReq):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    clean_name = req.name.strip() or "Untitled"
    next_slug = _slug(clean_name)
    next_path = _workflow_path(next_slug)
    if next_slug != slug and os.path.exists(next_path):
        raise HTTPException(409, f"Workflow '{clean_name}' already exists")
    with open(path) as f:
        data = json.load(f)
    _ensure_workflow_header(data)
    data["name"] = clean_name
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    with open(next_path, "w") as f:
        json.dump(data, f, indent=2)
    if next_slug != slug:
        os.remove(path)
    return {"slug": next_slug, "name": clean_name, "saved_at": data["saved_at"]}


@app.post("/workflows/{slug}/duplicate")
def duplicate_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _ensure_workflow_header(data)
    name = f"{data.get('name', slug)} copy"
    next_slug = _unique_workflow_slug(_slug(name))
    data["name"] = name
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    with open(_workflow_path(next_slug), "w") as f:
        json.dump(data, f, indent=2)
    return {"slug": next_slug, "name": name, "saved_at": data["saved_at"]}


@app.post("/workflows/{slug}/insert")
def insert_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _insert_workflow(data.get("node_meta", {}), data.get("edges", []))
    _save()
    return get_graph()


@app.post("/workflows/{slug}/load")
def load_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _restore_session(data.get("node_meta", {}), data.get("edges", []))
    _save()
    return get_graph()


@app.delete("/workflows/{slug}")
def delete_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    os.remove(path)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=7777,
        reload=True,
        reload_dirs=[
            os.path.dirname(__file__),
            os.path.join(os.path.dirname(__file__), "..", "python"),
        ],
    )
