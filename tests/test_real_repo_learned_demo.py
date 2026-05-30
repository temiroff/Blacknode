from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blacknode.learned import registry
from blacknode.mcp import tools as mcp_tools
from scripts import real_repo_learned_demo as demo


def fake_run_in_container(*, code, inputs, permissions, node_name=None):
    del permissions, node_name
    namespace = {}
    exec(code, namespace)
    return namespace["run"](**inputs)


def ready_sandbox_status():
    return {
        "disabled": False,
        "docker_available": True,
        "image": "blacknode-sandbox:latest",
        "image_present": True,
        "detail": "sandbox image present: blacknode-sandbox:latest",
    }


class RealRepoLearnedDemoTests(unittest.TestCase):
    def tearDown(self):
        for name in ("RealRepoInventory", "RealRepoFindings", "RealRepoArchitecture", "RealRepoBriefing"):
            registry.unregister_one(name)

    def test_real_repo_demo_uses_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real-project"
            (target / "src").mkdir(parents=True)
            (target / "tests").mkdir()
            (target / "README.md").write_text("# Real Project\n\nThis is real demo input.\n", encoding="utf-8")
            (target / "src" / "app.py").write_text(
                "def main():\n"
                "    # TODO: wire production guardrails before release\n"
                "    return 'ok'\n",
                encoding="utf-8",
            )
            (target / "tests" / "test_app.py").write_text("def test_main():\n    assert True\n", encoding="utf-8")

            stdout = io.StringIO()
            with patch.object(registry.docker_runner, "run_in_container", side_effect=fake_run_in_container):
                with patch.object(demo.docker_runner, "learned_node_runtime_status", return_value=ready_sandbox_status()):
                    with patch.object(mcp_tools, "_notify_learned_node_event"):
                        with contextlib.redirect_stdout(stdout):
                            status = demo.main(["--target", str(target)])

        output = stdout.getvalue()
        self.assertEqual(status, 0, output)
        self.assertIn(f"target: {target}", output)
        self.assertIn("sampled files: 3", output)
        self.assertIn("workflow node count: 14", output)
        self.assertIn("What this repo appears to be", output)
        self.assertIn("Why this demo is not canned", output)
        self.assertIn("production guardrails", output)

    def test_snapshot_prioritizes_reviewable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real-project"
            (target / "python" / "blacknode").mkdir(parents=True)
            (target / "editor-server" / "runs").mkdir(parents=True)
            (target / "tests").mkdir()
            (target / "README.md").write_text("# Real Project\n", encoding="utf-8")
            (target / "python" / "blacknode" / "workflow.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            (target / "tests" / "test_workflow.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")
            (target / "editor-server" / "runs" / "old-run.json").write_text('{"noisy": true}\n', encoding="utf-8")

            snapshot = demo.build_snapshot(target, max_files=3, max_chars_per_file=200)

        paths = [item["path"] for item in snapshot["files"]]
        self.assertEqual(paths[0], "README.md")
        self.assertIn("python/blacknode/workflow.py", paths)
        self.assertIn("tests/test_workflow.py", paths)
        self.assertNotIn("editor-server/runs/old-run.json", paths)
        self.assertEqual(snapshot["candidate_files"], 3)

    def test_unavailable_docker_fails_with_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real-project"
            target.mkdir()
            (target / "README.md").write_text("# Real Project\n", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            docker_status = {
                "disabled": False,
                "docker_available": False,
                "image": "blacknode-sandbox:latest",
                "image_present": False,
                "detail": "Docker daemon is not running",
            }
            with patch.object(demo.docker_runner, "learned_node_runtime_status", return_value=docker_status):
                with patch.object(mcp_tools, "open_workflow_in_editor_tab") as open_editor:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        status = demo.main(["--target", str(target), "--open-editor"])

        self.assertEqual(status, 1)
        self.assertEqual("", stdout.getvalue())
        error = stderr.getvalue()
        self.assertIn("Docker is not available for learned-node execution", error)
        self.assertIn("blacknode doctor", error)
        self.assertIn("Docker daemon is not running", error)
        self.assertNotIn("Traceback", error)
        self.assertNotIn("'events'", error)
        open_editor.assert_not_called()

    def test_workflow_failure_message_does_not_dump_event_log(self):
        message = demo._format_workflow_run_failure({
            "ok": False,
            "error": "Docker is not available - learned nodes require Docker.",
            "run_id": "run-123",
            "events": [
                {
                    "type": "run_error",
                    "error": "Traceback (most recent call last):\nnoisy internals",
                }
            ],
        })

        self.assertEqual(
            "workflow run failed (run_id: run-123): "
            "Docker is not available - learned nodes require Docker.",
            message,
        )
        self.assertNotIn("Traceback", message)
        self.assertNotIn("events", message)


if __name__ == "__main__":
    unittest.main()
