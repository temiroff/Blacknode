from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.nodes import nvidia  # noqa: E402
from blacknode.nodes.nvidia import nim_fine_tune, nim_fine_tune_status  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._raw


class NimFineTuneDryRunTests(unittest.TestCase):
    def test_dry_run_is_default_and_builds_request(self):
        out = nim_fine_tune({
            "base_url": "http://nemo.test",
            "dataset": "agent-traj",
            "config": "meta/llama-3.1-8b-instruct@v1.0.0+A100",
            "api_key": "key-123",
            "epochs": 5,
            "adapter_dim": 32,
        })
        self.assertEqual(out["status"], "dry_run")
        self.assertEqual(out["job_id"], "")
        self.assertEqual(out["response"], {})
        self.assertIn("dry run", out["notes"])
        req = out["request"]
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "http://nemo.test/v1/customization/jobs")
        self.assertEqual(req["body"]["dataset"], {"name": "agent-traj", "namespace": "default"})
        self.assertEqual(req["body"]["hyperparameters"]["training_type"], "sft")
        self.assertEqual(req["body"]["hyperparameters"]["epochs"], 5)
        self.assertEqual(req["body"]["hyperparameters"]["lora"], {"adapter_dim": 32})
        self.assertIn("curl -X POST 'http://nemo.test/v1/customization/jobs'", out["curl"])
        self.assertNotIn("key-123", out["curl"])  # key never leaked into curl

    def test_dpo_training_type_and_no_lora_for_full(self):
        out = nim_fine_tune({
            "base_url": "http://nemo.test",
            "dataset": "prefs",
            "api_key": "k",
            "training_type": "dpo",
            "finetuning_type": "all_weights",
        })
        hp = out["request"]["body"]["hyperparameters"]
        self.assertEqual(hp["training_type"], "dpo")
        self.assertNotIn("lora", hp)

    def test_missing_prerequisites_forces_dry_run_even_if_requested_live(self):
        out = nim_fine_tune({"dataset": "ds", "api_key": "k", "dry_run": False})  # no base_url
        self.assertEqual(out["status"], "dry_run")
        self.assertIn("cannot launch live: missing base_url", out["notes"])

    def test_reports_local_dataset_file_record_count(self):
        with TemporaryDirectory() as tmp:
            ds = Path(tmp) / "dataset.jsonl"
            ds.write_text('{"messages": []}\n{"messages": []}\n\n', encoding="utf-8")
            out = nim_fine_tune({"base_url": "http://nemo.test", "dataset": "d", "dataset_file": str(ds)})
        self.assertTrue(out["request"]["dataset_file"]["exists"])
        self.assertEqual(out["request"]["dataset_file"]["records"], 2)
        self.assertIn("2 records", out["notes"])


class NimFineTuneLiveTests(unittest.TestCase):
    def test_live_submit_posts_and_parses_job(self):
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["auth"] = req.get_header("Authorization")
            return _FakeResponse({"id": "cust-abc", "status": "created"}, status=201)

        with patch.object(nvidia.urllib_request, "urlopen", fake_urlopen):
            out = nim_fine_tune({
                "base_url": "http://nemo.test",
                "dataset": "agent-traj",
                "api_key": "secret",
                "dry_run": False,
            })

        self.assertEqual(out["job_id"], "cust-abc")
        self.assertEqual(out["status"], "created")
        self.assertIn("HTTP 201", out["notes"])
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "http://nemo.test/v1/customization/jobs")
        self.assertEqual(captured["auth"], "Bearer secret")
        self.assertEqual(captured["body"]["dataset"]["name"], "agent-traj")


class NimFineTuneStatusTests(unittest.TestCase):
    def test_status_missing_inputs(self):
        out = nim_fine_tune_status({"base_url": "", "job_id": ""})
        self.assertFalse(out["ok"])
        self.assertIn("missing", out["status"])

    def test_status_polls_job(self):
        def fake_urlopen(req, timeout=0):
            assert req.full_url == "http://nemo.test/v1/customization/jobs/cust-abc/status"
            return _FakeResponse({"status": "running", "percentage_done": 42.5}, status=200)

        with patch.object(nvidia.urllib_request, "urlopen", fake_urlopen):
            out = nim_fine_tune_status({"base_url": "http://nemo.test", "job_id": "cust-abc", "api_key": "k"})

        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "running")
        self.assertEqual(out["percent"], 42.5)


if __name__ == "__main__":
    unittest.main()
