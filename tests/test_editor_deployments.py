"""Deployment HTTP surface on the editor server.

Nothing here starts a real deployment: the endpoints are exercised against a
temporary store with ``autostart`` suppressed, so the tests stay fast and
leave no background processes behind.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402

from blacknode.deployments import DeploymentStore  # noqa: E402


class EditorDeploymentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self._tmp = tempfile.TemporaryDirectory()
        self._original_store = server._deployment_store
        server._deployment_store = DeploymentStore(Path(self._tmp.name) / "deployments")

    def tearDown(self):
        server._deployment_store.stop_all()
        server._deployment_store = self._original_store
        self._tmp.cleanup()

    def _deploy(self, **payload):
        body = {"autostart": False, **payload}
        return self.client.post("/deployments", json=body)

    def test_deploying_the_current_graph_snapshots_it(self):
        response = self._deploy(name="From editor")
        # An empty editor graph cannot be deployed; either outcome is a
        # deliberate, explained answer rather than a server error.
        self.assertIn(response.status_code, (200, 400))
        if response.status_code == 400:
            self.assertIn("deploy", response.json()["detail"].lower())
            return
        record = response.json()
        self.assertEqual(record["name"], "From editor")
        self.assertTrue(record["snapshot_hash"])

    def test_supplied_workflow_round_trips_through_the_api(self):
        workflow = _output_only_workflow()
        record = self._deploy(name="Supplied", workflow=workflow).json()

        self.assertEqual(record["name"], "Supplied")
        self.assertEqual(record["kind"], "job")
        self.assertEqual(record["state"], "stopped")
        self.assertEqual(record["node_count"], 1)

        listed = self.client.get("/deployments").json()["deployments"]
        self.assertIn(record["id"], [item["id"] for item in listed])

        fetched = self.client.get(f"/deployments/{record['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["snapshot_hash"], record["snapshot_hash"])

    def test_undeployable_graph_answers_400_with_the_reason(self):
        empty = {"kind": "blacknode.workflow", "schema_version": 1, "name": "Empty",
                 "node_meta": {}, "edges": []}
        response = self._deploy(name="Empty", workflow=empty)
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty graph", response.json()["detail"].lower())

    def test_unsupported_target_is_refused_up_front(self):
        response = self._deploy(
            name="Container", workflow=_output_only_workflow(), target="docker"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("docker", response.json()["detail"].lower())

    def test_stop_and_delete_lifecycle(self):
        record = self._deploy(name="Lifecycle", workflow=_output_only_workflow()).json()

        stopped = self.client.post(f"/deployments/{record['id']}/stop")
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["state"], "stopped")

        deleted = self.client.delete(f"/deployments/{record['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["ok"])

        self.assertEqual(self.client.get(f"/deployments/{record['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/deployments/{record['id']}").status_code, 404)

    def test_unknown_deployment_is_404_everywhere(self):
        self.assertEqual(self.client.get("/deployments/nope").status_code, 404)
        self.assertEqual(self.client.post("/deployments/nope/stop").status_code, 404)
        self.assertEqual(self.client.post("/deployments/nope/start").status_code, 404)
        self.assertEqual(self.client.get("/deployments/nope/logs").status_code, 404)

    def test_logs_endpoint_returns_a_string_before_anything_ran(self):
        record = self._deploy(name="Logs", workflow=_output_only_workflow()).json()
        response = self.client.get(f"/deployments/{record['id']}/logs")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["logs"], str)


def _output_only_workflow() -> dict:
    from blacknode.node import _NODE_REGISTRY

    fn = _NODE_REGISTRY["Output"]
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Output only",
        "node_meta": {
            "out": {
                "id": "out",
                "type": "Output",
                "params": {},
                "pos": [0, 0],
                "inputs": list(getattr(fn, "_bn_inputs", [])),
                "outputs": list(getattr(fn, "_bn_outputs", [])),
                "input_types": dict(getattr(fn, "_bn_input_types", {})),
                "output_types": dict(getattr(fn, "_bn_output_types", {})),
                "input_defaults": dict(getattr(fn, "_bn_input_defaults", {})),
            }
        },
        "edges": [],
    }


if __name__ == "__main__":
    unittest.main()
