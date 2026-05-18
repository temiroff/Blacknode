"""Blacknode editor backend — FastAPI server the React editor talks to."""
from __future__ import annotations
import uuid
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import blacknode as bn
from blacknode.node import _NODE_REGISTRY

app = FastAPI(title="Blacknode Editor Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── In-memory state ───────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.graph = bn.Graph()
        self.node_meta: dict[str, dict] = {}  # id -> {type, params, pos}

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

class CookReq(BaseModel):
    node_id: str
    port: str = "output"

class ExecNodeReq(BaseModel):
    code: str

class SetApiKeyReq(BaseModel):
    provider: str
    key: str

_PROVIDER_ENV: dict[str, str] = {
    "Anthropic":      "ANTHROPIC_API_KEY",
    "OpenAI":         "OPENAI_API_KEY",
    "NVIDIA NIM":     "NVIDIA_API_KEY",
}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/node-types")
def list_node_types():
    """Return all registered node type names."""
    return sorted(_NODE_REGISTRY.keys())


@app.get("/graph")
def get_graph():
    """Return current graph state (nodes + edges)."""
    return {
        "nodes": list(_session.node_meta.values()),
        "edges": _session.graph._edges,
    }


@app.post("/nodes")
def add_node(req: AddNodeReq):
    if req.type_name not in _NODE_REGISTRY:
        raise HTTPException(400, f"Unknown node type '{req.type_name}'")
    proxy = _session.graph.node(req.type_name, **req.params)
    fn = _NODE_REGISTRY[req.type_name]
    meta = {
        "id": proxy._id,
        "type": req.type_name,
        "params": req.params,
        "pos": list(req.pos),
        "inputs": getattr(fn, "_bn_inputs", []),
        "outputs": getattr(fn, "_bn_outputs", ["output"]),
        "input_types": getattr(fn, "_bn_input_types", {}),
        "output_types": getattr(fn, "_bn_output_types", {}),
    }
    _session.node_meta[proxy._id] = meta
    return meta


@app.delete("/nodes/{node_id}")
def remove_node(node_id: str):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    del _session.node_meta[node_id]
    # remove connected edges
    _session.graph._edges = [
        e for e in _session.graph._edges
        if e["from"] != node_id and e["to"] != node_id
    ]
    _session.graph._nodes.pop(node_id, None)
    _session.graph._dirty.discard(node_id)
    return {"ok": True}


@app.patch("/nodes/{node_id}/params")
def update_param(node_id: str, req: UpdateParamReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    _session.node_meta[node_id]["params"][req.key] = req.value
    _session.graph._nodes[node_id]["params"][req.key] = req.value
    _session.graph._dirty.add(node_id)
    return _session.node_meta[node_id]


@app.patch("/nodes/{node_id}/pos")
def update_pos(node_id: str, pos: list[float]):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    _session.node_meta[node_id]["pos"] = pos
    return {"ok": True}


@app.post("/edges")
def connect(req: ConnectReq):
    try:
        _session.graph._add_edge(req.from_id, req.from_port, req.to_id, req.to_port)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/edges")
def disconnect(from_id: str, from_port: str, to_id: str, to_port: str):
    _session.graph._edges = [
        e for e in _session.graph._edges
        if not (e["from"] == from_id and e["from_port"] == from_port
                and e["to"] == to_id and e["to_port"] == to_port)
    ]
    return {"ok": True}


@app.post("/cook")
def cook(req: CookReq):
    if req.node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    try:
        proxy = bn.NodeProxy(_session.graph, req.node_id,
                             _session.node_meta[req.node_id]["type"], {})
        result = _session.graph.cook(proxy, req.port)
        return {"value": result, "port": req.port}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/settings/api-key")
def set_api_key(req: SetApiKeyReq):
    """Write a provider API key into os.environ so all node functions pick it up."""
    env_var = _PROVIDER_ENV.get(req.provider)
    if env_var and req.key:
        os.environ[env_var] = req.key
    return {"ok": True}


@app.post("/exec-node")
def exec_node(req: ExecNodeReq):
    """Execute Python code and register any new @node-decorated functions."""
    import traceback
    before = set(_NODE_REGISTRY.keys())
    globs: dict = {
        'node': bn.node,
        '__builtins__': __builtins__,
    }
    try:
        exec(compile(req.code, '<custom>', 'exec'), globs)
        new_types = sorted(set(_NODE_REGISTRY.keys()) - before)
        return {"ok": True, "new_types": new_types}
    except Exception:
        raise HTTPException(400, traceback.format_exc())


@app.post("/reset")
def reset():
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7777)
