from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


class EditorCloudTests(unittest.TestCase):
    def test_cloud_status_reports_configuration_without_exposing_key(self):
        with patch.dict(
            os.environ,
            {
                "BLACKNODE_CLOUD_URL": "https://cloud.blacknode.example",
                "BLACKNODE_CLOUD_API_KEY": "private-cloud-key-with-24-characters",
            },
            clear=False,
        ):
            response = TestClient(server.app).get("/cloud/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertEqual(response.json()["gpu"], "NVIDIA L40S")
        self.assertNotIn("private-cloud-key", response.text)

    def test_create_cloud_job_sends_portable_workflow_to_private_api(self):
        session = server.Session()
        session.node_meta = {"out": {"type": "Output"}}
        calls: list[tuple[str, str, dict]] = []
        workflow = {
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": "Cloud graph",
            "entrypoint": {"node_id": "out", "port": "value"},
            "node_meta": {"out": {"type": "Output"}},
            "edges": [],
            "metadata": {},
        }

        def cloud_call(method, path, payload=None):
            calls.append((method, path, payload))
            return {"id": "job_" + "a" * 32, "status": "QUEUED"}

        with (
            patch.object(server, "_session", session),
            patch.object(server, "_workflow_payload", return_value=workflow),
            patch.object(
                server,
                "validate_bn_workflow",
                return_value=SimpleNamespace(ok=True, to_dict=lambda: {"ok": True}),
            ),
            patch.object(server, "_cloud_call", side_effect=cloud_call),
        ):
            response = TestClient(server.app).post(
                "/cloud/jobs",
                json={
                    "entrypoint": {"node_id": "out", "port": "value"},
                    "workflow_name": "Cloud graph",
                    "project_ref": "robot-project",
                },
            )

        self.assertEqual(response.status_code, 200)
        method, path, payload = calls[0]
        self.assertEqual((method, path), ("POST", "/v1/jobs"))
        self.assertEqual(payload["compute"]["gpu_class"], "l40s")
        self.assertEqual(payload["compute"]["gpu_count"], 1)
        self.assertEqual(payload["workflow"]["entrypoint"]["node_id"], "out")
        self.assertNotIn("image", payload["runtime"])

    def test_invalid_job_id_never_reaches_cloud(self):
        with patch.object(server, "_cloud_call") as cloud_call:
            response = TestClient(server.app).get("/cloud/jobs/../../secrets")

        self.assertIn(response.status_code, {400, 404})
        cloud_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
