"""Convert recorded trajectories into fine-tuning datasets.

Reads the JSONL files written by ``TrajectoryRecorder`` / ``RateOutput`` (one
``run_NNN.jsonl`` per agent run) and emits records in formats that TRL, Unsloth,
and OpenPipe consume directly:

* ``chat``     — ``{"messages": [...], "metadata": {...}}`` OpenAI-style chat.
                 Works for TRL ``SFTTrainer``, Unsloth (messages), and OpenPipe.
* ``sharegpt`` — ``{"conversations": [{"from": ..., "value": ...}]}`` Unsloth's
                 native ShareGPT layout.
* ``dpo``      — ``{"prompt", "chosen", "rejected", "metadata"}`` preference
                 pairs for TRL ``DPOTrainer``, built by grouping trajectories
                 with the same input and pairing the highest-scored response
                 against each strictly lower-scored one.

Filtering (min score, label, tag, rated-only) implements the
"run 100×, keep the good ones, export" loop the recorder was built for.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CHAT_FORMATS = {"chat", "messages", "jsonl", "openai", "trl", "openpipe"}
SHAREGPT_FORMATS = {"sharegpt", "unsloth"}
DPO_FORMATS = {"dpo", "preference"}
KNOWN_FORMATS = CHAT_FORMATS | SHAREGPT_FORMATS | DPO_FORMATS

_SHAREGPT_ROLE = {"user": "human", "assistant": "gpt", "system": "system", "tool": "tool"}


@dataclass
class Trajectory:
    """One parsed agent run, reconstructed from a ``run_NNN.jsonl`` file."""

    source: str
    meta: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)  # model_output / tool_result lines, in order
    final: str = ""
    rating: dict[str, Any] | None = None

    @property
    def score(self) -> float | None:
        if self.rating is None:
            return None
        value = self.rating.get("score")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def label(self) -> str:
        return str((self.rating or {}).get("label") or "")

    @property
    def tags(self) -> list[str]:
        tags = self.meta.get("tags")
        return [str(t) for t in tags] if isinstance(tags, list) else []


def _parse_file(path: Path) -> Trajectory | None:
    meta: dict[str, Any] = {}
    prompt = ""
    steps: list[dict[str, Any]] = []
    final = ""
    rating: dict[str, Any] | None = None
    saw_input = False

    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    line = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(line, dict):
                    continue
                kind = line.get("type")
                if kind == "meta":
                    meta = line
                    if isinstance(line.get("label"), dict):
                        rating = line["label"]
                elif kind == "input":
                    prompt = str(line.get("content", ""))
                    saw_input = True
                elif kind in ("model_output", "tool_result"):
                    steps.append(line)
                elif kind == "final":
                    final = str(line.get("content", ""))
                elif kind == "rating" and rating is None:
                    rating = {k: v for k, v in line.items() if k != "type"}
    except OSError:
        return None

    if not saw_input and not steps and not final:
        return None
    return Trajectory(source=path.name, meta=meta, prompt=prompt, steps=steps, final=final, rating=rating)


def load_trajectories(input_path: str | Path) -> list[Trajectory]:
    """Load every trajectory under ``input_path`` (a directory or a single file)."""
    path = Path(input_path).expanduser()
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("*.jsonl"))
    else:
        raise FileNotFoundError(f"No such trajectory path: {path}")
    return [traj for file in files if (traj := _parse_file(file)) is not None]


def filter_trajectories(
    trajectories: Iterable[Trajectory],
    *,
    min_score: float | None = None,
    label: str | None = None,
    tag: str | None = None,
    rated_only: bool = False,
) -> list[Trajectory]:
    selected: list[Trajectory] = []
    for traj in trajectories:
        if (rated_only or min_score is not None or label) and traj.rating is None:
            continue
        if min_score is not None and (traj.score is None or traj.score < min_score):
            continue
        if label and traj.label.lower() != label.lower():
            continue
        if tag and tag not in traj.tags:
            continue
        selected.append(traj)
    return selected


# ── Conversation reconstruction ────────────────────────────────────────────

def _openai_messages(traj: Trajectory) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if traj.prompt or not traj.steps:
        messages.append({"role": "user", "content": traj.prompt})
    counter = 0
    pending: list[tuple[str, str]] = []
    for step in traj.steps:
        if step.get("type") == "tool_result":
            name = str(step.get("name", ""))
            call_id = _take_pending(pending, name)
            tool_msg: dict[str, Any] = {"role": "tool", "content": str(step.get("content", ""))}
            if call_id:
                tool_msg["tool_call_id"] = call_id
            if name:
                tool_msg["name"] = name
            messages.append(tool_msg)
            continue
        assistant: dict[str, Any] = {"role": "assistant", "content": str(step.get("content", ""))}
        tool_calls = step.get("tool_calls") or []
        if tool_calls:
            pending = []
            rendered = []
            for call in tool_calls:
                counter += 1
                call_id = f"call_{counter}"
                name = str(call.get("name", ""))
                args = call.get("arguments", {})
                rendered.append({
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)},
                })
                pending.append((call_id, name))
            assistant["tool_calls"] = rendered
        messages.append(assistant)

    last = messages[-1] if messages else None
    if traj.final and not (last and last.get("role") == "assistant" and last.get("content") == traj.final and "tool_calls" not in last):
        messages.append({"role": "assistant", "content": traj.final})
    return messages


def _take_pending(pending: list[tuple[str, str]], name: str) -> str:
    for index, (call_id, call_name) in enumerate(pending):
        if call_name == name:
            return pending.pop(index)[0]
    if pending:
        return pending.pop(0)[0]
    return ""


def _record_metadata(traj: Trajectory) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": traj.source}
    if traj.meta.get("run_id"):
        metadata["run_id"] = traj.meta["run_id"]
    if traj.meta.get("model"):
        metadata["model"] = traj.meta["model"]
    if traj.tags:
        metadata["tags"] = traj.tags
    if traj.rating is not None:
        if traj.score is not None:
            metadata["score"] = traj.score
        if traj.label:
            metadata["label"] = traj.label
    return metadata


def to_chat_record(traj: Trajectory) -> dict[str, Any]:
    return {"messages": _openai_messages(traj), "metadata": _record_metadata(traj)}


def to_sharegpt_record(traj: Trajectory) -> dict[str, Any]:
    conversations = [
        {"from": _SHAREGPT_ROLE.get(msg["role"], msg["role"]), "value": str(msg.get("content", ""))}
        for msg in _openai_messages(traj)
    ]
    return {"conversations": conversations, "metadata": _record_metadata(traj)}


def build_dpo_pairs(trajectories: Iterable[Trajectory]) -> list[dict[str, Any]]:
    groups: dict[str, list[Trajectory]] = defaultdict(list)
    for traj in trajectories:
        if traj.score is not None and traj.final:
            groups[traj.prompt].append(traj)

    pairs: list[dict[str, Any]] = []
    for prompt, group in groups.items():
        ranked = sorted(group, key=lambda t: t.score, reverse=True)  # type: ignore[arg-type, return-value]
        best = ranked[0]
        for worse in ranked[1:]:
            if worse.final == best.final or worse.score is None or worse.score >= best.score:  # type: ignore[operator]
                continue
            pairs.append({
                "prompt": prompt,
                "chosen": best.final,
                "rejected": worse.final,
                "metadata": {
                    "chosen_score": best.score,
                    "rejected_score": worse.score,
                    "chosen_source": best.source,
                    "rejected_source": worse.source,
                },
            })
    return pairs


def export_dataset(
    input_path: str | Path,
    *,
    fmt: str = "chat",
    min_score: float | None = None,
    label: str | None = None,
    tag: str | None = None,
    rated_only: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return ``(records, stats)`` for the requested export format."""
    fmt = (fmt or "chat").lower()
    if fmt not in KNOWN_FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: chat, sharegpt, dpo.")

    loaded = load_trajectories(input_path)
    selected = filter_trajectories(
        loaded, min_score=min_score, label=label, tag=tag, rated_only=rated_only
    )

    if fmt in DPO_FORMATS:
        records = build_dpo_pairs(selected)
    elif fmt in SHAREGPT_FORMATS:
        records = [to_sharegpt_record(traj) for traj in selected]
    else:
        records = [to_chat_record(traj) for traj in selected]

    stats = {
        "format": "dpo" if fmt in DPO_FORMATS else "sharegpt" if fmt in SHAREGPT_FORMATS else "chat",
        "trajectories_found": len(loaded),
        "trajectories_selected": len(selected),
        "records_written": len(records),
        "rated": sum(1 for t in selected if t.rating is not None),
    }
    return records, stats


def write_jsonl(records: list[dict[str, Any]], output: str | Path | None) -> None:
    lines = "\n".join(json.dumps(record, ensure_ascii=False, default=str) for record in records)
    if output is None:
        print(lines)
        return
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lines + "\n" if lines else "", encoding="utf-8")
