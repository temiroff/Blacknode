from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from blacknode.cli import main


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
            self.assertEqual(result, {"node_id": "out", "port": "value", "value": "hello"})


def _valid_workflow() -> dict:
    return workflow(
        {
            "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}, params={"value": "hello"}),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
        },
        [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
    )


if __name__ == "__main__":
    unittest.main()
