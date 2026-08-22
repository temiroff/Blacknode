from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from blacknode.app_deployments import build_app_deployment


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER = ROOT / "editor-server"
if str(EDITOR_SERVER) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER))

from app_mode import route_allowed  # noqa: E402
import server  # noqa: E402


def _app_workflow() -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Customer App",
        "entrypoint": {"node_id": "out", "port": "value"},
        "metadata": {
            "operator_view": {
                "schema_version": 1,
                "id": "customer-app",
                "title": "Customer App",
                "run_target": {"node_id": "out", "port": "value"},
                "sections": [{
                    "id": "setup",
                    "widgets": [{
                        "type": "fields",
                        "id": "fields",
                        "items": [{"node_id": "text", "param": "value", "label": "Value"}],
                    }],
                }],
            },
        },
        "node_meta": {
            "text": {
                "id": "text", "type": "Text", "params": {"value": "hello"}, "pos": [0, 0],
                "inputs": ["value"], "outputs": ["value"],
                "input_types": {"value": "Text"}, "output_types": {"value": "Text"},
                "input_defaults": {"value": ""},
            },
            "out": {
                "id": "out", "type": "Output", "params": {}, "pos": [200, 0],
                "inputs": ["value"], "outputs": ["value"],
                "input_types": {"value": "Any"}, "output_types": {"value": "Any"},
                "input_defaults": {},
            },
        },
        "edges": [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
    }


class EditorAppModeTests(unittest.TestCase):
    def test_route_boundary_allows_operator_surface_and_blocks_editor_mutation(self):
        self.assertTrue(route_allowed("GET", "/app-deployment"))
        self.assertTrue(route_allowed("POST", "/app-deployment/apps/customer-app/activate"))
        self.assertTrue(route_allowed("PATCH", "/nodes/text/params"))
        self.assertTrue(route_allowed("POST", "/nodes/recorder/control"))
        self.assertTrue(route_allowed("POST", "/cook-stream"))
        self.assertFalse(route_allowed("POST", "/nodes"))
        self.assertFalse(route_allowed("POST", "/graph"))
        self.assertFalse(route_allowed("GET", "/workflows"))
        self.assertFalse(route_allowed("POST", "/console/exec"))
        self.assertFalse(route_allowed("POST", "/packages/install"))

    def test_active_app_grants_only_declared_parameters(self):
        manifest = build_app_deployment(
            [("customer.json", _app_workflow())],
            deployment_id="customer-deployment",
        )
        with (
            patch.object(server, "_APP_DEPLOYMENT", manifest),
            patch.object(server, "_active_deployment_app_id", None),
            patch.object(server, "_active_deployment_permissions", {"params": set(), "updates": set(), "controls": set(), "cooks": set()}),
            patch.object(server, "_stop_active_cook"),
            patch.object(server, "_stop_runtime_services", return_value={}),
        ):
            client = TestClient(server.app)

            summary = client.get("/app-deployment")
            self.assertEqual(summary.status_code, 200)
            self.assertNotIn("workflow", summary.json()["apps"][0])

            blocked_editor = client.post("/nodes", json={"type_name": "Text"})
            self.assertEqual(blocked_editor.status_code, 403)

            invalid_origin = client.post(
                "/app-deployment/apps/customer-app/activate",
                headers={"Origin": "https://untrusted.example"},
            )
            self.assertEqual(invalid_origin.status_code, 403)

            preflight = client.options(
                "/app-deployment/apps/customer-app/activate",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(preflight.status_code, 204)

            activated = client.post("/app-deployment/apps/customer-app/activate")
            self.assertEqual(activated.status_code, 200, activated.text)

            allowed = client.patch("/nodes/text/params", json={"key": "value", "value": "operator"})
            self.assertEqual(allowed.status_code, 200, allowed.text)

            denied = client.patch("/nodes/text/params", json={"key": "undeclared", "value": "blocked"})
            self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
