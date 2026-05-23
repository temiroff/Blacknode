from __future__ import annotations

import json
from pprint import pformat
from typing import Any, Mapping

from ..workflow import WorkflowRunError, infer_entrypoint, validate_workflow


def export_framework_scaffold(
    data: Mapping[str, Any],
    target_id: str,
    label: str,
) -> tuple[str, list[str]]:
    report = validate_workflow(data)
    if not report.ok:
        raise WorkflowRunError(json.dumps(report.to_dict(), indent=2))

    entry_node, entry_port = infer_entrypoint(data)
    projection = _workflow_projection(data, {"node_id": entry_node, "port": entry_port})
    builder_name = {
        "crewai": "build_crewai_tasks",
        "autogen": "build_autogen_agents",
        "swarm": "build_swarm_handoffs",
    }[target_id]
    body = {
        "crewai": _crewai_builder(),
        "autogen": _autogen_builder(),
        "swarm": _swarm_builder(),
    }[target_id]

    code = "\n".join([
        "from __future__ import annotations",
        "",
        "from pprint import pprint",
        "",
        "",
        f"WORKFLOW = {pformat(projection, width=100)}",
        "",
        "",
        body,
        "",
        "",
        "if __name__ == '__main__':",
        f"    pprint({builder_name}())",
        "",
    ])
    return code, [f"{label} export carries graph structure; add framework-specific model clients and policies in the generated file."]


def _workflow_projection(data: Mapping[str, Any], entrypoint: dict[str, str]) -> dict[str, Any]:
    node_meta = data.get("node_meta") or {}
    return {
        "name": data.get("name") or "Blacknode Workflow",
        "entrypoint": entrypoint,
        "nodes": [
            {
                "id": str(node_id),
                "type": str(meta.get("type")),
                "params": dict(meta.get("params") or {}),
                "inputs": list(meta.get("inputs") or []),
                "outputs": list(meta.get("outputs") or []),
            }
            for node_id, meta in node_meta.items()
            if isinstance(meta, Mapping)
        ],
        "edges": [dict(edge) for edge in data.get("edges") or []],
    }


def _crewai_builder() -> str:
    return '''def build_crewai_tasks() -> list[dict]:
    """Return CrewAI task descriptors mapped from Blacknode nodes."""
    tasks = []
    for node in WORKFLOW["nodes"]:
        upstream = [
            edge["from"]
            for edge in WORKFLOW["edges"]
            if edge["to"] == node["id"]
        ]
        tasks.append({
            "name": node["id"],
            "description": f"Run Blacknode {node['type']} node",
            "expected_output": ", ".join(node["outputs"]) or "node result",
            "blacknode_type": node["type"],
            "params": node["params"],
            "context": upstream,
        })
    return tasks'''


def _autogen_builder() -> str:
    return '''def build_autogen_agents() -> list[dict]:
    """Return AutoGen agent descriptors mapped from Blacknode nodes."""
    agents = []
    for node in WORKFLOW["nodes"]:
        outbound = [
            edge["to"]
            for edge in WORKFLOW["edges"]
            if edge["from"] == node["id"]
        ]
        agents.append({
            "name": node["id"],
            "system_message": f"You execute the Blacknode {node['type']} step.",
            "blacknode_type": node["type"],
            "params": node["params"],
            "handoffs": outbound,
        })
    return agents'''


def _swarm_builder() -> str:
    return '''def build_swarm_handoffs() -> list[dict]:
    """Return OpenAI Swarm-style handoff descriptors mapped from Blacknode nodes."""
    handoffs = []
    for node in WORKFLOW["nodes"]:
        targets = [
            edge["to"]
            for edge in WORKFLOW["edges"]
            if edge["from"] == node["id"]
        ]
        handoffs.append({
            "agent": node["id"],
            "instructions": f"Handle the Blacknode {node['type']} step.",
            "blacknode_type": node["type"],
            "params": node["params"],
            "handoff_targets": targets,
        })
    return handoffs'''
