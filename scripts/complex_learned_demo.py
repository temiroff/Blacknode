"""Build and run a 10+ node Blacknode workflow with learned nodes.

The demo creates temporary learned nodes, assigns them to explicit palette
categories, builds a 15-node workflow, validates it, runs it, and cleans up.
Use ``--mock-sandbox`` for a fast local dry run that does not require Docker.
Without that flag, learned-node execution goes through the configured Docker
sandbox. Use ``--open-editor`` with a running Blacknode editor backend to open
the generated 14-node graph as a live editor tab.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


REPORT_TEXT = """[Risk]: GPU memory pressure is rising during batch inference.
[Opportunity]: Retrieval cache hits improved latency for repeated prompts.
[Need]: Add better guardrail coverage for tool calls before launch.
[Risk]: API retries can hide slow downstream dependencies.
[Opportunity]: Learned node categories make the workflow easier to inspect.
[Need]: Promotion should happen only after repeatable test coverage exists.
"""

POLICY_TEXT = (
    "Prioritize reliability, explainability, and demo repeatability. "
    "Escalate high-scoring risks before expanding scope."
)

QUERY_TEXT = "gpu memory latency guardrail learned categories promotion"

EXTRACT_SIGNALS_CODE = """def run(report):
    signals = []
    labels = {"risk": 5, "opportunity": 3, "need": 4}
    for raw in str(report or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        label, text = line.split(":", 1)
        category = label.strip("[] ").lower()
        severity = labels.get(category, 2)
        signals.append({
            "id": len(signals) + 1,
            "category": category,
            "severity": severity,
            "text": text.strip(),
        })
    return {"signals": signals}
"""

SCORE_SIGNALS_CODE = """def run(signals):
    keywords = {
        "risk": 3,
        "memory": 2,
        "latency": 2,
        "guardrail": 2,
        "promotion": 1,
        "coverage": 2,
    }
    scored = []
    for item in signals or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        score = int(item.get("severity") or 1)
        lower = text.lower()
        for keyword, weight in keywords.items():
            if keyword in lower:
                score += weight
        scored.append({
            "id": item.get("id"),
            "category": item.get("category", "signal"),
            "score": score,
            "text": text,
        })
    scored.sort(key=lambda row: row["score"], reverse=True)
    return {"scored": {"items": scored, "count": len(scored), "top_score": scored[0]["score"] if scored else 0}}
"""

BUILD_BRIEFING_CODE = """def run(scored, context, policy):
    items = scored.get("items", []) if isinstance(scored, dict) else []
    top = items[:3]
    actions = []
    for item in top:
        category = item.get("category", "signal")
        text = item.get("text", "")
        actions.append(f"{category.upper()}: {text}")
    return {
        "brief": {
            "summary": f"Analyzed {len(items)} signals; top score {scored.get('top_score', 0) if isinstance(scored, dict) else 0}.",
            "policy": str(policy or ""),
            "context_excerpt": str(context or "")[:260],
            "top_signals": top,
            "recommended_actions": actions,
            "promotion_note": "Promote learned nodes only after this workflow is stable.",
        }
    }
"""


LEARNED_NODE_SPECS = [
    {
        "name": "DemoExtractSignals",
        "description": "Extract structured risk, need, and opportunity signals from report text.",
        "category": "Parsing",
        "inputs": ["report:Text"],
        "outputs": ["signals:List"],
        "code": EXTRACT_SIGNALS_CODE,
    },
    {
        "name": "DemoScoreSignals",
        "description": "Score extracted signals with deterministic keyword and severity rules.",
        "category": "Analysis",
        "inputs": ["signals:List"],
        "outputs": ["scored:Dict"],
        "code": SCORE_SIGNALS_CODE,
    },
    {
        "name": "DemoBuildBriefing",
        "description": "Build an executive briefing from ranked signals and retrieved context.",
        "category": "Research",
        "inputs": ["scored:Dict", "context:Text", "policy:Text"],
        "outputs": ["brief:Dict"],
        "code": BUILD_BRIEFING_CODE,
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="complex_learned_demo.py")
    parser.add_argument(
        "--mock-sandbox",
        action="store_true",
        help="Run learned nodes through an in-process deterministic mock instead of Docker.",
    )
    parser.add_argument(
        "--min-nodes",
        type=int,
        default=10,
        help="Minimum workflow node count to assert before running.",
    )
    parser.add_argument(
        "--open-editor",
        action="store_true",
        help="Open the generated workflow in the running Blacknode editor.",
    )
    parser.add_argument(
        "--editor-url",
        default="http://127.0.0.1:7777",
        help="Editor backend URL used with --open-editor.",
    )
    parser.add_argument(
        "--keep-learned",
        action="store_true",
        help="Keep demo learned nodes after the script exits.",
    )
    parser.add_argument(
        "--cleanup-demo-nodes",
        action="store_true",
        help="Delete the persistent demo learned nodes and exit.",
    )
    args = parser.parse_args(argv)

    if args.cleanup_demo_nodes:
        _configure_live_env(args.editor_url)
        from blacknode.mcp import tools

        _delete_demo_nodes(tools, notify_editor=True)
        print("[complex-demo] deleted persistent demo learned nodes")
        return 0

    live_editor = bool(args.open_editor)
    keep_learned = bool(args.keep_learned or live_editor)

    temp_dir = tempfile.TemporaryDirectory(prefix="blacknode-complex-demo-") if not keep_learned else None
    try:
        if temp_dir is not None:
            _configure_demo_env(Path(temp_dir.name))
        else:
            _configure_live_env(args.editor_url)

        from blacknode.learned import registry
        from blacknode.mcp import tools

        created: list[str] = []
        runner_patch = (
            patch.object(registry.docker_runner, "run_in_container", side_effect=_mock_run_in_container)
            if args.mock_sandbox
            else _nullcontext()
        )

        with runner_patch:
            if keep_learned:
                _delete_demo_nodes(tools, notify_editor=live_editor)

            for spec in LEARNED_NODE_SPECS:
                result = tools.create_node_type(**spec, requires_network=False)
                if result.get("status") != "created":
                    raise RuntimeError(f"create_node_type failed for {spec['name']}: {result}")
                created.append(spec["name"])

            workflow = build_workflow(tools)
            node_count = len(workflow.get("node_meta") or {})
            if node_count < args.min_nodes:
                raise RuntimeError(f"workflow has {node_count} nodes, expected at least {args.min_nodes}")

            validation = tools.validate_workflow_tool(workflow)
            if not validation.get("ok"):
                raise RuntimeError(f"workflow validation failed: {validation}")

            if live_editor:
                open_result = tools.open_workflow_in_editor_tab(
                    workflow,
                    name="Complex Learned Nodes Demo",
                    editor_url=args.editor_url,
                    organize=True,
                )
                print(f"[complex-demo] opened editor tab: {open_result.get('editor_url')}")

            run_result = tools.run_workflow_tool(workflow)
            if run_result.get("ok") is False:
                raise RuntimeError(f"workflow run failed: {run_result}")

            value = run_result.get("value")
            if not isinstance(value, str) or "promotion_note" not in value:
                raise RuntimeError(f"unexpected demo output: {value!r}")

            learned = tools.list_learned_nodes()
            categories = sorted({node.get("category") for node in learned.get("nodes", []) if node.get("name") in created})

            print(f"[complex-demo] learned nodes: {', '.join(created)}")
            print(f"[complex-demo] categories: {', '.join(categories)}")
            print(f"[complex-demo] workflow node count: {node_count}")
            print("[complex-demo] validation: ok")
            if keep_learned:
                print("[complex-demo] learned nodes kept for live demo")
            print("[complex-demo] output preview:")
            print(value[:900])
            return 0
    except Exception as exc:
        print(f"[complex-demo] FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if not keep_learned:
                from blacknode.mcp import tools

                for name in [spec["name"] for spec in LEARNED_NODE_SPECS]:
                    try:
                        tools.delete_learned_node(name, confirm=True, notify_editor=False)
                    except Exception:
                        pass
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()


def build_workflow(tools: Any) -> dict[str, Any]:
    workflow = tools.create_workflow(
        name="Complex Learned Nodes Demo",
        description="A 15-node learned-node + RAG workflow for demo validation.",
    )
    workflow = _add(tools, workflow, "Text", "report", {"value": REPORT_TEXT}, (60, 80))
    workflow = _add(tools, workflow, "Text", "policy", {"value": POLICY_TEXT}, (60, 260))
    workflow = _add(tools, workflow, "Text", "query", {"value": QUERY_TEXT}, (60, 440))
    workflow = _add(tools, workflow, "Text", "headline", {"value": "Complex learned-node briefing\n\n"}, (60, 620))

    workflow = _add(tools, workflow, "DemoExtractSignals", "extract", {}, (360, 80))
    workflow = _add(tools, workflow, "DemoScoreSignals", "score", {}, (650, 80))
    workflow = _add(tools, workflow, "TextChunker", "chunk", {}, (360, 320))
    workflow = _add(tools, workflow, "KeywordIndex", "index", {}, (650, 320))
    workflow = _add(tools, workflow, "KeywordSearch", "search", {}, (930, 320))
    workflow = _add(tools, workflow, "RAGContext", "context", {}, (1210, 320))
    workflow = _add(tools, workflow, "DemoBuildBriefing", "brief", {}, (1480, 170))
    workflow = _add(tools, workflow, "JSONDump", "dump", {}, (1760, 170))
    workflow = _add(tools, workflow, "Concat", "concat", {}, (2040, 300))

    edges = [
        ("report", "value", "extract", "report"),
        ("extract", "signals", "score", "signals"),
        ("report", "value", "chunk", "text"),
        ("chunk", "chunks", "index", "documents"),
        ("index", "index", "search", "index"),
        ("query", "value", "search", "query"),
        ("search", "results", "context", "results"),
        ("score", "scored", "brief", "scored"),
        ("context", "context", "brief", "context"),
        ("policy", "value", "brief", "policy"),
        ("brief", "brief", "dump", "data"),
        ("headline", "value", "concat", "a"),
        ("dump", "text", "concat", "b"),
        ("concat", "value", "out", "value"),
    ]
    for from_node, from_port, to_node, to_port in edges:
        workflow = tools.connect_nodes(
            workflow,
            from_node=from_node,
            from_port=from_port,
            to_node=to_node,
            to_port=to_port,
        )["workflow"]
    return workflow


def _add(
    tools: Any,
    workflow: dict[str, Any],
    type_name: str,
    node_id: str,
    params: dict[str, Any],
    pos: tuple[float, float],
) -> dict[str, Any]:
    return tools.add_node(
        workflow,
        type_name,
        params=params,
        node_id=node_id,
        pos=pos,
    )["workflow"]


def _configure_demo_env(root: Path) -> None:
    os.environ["BLACKNODE_LEARNED_DIR"] = str(root / "learned")
    os.environ["BLACKNODE_CONFIG_DIR"] = str(root / "config")
    os.environ["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
    os.environ.setdefault("BLACKNODE_MCP_QUIET", "1")


def _configure_live_env(editor_url: str) -> None:
    os.environ.pop("BLACKNODE_LEARNED_DIR", None)
    os.environ["BLACKNODE_EDITOR_URL"] = editor_url.rstrip("/")
    os.environ["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
    os.environ.setdefault("BLACKNODE_MCP_QUIET", "1")


def _delete_demo_nodes(tools: Any, *, notify_editor: bool) -> None:
    for spec in LEARNED_NODE_SPECS:
        tools.delete_learned_node(spec["name"], confirm=True, notify_editor=notify_editor)


def _mock_run_in_container(
    *,
    code: str,
    inputs: dict[str, Any],
    permissions: dict[str, bool],
    node_name: str | None = None,
) -> dict[str, Any]:
    del code, permissions
    if node_name == "DemoExtractSignals":
        return _mock_extract_signals(inputs.get("report", ""))
    if node_name == "DemoScoreSignals":
        return _mock_score_signals(inputs.get("signals", []))
    if node_name == "DemoBuildBriefing":
        return _mock_build_briefing(
            inputs.get("scored", {}),
            inputs.get("context", ""),
            inputs.get("policy", ""),
        )
    raise RuntimeError(f"Unexpected learned node in mock sandbox: {node_name}")


def _mock_extract_signals(report: str) -> dict[str, Any]:
    signals = []
    labels = {"risk": 5, "opportunity": 3, "need": 4}
    for raw in str(report or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        label, text = line.split(":", 1)
        category = label.strip("[] ").lower()
        signals.append({
            "id": len(signals) + 1,
            "category": category,
            "severity": labels.get(category, 2),
            "text": text.strip(),
        })
    return {"signals": signals}


def _mock_score_signals(signals: list[Any]) -> dict[str, Any]:
    weights = {"risk": 3, "memory": 2, "latency": 2, "guardrail": 2, "promotion": 1, "coverage": 2}
    scored = []
    for item in signals or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        score = int(item.get("severity") or 1)
        lower = text.lower()
        for keyword, weight in weights.items():
            if keyword in lower:
                score += weight
        scored.append({"id": item.get("id"), "category": item.get("category"), "score": score, "text": text})
    scored.sort(key=lambda row: row["score"], reverse=True)
    return {"scored": {"items": scored, "count": len(scored), "top_score": scored[0]["score"] if scored else 0}}


def _mock_build_briefing(scored: dict[str, Any], context: str, policy: str) -> dict[str, Any]:
    items = scored.get("items", []) if isinstance(scored, dict) else []
    top = items[:3]
    return {
        "brief": {
            "summary": f"Analyzed {len(items)} signals; top score {scored.get('top_score', 0) if isinstance(scored, dict) else 0}.",
            "policy": str(policy or ""),
            "context_excerpt": str(context or "")[:260],
            "top_signals": top,
            "recommended_actions": [f"{item.get('category', 'signal').upper()}: {item.get('text', '')}" for item in top],
            "promotion_note": "Promote learned nodes only after this workflow is stable.",
        }
    }


class _nullcontext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


if __name__ == "__main__":
    sys.exit(main())
