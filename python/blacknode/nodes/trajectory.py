"""Trajectory recording — turn every agent run into training data.

A *trajectory* is the full record of one agent run: the input prompt, every
model output, every tool call and its result, and the final answer. The
:class:`AgentLoop` node already produces this as its ``steps`` list, and the
:class:`RunLogger` already captures model/tool events with timing. The
``TrajectoryRecorder`` node formats both into a JSONL file under
``trajectories/`` that downstream training pipelines can consume directly.

The node is *passive*: it passes ``result`` through unchanged so it can sit
inline between an ``AgentLoop`` and an ``Output`` without altering behaviour::

    [Input] -> [AgentLoop] -> [TrajectoryRecorder] -> [Output]
                                     |
                           trajectories/run_042.jsonl

File format (one JSON object per line):

* line 1 — ``{"type": "meta", ...}`` run-level metadata and aggregate counts
* line 2 — ``{"type": "input", "role": "user", ...}`` the original prompt
* then, per step — ``model_output`` (assistant) and ``tool_result`` (tool) lines
* optionally — ``{"type": "event", ...}`` raw logger events when enabled
* last line — ``{"type": "final", "role": "assistant", ...}`` the final answer
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from blacknode.node import node

SCHEMA = "blacknode.trajectory/1"
_RUN_FILE_RE = re.compile(r"run_(\d+)\.jsonl$")


def _resolve_dir(raw: str) -> Path:
    path = Path(str(raw or "trajectories")).expanduser()
    full = path if path.is_absolute() else Path.cwd() / path
    return full.resolve()


def _next_run_path(directory: Path) -> Path:
    """Return ``run_NNN.jsonl`` with the next free zero-padded counter."""
    highest = 0
    for existing in directory.glob("run_*.jsonl"):
        match = _RUN_FILE_RE.search(existing.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return directory / f"run_{highest + 1:03d}.jsonl"


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(t).strip() for t in raw if str(t).strip()]
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _messages_from_steps(prompt: str, steps: list, result: str) -> list[dict]:
    """Flatten AgentLoop ``steps`` into one message dict per trajectory line."""
    messages: list[dict] = [{"type": "input", "role": "user", "content": prompt}]
    for step in steps:
        if not isinstance(step, dict):
            messages.append({"type": "model_output", "role": "assistant", "content": str(step), "tool_calls": []})
            continue
        role = step.get("role")
        if role == "tool":
            messages.append({
                "type": "tool_result",
                "role": "tool",
                "name": step.get("name", ""),
                "content": str(step.get("output", "")),
            })
        else:
            messages.append({
                "type": "model_output",
                "role": "assistant",
                "content": str(step.get("text", "")),
                "tool_calls": list(step.get("tool_calls") or []),
            })
    messages.append({"type": "final", "role": "assistant", "content": result})
    return messages


def _event_line(event: dict) -> dict:
    """Render a raw logger event as a trajectory line (its own ``type`` preserved)."""
    return {"type": "event", "event_type": event.get("type"), **{k: v for k, v in event.items() if k != "type"}}


def build_trajectory(
    *,
    prompt: str,
    steps: list,
    result: str,
    run_logger: Any = None,
    model: str = "",
    system: str = "",
    tags: Any = None,
    node_id: str | None = None,
    extra_meta: dict | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """Build the ``(meta, messages, events)`` triple for one trajectory.

    Shared by :func:`trajectory_recorder` and the ``RateOutput`` rater so the
    on-disk format stays identical whether a run is merely recorded or labeled.
    """
    steps = steps if isinstance(steps, list) else ([steps] if steps else [])
    events = list(getattr(run_logger, "events", []) or [])
    run_id = getattr(run_logger, "run_id", None) or str(uuid.uuid4())
    messages = _messages_from_steps(str(prompt or ""), steps, str(result or ""))
    meta: dict[str, Any] = {
        "type": "meta",
        "schema": SCHEMA,
        "run_id": run_id,
        "node_id": node_id,
        "ts": time.time(),
        "model": str(model or ""),
        "system": str(system or ""),
        "tags": _parse_tags(tags),
        **_run_aggregates(events, steps),
    }
    if extra_meta:
        meta.update(extra_meta)
    return meta, messages, events


def write_trajectory(
    raw_dir: Any,
    meta: dict,
    messages: list[dict],
    *,
    events: list[dict] | None = None,
    extra_lines: list[dict] | None = None,
) -> Path:
    """Write one ``run_NNN.jsonl`` under ``raw_dir`` and return its path."""
    directory = _resolve_dir(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    out_path = _next_run_path(directory)
    lines = [meta, *messages]
    if events:
        lines.extend(_event_line(event) for event in events)
    if extra_lines:
        lines.extend(extra_lines)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in lines:
            f.write(json.dumps(record, default=str, ensure_ascii=False))
            f.write("\n")
    return out_path


def _run_aggregates(events: list[dict], steps: list) -> dict[str, Any]:
    """Derive trajectory-scoped counts from steps plus run-level timing."""
    tool_calls = sum(
        len(step.get("tool_calls") or [])
        for step in steps
        if isinstance(step, dict) and step.get("role") != "tool"
    )
    model_outputs = sum(
        1 for step in steps if isinstance(step, dict) and step.get("role") != "tool"
    )
    aggregates: dict[str, Any] = {
        "num_steps": len(steps),
        "model_outputs": model_outputs,
        "tool_calls": tool_calls,
    }
    timestamps = [e["ts"] for e in events if isinstance(e, dict) and isinstance(e.get("ts"), (int, float))]
    if timestamps:
        aggregates["run_duration_ms"] = round((max(timestamps) - min(timestamps)) * 1000, 3)
    aggregates["run_model_calls"] = sum(1 for e in events if isinstance(e, dict) and e.get("type") == "model_call")
    aggregates["run_tool_calls"] = sum(1 for e in events if isinstance(e, dict) and e.get("type") == "tool_call")
    return aggregates


@node(
    inputs=[
        "result:Text",
        "steps:List",
        "prompt:Text",
        "system:Text",
        "model:Text",
        "dir:Text=trajectories",
        "tags:Text",
        "include_events:Bool=false",
    ],
    outputs=["result:Text", "path:Text", "trajectory:Dict"],
    name="TrajectoryRecorder",
    category="AI",
    description="Record one agent run as a JSONL trajectory for training; passes result through unchanged.",
)
def trajectory_recorder(ctx: dict) -> dict:
    result = str(ctx.get("result") or "")
    meta, messages, events = build_trajectory(
        prompt=ctx.get("prompt"),
        steps=ctx.get("steps"),
        result=result,
        run_logger=ctx.get("__run_logger__"),
        model=ctx.get("model"),
        system=ctx.get("system"),
        tags=ctx.get("tags"),
        node_id=ctx.get("__node_id__"),
    )
    out_path = write_trajectory(
        ctx.get("dir", "trajectories"),
        meta,
        messages,
        events=events if bool(ctx.get("include_events", False)) else None,
    )
    return {"result": result, "path": str(out_path), "trajectory": {"meta": meta, "messages": messages}}
