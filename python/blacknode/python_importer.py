from __future__ import annotations

import ast
import time
from typing import Any

from .node import _NODE_REGISTRY
from .workflow import WORKFLOW_KIND, WORKFLOW_SCHEMA_VERSION, SUBGRAPH_NODE_TYPES


class PythonImportError(ValueError):
    pass


def import_workflow_python(source: str, *, name: str = "Imported Python Workflow") -> dict[str, Any]:
    tree = ast.parse(source)
    importer = _PythonWorkflowImporter(name)
    importer.visit(tree)
    return importer.workflow()


class _PythonWorkflowImporter(ast.NodeVisitor):
    def __init__(self, name: str):
        self.name = name
        self.node_meta: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.entrypoint: dict[str, str] | None = None
        self.source_workflow: dict[str, Any] | None = None
        self.runtime_nodes: dict[str, Any] | None = None
        self.runtime_edges: list[Any] | None = None
        self._var_to_id: dict[str, str] = {}
        self._next_position = 0

    def workflow(self) -> dict[str, Any]:
        if not self.node_meta and _looks_like_workflow(self.source_workflow):
            payload = dict(self.source_workflow or {})
            payload["name"] = self.name
            metadata = dict(payload.get("metadata") or {})
            metadata["source"] = "python_import"
            payload["metadata"] = metadata
            return payload
        if not self.node_meta and self.runtime_nodes is not None:
            return _workflow_from_runtime(
                self.runtime_nodes,
                self.runtime_edges or [],
                name=self.name,
                entrypoint=self.entrypoint,
            )

        node_meta = self._enriched_node_meta()
        edges = self.edges or _source_edges(self.source_workflow)
        entrypoint = self.entrypoint or _source_entrypoint(self.source_workflow)
        payload: dict[str, Any] = {
            "kind": WORKFLOW_KIND,
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "name": self.name,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "node_meta": node_meta,
            "edges": edges,
            "metadata": {"source": "python_import"},
        }
        if entrypoint:
            payload["entrypoint"] = dict(entrypoint)
        return payload

    def visit_Assign(self, node: ast.Assign) -> Any:
        value = node.value
        for target in node.targets:
            target_name = _target_name(target)
            if not target_name:
                continue
            if target_name in {"_WORKFLOW", "_BLACKNODE_WORKFLOW"}:
                embedded = _literal_dict(value)
                if _looks_like_workflow(embedded):
                    self.source_workflow = embedded
                continue
            if target_name == "_RUNTIME_NODES":
                embedded_nodes = _literal_dict(value)
                if isinstance(embedded_nodes, dict):
                    self.runtime_nodes = embedded_nodes
                continue
            if target_name == "_RUNTIME_EDGES":
                embedded_edges = _literal_list(value)
                if isinstance(embedded_edges, list):
                    self.runtime_edges = embedded_edges
                continue
            node_call = _extract_node_call(value)
            if node_call is not None:
                type_name, params, explicit_id = node_call
                node_id = explicit_id or target_name
                self._add_node(target_name, node_id, type_name, params)
                continue
            cook_target = _extract_cook_call(value, self._var_to_id)
            if cook_target is not None:
                self.entrypoint = cook_target
                continue

        subgraph_assignment = _extract_subgraph_assignment(node)
        if subgraph_assignment is not None:
            node_id, subgraph = subgraph_assignment
            if node_id in self.node_meta and isinstance(subgraph, dict):
                self.node_meta[node_id]["subgraph"] = subgraph

        edge_assignment = _extract_edge_assignment(node)
        if edge_assignment is not None:
            self.edges = edge_assignment

        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> Any:
        edge = _extract_wire_expr(node.value, self._var_to_id)
        if edge is not None:
            self.edges.append(edge)
            return
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> Any:
        if node.value is not None:
            cook_target = _extract_cook_call(node.value, self._var_to_id)
            if cook_target is not None:
                self.entrypoint = cook_target
                return
        self.generic_visit(node)

    def _add_node(self, target_name: str, node_id: str, type_name: str, params: dict[str, Any]) -> None:
        fn = _NODE_REGISTRY.get(type_name)
        x = 120 + (self._next_position % 4) * 240
        y = 80 + (self._next_position // 4) * 160
        self._next_position += 1
        meta: dict[str, Any] = {
            "id": node_id,
            "type": type_name,
            "params": params,
            "pos": [x, y],
            "inputs": getattr(fn, "_bn_inputs", []),
            "outputs": getattr(fn, "_bn_outputs", ["output"]) if fn else ["output"],
            "input_types": getattr(fn, "_bn_input_types", {}),
            "output_types": getattr(fn, "_bn_output_types", {}),
            "input_defaults": getattr(fn, "_bn_input_defaults", {}),
        }
        if fn is not None and getattr(fn, "_bn_primary_inputs", None) is not None:
            meta["promoted_inputs"] = list(fn._bn_primary_inputs)
        if fn is not None and getattr(fn, "_bn_primary_outputs", None) is not None:
            meta["promoted_outputs"] = list(fn._bn_primary_outputs)
        if type_name in SUBGRAPH_NODE_TYPES:
            meta["subgraph"] = {"node_meta": {}, "edges": []}
        self.node_meta[node_id] = meta
        self._var_to_id[target_name] = node_id

    def _enriched_node_meta(self) -> dict[str, dict[str, Any]]:
        source_nodes = _source_node_meta(self.source_workflow)
        if not source_nodes:
            return self.node_meta
        enriched: dict[str, dict[str, Any]] = {}
        preserve_keys = (
            "pos",
            "inputs",
            "outputs",
            "input_types",
            "output_types",
            "input_defaults",
            "multi_input_ports",
            "variadic_input",
            "promoted_inputs",
            "promoted_outputs",
            "subgraph",
        )
        for node_id, meta in self.node_meta.items():
            original = source_nodes.get(node_id)
            if not isinstance(original, dict):
                enriched[node_id] = meta
                continue
            merged = dict(meta)
            for key in preserve_keys:
                if key in original:
                    merged[key] = original[key]
            merged["id"] = node_id
            merged["type"] = meta["type"]
            merged["params"] = meta["params"]
            enriched[node_id] = merged
        return enriched


def _extract_node_call(value: ast.AST) -> tuple[str, dict[str, Any], str | None] | None:
    explicit_id: str | None = None
    call = value
    if isinstance(value, ast.Call) and _call_name(value.func) == "_bind_node_id":
        if len(value.args) < 3:
            return None
        call = value.args[1]
        explicit_id = _literal_string(value.args[2])
    if not isinstance(call, ast.Call) or not _is_node_call(call):
        return None
    if not call.args:
        return None
    type_name = _literal_string(call.args[0])
    if not type_name:
        return None
    return type_name, _call_kwargs(call), explicit_id


def _extract_cook_call(value: ast.AST, var_to_id: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(value, ast.Call):
        return None
    if isinstance(value.func, ast.Attribute) and value.func.attr == "cook":
        node_ref = _ref_name(value.func.value)
        node_id = var_to_id.get(node_ref or "")
        if node_id:
            return {"node_id": node_id, "port": _first_string_arg(value, "output")}
    if _is_attr_call(value, "_cook") and len(value.args) >= 2:
        node_id = _literal_string(value.args[0])
        port = _literal_string(value.args[1]) or "output"
        if node_id:
            return {"node_id": node_id, "port": port}
    if _call_name(value.func) == "run_graph_live" and len(value.args) >= 3:
        node_id = _literal_string(value.args[1])
        port = _literal_string(value.args[2]) or "output"
        if node_id:
            return {"node_id": node_id, "port": port}
    return None


def _extract_wire_expr(value: ast.AST, var_to_id: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.RShift):
        return None
    left = _extract_port_call(value.left, "out", var_to_id)
    right = _extract_port_call(value.right, "inp", var_to_id)
    if left is None or right is None:
        return None
    from_id, from_port = left
    to_id, to_port = right
    return {"from": from_id, "from_port": from_port, "to": to_id, "to_port": to_port}


def _extract_port_call(value: ast.AST, method: str, var_to_id: dict[str, str]) -> tuple[str, str] | None:
    if not isinstance(value, ast.Call):
        return None
    if not isinstance(value.func, ast.Attribute) or value.func.attr != method:
        return None
    ref_name = _ref_name(value.func.value)
    node_id = var_to_id.get(ref_name or "")
    if not node_id:
        return None
    default_port = "output" if method == "out" else "input"
    return node_id, _first_string_arg(value, default_port)


def _extract_subgraph_assignment(node: ast.Assign) -> tuple[str, Any] | None:
    for target in node.targets:
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Subscript)
            and _subscript_key(target) == "subgraph"
            and _subscript_key(target.value)
        ):
            return str(_subscript_key(target.value)), ast.literal_eval(node.value)
    return None


def _extract_edge_assignment(node: ast.Assign) -> list[dict[str, str]] | None:
    for target in node.targets:
        if isinstance(target, ast.Attribute) and target.attr == "_edges":
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if isinstance(value, list):
                return [dict(edge) for edge in value if isinstance(edge, dict)]
    return None


def _call_kwargs(call: ast.Call) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for keyword in call.keywords:
        try:
            value = ast.literal_eval(keyword.value)
        except (ValueError, SyntaxError):
            continue
        if keyword.arg is None:
            if isinstance(value, dict):
                params.update(value)
        else:
            params[keyword.arg] = value
    return params


def _literal_dict(value: ast.AST) -> dict[str, Any] | None:
    try:
        literal = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    return literal if isinstance(literal, dict) else None


def _literal_list(value: ast.AST) -> list[Any] | None:
    try:
        literal = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    return literal if isinstance(literal, list) else None


def _workflow_from_runtime(
    runtime_nodes: dict[str, Any],
    runtime_edges: list[Any],
    *,
    name: str,
    entrypoint: dict[str, str] | None,
) -> dict[str, Any]:
    node_meta: dict[str, dict[str, Any]] = {}
    for index, (node_id, raw_node) in enumerate(runtime_nodes.items()):
        if not isinstance(raw_node, dict):
            continue
        type_name = str(raw_node.get("type") or "")
        fn = _NODE_REGISTRY.get(type_name)
        meta: dict[str, Any] = {
            "id": str(node_id),
            "type": type_name,
            "params": dict(raw_node.get("params") or {}),
            "pos": [120 + (index % 4) * 240, 80 + (index // 4) * 160],
            "inputs": list(getattr(fn, "_bn_inputs", [])),
            "outputs": list(getattr(fn, "_bn_outputs", ["output"]) if fn else ["output"]),
            "input_types": dict(getattr(fn, "_bn_input_types", {})),
            "output_types": dict(getattr(fn, "_bn_output_types", {})),
            "input_defaults": dict(getattr(fn, "_bn_input_defaults", {})),
        }
        if isinstance(raw_node.get("subgraph"), dict):
            meta["subgraph"] = raw_node["subgraph"]
        elif type_name in SUBGRAPH_NODE_TYPES:
            meta["subgraph"] = {"node_meta": {}, "edges": []}
        node_meta[str(node_id)] = meta

    edges = [
        dict(edge)
        for edge in runtime_edges
        if isinstance(edge, dict)
    ]
    payload: dict[str, Any] = {
        "kind": WORKFLOW_KIND,
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "name": name,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "node_meta": node_meta,
        "edges": edges,
        "metadata": {"source": "python_import", "import_format": "langgraph_runtime"},
    }
    resolved_entrypoint = entrypoint or _infer_runtime_entrypoint(node_meta)
    if resolved_entrypoint:
        payload["entrypoint"] = resolved_entrypoint
    return payload


def _infer_runtime_entrypoint(node_meta: dict[str, dict[str, Any]]) -> dict[str, str] | None:
    for node_id, meta in node_meta.items():
        if meta.get("type") in {"Output", "SubnetOutput"}:
            inputs = meta.get("inputs") or []
            port = "value" if "value" in inputs else (str(inputs[0]) if inputs else "output")
            return {"node_id": node_id, "port": port}
    for node_id, meta in node_meta.items():
        outputs = meta.get("outputs") or []
        if outputs:
            return {"node_id": node_id, "port": str(outputs[0])}
    return None


def _looks_like_workflow(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("kind") == WORKFLOW_KIND
        and isinstance(value.get("node_meta"), dict)
        and isinstance(value.get("edges"), list)
    )


def _source_node_meta(workflow: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not _looks_like_workflow(workflow):
        return {}
    nodes = workflow.get("node_meta", {})
    return {
        str(node_id): dict(meta)
        for node_id, meta in nodes.items()
        if isinstance(meta, dict)
    }


def _source_edges(workflow: dict[str, Any] | None) -> list[dict[str, str]]:
    if not _looks_like_workflow(workflow):
        return []
    return [
        dict(edge)
        for edge in workflow.get("edges", [])
        if isinstance(edge, dict)
    ]


def _source_entrypoint(workflow: dict[str, Any] | None) -> dict[str, str] | None:
    if not _looks_like_workflow(workflow):
        return None
    entrypoint = workflow.get("entrypoint")
    if not isinstance(entrypoint, dict):
        return None
    node_id = entrypoint.get("node_id")
    port = entrypoint.get("port")
    if isinstance(node_id, str) and isinstance(port, str):
        return {"node_id": node_id, "port": port}
    return None


def _is_node_call(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == "node"


def _is_attr_call(call: ast.Call, attr: str) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == attr


def _call_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _target_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _ref_name(value: ast.AST) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _literal_string(value: ast.AST) -> str | None:
    try:
        literal = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    return literal if isinstance(literal, str) else None


def _first_string_arg(call: ast.Call, default: str) -> str:
    if call.args:
        return _literal_string(call.args[0]) or default
    return default


def _subscript_key(node: ast.Subscript) -> Any:
    try:
        return ast.literal_eval(node.slice)
    except (ValueError, SyntaxError):
        return None
