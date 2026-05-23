from __future__ import annotations

import json
import keyword
import re
from collections import defaultdict
from typing import Any, Mapping

from ..workflow import WorkflowRunError, infer_entrypoint, validate_workflow


def export_langgraph_workflow(data: Mapping[str, Any]) -> tuple[str, list[str]]:
    report = validate_workflow(data)
    if not report.ok:
        raise WorkflowRunError(json.dumps(report.to_dict(), indent=2))

    entry_node, entry_port = infer_entrypoint(data)
    node_meta = _node_meta(data)
    edges = [dict(edge) for edge in data.get("edges") or []]
    node_names = _unique_names(node_meta.keys(), prefix="node")

    output_ports = {
        node_id: _output_ports(node_id, meta, edges, (entry_node, entry_port))
        for node_id, meta in node_meta.items()
    }
    state_keys = _state_keys(node_names, output_ports)
    incoming = _incoming_edges(edges)
    predecessors = _predecessors(edges)
    successors = _successors(edges)
    runtime_nodes = _runtime_nodes(node_meta)

    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from typing import Any, TypedDict",
        "",
        "import blacknode as bn",
        "from blacknode.node import _NODE_REGISTRY",
        "from langgraph.graph import END, START, StateGraph",
        "",
        "",
        f"_RUNTIME_NODES = {runtime_nodes!r}",
        f"_RUNTIME_EDGES = {edges!r}",
        "",
        "_RUNTIME_GRAPH = bn.Graph()",
        "_RUNTIME_GRAPH._nodes = _RUNTIME_NODES",
        "_RUNTIME_GRAPH._edges = _RUNTIME_EDGES",
        "_RUNTIME_GRAPH._dirty = set(_RUNTIME_NODES)",
        "_RUNTIME_GRAPH._cache = {}",
        "",
        "",
        "class WorkflowState(TypedDict, total=False):",
    ]

    for key in sorted({key for outputs in state_keys.values() for key in outputs.values()}):
        lines.append(f"    {key}: Any")
    if not any(state_keys.values()):
        lines.append("    value: Any")

    lines.extend([
        "",
        "",
        "def _run_blacknode_node(",
        "    node_id: str,",
        "    type_name: str,",
        "    ctx: dict[str, Any],",
        "    output_ports: list[str],",
        ") -> dict[str, Any]:",
        "    ctx['__graph__'] = _RUNTIME_GRAPH",
        "    ctx['__node_id__'] = node_id",
        "    if type_name == 'Subnet':",
        "        result: dict[str, Any] = {}",
        "        for output_port in output_ports:",
        "            result.update(_RUNTIME_GRAPH._cook_subnet(node_id, output_port, ctx))",
        "        return result",
        "    value = _NODE_REGISTRY[type_name](ctx)",
        "    return value if isinstance(value, dict) else {'output': value}",
        "",
        "",
    ])

    for node_id, meta in node_meta.items():
        function_name = f"run_{node_names[node_id]}"
        type_name = str(meta.get("type"))
        params = dict(meta.get("params") or {})
        lines.append(f"def {function_name}(state: WorkflowState) -> dict[str, Any]:")
        lines.append(f"    ctx: dict[str, Any] = {params!r}")
        for edge in incoming.get(node_id, []):
            from_id = str(edge.get("from"))
            from_port = str(edge.get("from_port", "output"))
            to_port = str(edge.get("to_port", "input"))
            source_key = state_keys[from_id][from_port]
            lines.append(f"    ctx[{to_port!r}] = state.get({source_key!r})")
        lines.append(
            f"    result = _run_blacknode_node({node_id!r}, {type_name!r}, ctx, {output_ports[node_id]!r})"
        )
        if output_ports[node_id]:
            returned = {
                state_keys[node_id][output_port]: f"result.get({output_port!r})"
                for output_port in output_ports[node_id]
            }
            lines.append("    return {")
            for key, expr in returned.items():
                lines.append(f"        {key!r}: {expr},")
            lines.append("    }")
        else:
            lines.append("    return {}")
        lines.append("")

    lines.extend([
        "",
        "workflow = StateGraph(WorkflowState)",
    ])

    for node_id in node_meta:
        graph_name = node_names[node_id]
        lines.append(f"workflow.add_node({graph_name!r}, run_{graph_name})")

    for node_id in node_meta:
        graph_name = node_names[node_id]
        preds = [node_names[pred] for pred in predecessors.get(node_id, []) if pred in node_names]
        if not preds:
            lines.append(f"workflow.add_edge(START, {graph_name!r})")
        elif len(preds) == 1:
            lines.append(f"workflow.add_edge({preds[0]!r}, {graph_name!r})")
        else:
            lines.append(f"workflow.add_edge({preds!r}, {graph_name!r})")

    for node_id in node_meta:
        if not successors.get(node_id):
            lines.append(f"workflow.add_edge({node_names[node_id]!r}, END)")

    entry_key = state_keys[entry_node][entry_port]
    lines.extend([
        "",
        "compiled = workflow.compile()",
        "",
        "",
        "if __name__ == '__main__':",
        "    result = compiled.invoke({})",
        f"    print(result.get({entry_key!r}))",
        "",
    ])

    return "\n".join(lines), ["Install LangGraph before running this export: pip install langgraph"]


def _node_meta(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node_id): dict(meta)
        for node_id, meta in (data.get("node_meta") or {}).items()
        if isinstance(meta, Mapping)
    }


def _runtime_nodes(node_meta: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    runtime: dict[str, dict[str, Any]] = {}
    for node_id, meta in node_meta.items():
        node_def = {
            "type": str(meta.get("type")),
            "params": dict(meta.get("params") or {}),
        }
        if isinstance(meta.get("subgraph"), Mapping):
            node_def["subgraph"] = dict(meta["subgraph"])
        runtime[str(node_id)] = node_def
    return runtime


def _incoming_edges(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        incoming[str(edge.get("to"))].append(edge)
    return incoming


def _predecessors(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        from_id = str(edge.get("from"))
        to_id = str(edge.get("to"))
        if from_id not in result[to_id]:
            result[to_id].append(from_id)
    return result


def _successors(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        from_id = str(edge.get("from"))
        to_id = str(edge.get("to"))
        if to_id not in result[from_id]:
            result[from_id].append(to_id)
    return result


def _output_ports(
    node_id: str,
    meta: Mapping[str, Any],
    edges: list[dict[str, Any]],
    entrypoint: tuple[str, str],
) -> list[str]:
    ports: list[str] = [str(port) for port in meta.get("outputs") or []]
    for edge in edges:
        if str(edge.get("from")) == node_id:
            port = str(edge.get("from_port", "output"))
            if port not in ports:
                ports.append(port)
    if entrypoint[0] == node_id and entrypoint[1] not in ports:
        ports.append(entrypoint[1])
    return ports or ["output"]


def _state_keys(
    node_names: Mapping[str, str],
    output_ports: Mapping[str, list[str]],
) -> dict[str, dict[str, str]]:
    used: set[str] = set()
    keys: dict[str, dict[str, str]] = {}
    for node_id, ports in output_ports.items():
        node_keys: dict[str, str] = {}
        for port in ports:
            base = f"{node_names[node_id]}__{_identifier(port) or 'output'}"
            node_keys[port] = _dedupe(base, used)
        keys[node_id] = node_keys
    return keys


def _unique_names(values, prefix: str) -> dict[str, str]:
    used: set[str] = set()
    result: dict[str, str] = {}
    for index, value in enumerate(values, start=1):
        base = _identifier(str(value)) or f"{prefix}_{index}"
        result[str(value)] = _dedupe(base, used)
    return result


def _dedupe(base: str, used: set[str]) -> str:
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _identifier(value: str) -> str:
    name = re.sub(r"\W+", "_", value.strip()).strip("_").lower()
    if not name:
        return ""
    if name[0].isdigit():
        name = f"node_{name}"
    if keyword.iskeyword(name):
        name = f"{name}_node"
    return name
