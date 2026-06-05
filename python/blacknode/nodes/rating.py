"""LLM-as-judge rating — the DPO/RLHF labeling layer.

``RateOutput`` scores an agent's output with a *judge model* and saves the run
as a labeled trajectory. The judge is pluggable: any model the provider stack
can resolve works — ``nim:...`` (NVIDIA NIM), ``claude-...``, ``gpt-...``,
``ollama:...``, or a ``local:...`` endpoint — so the same node runs at full
speed and scales for bulk preference-pair generation::

    [AgentLoop] -> [RateOutput] -> [Output]
                        |
              trajectories/run_007.jsonl   (meta.label = {score, reason, ...})

The judge is asked to return strict JSON; parsing falls back to a number/verdict
scan so a chatty model still yields a usable score. Outputs ``score``/``label``/
``reason`` for downstream wiring, plus the labeled trajectory ``path``.

Human rating mode is intentionally not implemented here — the synchronous graph
cook has no suspend/resume, so a real in-editor pause is a separate task. A
``review_band`` param flags low-confidence model scores (``needs_human_review``)
so they can be routed to a future human queue without changing this node.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from blacknode.node import node
from blacknode.nodes.trajectory import build_trajectory, write_trajectory
from blacknode.providers import resolve

DEFAULT_RUBRIC = "Rate the response for accuracy and helpfulness."
DEFAULT_JUDGE_SYSTEM = "You are a strict, fair evaluator. Reply with ONLY the requested JSON object."
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)$")
_BINARY_SCALES = {"updown", "up/down", "thumbs", "thumb", "binary", "pass/fail", "passfail"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "off", "")


def _parse_scale(scale: Any) -> tuple[str, float, float]:
    """Return ``(kind, low, high)`` where kind is ``"binary"`` or ``"numeric"``."""
    text = str(scale or "1-5").strip().lower()
    if text in _BINARY_SCALES:
        return "binary", 0.0, 1.0
    match = _RANGE_RE.match(text)
    if match:
        return "numeric", float(match.group(1)), float(match.group(2))
    return "numeric", 1.0, 5.0


def _judge_messages(prompt: str, response: str, rubric: str, kind: str, low: float, high: float) -> list[dict]:
    if kind == "binary":
        ask = "Give a thumbs up (good) or thumbs down (bad)."
        fmt = '{"verdict": "up" | "down", "reason": "<one sentence>"}'
    else:
        ask = f"Give a score from {int(low)} (worst) to {int(high)} (best)."
        fmt = f'{{"score": <number {int(low)}-{int(high)}>, "reason": "<one sentence>"}}'
    content = (
        f"Rubric: {rubric}\n\n"
        f"Original task:\n{prompt or '(none provided)'}\n\n"
        f"Response to evaluate:\n{response}\n\n"
        f"{ask} Reply with ONLY this JSON: {fmt}"
    )
    return [{"role": "user", "content": content}]


def _extract_json(text: str) -> dict:
    match = _JSON_BLOCK_RE.search(text or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_judgement(text: str, kind: str, low: float, high: float) -> tuple[float | None, str, str]:
    """Parse the judge reply into ``(score, label, reason)``; score None if unreadable."""
    data = _extract_json(text)
    reason = str(data.get("reason") or "").strip()
    if kind == "binary":
        verdict = str(data.get("verdict") or data.get("label") or "").strip().lower()
        if verdict not in ("up", "down"):
            low_text = (text or "").lower()
            up, down = "up" in low_text or "thumbs up" in low_text, "down" in low_text or "thumbs down" in low_text
            verdict = "up" if up and not down else "down" if down and not up else ""
        if verdict == "up":
            return high, "up", reason
        if verdict == "down":
            return low, "down", reason
        return None, "", reason or str(text or "").strip()

    raw = data.get("score", data.get("rating"))
    if raw is None:
        match = _NUMBER_RE.search(text or "")
        raw = match.group(0) if match else None
    try:
        score = max(low, min(high, float(raw)))
    except (TypeError, ValueError):
        return None, "", reason or str(text or "").strip()
    label = str(int(score)) if float(score).is_integer() else str(score)
    return score, label, reason


def _in_review_band(score: float | None, band: Any) -> bool:
    if score is None:
        return True
    match = _RANGE_RE.match(str(band or "").strip())
    if not match:
        return False
    low, high = float(match.group(1)), float(match.group(2))
    return low <= score <= high


@node(
    inputs=[
        "result:Text",
        "steps:List",
        "prompt:Text",
        "judge_model:Model=claude-sonnet-4-6",
        "rubric:Text",
        "scale:Text=1-5",
        "system:Text",
        "dir:Text=trajectories",
        "review_band:Text",
        "max_tokens:Int=512",
        "save:Bool=true",
    ],
    outputs=["result:Text", "score:Float", "label:Text", "reason:Text", "rating:Dict", "path:Text"],
    name="RateOutput",
    category="AI",
    description="LLM-as-judge: rate an agent output with any model (NIM/Claude/GPT/local) and save a labeled trajectory for DPO/RLHF.",
)
def rate_output(ctx: dict) -> dict:
    result = str(ctx.get("result") or "")
    prompt = str(ctx.get("prompt") or "")
    steps = ctx.get("steps") or []
    if not isinstance(steps, list):
        steps = [steps]
    rubric = str(ctx.get("rubric") or DEFAULT_RUBRIC)
    judge_model = str(ctx.get("judge_model") or "claude-sonnet-4-6")
    scale_text = str(ctx.get("scale") or "1-5")
    kind, low, high = _parse_scale(scale_text)
    max_tokens = max(1, _int(ctx.get("max_tokens"), 512))

    provider, clean_model = resolve(
        judge_model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )
    provider_name = ctx.get("provider") or provider.__class__.__name__
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=clean_model,
            provider=provider_name,
            action="judge",
            tool_count=0,
        )

    resp = provider.complete(
        _judge_messages(prompt, result, rubric, kind, low, high),
        model=clean_model,
        system=str(ctx.get("system") or DEFAULT_JUDGE_SYSTEM),
        max_tokens=max_tokens,
        temperature=0.0,
    )
    score, label, reason = _parse_judgement(resp.text, kind, low, high)
    needs_review = _in_review_band(score, ctx.get("review_band"))

    rating: dict[str, Any] = {
        "score": score,
        "label": label,
        "reason": reason,
        "scale": scale_text,
        "rater": "model",
        "judge_model": clean_model,
        "judge_provider": provider_name,
        "rubric": rubric,
        "needs_human_review": needs_review,
        "ts": time.time(),
    }

    path = ""
    if _bool(ctx.get("save", True)):
        meta, messages, _events = build_trajectory(
            prompt=prompt,
            steps=steps,
            result=result,
            run_logger=run_logger,
            model=str(ctx.get("model") or ""),
            system=str(ctx.get("agent_system") or ""),
            node_id=ctx.get("__node_id__"),
            extra_meta={"label": rating},
        )
        out_path = write_trajectory(
            ctx.get("dir", "trajectories"),
            meta,
            messages,
            extra_lines=[{"type": "rating", **rating}],
        )
        path = str(out_path)

    return {
        "result": result,
        "score": score if score is not None else 0.0,
        "label": label,
        "reason": reason,
        "rating": rating,
        "path": path,
    }
