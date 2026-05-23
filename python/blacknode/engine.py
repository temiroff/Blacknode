from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Protocol, Sequence

from .graph import Graph
from .node import _NODE_REGISTRY
from .workflow import (
    SUBGRAPH_NODE_TYPES,
    WORKFLOW_KIND,
    WORKFLOW_SCHEMA_VERSION,
    ValidationReport,
    validate_graph,
)


class WorkflowEngine(Protocol):
    """Common control surface for agents and non-MCP framework adapters."""

    def create_node(
        self,
        type_name: str,
        params: Mapping[str, Any] | None = None,
        pos: Sequence[float] = (0.0, 0.0),
    ) -> dict[str, Any]:
        ...

    def connect(self, from_id: str, from_port: str, to_id: str, to_port: str) -> dict[str, str]:
        ...

    def validate(self) -> ValidationReport:
        ...

    def execute(self, node_id: str, port: str = "output") -> Any:
        ...

    def get_state(self) -> dict[str, Any]:
        ...


@dataclass
class BlacknodeWorkflowEngine:
    """WorkflowEngine backed by Blacknode's native graph runtime."""

    graph: Graph = field(default_factory=Graph)
    node_meta: MutableMapping[str, dict[str, Any]] = field(default_factory=dict)

    def create_node(
        self,
        type_name: str,
        params: Mapping[str, Any] | None = None,
        pos: Sequence[float] = (0.0, 0.0),
    ) -> dict[str, Any]:
        params_dict = dict(params or {})
        if type_name not in SUBGRAPH_NODE_TYPES and type_name not in _NODE_REGISTRY:
            raise ValueError(f"Unknown node type '{type_name}'")

        proxy = self.graph.node(type_name, **params_dict)
        fn = _NODE_REGISTRY.get(type_name)
        meta: dict[str, Any] = {
            "id": proxy._id,
            "type": type_name,
            "params": params_dict,
            "pos": [float(pos[0]), float(pos[1])],
            "inputs": getattr(fn, "_bn_inputs", []) if fn else [],
            "outputs": getattr(fn, "_bn_outputs", ["output"]) if fn else [],
            "input_types": getattr(fn, "_bn_input_types", {}) if fn else {},
            "output_types": getattr(fn, "_bn_output_types", {}) if fn else {},
            "input_defaults": getattr(fn, "_bn_input_defaults", {}) if fn else {},
        }
        if type_name in SUBGRAPH_NODE_TYPES:
            meta["subgraph"] = {"node_meta": {}, "edges": []}
            self.graph._nodes[proxy._id]["subgraph"] = meta["subgraph"]

        self.node_meta[proxy._id] = meta
        return dict(meta)

    def connect(self, from_id: str, from_port: str, to_id: str, to_port: str) -> dict[str, str]:
        self.graph._add_edge(from_id, from_port, to_id, to_port)
        return {"from": from_id, "from_port": from_port, "to": to_id, "to_port": to_port}

    def validate(self) -> ValidationReport:
        return validate_graph(dict(self.node_meta), [dict(edge) for edge in self.graph._edges])

    def execute(self, node_id: str, port: str = "output") -> Any:
        self.graph._cache.clear()
        self.graph._dirty = set(self.graph._nodes)
        return self.graph._cook(node_id, port)

    def get_state(self) -> dict[str, Any]:
        return {
            "nodes": [dict(meta) for meta in self.node_meta.values()],
            "edges": [dict(edge) for edge in self.graph._edges],
        }

    def workflow_payload(
        self,
        name: str = "Blacknode Workflow",
        *,
        entrypoint: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": WORKFLOW_KIND,
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "name": name,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "node_meta": {node_id: dict(meta) for node_id, meta in self.node_meta.items()},
            "edges": [dict(edge) for edge in self.graph._edges],
        }
        if entrypoint is not None:
            payload["entrypoint"] = dict(entrypoint)
        if metadata is not None:
            payload["metadata"] = dict(metadata)
        return payload
