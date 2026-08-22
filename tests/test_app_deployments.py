from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from blacknode.app_deployments import (
    APP_DEPLOYMENT_KIND,
    AppDeploymentError,
    build_app_deployment,
    load_app_deployment,
    operator_permissions,
    public_app_deployment,
)
from blacknode.cli import main


def _workflow(*, secret: str = "") -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Customer Task",
        "entrypoint": {"node_id": "out", "port": "value"},
        "metadata": {
            "required_packages": ["blacknode-example"],
            "operator_view": {
                "schema_version": 1,
                "id": "customer-task",
                "title": "Customer task",
                "icon": "record",
                "settings": {
                    "groups": [{
                        "id": "connection",
                        "title": "Connection",
                        "items": [{
                            "node_id": "text",
                            "param": "value",
                            "label": "Value",
                            "apply_to": [{"node_id": "mirror", "param": "value"}],
                        }],
                    }],
                },
                "run_target": {"node_id": "out", "port": "value"},
                "sections": [{
                    "id": "controls",
                    "widgets": [
                        {
                            "type": "fields",
                            "id": "fields",
                            "items": [{"node_id": "text", "param": "value", "label": "Value"}],
                        },
                        {
                            "type": "actions",
                            "id": "actions",
                            "items": [{
                                "id": "run",
                                "label": "Run",
                                "updates": [{"node_id": "text", "param": "value", "value": "ready"}],
                                "control": {"node_id": "out", "action": "refresh"},
                                "cook_target": {"node_id": "out", "port": "value"},
                            }],
                        },
                    ],
                }],
            },
        },
        "node_meta": {
            "text": {
                "id": "text",
                "type": "Text",
                "params": {"value": "hello", **({"api_key": secret} if secret else {})},
                "pos": [0, 0],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Text"},
                "output_types": {"value": "Text"},
                "input_defaults": {"value": ""},
            },
            "out": {
                "id": "out",
                "type": "Output",
                "params": {},
                "pos": [200, 0],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Any"},
                "output_types": {"value": "Any"},
                "input_defaults": {},
            },
            "mirror": {
                "id": "mirror",
                "type": "Text",
                "params": {"value": "hello"},
                "pos": [0, 100],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Text"},
                "output_types": {"value": "Text"},
                "input_defaults": {"value": ""},
            },
        },
        "edges": [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
    }


class AppDeploymentTests(unittest.TestCase):
    def test_bundle_exposes_summary_and_operator_permissions(self):
        manifest = build_app_deployment(
            [("customer.json", _workflow())],
            deployment_id="customer-demo",
        )

        self.assertEqual(manifest["kind"], APP_DEPLOYMENT_KIND)
        self.assertEqual(manifest["start_app"], "customer-task")
        self.assertEqual(manifest["required_packages"], ["blacknode-example"])
        public_app = public_app_deployment(manifest)["apps"][0]
        self.assertNotIn("workflow", public_app)
        self.assertEqual(public_app["icon"], "record")
        permissions = operator_permissions(manifest["apps"][0])
        self.assertEqual(permissions["params"], {("text", "value"), ("mirror", "value")})
        self.assertEqual(permissions["updates"], {("text", "value", '"ready"')})
        self.assertEqual(permissions["controls"], {("out", "refresh", "{}")})
        self.assertEqual(permissions["cooks"], {("out", "value", "once")})

    def test_bundle_rejects_persisted_secrets(self):
        with self.assertRaisesRegex(AppDeploymentError, "persisted secret"):
            build_app_deployment(
                [("customer.json", _workflow(secret="do-not-ship"))],
                deployment_id="customer-demo",
            )

    def test_export_app_cli_writes_reloadable_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow_path = root / "customer.json"
            output_path = root / "customer.blacknode-app.json"
            workflow_path.write_text(json.dumps(_workflow()), encoding="utf-8")

            code = main([
                "export-app",
                str(workflow_path),
                "--id", "customer-demo",
                "--output", str(output_path),
            ])

            self.assertEqual(code, 0)
            manifest = load_app_deployment(output_path)
            self.assertEqual(manifest["id"], "customer-demo")
            self.assertEqual(manifest["apps"][0]["id"], "customer-task")


if __name__ == "__main__":
    unittest.main()
