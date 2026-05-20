from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
TEMPLATE_DIR = ROOT / "templates"

if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.workflow import export_workflow_python, run_workflow, validate_workflow  # noqa: E402


class WorkflowTemplateTests(unittest.TestCase):
    def test_tracked_templates_validate_and_export(self):
        paths = sorted(TEMPLATE_DIR.glob("*.json"))
        self.assertGreater(len(paths), 0, "Expected tracked workflow templates.")

        for path in paths:
            with self.subTest(template=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                report = validate_workflow(data)
                self.assertTrue(report.ok, report.to_dict())

                script = export_workflow_python(data)
                compile(script, f"{path}.py", "exec")

    def test_text_pipeline_template_runs(self):
        data = json.loads((TEMPLATE_DIR / "text-pipeline.json").read_text(encoding="utf-8"))

        result = run_workflow(data)

        self.assertEqual(result["value"], "Hello World")


if __name__ == "__main__":
    unittest.main()
