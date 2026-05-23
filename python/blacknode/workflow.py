from __future__ import annotations

import json
import keyword
import pprint
import time
import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .node import _NODE_REGISTRY

WORKFLOW_KIND = "blacknode.workflow"
WORKFLOW_SCHEMA_VERSION = 1
RUNTIME_STATUS_KEYS = {"cookResult", "cookError", "cooking", "cookPort"}
SUBGRAPH_NODE_TYPES = {"Subnet", "SubnetAsTool", "VisualAgentLoop"}
SPECIAL_NODE_TYPES = {"Subnet"}

_COMPAT: dict[str, set[str]] = {
    "Text": {"Text", "Any"},
    "Int": {"Int", "Float", "Number", "Any"},
    "Float": {"Float", "Int", "Number", "Any"},
    "Number": {"Number", "Int", "Float", "Any"},
    "Bool": {"Bool", "Any"},
    "List": {"List", "Any"},
    "Dict": {"Dict", "Any"},
    "Embedding": {"Embedding", "Any"},
    "Fn": {"Fn", "Any"},
    "Model": {"Model", "Text", "Any"},
}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str
    severity: str = "error"


@dataclass
class ValidationReport:
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
        }


class WorkflowRunError(Exception):
    def __init__(self, message: str, *, run_id: str | None = None, events: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.run_id = run_id
        self.events = events or []


class RunLogger:
    def __init__(self):
        self.run_id = str(uuid.uuid4())
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def emit(self, event_type: str, **fields: Any) -> None:
        self._events.append({
            "type": event_type,
            "run_id": self.run_id,
            "ts": time.time(),
            **fields,
        })

    def node_start(self, node_id: str, node_type: str, port: str) -> None:
        self.emit("node_start", node_id=node_id, node_type=node_type, port=port)

    def node_finish(
        self,
        node_id: str,
        node_type: str,
        port: str,
        *,
        duration_ms: float,
        outputs: Mapping[str, Any],
        cached: bool = False,
    ) -> None:
        self.emit(
            "node_finish",
            node_id=node_id,
            node_type=node_type,
            port=port,
            duration_ms=round(duration_ms, 3),
            output_ports=sorted(str(key) for key in outputs),
            cached=cached,
        )

    def node_error(self, node_id: str, node_type: str, port: str, *, duration_ms: float, error: str) -> None:
        self.emit(
            "node_error",
            node_id=node_id,
            node_type=node_type,
            port=port,
            duration_ms=round(duration_ms, 3),
            error=error,
        )

    def model_call(
        self,
        *,
        node_id: str | None,
        model: str,
        provider: str | None = None,
        action: str = "complete",
        tool_count: int | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "node_id": node_id,
            "model": model,
            "action": action,
        }
        if provider:
            fields["provider"] = provider
        if tool_count is not None:
            fields["tool_count"] = tool_count
        self.emit("model_call", **fields)

    def tool_call(self, *, node_id: str | None, name: str, arguments: Mapping[str, Any] | None = None) -> None:
        self.emit("tool_call", node_id=node_id, name=name, arguments=dict(arguments or {}))


def ports_compatible(from_type: str, to_type: str) -> bool:
    if from_type == "Any" or to_type == "Any":
        return True
    if from_type == to_type:
        return True
    return to_type in _COMPAT.get(from_type, set())


def validate_graph(
    node_meta: Mapping[str, Any],
    edges: list[Any],
    *,
    entrypoint: Mapping[str, Any] | None = None,
    require_output: bool = True,
    path: str = "$",
) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    _validate_graph(
        node_meta,
        edges,
        entrypoint=entrypoint,
        require_output=require_output,
        path=path,
        errors=errors,
        warnings=warnings,
        is_root=True,
    )
    return ValidationReport(errors=errors, warnings=warnings)


def validate_workflow(data: Mapping[str, Any]) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    if data.get("kind", WORKFLOW_KIND) != WORKFLOW_KIND:
        _error(errors, "invalid_kind", "Workflow kind must be 'blacknode.workflow'.", "$.kind")
    if data.get("schema_version", WORKFLOW_SCHEMA_VERSION) != WORKFLOW_SCHEMA_VERSION:
        _error(errors, "unsupported_schema_version", "Workflow schema_version must be 1.", "$.schema_version")

    node_meta = data.get("node_meta")
    edges = data.get("edges")
    if not isinstance(node_meta, Mapping):
        _error(errors, "invalid_node_meta", "Workflow node_meta must be an object.", "$.node_meta")
        node_meta = {}
    if not isinstance(edges, list):
        _error(errors, "invalid_edges", "Workflow edges must be an array.", "$.edges")
        edges = []

    entrypoint = data.get("entrypoint")
    if entrypoint is not None and not isinstance(entrypoint, Mapping):
        _error(errors, "invalid_entrypoint", "Workflow entrypoint must be an object.", "$.entrypoint")
        entrypoint = None

    _validate_graph(
        node_meta,
        edges,
        entrypoint=entrypoint,
        require_output=True,
        path="$",
        errors=errors,
        warnings=warnings,
        is_root=True,
    )
    return ValidationReport(errors=errors, warnings=warnings)


def load_workflow(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise WorkflowRunError("Workflow file must contain a JSON object.")
    return data


def graph_from_workflow(data: Mapping[str, Any]):
    from .graph import Graph

    graph = Graph()
    node_meta = data.get("node_meta") or {}
    edges = data.get("edges") or []
    for node_id, meta in node_meta.items():
        entry = {
            "type": meta["type"],
            "params": dict(meta.get("params", {})),
        }
        if isinstance(meta.get("subgraph"), Mapping):
            entry["subgraph"] = _runtime_subgraph(meta["subgraph"])
        graph._nodes[node_id] = entry
        graph._dirty.add(node_id)
    graph._edges = [dict(edge) for edge in edges]
    return graph


def infer_entrypoint(data: Mapping[str, Any]) -> tuple[str, str]:
    entrypoint = data.get("entrypoint")
    if isinstance(entrypoint, Mapping):
        node_id = entrypoint.get("node_id")
        port = entrypoint.get("port")
        if isinstance(node_id, str) and isinstance(port, str):
            return node_id, port

    node_meta = data.get("node_meta") or {}
    output_nodes = [
        node_id
        for node_id, meta in node_meta.items()
        if isinstance(meta, Mapping) and meta.get("type") == "Output"
    ]
    if len(output_nodes) == 1:
        return output_nodes[0], "value"
    if not output_nodes:
        raise WorkflowRunError("Workflow has no Output node or explicit entrypoint.")
    raise WorkflowRunError("Workflow has multiple Output nodes; add an explicit entrypoint.")


def run_workflow(data: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_workflow(data)
    if not report.ok:
        raise WorkflowRunError(json.dumps(report.to_dict(), indent=2))

    node_id, port = infer_entrypoint(data)
    graph = graph_from_workflow(data)
    logger = RunLogger()
    graph._run_logger = logger
    logger.emit("run_start", node_id=node_id, port=port)
    try:
        value = _cook_logged(graph, node_id, port, logger)
    except Exception as exc:
        logger.emit("run_error", node_id=node_id, port=port, error=traceback.format_exc())
        raise WorkflowRunError(str(exc), run_id=logger.run_id, events=logger.events) from exc
    logger.emit("run_finish", node_id=node_id, port=port)
    return {
        "run_id": logger.run_id,
        "node_id": node_id,
        "port": port,
        "value": value,
        "events": logger.events,
    }


def run_workflow_logged(data: Mapping[str, Any]) -> dict[str, Any]:
    return run_workflow(data)


def export_workflow_python(data: Mapping[str, Any], *, style: str = "flat") -> str:
    report = validate_workflow(data)
    if not report.ok:
        raise WorkflowRunError(json.dumps(report.to_dict(), indent=2))
    if style not in {"flat", "class"}:
        raise ValueError("Python export style must be 'flat' or 'class'.")

    node_id, port = infer_entrypoint(data)
    node_meta = data.get("node_meta") or {}
    edges = data.get("edges") or []
    names = _python_node_names_from_meta(node_meta)
    workflow_payload = _export_workflow_payload(data)
    lines = [
        "from __future__ import annotations",
        "",
        "import blacknode as bn",
        "from blacknode.live_sync import run_graph_live",
        "",
        "",
        "def _bind_node_id(graph: bn.Graph, node: bn.NodeProxy, node_id: str) -> bn.NodeProxy:",
        "    generated_id = node._id",
        "    node._id = node_id",
        "    node._params = graph._nodes[generated_id]['params']",
        "    graph._nodes[node_id] = graph._nodes.pop(generated_id)",
        "    graph._dirty.discard(generated_id)",
        "    graph._dirty.add(node_id)",
        "    return node",
        "",
        "",
        f"_WORKFLOW = {_pretty_literal(workflow_payload)}",
        "",
    ]

    if style == "class":
        lines.extend(_export_workflow_python_class(node_meta, edges, names, node_id, port))
    else:
        lines.extend(_export_workflow_python_flat(node_meta, edges, names, node_id, port))
    lines.append("")
    return "\n".join(lines)


def _export_workflow_python_flat(
    node_meta: Mapping[str, Any],
    edges: list[dict[str, Any]],
    names: Mapping[str, str],
    node_id: str,
    port: str,
) -> list[str]:
    lines = [
        "g = bn.Graph()",
        "",
    ]
    for index, (original_id, meta) in enumerate(node_meta.items(), start=1):
        lines.extend(_node_binding_lines(
            graph_expr="g",
            target_expr=names[str(original_id)],
            original_id=str(original_id),
            meta=meta,
            step=index,
            indent="",
        ))
    lines.extend(_edge_lines(edges, names, indent=""))
    lines.extend([
        f"result = run_graph_live(g, {node_id!r}, {port!r}, workflow=_WORKFLOW)",
        "print(result)",
    ])
    return lines


def _export_workflow_python_class(
    node_meta: Mapping[str, Any],
    edges: list[dict[str, Any]],
    names: Mapping[str, str],
    node_id: str,
    port: str,
) -> list[str]:
    lines = [
        "class BlacknodeWorkflow:",
        "    def __init__(self) -> None:",
        "        self.graph = bn.Graph()",
        "",
    ]
    for index, (original_id, meta) in enumerate(node_meta.items(), start=1):
        lines.extend(_node_binding_lines(
            graph_expr="self.graph",
            target_expr=f"self.{names[str(original_id)]}",
            original_id=str(original_id),
            meta=meta,
            step=index,
            indent="        ",
        ))
    lines.extend(_edge_lines(edges, {key: f"self.{value}" for key, value in names.items()}, indent="        "))
    lines.extend([
        "    def run(self):",
        f"        return run_graph_live(self.graph, {node_id!r}, {port!r}, workflow=_WORKFLOW)",
        "",
        "",
        "if __name__ == \"__main__\":",
        "    workflow = BlacknodeWorkflow()",
        "    print(workflow.run())",
    ])
    return lines


def _node_binding_lines(
    *,
    graph_expr: str,
    target_expr: str,
    original_id: str,
    meta: Mapping[str, Any],
    step: int,
    indent: str,
) -> list[str]:
    params = dict(meta.get("params", {}))
    call = _format_node_call(graph_expr, str(meta["type"]), params)
    label = _node_label(original_id, meta).replace("\n", " ").strip()
    lines = [
        f"{indent}# Step {step}: {label}",
        f"{indent}{target_expr} = _bind_node_id({graph_expr}, {call}, {original_id!r})",
    ]
    subgraph = meta.get("subgraph")
    if isinstance(subgraph, Mapping):
        lines.append(f"{indent}{graph_expr}._nodes[{original_id!r}]['subgraph'] = {_literal(_runtime_subgraph(subgraph))}")
    lines.append("")
    return lines


def _edge_lines(edges: list[dict[str, Any]], names: Mapping[str, str], *, indent: str) -> list[str]:
    lines: list[str] = []
    if edges:
        lines.append(f"{indent}# Wire node outputs into inputs.")
    for edge in edges:
        from_name = names[str(edge["from"])]
        to_name = names[str(edge["to"])]
        lines.append(
            f"{indent}{from_name}.out({str(edge['from_port'])!r}) >> "
            f"{to_name}.inp({str(edge['to_port'])!r})"
        )
    if lines:
        lines.append("")
    return lines


def _format_node_call(graph_expr: str, type_name: str, params: Mapping[str, Any]) -> str:
    if not params:
        return f"{graph_expr}.node({type_name!r})"
    keyword_parts: list[str] = []
    splat: dict[str, Any] = {}
    for key, value in params.items():
        if _is_python_kwarg(key):
            keyword_parts.append(f"{key}={_literal(value)}")
        else:
            splat[str(key)] = value
    args = [repr(type_name)]
    args.extend(keyword_parts)
    if splat:
        args.append(f"**{_literal(splat)}")
    return f"{graph_expr}.node({', '.join(args)})"


def _export_workflow_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    node_id, port = infer_entrypoint(data)
    payload: dict[str, Any] = {
        "kind": WORKFLOW_KIND,
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "name": str(data.get("name") or "Blacknode Workflow"),
        "node_meta": {
            str(node_id): dict(meta)
            for node_id, meta in (data.get("node_meta") or {}).items()
            if isinstance(meta, Mapping)
        },
        "edges": [
            dict(edge)
            for edge in (data.get("edges") or [])
            if isinstance(edge, Mapping)
        ],
        "entrypoint": {"node_id": node_id, "port": port},
    }
    saved_at = data.get("saved_at")
    if saved_at:
        payload["saved_at"] = saved_at
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        payload["metadata"] = dict(metadata)
    return payload


def _cook_logged(graph, node_id: str, port: str, logger: RunLogger) -> Any:
    cache_key = (node_id, port)
    node_def = graph._nodes[node_id]
    node_type = node_def["type"]
    if node_id not in graph._dirty and cache_key in graph._cache:
        outputs = {
            cached_port: value
            for (cached_id, cached_port), value in graph._cache.items()
            if cached_id == node_id
        }
        logger.node_finish(node_id, node_type, port, duration_ms=0.0, outputs=outputs, cached=True)
        return graph._cache[cache_key]

    ctx = dict(node_def["params"])
    for edge in graph._edges:
        if edge["to"] == node_id:
            ctx[edge["to_port"]] = _cook_logged(graph, edge["from"], edge["from_port"], logger)

    logger.node_start(node_id, node_type, port)
    started = time.perf_counter()
    try:
        if node_type == "Subnet":
            result = _cook_subnet_logged(graph, node_id, port, ctx, logger)
        else:
            fn = _NODE_REGISTRY[node_type]
            ctx["__graph__"] = graph
            ctx["__node_id__"] = node_id
            ctx["__run_logger__"] = logger
            result = fn(ctx)
        if not isinstance(result, dict):
            result = {"output": result}
        for output_port, value in result.items():
            graph._cache[(node_id, output_port)] = value
        graph._dirty.discard(node_id)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.node_finish(node_id, node_type, port, duration_ms=duration_ms, outputs=result)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.node_error(node_id, node_type, port, duration_ms=duration_ms, error=str(exc))
        raise

    if cache_key not in graph._cache:
        raise KeyError(
            f"Node '{node_type}' did not produce port '{port}'. "
            f"Available: {[cached_port for (cached_id, cached_port) in graph._cache if cached_id == node_id]}"
        )
    return graph._cache[cache_key]


def _cook_subnet_logged(graph, node_id: str, port: str, outer_ctx: dict, logger: RunLogger) -> dict[str, Any]:
    from .graph import Graph

    subgraph = graph._nodes[node_id].get("subgraph", {})
    inner_meta = subgraph.get("node_meta", {})
    inner_edges = subgraph.get("edges", [])

    inner = Graph.__new__(Graph)
    inner._edges = inner_edges
    inner._cache = {}
    inner._dirty = set(inner_meta.keys())
    inner._nodes = {}
    inner._run_logger = logger
    for nid, meta in inner_meta.items():
        entry = {"type": meta["type"], "params": dict(meta.get("params", {}))}
        if "subgraph" in meta:
            entry["subgraph"] = meta["subgraph"]
        inner._nodes[nid] = entry

    for nid, meta in inner_meta.items():
        if meta["type"] == "SubnetInput":
            injected = {
                out_port: outer_ctx[out_port]
                for out_port in meta.get("outputs", [])
                if out_port in outer_ctx
            }
            for out_port, value in injected.items():
                inner._cache[(nid, out_port)] = value
            inner._dirty.discard(nid)
            logger.node_finish(nid, "SubnetInput", "inputs", duration_ms=0.0, outputs=injected, cached=True)

    for nid, meta in inner_meta.items():
        if meta["type"] == "SubnetOutput":
            try:
                return {port: _cook_logged(inner, nid, port, logger)}
            except KeyError:
                return {port: None}

    return {port: None}


def _validate_graph(
    node_meta: Mapping[str, Any],
    edges: list[Any],
    *,
    entrypoint: Mapping[str, Any] | None,
    require_output: bool,
    path: str,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
    is_root: bool,
) -> None:
    known_nodes: dict[str, Mapping[str, Any]] = {}
    seen_value_ids: dict[str, str] = {}

    for key, raw_meta in node_meta.items():
        node_path = f"{path}.node_meta.{key}"
        if not isinstance(raw_meta, Mapping):
            _error(errors, "invalid_node", "Node metadata must be an object.", node_path)
            continue

        node_id = raw_meta.get("id")
        if not isinstance(node_id, str) or not node_id:
            _error(errors, "invalid_node_id", "Node id must be a non-empty string.", f"{node_path}.id")
            continue
        if node_id != key:
            _error(errors, "node_id_mismatch", f"Node id '{node_id}' does not match node_meta key '{key}'.", f"{node_path}.id")
        if node_id in seen_value_ids:
            _error(errors, "duplicate_node_id", f"Node id '{node_id}' is also used by '{seen_value_ids[node_id]}'.", f"{node_path}.id")
        seen_value_ids[node_id] = key
        known_nodes[key] = raw_meta

        _validate_node(raw_meta, node_path, errors, warnings)

    _validate_entrypoint(
        known_nodes,
        entrypoint,
        require_output=require_output,
        path=path,
        errors=errors,
        warnings=warnings,
        is_root=is_root,
    )
    _validate_edges(known_nodes, edges, path, errors)
    _validate_acyclic_edges(known_nodes, edges, path, errors)

    for key, meta in known_nodes.items():
        node_type = str(meta.get("type", ""))
        subgraph = meta.get("subgraph")
        if node_type in SUBGRAPH_NODE_TYPES:
            if not isinstance(subgraph, Mapping):
                _error(errors, "missing_subgraph", f"{node_type} node must include a subgraph object.", f"{path}.node_meta.{key}.subgraph")
                continue
            inner_meta = subgraph.get("node_meta")
            inner_edges = subgraph.get("edges")
            if not isinstance(inner_meta, Mapping):
                _error(errors, "invalid_subgraph_node_meta", "Subgraph node_meta must be an object.", f"{path}.node_meta.{key}.subgraph.node_meta")
                inner_meta = {}
            if not isinstance(inner_edges, list):
                _error(errors, "invalid_subgraph_edges", "Subgraph edges must be an array.", f"{path}.node_meta.{key}.subgraph.edges")
                inner_edges = []
            _validate_graph(
                inner_meta,
                inner_edges,
                entrypoint=None,
                require_output=True,
                path=f"{path}.node_meta.{key}.subgraph",
                errors=errors,
                warnings=warnings,
                is_root=False,
            )


def _validate_node(
    meta: Mapping[str, Any],
    path: str,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> None:
    node_type = meta.get("type")
    if not isinstance(node_type, str) or not node_type:
        _error(errors, "invalid_node_type", "Node type must be a non-empty string.", f"{path}.type")
    elif node_type not in _NODE_REGISTRY and node_type not in SPECIAL_NODE_TYPES:
        _error(errors, "unknown_node_type", f"Unknown node type '{node_type}'.", f"{path}.type")

    if not isinstance(meta.get("params"), Mapping):
        _error(errors, "invalid_params", "Node params must be an object.", f"{path}.params")
    if not _is_position(meta.get("pos")):
        _error(errors, "invalid_position", "Node pos must be a two-number array.", f"{path}.pos")

    inputs = _port_list(meta.get("inputs"), f"{path}.inputs", errors)
    outputs = _port_list(meta.get("outputs"), f"{path}.outputs", errors)
    _check_duplicate_ports(inputs, f"{path}.inputs", errors)
    _check_duplicate_ports(outputs, f"{path}.outputs", errors)
    _port_type_map(meta.get("input_types"), inputs, f"{path}.input_types", errors, warnings)
    _port_type_map(meta.get("output_types"), outputs, f"{path}.output_types", errors, warnings)

    input_defaults = meta.get("input_defaults")
    if not isinstance(input_defaults, Mapping):
        _error(errors, "invalid_input_defaults", "Node input_defaults must be an object.", f"{path}.input_defaults")
    else:
        for port in input_defaults:
            if port not in inputs:
                _warn(warnings, "unknown_input_default", f"Input default references unknown input port '{port}'.", f"{path}.input_defaults.{port}")

    multi_input_ports = meta.get("multi_input_ports")
    if multi_input_ports is not None:
        ports = _port_list(multi_input_ports, f"{path}.multi_input_ports", errors)
        for port in ports:
            if port not in inputs:
                _error(errors, "invalid_multi_input_port", f"Multi-input port '{port}' is not an input port.", f"{path}.multi_input_ports")

    runtime_keys = sorted(key for key in RUNTIME_STATUS_KEYS if key in meta)
    for key in runtime_keys:
        _error(errors, "runtime_status_in_workflow", f"Runtime-only field '{key}' must not be saved in workflow files.", f"{path}.{key}")


def _validate_entrypoint(
    nodes: Mapping[str, Mapping[str, Any]],
    entrypoint: Mapping[str, Any] | None,
    *,
    require_output: bool,
    path: str,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
    is_root: bool,
) -> None:
    if entrypoint is not None:
        node_id = entrypoint.get("node_id")
        port = entrypoint.get("port")
        if not isinstance(node_id, str) or not node_id:
            _error(errors, "invalid_entrypoint_node", "Entrypoint node_id must be a non-empty string.", f"{path}.entrypoint.node_id")
            return
        if not isinstance(port, str) or not port:
            _error(errors, "invalid_entrypoint_port", "Entrypoint port must be a non-empty string.", f"{path}.entrypoint.port")
            return
        meta = nodes.get(node_id)
        if meta is None:
            _error(errors, "missing_entrypoint_node", f"Entrypoint node '{node_id}' does not exist.", f"{path}.entrypoint.node_id")
            return
        if port not in _cookable_ports(meta):
            _error(errors, "invalid_entrypoint_port", f"Entrypoint port '{port}' is not cookable on node '{node_id}'.", f"{path}.entrypoint.port")
        return

    if not require_output:
        return

    output_type = "Output" if is_root else "SubnetOutput"
    output_nodes = [node_id for node_id, meta in nodes.items() if meta.get("type") == output_type]
    if not output_nodes:
        code = "missing_output_node" if is_root else "missing_subgraph_output_node"
        _error(errors, code, f"Graph must include an {output_type} node or explicit entrypoint.", path)
    elif is_root and len(output_nodes) > 1:
        _warn(warnings, "multiple_output_nodes", "Graph has multiple Output nodes; add an entrypoint to make CLI execution unambiguous.", path)


def _validate_edges(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: list[Any],
    path: str,
    errors: list[ValidationIssue],
) -> None:
    for index, edge in enumerate(edges):
        edge_path = f"{path}.edges[{index}]"
        if not isinstance(edge, Mapping):
            _error(errors, "invalid_edge", "Edge must be an object.", edge_path)
            continue

        from_id = edge.get("from")
        from_port = edge.get("from_port")
        to_id = edge.get("to")
        to_port = edge.get("to_port")
        for field, value in (("from", from_id), ("from_port", from_port), ("to", to_id), ("to_port", to_port)):
            if not isinstance(value, str) or not value:
                _error(errors, "invalid_edge_field", f"Edge field '{field}' must be a non-empty string.", f"{edge_path}.{field}")

        if not all(isinstance(value, str) and value for value in (from_id, from_port, to_id, to_port)):
            continue

        source = nodes.get(from_id)
        target = nodes.get(to_id)
        if source is None:
            _error(errors, "missing_source_node", f"Edge source node '{from_id}' does not exist.", f"{edge_path}.from")
        if target is None:
            _error(errors, "missing_target_node", f"Edge target node '{to_id}' does not exist.", f"{edge_path}.to")
        if source is None or target is None:
            continue

        source_outputs = set(_list_value(source.get("outputs")))
        target_inputs = set(_list_value(target.get("inputs")))
        if from_port not in source_outputs:
            _error(errors, "invalid_source_port", f"Node '{from_id}' has no output port '{from_port}'.", f"{edge_path}.from_port")
        if to_port not in target_inputs:
            _error(errors, "invalid_target_port", f"Node '{to_id}' has no input port '{to_port}'.", f"{edge_path}.to_port")
        if from_port not in source_outputs or to_port not in target_inputs:
            continue

        from_type = str(_mapping_value(source.get("output_types")).get(from_port, "Any"))
        to_type = str(_mapping_value(target.get("input_types")).get(to_port, "Any"))
        if not ports_compatible(from_type, to_type):
            _error(errors, "incompatible_port_types", f"Cannot connect {from_type} output to {to_type} input.", edge_path)


def _validate_acyclic_edges(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: list[Any],
    path: str,
    errors: list[ValidationIssue],
) -> None:
    graph: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        from_id = edge.get("from")
        to_id = edge.get("to")
        if isinstance(from_id, str) and isinstance(to_id, str) and from_id in nodes and to_id in nodes:
            graph[from_id].append(to_id)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        if node_id in visiting:
            start = stack.index(node_id) if node_id in stack else 0
            return [*stack[start:], node_id]
        if node_id in visited:
            return None
        visiting.add(node_id)
        stack.append(node_id)
        for child_id in graph.get(node_id, []):
            cycle = visit(child_id)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return None

    for node_id in graph:
        cycle = visit(node_id)
        if cycle:
            _error(errors, "cycle_detected", f"Workflow edges must be acyclic; detected cycle: {' -> '.join(cycle)}.", f"{path}.edges")
            return


def _cookable_ports(meta: Mapping[str, Any]) -> set[str]:
    ports = set(_list_value(meta.get("outputs")))
    if meta.get("type") in {"Output", "SubnetOutput"}:
        ports.update(_list_value(meta.get("inputs")))
    return ports


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


def _port_list(value: Any, path: str, errors: list[ValidationIssue]) -> list[str]:
    if not isinstance(value, list):
        _error(errors, "invalid_port_list", "Port list must be an array.", path)
        return []
    ports: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            _error(errors, "invalid_port_name", "Port names must be non-empty strings.", f"{path}[{index}]")
        else:
            ports.append(item)
    return ports


def _port_type_map(
    value: Any,
    ports: list[str],
    path: str,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        _error(errors, "invalid_port_type_map", "Port type map must be an object.", path)
        return {}
    port_set = set(ports)
    result: dict[str, str] = {}
    for port, typ in value.items():
        if not isinstance(port, str) or not port:
            _error(errors, "invalid_port_type_key", "Port type keys must be non-empty strings.", path)
            continue
        if not isinstance(typ, str) or not typ:
            _error(errors, "invalid_port_type_value", f"Port type for '{port}' must be a non-empty string.", f"{path}.{port}")
            continue
        if port not in port_set:
            _warn(warnings, "unknown_typed_port", f"Type map references unknown port '{port}'.", f"{path}.{port}")
        result[port] = typ
    return result


def _check_duplicate_ports(ports: list[str], path: str, errors: list[ValidationIssue]) -> None:
    seen: set[str] = set()
    for port in ports:
        if port in seen:
            _error(errors, "duplicate_port", f"Port '{port}' is duplicated.", path)
        seen.add(port)


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _error(errors: list[ValidationIssue], code: str, message: str, path: str) -> None:
    errors.append(ValidationIssue(code=code, message=message, path=path, severity="error"))


def _warn(warnings: list[ValidationIssue], code: str, message: str, path: str) -> None:
    warnings.append(ValidationIssue(code=code, message=message, path=path, severity="warning"))


def _runtime_subgraph(subgraph: Mapping[str, Any]) -> dict[str, Any]:
    node_meta = subgraph.get("node_meta") or {}
    edges = subgraph.get("edges") or []
    return {
        "node_meta": {
            str(node_id): dict(meta)
            for node_id, meta in node_meta.items()
            if isinstance(meta, Mapping)
        },
        "edges": [
            dict(edge)
            for edge in edges
            if isinstance(edge, Mapping)
        ],
    }


def _python_node_names_from_meta(node_meta: Mapping[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    used: set[str] = {"bn", "g", "graph", "result", "run_graph_live", "workflow", "_WORKFLOW", "_bind_node_id"}
    for fallback_index, (node_id, meta) in enumerate(node_meta.items(), start=1):
        label = _node_label(str(node_id), meta if isinstance(meta, Mapping) else {})
        base = _python_identifier(label) or f"node_{fallback_index}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        names[str(node_id)] = name
        used.add(name)
    return names


def _python_node_names(node_ids) -> dict[str, str]:
    names: dict[str, str] = {}
    used: set[str] = {"bn", "g", "graph", "result", "run_graph_live", "workflow", "_WORKFLOW", "_bind_node_id"}
    for fallback_index, node_id in enumerate(node_ids, start=1):
        base = _python_identifier(str(node_id)) or f"node_{fallback_index}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        names[str(node_id)] = name
        used.add(name)
    return names


def _python_identifier(value: str) -> str:
    chars = [ch if ch.isalnum() or ch == "_" else "_" for ch in value.strip()]
    name = "".join(chars).strip("_").lower()
    if not name:
        return ""
    if name[0].isdigit():
        name = f"node_{name}"
    if name in {"False", "None", "True"} or keyword.iskeyword(name):
        name = f"{name.lower()}_node"
    return name


def _node_label(node_id: str, meta: Mapping[str, Any]) -> str:
    params = meta.get("params", {}) if isinstance(meta, Mapping) else {}
    if isinstance(params, Mapping):
        for key in ("label", "name", "title"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    type_name = meta.get("type") if isinstance(meta, Mapping) else None
    if isinstance(type_name, str) and type_name.strip():
        return type_name.strip()
    return node_id


def _is_python_kwarg(value: Any) -> bool:
    return isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)


def _literal(value: Any) -> str:
    return repr(value)


def _pretty_literal(value: Any) -> str:
    return pprint.pformat(value, width=100, sort_dicts=False)
