from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import device_registry  # noqa: E402
import server  # noqa: E402


class ComputeDeviceInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_registry = server._device_registry
        server._device_registry = device_registry.DeviceRegistry(
            Path(self.temporary.name) / "devices.json"
        )
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server._device_registry = self.previous_registry
        self.temporary.cleanup()

    def test_registered_ssh_inspection_is_credential_free_and_selectable(self):
        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-key",
            "instances": [],
            "environment": {
                "policy": "preserve",
                "os": {"name": "Ubuntu", "version": "22.04"},
                "ros2": {
                    "available": True,
                    "selected_distribution": "humble",
                },
            },
            "ros2_graph": {
                "available": False,
                "state": "unavailable",
                "read_only": True,
                "daemon_used": False,
                "topics": [],
                "nodes": [],
                "services": [],
                "errors": [],
            },
            "suggested_port": 8766,
            "suggested_instance_id": "instance-2",
        }
        with patch.object(server, "inspect_runtime", return_value=inspection):
            response = self.client.post("/device-hosts/inspect", json={
                "host": "192.168.55.1",
                "port": 22,
                "username": "ubuntu",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-key",
                "name": "Jetson",
                "save_inspection": True,
            })

        self.assertEqual(response.status_code, 200)
        device = response.json()["device"]
        self.assertTrue(device["inspection_only"])
        self.assertEqual(device["name"], "Jetson")
        self.assertEqual(
            device["inspection_connection"]["ssh_host"],
            "192.168.55.1",
        )
        listed = self.client.get("/device-hosts").json()["devices"]
        self.assertEqual([item["id"] for item in listed], [device["id"]])
        serialized = json.dumps(listed)
        self.assertNotIn("ssh-password", serialized)
        self.assertNotIn('"runtime_token":', serialized)
        self.assertTrue(listed[0]["last_inspection"]["ros2_graph"]["read_only"])

    def test_inspection_only_host_rejects_runtime_client(self):
        registry = server._device_registry
        device = registry.register_inspection_host(
            name="Jetson",
            runtime_url="http://192.168.55.1:8766",
            ssh_host="192.168.55.1",
            ssh_port=22,
            ssh_username="ubuntu",
            host_fingerprint="SHA256:trusted-key",
            inspection={"ok": True},
        )

        with self.assertRaisesRegex(
            device_registry.DeviceRegistryError,
            "read-only inspection",
        ):
            registry.host_client(device["id"])

    def test_pairing_runtime_upgrades_matching_inspection_device_in_place(self):
        registry = server._device_registry
        inspected = registry.register_inspection_host(
            name="Jetson",
            runtime_url="http://192.168.55.1:8766",
            ssh_host="192.168.55.1",
            ssh_port=22,
            ssh_username="ubuntu",
            host_fingerprint="SHA256:trusted-key",
            inspection={"ok": True},
        )

        paired = registry.pair_host(
            name="Jetson",
            runtime_url="http://192.168.55.1:8767",
            runtime_token="runtime-secret-value-that-is-long-enough",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "jetson-device",
            },
            managed_runtime={
                "ssh_host": "192.168.55.1",
                "ssh_port": 22,
                "ssh_username": "ubuntu",
                "host_fingerprint": "SHA256:trusted-key",
                "runtime_port": 8767,
            },
        )

        self.assertEqual(paired["id"], inspected["id"])
        self.assertFalse(paired["inspection_only"])
        self.assertEqual(paired["runtime_url"], "http://192.168.55.1:8767")
        self.assertEqual(len(registry.list_hosts()), 1)


if __name__ == "__main__":
    unittest.main()
