from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blacknode.cli import main
from blacknode.python_importer import import_workflow_python
from blacknode.workflow import export_workflow_python, validate_workflow


def node(
    node_id: str,
    type_name: str,
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    input_types: dict[str, str] | None = None,
    output_types: dict[str, str] | None = None,
    params: dict | None = None,
    pos: list[int] | None = None,
) -> dict:
    return {
        "id": node_id,
        "type": type_name,
        "params": params or {},
        "pos": pos or [0, 0],
        "inputs": inputs or [],
        "outputs": outputs or [],
        "input_types": input_types or {},
        "output_types": output_types or {},
        "input_defaults": {},
    }


def valid_workflow() -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Python Round Trip",
        "saved_at": "2026-05-22T12:00:00",
        "node_meta": {
            "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}, params={"value": "hello"}, pos=[10, 20]),
            "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}, pos=[300, 40]),
        },
        "edges": [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
        "entrypoint": {"node_id": "out", "port": "value"},
    }


class PythonRoundTripTests(unittest.TestCase):
    def test_flat_export_is_runnable_and_importable(self):
        script = export_workflow_python(valid_workflow())

        ast.parse(script)
        self.assertIn("# Step 1: Text", script)
        self.assertIn("g = bn.Graph()", script)
        self.assertIn("run_graph_live(g, 'out', 'value', workflow=_WORKFLOW)", script)
        self.assertIn("text.out('value') >> output.inp('value')", script)

        imported = import_workflow_python(script, name="Imported")
        self.assertTrue(validate_workflow(imported).ok)
        self.assertEqual(imported["entrypoint"], {"node_id": "out", "port": "value"})
        self.assertEqual(imported["edges"], valid_workflow()["edges"])
        self.assertEqual(imported["node_meta"]["text"]["pos"], [10, 20])

        self.assertEqual(_run_script(script), "hello")

    def test_class_export_is_runnable_and_importable(self):
        script = export_workflow_python(valid_workflow(), style="class")

        ast.parse(script)
        self.assertIn("class BlacknodeWorkflow:", script)
        self.assertIn("return run_graph_live(self.graph, 'out', 'value', workflow=_WORKFLOW)", script)

        imported = import_workflow_python(script, name="Imported Class")
        self.assertTrue(validate_workflow(imported).ok)
        self.assertEqual(imported["entrypoint"], {"node_id": "out", "port": "value"})
        self.assertEqual(_run_script(script), "hello")

    def test_import_python_accepts_bind_helper_shape(self):
        source = """
from __future__ import annotations

import blacknode as bn
from blacknode.live_sync import run_graph_live

g = bn.Graph()
prompt = _bind_node_id(g, g.node("Text", value="hi"), "prompt")
out = _bind_node_id(g, g.node("Output"), "out")
prompt.out("value") >> out.inp("value")
result = run_graph_live(g, "out", "value")
"""

        imported = import_workflow_python(source, name="Manual")

        self.assertTrue(validate_workflow(imported).ok)
        self.assertEqual(imported["node_meta"]["prompt"]["params"]["value"], "hi")
        self.assertEqual(imported["edges"][0]["from"], "prompt")

    def test_cli_import_python_writes_workflow_json(self):
        with tempfile.TemporaryDirectory() as td:
            workflow_path = Path(td) / "workflow.json"
            script_path = Path(td) / "workflow.py"
            imported_path = Path(td) / "imported.json"
            workflow_path.write_text(json.dumps(valid_workflow()), encoding="utf-8")

            self.assertEqual(main(["export-python", str(workflow_path), "--output", str(script_path)]), 0)
            self.assertEqual(main(["import-python", str(script_path), "--output", str(imported_path)]), 0)

            imported = json.loads(imported_path.read_text(encoding="utf-8"))
            self.assertTrue(validate_workflow(imported).ok)
            self.assertEqual(imported["entrypoint"], {"node_id": "out", "port": "value"})


def _run_script(script: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "workflow.py"
        path.write_text(script, encoding="utf-8")
        stdout = io.StringIO()
        with patch.dict(os.environ, {"BLACKNODE_SYNC_URL": ""}), contextlib.redirect_stdout(stdout):
            runpy.run_path(str(path), run_name="__main__")
        return stdout.getvalue().strip()


if __name__ == "__main__":
    unittest.main()
