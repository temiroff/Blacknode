from __future__ import annotations
from typing import Any
import uuid
import json

from .node import _NODE_REGISTRY


class _Wire:
    """Represents a pending connection from a node output port."""
    def __init__(self, src: NodeProxy, port: str):
        self._src = src
        self._port = port

    def __rshift__(self, dest: _InputRef) -> _InputRef:
        dest._node._graph._add_edge(
            self._src._id, self._port,
            dest._node._id, dest._port,
        )
        return dest


class _InputRef:
    def __init__(self, node: NodeProxy, port: str):
        self._node = node
        self._port = port


class NodeProxy:
    """Handle to a node in the graph — used for wiring and cooking."""

    def __init__(self, graph: Graph, node_id: str, type_name: str, params: dict):
        self._graph = graph
        self._id = node_id
        self._type = type_name
        self._params = params

    def out(self, port: str = "output") -> _Wire:
        return _Wire(self, port)

    def inp(self, port: str = "input") -> _InputRef:
        return _InputRef(self, port)

    def set(self, **kwargs) -> NodeProxy:
        self._params.update(kwargs)
        self._graph._nodes[self._id]["params"].update(kwargs)
        self._graph._dirty.add(self._id)
        return self

    def cook(self, port: str = "output") -> Any:
        return self._graph.cook(self, port)

    def __repr__(self) -> str:
        return f"<Node {self._type} id={self._id[:8]}>"


class Graph:
    """Pure-Python Blacknode graph.

    Nodes execute lazily — cooking a port pulls from all upstream nodes first.
    Results are cached until a node (or any of its ancestors) is dirtied.
    """

    def __init__(self):
        self._nodes: dict[str, dict] = {}  # id -> {type, params}
        self._edges: list[dict] = []       # {from, from_port, to, to_port}
        self._cache: dict[tuple, Any] = {}
        self._dirty: set[str] = set()

    # ── Building ──────────────────────────────────────────────────────────────

    def node(self, type_name: str, **params) -> NodeProxy:
        """Add a node of the given registered type."""
        if type_name != "Subnet" and type_name not in _NODE_REGISTRY:
            raise ValueError(
                f"Unknown node type '{type_name}'. "
                f"Available: {sorted(_NODE_REGISTRY)}"
            )
        node_id = str(uuid.uuid4())
        self._nodes[node_id] = {"type": type_name, "params": dict(params)}
        self._dirty.add(node_id)
        return NodeProxy(self, node_id, type_name, params)

    def _add_edge(self, from_id: str, from_port: str, to_id: str, to_port: str):
        self._edges = [e for e in self._edges if not (e["to"] == to_id and e["to_port"] == to_port)]
        self._edges.append({
            "from": from_id, "from_port": from_port,
            "to":   to_id,   "to_port":   to_port,
        })
        self._mark_dirty(to_id)

    def _mark_dirty(self, node_id: str):
        if node_id in self._dirty:
            return
        self._dirty.add(node_id)
        for e in self._edges:
            if e["from"] == node_id:
                self._mark_dirty(e["to"])

    # ── Cooking ───────────────────────────────────────────────────────────────

    def cook(self, node_proxy: NodeProxy, port: str = "output") -> Any:
        """Pull-cook the requested port of a node."""
        return self._cook(node_proxy._id, port)

    def _cook(self, node_id: str, port: str) -> Any:
        cache_key = (node_id, port)
        if node_id not in self._dirty and cache_key in self._cache:
            return self._cache[cache_key]

        node_def = self._nodes[node_id]
        ctx = dict(node_def["params"])

        # resolve upstream wires
        for e in self._edges:
            if e["to"] == node_id:
                val = self._cook(e["from"], e["from_port"])
                ctx[e["to_port"]] = val

        # Subnet: delegate to nested graph
        if node_def["type"] == "Subnet":
            result = self._cook_subnet(node_id, port, ctx)
            for k, v in result.items():
                self._cache[(node_id, k)] = v
            self._dirty.discard(node_id)
            if cache_key not in self._cache:
                raise KeyError(f"Subnet '{node_id}' did not produce port '{port}'.")
            return self._cache[cache_key]

        fn = _NODE_REGISTRY[node_def["type"]]
        result = fn(ctx)

        if not isinstance(result, dict):
            result = {"output": result}

        for k, v in result.items():
            self._cache[(node_id, k)] = v
        self._dirty.discard(node_id)

        if cache_key not in self._cache:
            raise KeyError(
                f"Node '{node_def['type']}' did not produce port '{port}'. "
                f"Available: {[k for (_, k) in self._cache if _ == node_id]}"
            )
        return self._cache[cache_key]

    def _cook_subnet(self, node_id: str, port: str, outer_ctx: dict) -> dict:
        """Cook a Subnet node by executing its internal subgraph."""
        subgraph = self._nodes[node_id].get("subgraph", {})
        inner_meta = subgraph.get("node_meta", {})
        inner_edges = subgraph.get("edges", [])

        # Build ephemeral inner graph
        inner = Graph.__new__(Graph)
        inner._edges = inner_edges
        inner._cache = {}
        inner._dirty = set(inner_meta.keys())
        inner._nodes = {
            nid: {"type": m["type"], "params": dict(m.get("params", {}))}
            for nid, m in inner_meta.items()
        }

        # Inject outer input values into the single SubgraphInput node's output
        # ports.  We pre-populate the cache so downstream nodes can pull from
        # it without ever calling the Python function.
        for nid, m in inner_meta.items():
            if m["type"] == "SubgraphInput":
                for out_port in m.get("outputs", []):
                    if out_port in outer_ctx:
                        inner._cache[(nid, out_port)] = outer_ctx[out_port]
                inner._dirty.discard(nid)

        # Find the single SubgraphOutput node and cook the requested port.
        for nid, m in inner_meta.items():
            if m["type"] == "SubgraphOutput":
                try:
                    val = inner._cook(nid, port)
                except KeyError:
                    val = None
                return {port: val}

        return {port: None}

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"nodes": self._nodes, "edges": self._edges}

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> Graph:
        with open(path) as f:
            data = json.load(f)
        g = cls()
        g._nodes = data["nodes"]
        g._edges = data["edges"]
        g._dirty = set(g._nodes)
        return g
