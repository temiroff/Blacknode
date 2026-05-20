from __future__ import annotations

import contextlib
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blacknode.cli import main
from blacknode.providers import registry
from blacknode.providers.base import CompletionResponse
from blacknode.workflow import WorkflowRunError, run_workflow


def node(
    node_id: str,
    type_name: str,
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    input_types: dict[str, str] | None = None,
    output_types: dict[str, str] | None = None,
    params: dict | None = None,
) -> dict:
    return {
        "id": node_id,
        "type": type_name,
        "params": params or {},
        "pos": [0, 0],
        "inputs": inputs or [],
        "outputs": outputs or [],
        "input_types": input_types or {},
        "output_types": output_types or {},
        "input_defaults": {},
    }


def workflow(node_meta: dict[str, dict], edges: list[dict]) -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "CLI Test",
        "saved_at": "2026-05-20T12:00:00",
        "node_meta": node_meta,
        "edges": edges,
    }


class CliTests(unittest.TestCase):
    def test_validate_returns_success_for_valid_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "workflow.json"
            path.write_text(json.dumps(_valid_workflow()), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(path)])

            self.assertEqual(code, 0)
            report = json.loads(stdout.getvalue())
            self.assertTrue(report["ok"])

    def test_validate_returns_failure_for_invalid_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "workflow.json"
            data = _valid_workflow()
            data["edges"][0]["from"] = "missing"
            path.write_text(json.dumps(data), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(path)])

            self.assertEqual(code, 1)
            report = json.loads(stdout.getvalue())
            self.assertFalse(report["ok"])
            self.assertEqual(report["errors"][0]["code"], "missing_source_node")

    def test_run_writes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            workflow_path = Path(td) / "workflow.json"
            output_path = Path(td) / "result.json"
            workflow_path.write_text(json.dumps(_valid_workflow()), encoding="utf-8")

            code = main(["run", str(workflow_path), "--output", str(output_path)])

            self.assertEqual(code, 0)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["node_id"], "out")
            self.assertEqual(result["port"], "value")
            self.assertEqual(result["value"], "hello")
            self.assertTrue(result["run_id"])
            self.assertIn("events", result)
            self.assertIn("node_start", _event_types(result))
            self.assertIn("node_finish", _event_types(result))

    def test_run_logs_tool_call_event(self):
        with tempfile.TemporaryDirectory() as td:
            workflow_path = Path(td) / "workflow.json"
            output_path = Path(td) / "result.json"
            workflow_path.write_text(json.dumps(_tool_workflow()), encoding="utf-8")

            code = main(["run", str(workflow_path), "--output", str(output_path)])

            self.assertEqual(code, 0)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["value"], 3)
            tool_events = [event for event in result["events"] if event["type"] == "tool_call"]
            self.assertEqual(len(tool_events), 1)
            self.assertEqual(tool_events[0]["name"], "increment")
            self.assertEqual(tool_events[0]["arguments"], {"x": 2})

    def test_run_logs_model_call_event(self):
        class FakeProvider:
            def complete(self, messages, *, model, system="", max_tokens=1024, tools=None, temperature=1.0, **kwargs):
                return CompletionResponse(text="Paris")

        def make_nim(api_key=None):
            return FakeProvider()

        with tempfile.TemporaryDirectory() as td, patch.object(registry, "_make_nim", make_nim):
            workflow_path = Path(td) / "workflow.json"
            output_path = Path(td) / "result.json"
            workflow_path.write_text(json.dumps(_llm_workflow()), encoding="utf-8")

            code = main(["run", str(workflow_path), "--output", str(output_path)])

            self.assertEqual(code, 0)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["value"], "Paris")
            model_events = [event for event in result["events"] if event["type"] == "model_call"]
            self.assertEqual(len(model_events), 1)
            self.assertEqual(model_events[0]["model"], "test-model")

    def test_run_error_keeps_structured_events(self):
        with self.assertRaises(WorkflowRunError) as caught:
            run_workflow(_failing_workflow())

        event_types = {event["type"] for event in caught.exception.events}
        self.assertIn("node_error", event_types)
        self.assertIn("run_error", event_types)

    def test_export_python_writes_runnable_script(self):
        with tempfile.TemporaryDirectory() as td:
            workflow_path = Path(td) / "workflow.json"
            script_path = Path(td) / "workflow.py"
            workflow_path.write_text(json.dumps(_valid_workflow()), encoding="utf-8")

            code = main(["export-python", str(workflow_path), "--output", str(script_path)])

            self.assertEqual(code, 0)
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("g = bn.Graph()", script)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                runpy.run_path(str(script_path), run_name="__main__")
            self.assertEqual(stdout.getvalue().strip(), "hello")


def _valid_workflow() -> dict:
    return workflow(
        {
            "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}, params={"value": "hello"}),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
        },
        [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
    )


def _tool_workflow() -> dict:
    return workflow(
        {
            "fn": node(
                "fn",
                "PythonFn",
                outputs=["fn"],
                output_types={"fn": "Fn"},
                params={
                    "name": "increment",
                    "description": "Increment x",
                    "code": "def run(x: int) -> int:\n    return x + 1",
                },
            ),
            "args": node("args", "Dict", outputs=["value"], output_types={"value": "Dict"}, params={"value": {"x": 2}}),
            "call": node(
                "call",
                "ToolCall",
                inputs=["fn", "args"],
                outputs=["result"],
                input_types={"fn": "Fn", "args": "Dict"},
                output_types={"result": "Any"},
            ),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
        },
        [
            {"from": "fn", "from_port": "fn", "to": "call", "to_port": "fn"},
            {"from": "args", "from_port": "value", "to": "call", "to_port": "args"},
            {"from": "call", "from_port": "result", "to": "out", "to_port": "value"},
        ],
    )


def _llm_workflow() -> dict:
    return workflow(
        {
            "prompt": node("prompt", "Text", outputs=["value"], output_types={"value": "Text"}, params={"value": "Capital of France?"}),
            "agent": node(
                "agent",
                "LLMAgent",
                inputs=["prompt", "system", "model", "max_tokens", "temperature"],
                outputs=["text"],
                input_types={"prompt": "Text", "system": "Text", "model": "Model", "max_tokens": "Int", "temperature": "Float"},
                output_types={"text": "Text"},
                params={"model": "nim:test-model"},
            ),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
        },
        [
            {"from": "prompt", "from_port": "value", "to": "agent", "to_port": "prompt"},
            {"from": "agent", "from_port": "text", "to": "out", "to_port": "value"},
        ],
    )


def _failing_workflow() -> dict:
    return workflow(
        {
            "fn": node(
                "fn",
                "PythonFn",
                outputs=["fn"],
                output_types={"fn": "Fn"},
                params={
                    "name": "fail",
                    "description": "Always fails",
                    "code": "def run() -> str:\n    raise ValueError('boom')",
                },
            ),
            "args": node("args", "Dict", outputs=["value"], output_types={"value": "Dict"}, params={"value": {}}),
            "call": node(
                "call",
                "ToolCall",
                inputs=["fn", "args"],
                outputs=["result"],
                input_types={"fn": "Fn", "args": "Dict"},
                output_types={"result": "Any"},
            ),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
        },
        [
            {"from": "fn", "from_port": "fn", "to": "call", "to_port": "fn"},
            {"from": "args", "from_port": "value", "to": "call", "to_port": "args"},
            {"from": "call", "from_port": "result", "to": "out", "to_port": "value"},
        ],
    )


def _event_types(result: dict) -> set[str]:
    return {event["type"] for event in result["events"]}


if __name__ == "__main__":
    unittest.main()
