"""Blacknode editor backend — FastAPI server the React editor talks to."""
from __future__ import annotations
import uuid, os, sys, json, threading, re
from datetime import datetime
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import blacknode as bn
from blacknode.node import _NODE_REGISTRY

app = FastAPI(title="Blacknode Editor Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Persistence ───────────────────────────────────────────────────────────────

_SAVE_PATH      = os.path.join(os.path.dirname(__file__), "blacknode_graph.json")
_WORKFLOWS_DIR  = os.path.join(os.path.dirname(__file__), "..", "workflows")
_save_timer: threading.Timer | None = None


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
        for node_id, meta in meta_map.items():
            if meta["type"] not in _NODE_REGISTRY:
                continue
            _session.node_meta[node_id] = meta
            _session.graph._nodes[node_id] = {
                "type":   meta["type"],
                "params": dict(meta.get("params", {})),
            }
            _session.graph._dirty.add(node_id)
        _session.graph._edges = [
            e for e in edges
            if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
        ]
        print(f"[blacknode] Loaded {len(_session.node_meta)} nodes, "
              f"{len(_session.graph._edges)} edges from {_SAVE_PATH}")
    except Exception as e:
        print(f"[blacknode] Could not load saved graph: {e}")


# ── In-memory state ───────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.graph = bn.Graph()
        self.node_meta: dict[str, dict] = {}

_session = Session()
_load()   # restore last session on startup


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

class CookReq(BaseModel):
    node_id: str
    port: str = "output"

class ExecNodeReq(BaseModel):
    code: str

class SetApiKeyReq(BaseModel):
    provider: str
    key: str

class SaveWorkflowReq(BaseModel):
    name: str
    previous_slug: str | None = None

_PROVIDER_ENV: dict[str, str] = {
    "Anthropic":     "ANTHROPIC_API_KEY",
    "OpenAI":        "OPENAI_API_KEY",
    "NVIDIA NIM":    "NVIDIA_API_KEY",
    "Ollama (local)": "",
}

_KEYS_PATH = os.path.join(os.path.dirname(__file__), "api_keys.json")
_api_keys: dict[str, str] = {}


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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/node-types")
def list_node_types():
    return sorted(_NODE_REGISTRY.keys())


@app.get("/graph")
def get_graph():
    """Return nodes with types always read fresh from registry."""
    nodes = []
    for meta in _session.node_meta.values():
        fn = _NODE_REGISTRY.get(meta["type"])
        nodes.append({
            **meta,
            "inputs":       getattr(fn, "_bn_inputs",       meta.get("inputs",       [])),
            "outputs":      getattr(fn, "_bn_outputs",      meta.get("outputs",      [])),
            "input_types":  getattr(fn, "_bn_input_types",  meta.get("input_types",  {})),
            "output_types": getattr(fn, "_bn_output_types", meta.get("output_types", {})),
        })
    return {"nodes": nodes, "edges": _session.graph._edges}


@app.post("/nodes")
def add_node(req: AddNodeReq):
    if req.type_name not in _NODE_REGISTRY:
        raise HTTPException(400, f"Unknown node type '{req.type_name}'")
    proxy = _session.graph.node(req.type_name, **req.params)
    fn = _NODE_REGISTRY[req.type_name]
    meta = {
        "id":           proxy._id,
        "type":         req.type_name,
        "params":       req.params,
        "pos":          list(req.pos),
        "inputs":       getattr(fn, "_bn_inputs",       []),
        "outputs":      getattr(fn, "_bn_outputs",      ["output"]),
        "input_types":  getattr(fn, "_bn_input_types",  {}),
        "output_types": getattr(fn, "_bn_output_types", {}),
    }
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
    _save()
    return {"ok": True}


@app.delete("/edges")
def disconnect(from_id: str, from_port: str, to_id: str, to_port: str):
    _session.graph._edges = [
        e for e in _session.graph._edges
        if not (e["from"] == from_id and e["from_port"] == from_port
                and e["to"] == to_id and e["to_port"] == to_port)
    ]
    _save()
    return {"ok": True}


@app.post("/cook")
def cook(req: CookReq):
    import traceback
    if req.node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if req.node_id not in _session.graph._nodes:
        raise HTTPException(500, f"Node {req.node_id} missing from graph (try resetting)")
    try:
        proxy  = bn.NodeProxy(_session.graph, req.node_id,
                              _session.node_meta[req.node_id]["type"], {})
        result = _session.graph.cook(proxy, req.port)
        return {"value": result, "port": req.port}
    except Exception:
        raise HTTPException(500, traceback.format_exc())


@app.get("/settings/api-keys")
def get_api_keys():
    return _api_keys


@app.post("/settings/api-key")
def set_api_key(req: SetApiKeyReq):
    env_var = _PROVIDER_ENV.get(req.provider)
    if env_var is not None:
        if req.key:
            os.environ[env_var] = req.key
        elif env_var in os.environ:
            del os.environ[env_var]
    _api_keys[req.provider] = req.key
    _save_api_keys()
    return {"ok": True}


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


@app.post("/exec-node")
def exec_node(req: ExecNodeReq):
    import traceback
    before = set(_NODE_REGISTRY.keys())
    globs: dict = {"node": bn.node, "__builtins__": __builtins__}
    try:
        exec(compile(req.code, "<custom>", "exec"), globs)
        new_types = sorted(set(_NODE_REGISTRY.keys()) - before)
        return {"ok": True, "new_types": new_types}
    except Exception:
        raise HTTPException(400, traceback.format_exc())


@app.post("/reset")
def reset():
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    _save()
    return {"ok": True}


# ── Workflow persistence ──────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip())[:60] or "workflow"

def _workflow_path(slug: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug):
        raise HTTPException(400, "Invalid workflow slug")
    return os.path.join(_WORKFLOWS_DIR, f"{slug}.json")

def _save_workflow(name: str, previous_slug: str | None = None):
    os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
    clean_name = name.strip() or "Untitled"
    slug = _slug(clean_name)
    data = {
        "name":      clean_name,
        "saved_at":  datetime.now().isoformat(timespec="seconds"),
        "node_meta": _session.node_meta,
        "edges":     _session.graph._edges,
    }
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
        if meta["type"] not in _NODE_REGISTRY:
            continue
        _session.node_meta[node_id] = meta
        _session.graph._nodes[node_id] = {
            "type":   meta["type"],
            "params": dict(meta.get("params", {})),
        }
        _session.graph._dirty.add(node_id)
    _session.graph._edges = [
        e for e in edges
        if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
    ]


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


@app.post("/workflows")
def save_workflow(req: SaveWorkflowReq):
    return _save_workflow(req.name, req.previous_slug)


@app.post("/workflows/{name}")
def save_workflow_legacy(name: str):
    return _save_workflow(name)


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
