from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ..workflow import export_workflow_python
from .langgraph import export_langgraph_workflow
from .scaffolds import export_framework_scaffold


@dataclass(frozen=True)
class FrameworkExportTarget:
    id: str
    label: str
    description: str
    extension: str = ".py"


_TARGETS: tuple[FrameworkExportTarget, ...] = (
    FrameworkExportTarget(
        "python",
        "Plain Python",
        "Readable Blacknode Graph script.",
    ),
    FrameworkExportTarget(
        "python-class",
        "Python Class",
        "Class-based Blacknode workflow script.",
    ),
    FrameworkExportTarget(
        "langgraph",
        "LangGraph",
        "LangGraph StateGraph with START, END, nodes, and edges.",
    ),
    FrameworkExportTarget(
        "crewai",
        "CrewAI",
        "CrewAI task map generated from the Blacknode graph.",
    ),
    FrameworkExportTarget(
        "autogen",
        "AutoGen",
        "AutoGen agent map generated from the Blacknode graph.",
    ),
    FrameworkExportTarget(
        "swarm",
        "OpenAI Swarm",
        "Swarm handoff map generated from the Blacknode graph.",
    ),
)

_TARGET_BY_ID = {target.id: target for target in _TARGETS}


def list_export_targets() -> list[dict[str, str]]:
    return [asdict(target) for target in _TARGETS]


def export_workflow(data: Mapping[str, Any], target_id: str) -> dict[str, Any]:
    target_key = target_id.strip().lower()
    target = _TARGET_BY_ID.get(target_key)
    if target is None:
        available = ", ".join(item.id for item in _TARGETS)
        raise ValueError(f"Unknown export target '{target_id}'. Available targets: {available}")

    warnings: list[str] = []
    if target.id == "python":
        code = export_workflow_python(data)
    elif target.id == "python-class":
        code = export_workflow_python(data, style="class")
    elif target.id == "langgraph":
        code, warnings = export_langgraph_workflow(data)
    else:
        code, warnings = export_framework_scaffold(data, target.id, target.label)

    return {
        "target": target.id,
        "label": target.label,
        "description": target.description,
        "filename": _export_filename(data, target),
        "code": code,
        "warnings": warnings,
    }


def _export_filename(data: Mapping[str, Any], target: FrameworkExportTarget) -> str:
    base = _slug(str(data.get("name") or "blacknode-workflow"))
    return f"{base}.{target.id}{target.extension}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "blacknode-workflow"
