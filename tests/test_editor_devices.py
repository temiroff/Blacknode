from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import device_registry  # noqa: E402
import server  # noqa: E402


class _JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _HardwareService:
    def __init__(
        self,
        token: str = "pairing-secret",
        *,
        status_overrides: dict | None = None,
    ) -> None:
        self.token = token
        self.requests: list[tuple[str, str, str | None, dict | None]] = []
        self.status_payload = {
            "device_id": "alex-desktop",
            "connected": True,
            "armed": False,
            "calibrated": False,
            "joint_names": [f"servo_{index}" for index in range(1, 7)],
            "capabilities": ["joint_group", "servo_bus", "position_feedback"],
            "connection": {
                "transport": "serial",
                "port": "/dev/serial/by-id/workshop-arm",
            },
            **(status_overrides or {}),
        }
        self.runtime_deployments: dict[str, dict] = {}
        self.runtime_packages = [
            {"name": "blacknode-runtime", "version": "0.2.0"},
        ]
        self.runtime_node_types = ["Output", "OutputImage"]

    def __call__(self, request, timeout=0):
        del timeout
        path = urllib.parse.urlsplit(request.full_url).path
        authorization = request.get_header("Authorization")
        body = json.loads(request.data) if request.data else None
        self.requests.append((request.method, path, authorization, body))
        if path == "/health":
            return _JsonResponse({
                "ok": True,
                "service": "blacknode-hardware",
                "auth_required": True,
            })
        if authorization != f"Bearer {self.token}":
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        if path == "/status":
            return _JsonResponse(self.status_payload)
        if path == "/calibration":
            if request.method == "POST":
                calibration = body["calibration"]
                profile = body["profile"]
                active = {
                    "active": True,
                    "profile_id": profile["id"],
                    "hardware_id": calibration["hardware_id"],
                    "target_device_id": self.status_payload["device_id"],
                    "activated_at": "2026-07-24T00:00:00+00:00",
                    "joint_count": len(calibration["joints"]),
                    "digest": "0123456789abcdef",
                }
                self.status_payload["calibrated"] = True
                self.status_payload["calibration"] = {
                    key: value
                    for key, value in active.items()
                    if key not in {"active", "target_device_id"}
                }
                return _JsonResponse({"ok": True, "calibration": active})
            return _JsonResponse({
                "active": bool(self.status_payload.get("calibrated")),
                **(self.status_payload.get("calibration") or {}),
            })
        if path == "/manifest":
            return _JsonResponse({
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "runtime_version": "0.1.0",
                "device_id": "alex-desktop",
                "features": [
                    "manifest_v1",
                    "deployment_bundle_v1",
                    "process_supervision_v1",
                    "rollback_v1",
                    "package_sync_v1",
                    "component_sync_v1",
                ],
                "python": {"version": "3.12.3"},
                "blacknode": {"installed": True, "version": "0.3.0"},
                "packages": self.runtime_packages,
                "node_types": self.runtime_node_types,
            })
        if path == "/packages/sync":
            installed = []
            package_index = server.package_index_payload()["packages"]
            for spec in body.get("packages", []):
                name = spec["name"]
                existing = next(
                    (item for item in self.runtime_packages if item["name"] == name),
                    None,
                )
                if existing is None:
                    item = {
                        "name": name,
                        "version": spec.get("version") or "0.3.0",
                        "source": "workspace",
                    }
                    self.runtime_packages.append(item)
                    installed.append(item)
                elif spec.get("version"):
                    existing["version"] = spec["version"]
                indexed = package_index.get(name) or {}
                self.runtime_node_types = sorted(set(
                    self.runtime_node_types + list(indexed.get("node_types") or [])
                ))
            return _JsonResponse({
                "ok": True,
                "installed": installed,
                "already_present": [],
                "messages": [],
            })
        if path == "/deployments":
            if request.method == "GET":
                return _JsonResponse({
                    "deployments": list(self.runtime_deployments.values()),
                })
            deployment_id = str(body.get("deployment_id") or "camera-workflow-a1b2c3d4")
            existing = self.runtime_deployments.get(deployment_id)
            revisions = list(existing.get("revisions", [])) if existing else []
            revision = "cafebabecafebabe"
            if revision not in revisions:
                revisions.append(revision)
            record = {
                "id": deployment_id,
                "name": body.get("name") or "Deployment",
                "state": "staged",
                "staged_revision": revision,
                "active_revision": existing.get("active_revision") if existing else None,
                "revisions": revisions,
                "pid": None,
                "exit_code": None,
                "error": "",
                "created_at": "2026-07-23T00:00:00+00:00",
                "updated_at": "2026-07-23T00:00:01+00:00",
            }
            self.runtime_deployments[deployment_id] = record
            return _JsonResponse(record)
        if path.startswith("/deployments/"):
            parts = path.strip("/").split("/")
            deployment_id = parts[1]
            record = self.runtime_deployments.get(deployment_id)
            if record is None:
                raise AssertionError(f"Unknown fake deployment: {deployment_id}")
            action = parts[2] if len(parts) > 2 else ""
            if request.method == "GET" and action == "logs":
                return _JsonResponse({"id": deployment_id, "logs": "remote output\n"})
            if request.method == "GET" and not action:
                return _JsonResponse(record)
            if request.method == "DELETE" and not action:
                del self.runtime_deployments[deployment_id]
                return _JsonResponse({"ok": True, "id": deployment_id})
            if action == "start":
                record.update(state="running", active_revision=record["staged_revision"], pid=4321)
            elif action == "stop":
                record.update(state="stopped", pid=None)
            elif action == "rollback":
                record.update(state="staged", pid=None)
            else:
                raise AssertionError(f"Unexpected fake deployment action: {action}")
            return _JsonResponse(record)
        if path == "/capabilities":
            return _JsonResponse({
                "device_id": "alex-desktop",
                "connected": True,
                "capabilities": ["joint_group", "servo_bus", "position_feedback"],
            })
        if path == "/rpc":
            method = str((body or {}).get("method") or "")
            if method == "resume":
                self.status_payload["connected"] = True
                self.status_payload["leased_to_deployment"] = False
                self.status_payload.pop("error", None)
            elif method == "release":
                self.status_payload["connected"] = False
                self.status_payload["leased_to_deployment"] = True
                self.status_payload["error"] = (
                    "serial hardware is leased to a Blacknode deployment"
                )
            return _JsonResponse({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"ok": True},
            })
        raise AssertionError(f"Unexpected device path: {path}")


class EditorDeviceApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self._tmp = tempfile.TemporaryDirectory()
        self.registry_path = Path(self._tmp.name) / ".blacknode" / "devices.json"
        self._original_registry = server._device_registry
        server._device_registry = device_registry.DeviceRegistry(self.registry_path)

    def tearDown(self):
        server._device_registry = self._original_registry
        self._tmp.cleanup()

    def test_workflow_requirements_are_normalized_and_exposed_by_graph(self):
        original_metadata = dict(server._session.metadata)
        try:
            server._session.metadata = {"required_packages": ["blacknode-robot"]}
            with patch.object(server, "_save"):
                response = self.client.patch("/graph/requirements", json={
                    "required_capabilities": [
                        "servo_bus",
                        "joint_group",
                        "servo_bus",
                        "position_feedback",
                    ],
                    "device_calibration": {
                        "profile_id": "so_arm101_v002",
                        "hardware_id": "USB-SERIAL-42",
                    },
                })
            graph = self.client.get("/graph").json()
        finally:
            server._session.metadata = original_metadata

        self.assertEqual(response.status_code, 200)
        metadata = response.json()["metadata"]
        self.assertEqual(
            metadata["required_capabilities"],
            ["joint_group", "position_feedback", "servo_bus"],
        )
        self.assertEqual(
            metadata["device_calibration"],
            {
                "profile_id": "so_arm101_v002",
                "hardware_id": "USB-SERIAL-42",
            },
        )
        self.assertEqual(metadata["required_packages"], ["blacknode-robot"])
        self.assertEqual(graph["metadata"], metadata)

    def test_pairing_validates_and_keeps_token_out_of_api_responses(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            response = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765/",
                "token": hardware.token,
            })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["device"]["id"], "alex-desktop")
        self.assertEqual(payload["device"]["base_url"], "http://192.168.1.87:8765")
        self.assertEqual(payload["device"]["runtime_url"], "http://192.168.1.87:8766")
        self.assertTrue(payload["runtime"]["ok"])
        self.assertNotIn("token", payload["device"])
        self.assertNotIn(hardware.token, response.text)

        listed = self.client.get("/devices")
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn(hardware.token, listed.text)
        self.assertEqual(listed.json()["devices"][0]["name"], "Workshop arm")

        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["devices"]["alex-desktop"]["token"], hardware.token)
        self.assertEqual(
            [item[1] for item in hardware.requests],
            ["/health", "/status", "/manifest"],
        )
        self.assertIsNone(hardware.requests[0][2])
        self.assertEqual(hardware.requests[1][2], f"Bearer {hardware.token}")

    def test_pairing_stores_and_checks_a_separate_runtime_token(self):
        hardware = _HardwareService("hardware-token")
        runtime = _HardwareService("runtime-token")

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return hardware(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=route):
            response = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
                "runtime_token": runtime.token,
            })
            runtime_status = self.client.get(
                f"/devices/{response.json()['device']['id']}/runtime-status",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["runtime"]["ok"])
        self.assertTrue(runtime_status.json()["ok"])
        device = response.json()["device"]
        self.assertNotIn("token", device)
        self.assertNotIn("runtime_token", device)
        self.assertNotIn(hardware.token, response.text)
        self.assertNotIn(runtime.token, response.text)
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        record = saved["devices"]["alex-desktop"]
        self.assertEqual(record["token"], hardware.token)
        self.assertEqual(record["runtime_token"], runtime.token)
        manifest_requests = [
            item for item in runtime.requests if item[1] == "/manifest"
        ]
        self.assertTrue(manifest_requests)
        self.assertTrue(all(
            authorization == f"Bearer {runtime.token}"
            for _method, _path, authorization, _body in manifest_requests
        ))

    def test_pairing_succeeds_but_devices_reports_rejected_runtime_token(self):
        hardware = _HardwareService("hardware-token")
        runtime = _HardwareService("runtime-token")

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return hardware(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=route):
            response = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            })
            preflight = self.client.post(
                f"/devices/{response.json()['device']['id']}/deployment-preflight",
                json={"workflow": _workflow([])},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["runtime"]["ok"])
        self.assertIn(
            "./service.sh pairing",
            response.json()["runtime"]["error"],
        )
        runtime_check = next(
            item for item in preflight.json()["checks"]
            if item["id"] == "target_runtime"
        )
        self.assertIn("Open Devices", runtime_check["message"])
        self.assertNotIn("Pairing token was rejected", runtime_check["message"])

    def test_shared_runtime_token_updates_every_robot_on_the_same_runtime(self):
        leader = _HardwareService(
            "leader-token",
            status_overrides={"device_id": "leader-arm"},
        )
        follower = _HardwareService(
            "follower-token",
            status_overrides={"device_id": "follower-arm"},
        )
        runtime = _HardwareService("runtime-token")

        def route(request, timeout=0):
            port = urllib.parse.urlsplit(request.full_url).port
            if port == 8766:
                return runtime(request, timeout)
            if port == 8767:
                return follower(request, timeout)
            return leader(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=route):
            leader_id = self.client.post("/devices", json={
                "name": "Leader",
                "base_url": "http://192.168.1.87:8765",
                "token": leader.token,
            }).json()["device"]["id"]
            repaired = self.client.post("/devices", json={
                "name": "Leader",
                "base_url": "http://192.168.1.87:8765",
                "token": leader.token,
                "runtime_token": runtime.token,
            })
            follower_pairing = self.client.post("/devices", json={
                "name": "Follower",
                "base_url": "http://192.168.1.87:8767",
                "token": follower.token,
            })
            follower_id = follower_pairing.json()["device"]["id"]
            follower_runtime = self.client.get(
                f"/devices/{follower_id}/runtime-status",
            )

        self.assertEqual(leader_id, "leader-arm")
        self.assertTrue(repaired.json()["runtime"]["ok"])
        self.assertTrue(follower_pairing.json()["runtime"]["ok"])
        self.assertTrue(follower_runtime.json()["ok"])
        devices = {
            item["id"]: item for item in self.client.get("/devices").json()["devices"]
        }
        self.assertEqual(
            devices[leader_id]["runtime_token_fingerprint"],
            devices[follower_id]["runtime_token_fingerprint"],
        )
        self.assertTrue(devices[leader_id]["runtime_token_configured"])
        self.assertTrue(devices[follower_id]["runtime_token_configured"])

    def test_status_and_rpc_use_saved_token_on_fixed_device_endpoints(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            status = self.client.get(f"/devices/{paired['id']}/status")
            rpc = self.client.post(
                f"/devices/{paired['id']}/rpc",
                json={"id": "stop-1", "method": "stop", "params": {}},
            )

        self.assertTrue(status.json()["connected"])
        self.assertEqual(rpc.json()["result"], {"ok": True})
        self.assertEqual(hardware.requests[-2][1], "/status")
        self.assertEqual(hardware.requests[-2][2], f"Bearer {hardware.token}")
        self.assertEqual(hardware.requests[-1][1], "/rpc")
        self.assertEqual(hardware.requests[-1][3]["method"], "stop")

    def test_device_status_recovers_a_stale_deployment_lease(self):
        hardware = _HardwareService(status_overrides={
            "connected": False,
            "leased_to_deployment": True,
            "error": "serial hardware is leased to a Blacknode deployment",
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            response = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["connected"])
        self.assertFalse(response.json()["leased_to_deployment"])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("resume", rpc_methods)

    def test_device_status_identifies_the_running_lease_owner(self):
        hardware = _HardwareService(status_overrides={
            "connected": False,
            "leased_to_deployment": True,
            "error": "serial hardware is leased to a Blacknode deployment",
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            hardware.runtime_deployments["leader-live"] = {
                "id": "leader-live",
                "name": "Leader live",
                "state": "running",
                "target_device_id": paired["id"],
            }
            response = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment_lease"], {
            "id": "leader-live",
            "name": "Leader live",
            "state": "running",
        })
        self.assertIn("Leader live", payload["error"])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertNotIn("resume", rpc_methods)

    def test_repairing_same_url_replaces_token_without_duplicating_device(self):
        first = _HardwareService("first-token")
        with patch("device_registry.urllib.request.urlopen", side_effect=first):
            self.client.post("/devices", json={
                "name": "Old name",
                "base_url": "http://192.168.1.87:8765",
                "token": first.token,
            })

        second = _HardwareService("rotated-token")
        with patch("device_registry.urllib.request.urlopen", side_effect=second):
            response = self.client.post("/devices", json={
                "name": "New name",
                "base_url": "http://192.168.1.87:8765",
                "token": second.token,
            })

        self.assertEqual(response.status_code, 200)
        devices = self.client.get("/devices").json()["devices"]
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "New name")
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["devices"]["alex-desktop"]["token"], second.token)

    def test_rejected_token_is_not_saved(self):
        hardware = _HardwareService()

        def reject_status(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).path == "/health":
                return hardware(request, timeout)
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

        with patch("device_registry.urllib.request.urlopen", side_effect=reject_status):
            response = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": "wrong-token",
            })

        self.assertEqual(response.status_code, 400)
        self.assertIn("rejected", response.json()["detail"].lower())
        self.assertFalse(self.registry_path.exists())

    def test_runtime_port_is_rejected_as_a_hardware_pairing_url(self):
        response = self.client.post("/devices", json={
            "name": "Wrong endpoint",
            "base_url": "http://192.168.1.87:8766",
            "token": "pairing-token",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("shared Blacknode runtime", response.json()["detail"])
        self.assertFalse(self.registry_path.exists())

    def test_robot_deployment_is_bound_to_the_paired_service_serial_port(self):
        workflow = {
            "node_meta": {
                "robot": {
                    "id": "robot",
                    "type": "Robot",
                    "params": {},
                    "inputs": [],
                    "input_types": {},
                    "input_defaults": {},
                },
            },
            "edges": [],
        }

        server._bind_robot_to_device(workflow, {
            "device_id": "robot-service-id",
            "connected": True,
            "connection": {
                "transport": "serial",
                "port": "/dev/serial/by-id/follower-arm",
            },
            "calibration": {"hardware_id": "FOLLOWER-USB-ID"},
        })

        params = workflow["node_meta"]["robot"]["params"]
        self.assertEqual(
            params["serial_port"],
            "/dev/serial/by-id/follower-arm",
        )
        self.assertEqual(
            params["hardware"]["recommended"]["serial"],
            "FOLLOWER-USB-ID",
        )
        self.assertFalse(params["auto_discover"])

    def test_invalid_url_and_unknown_device_are_rejected(self):
        response = self.client.post("/devices", json={
            "name": "Bad URL",
            "base_url": "file:///tmp/device",
            "token": "secret",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("http", response.json()["detail"].lower())
        self.assertEqual(self.client.get("/devices/missing/status").status_code, 404)

    def test_delete_removes_local_pairing(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]

        response = self.client.delete(f"/devices/{device_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/devices").json()["devices"], [])

    def test_deployment_preflight_reports_safety_capabilities_and_runtime(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": _workflow(["joint_group"])},
            )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["workflow"]["status"], "pass")
        self.assertEqual(checks["service"]["status"], "pass")
        self.assertEqual(checks["hardware"]["status"], "pass")
        self.assertEqual(checks["safety"]["status"], "pass")
        self.assertEqual(checks["capabilities"]["status"], "pass")
        self.assertEqual(checks["calibration"]["status"], "fail")
        self.assertTrue(checks["calibration"]["blocking"])
        self.assertEqual(checks["target_runtime"]["status"], "pass")
        self.assertFalse(checks["target_runtime"]["blocking"])
        self.assertFalse(report["ready"])
        self.assertNotIn(hardware.token, response.text)

    def test_selected_calibration_can_be_activated_and_satisfies_preflight(self):
        hardware = _HardwareService(status_overrides={
            "connection": {
                "transport": "serial",
                "port": "/dev/serial/by-id/usb-USB-SERIAL-42-if00",
            },
        })
        robots_root = Path(self._tmp.name) / "robots"
        profile_dir = robots_root / "arm_profile"
        calibration_dir = profile_dir / "calibrations"
        calibration_dir.mkdir(parents=True)
        profile = {
            "schema_version": 1,
            "id": "arm_profile",
            "display_name": "Arm profile",
            "joints": [
                {"id": f"servo_{index}", "servo_id": index}
                for index in range(1, 7)
            ],
        }
        calibration = {
            "schema_version": 1,
            "name": "Workshop left arm",
            "profile_id": "arm_profile",
            "hardware_id": "USB-SERIAL-42",
            "recorded_at": "2026-07-24T00:00:00Z",
            "joints": {
                f"servo_{index}": {
                    "home_ticks": 2048,
                    "safe_min_deg": -80.0,
                    "safe_max_deg": 80.0,
                }
                for index in range(1, 7)
            },
        }
        (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (calibration_dir / "usb_serial_42.json").write_text(
            json.dumps(calibration),
            encoding="utf-8",
        )
        original_metadata = dict(server._session.metadata)
        original_node_meta = dict(server._session.node_meta)
        workflow = _workflow(["joint_group"])
        robot_fn = server._NODE_REGISTRY["Output"]
        workflow["node_meta"]["robot"] = {
            "id": "robot",
            "type": "Robot",
            "params": {"profile_id": "arm_profile"},
            "pos": [200, 0],
            "inputs": list(getattr(robot_fn, "_bn_inputs", [])),
            "outputs": list(getattr(robot_fn, "_bn_outputs", [])),
            "input_types": dict(getattr(robot_fn, "_bn_input_types", {})),
            "output_types": dict(getattr(robot_fn, "_bn_output_types", {})),
            "input_defaults": dict(getattr(robot_fn, "_bn_input_defaults", {})),
        }
        workflow["metadata"]["device_calibration"] = {
            "profile_id": "arm_profile",
            "hardware_id": "USB-SERIAL-42",
        }
        try:
            server._session.metadata = dict(workflow["metadata"])
            server._session.node_meta = {
                "robot": {
                    "id": "robot",
                    "type": "Robot",
                    "params": {"profile_id": "arm_profile"},
                },
            }
            with (
                patch.dict(server._NODE_REGISTRY, {"Robot": robot_fn}),
                patch.dict("os.environ", {"BLACKNODE_ROBOTS_DIR": str(robots_root)}),
                patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            ):
                device_id = self.client.post("/devices", json={
                    "name": "Workshop arm",
                    "base_url": "http://192.168.1.87:8765",
                    "token": hardware.token,
                }).json()["device"]["id"]
                candidates = self.client.get("/graph/calibrations")
                before_activation = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={"workflow": workflow},
                )
                activated = self.client.post(f"/devices/{device_id}/calibration")
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={"workflow": workflow},
                )
        finally:
            server._session.metadata = original_metadata
            server._session.node_meta = original_node_meta

        self.assertEqual(candidates.status_code, 200)
        listed_profile = next(
            item
            for item in candidates.json()["profiles"]
            if item["id"] == "arm_profile"
        )
        self.assertEqual(listed_profile["name"], "Arm profile")
        self.assertTrue(listed_profile["saved"])
        self.assertEqual(listed_profile["calibration_count"], 1)
        self.assertEqual(
            candidates.json()["calibrations"][0]["hardware_id"],
            "USB-SERIAL-42",
        )
        self.assertEqual(
            candidates.json()["calibrations"][0]["name"],
            "Workshop left arm",
        )
        self.assertEqual(activated.status_code, 200)
        before_checks = {
            item["id"]: item for item in before_activation.json()["checks"]
        }
        self.assertEqual(
            before_checks["calibration"]["action"],
            "activate_calibration",
        )
        self.assertTrue(activated.json()["status"]["calibrated"])
        checks = {item["id"]: item for item in preflight.json()["checks"]}
        self.assertEqual(checks["calibration"]["status"], "pass")
        self.assertFalse(checks["calibration"]["blocking"])
        calibration_requests = [
            item for item in hardware.requests if item[1] == "/calibration"
        ]
        self.assertEqual(len(calibration_requests), 1)
        self.assertEqual(
            calibration_requests[0][3]["calibration"]["hardware_id"],
            "USB-SERIAL-42",
        )

    def test_wrong_robot_calibration_is_rejected_before_activation(self):
        activated: list[dict] = []
        hardware = SimpleNamespace(
            status=lambda: {
                "device_id": (
                    "alex-desktop-usb-1a86-usb-single-serial-"
                    "5b41531741-if-03dc3457"
                ),
                "connected": True,
                "armed": False,
                "calibrated": False,
                "connection": {
                    "transport": "serial",
                    "port": (
                        "/dev/serial/by-id/"
                        "usb-1a86_USB_Single_Serial_5B41531741-if00"
                    ),
                },
            },
            activate_calibration=lambda profile, calibration: activated.append({
                "profile": profile,
                "calibration": calibration,
            }),
        )
        profile = {"id": "so_arm101_v002", "joints": []}
        calibration = {
            "profile_id": "so_arm101_v002",
            "hardware_id": "5B41531481",
            "joints": {},
        }

        with (
            patch.object(
                server,
                "_selected_local_calibration",
                return_value=(profile, calibration),
            ),
            patch.object(server, "_paired_device_client", return_value=hardware),
        ):
            response = self.client.post("/devices/paired/calibration")

        self.assertEqual(response.status_code, 409)
        message = response.json()["detail"]
        self.assertIn("different physical robot", message)
        self.assertIn("5B41531481", message)
        self.assertIn("5B41531741", message)
        self.assertIn("Do not activate", message)
        self.assertEqual(activated, [])
        self.assertFalse(
            server._remote_hardware_identity_match(
                hardware.status(),
                "5B41531481",
            ),
        )
        self.assertTrue(
            server._remote_hardware_identity_match(
                hardware.status(),
                "5B41531741",
            ),
        )

        workflow = _workflow(["joint_group"])
        workflow["metadata"]["device_calibration"] = {
            "profile_id": "so_arm101_v002",
            "hardware_id": "5B41531481",
        }
        robot_fn = server._NODE_REGISTRY["Output"]
        workflow["node_meta"]["robot"] = {
            "id": "robot",
            "type": "Robot",
            "params": {"profile_id": "so_arm101_v002"},
            "pos": [200, 0],
            "inputs": list(getattr(robot_fn, "_bn_inputs", [])),
            "outputs": list(getattr(robot_fn, "_bn_outputs", [])),
            "input_types": dict(getattr(robot_fn, "_bn_input_types", {})),
            "output_types": dict(getattr(robot_fn, "_bn_output_types", {})),
            "input_defaults": dict(getattr(robot_fn, "_bn_input_defaults", {})),
        }
        runtime = SimpleNamespace(manifest=lambda: {
            "service": "blacknode-runtime",
            "protocol_version": 1,
            "runtime_version": "0.2.0",
            "features": [
                "manifest_v1",
                "deployment_bundle_v1",
                "process_supervision_v1",
                "rollback_v1",
                "package_sync_v1",
            ],
            "python": {"version": "3.12.3"},
            "blacknode": {"installed": True, "version": "0.3.0"},
            "packages": [],
            "node_types": ["Output", "Robot"],
        })
        paired_device = {
            "id": "paired",
            "name": "Wrong arm",
            "base_url": "http://192.168.1.87:8765",
            "runtime_url": "http://192.168.1.87:8766",
            "remote_device_id": hardware.status()["device_id"],
        }
        with (
            patch.dict(server._NODE_REGISTRY, {"Robot": robot_fn}),
            patch.object(server._device_registry, "get_public", return_value=paired_device),
            patch.object(server._device_registry, "runtime_client", return_value=runtime),
            patch.object(server, "_paired_device_client", return_value=hardware),
            patch.object(
                server,
                "_selected_local_calibration",
                return_value=(profile, calibration),
            ),
        ):
            preflight = self.client.post(
                "/devices/paired/deployment-preflight",
                json={"workflow": workflow},
            )

        self.assertEqual(preflight.status_code, 200)
        checks = {item["id"]: item for item in preflight.json()["checks"]}
        self.assertEqual(checks["calibration"]["status"], "fail")
        self.assertTrue(checks["calibration"]["blocking"])
        self.assertEqual(
            checks["calibration"]["action"],
            "choose_matching_hardware",
        )
        self.assertIn(
            "different physical robot",
            checks["calibration"]["message"],
        )
        self.assertIn("Do not activate", checks["calibration"]["message"])

    def test_old_device_service_reports_calibration_upgrade_action(self):
        response = io.BytesIO(b'{"ok": false, "error": "not found"}')
        error = urllib.error.HTTPError(
            "http://192.168.1.87:8765/calibration",
            404,
            "Not Found",
            {},
            response,
        )
        client = device_registry.HardwareDeviceClient(
            "http://192.168.1.87:8765",
            "pairing-token",
        )

        with (
            patch("device_registry.urllib.request.urlopen", side_effect=error),
            self.assertRaisesRegex(
                device_registry.DeviceRegistryError,
                r"Update blacknode-hardware.*service\.sh restart",
            ),
        ):
            client.activate_calibration({}, {})

    def test_deployment_preflight_keeps_runtime_unavailable_as_a_blocker(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]

        def hardware_only(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                raise urllib.error.URLError("connection refused")
            return hardware(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=hardware_only):
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": _workflow([])},
            )

        checks = {item["id"]: item for item in response.json()["checks"]}
        self.assertEqual(checks["target_runtime"]["status"], "pending")
        self.assertTrue(checks["target_runtime"]["blocking"])

    def test_deployment_preflight_reports_auto_installable_target_package(self):
        hardware = _HardwareService()
        workflow = _workflow([])
        package_specs = [_target_package_spec()]
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            patch.object(
                server,
                "_workflow_target_package_specs",
                return_value=package_specs,
            ),
            patch.object(
                server,
                "_workflow_target_packages",
                return_value=[package_specs[0]["name"]],
            ),
        ):
            device_id = self.client.post("/devices", json={
                "name": "Workshop camera",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": workflow},
            )

        self.assertEqual(response.status_code, 200)
        target_runtime = next(
            item for item in response.json()["checks"]
            if item["id"] == "target_runtime"
        )
        self.assertEqual(target_runtime["status"], "warning")
        self.assertFalse(target_runtime["blocking"])
        self.assertIn("blacknode-perception", target_runtime["message"])
        self.assertTrue(response.json()["ready"])

    def test_target_package_specs_use_live_package_registry_for_new_package(self):
        package_dir = Path(self._tmp.name) / "blacknode-new-camera"
        package_dir.mkdir()
        subprocess.run(["git", "init", str(package_dir)], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(package_dir),
                "remote",
                "add",
                "origin",
                "git@github.com:example/blacknode-new-camera.git",
            ],
            check=True,
            capture_output=True,
        )
        package = SimpleNamespace(
            name="blacknode-new-camera",
            version="1.4.0",
            node_types=["NewCamera"],
            path=str(package_dir),
        )
        workflow = {
            "metadata": {
                "required_components": ["blacknode-new-camera/capture"],
                "required_adapters": ["blacknode-new-camera/capture@ros2"],
            },
            "node_meta": {"camera": {"type": "NewCamera"}},
            "edges": [],
        }

        with (
            patch.object(server, "installed_packages", return_value=[package]),
            patch.object(
                server,
                "package_index_payload",
                return_value={"packages": {}, "nodes": {}},
            ),
        ):
            specs = server._workflow_target_package_specs(workflow)

        self.assertEqual(specs, [{
            "name": "blacknode-new-camera",
            "git_url": "https://github.com/example/blacknode-new-camera.git",
            "version": "1.4.0",
            "components": ["capture"],
            "adapters": [{"component": "capture", "adapter": "ros2"}],
        }])

    def test_preflight_can_activate_an_installed_package_adapter(self):
        hardware = _HardwareService()
        hardware.runtime_packages.append({
            "name": "blacknode-skills",
            "version": "0.1.0",
            "source": "workspace",
        })
        workflow = _workflow([])
        package_specs = [{
            "name": "blacknode-skills",
            "git_url": "https://github.com/temiroff/blacknode-skills.git",
            "version": "0.1.0",
            "components": ["follow-person"],
            "adapters": [{"component": "follow-person", "adapter": "ros2"}],
        }]
        package_index = {
            "packages": {},
            "nodes": {
                "ROS2LeaderFollower": {
                    "package": "blacknode-skills",
                    "git_url": "https://github.com/temiroff/blacknode-skills.git",
                },
            },
        }
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            patch.object(
                server,
                "_workflow_target_package_specs",
                return_value=package_specs,
            ),
            patch.object(
                server,
                "_workflow_target_packages",
                return_value=["blacknode-skills"],
            ),
            patch.object(
                server,
                "workflow_node_types",
                return_value={"ROS2LeaderFollower"},
            ),
            patch.object(
                server,
                "package_index_payload",
                return_value=package_index,
            ),
        ):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": workflow},
            )

        target_runtime = next(
            item for item in response.json()["checks"]
            if item["id"] == "target_runtime"
        )
        self.assertEqual(target_runtime["status"], "warning")
        self.assertFalse(target_runtime["blocking"])
        self.assertIn("blacknode-skills", target_runtime["message"])
        self.assertTrue(response.json()["ready"])

    def test_staging_auto_installs_extension_packages_before_upload(self):
        hardware = _HardwareService()
        workflow = _workflow([])
        package_specs = [_target_package_spec()]
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            patch.object(
                server,
                "_workflow_target_package_specs",
                return_value=package_specs,
            ),
            patch.object(
                server,
                "_workflow_target_packages",
                return_value=[package_specs[0]["name"]],
            ),
        ):
            device_id = self.client.post("/devices", json={
                "name": "Workshop camera",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            with patch.object(server, "_workflow_payload", return_value=workflow):
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()
                response = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                    },
                )

        self.assertEqual(response.status_code, 200)
        runtime_paths = [
            path
            for method, path, _auth, _body in hardware.requests
            if method == "POST" and path in {"/packages/sync", "/deployments"}
        ]
        self.assertEqual(runtime_paths[-2:], ["/packages/sync", "/deployments"])
        sync_request = next(
            item for item in hardware.requests
            if item[0] == "POST" and item[1] == "/packages/sync"
        )
        self.assertEqual(
            sync_request[3]["packages"],
            package_specs,
        )

    def test_deployment_preflight_returns_structured_failure_when_device_is_offline(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]

        with patch(
            "device_registry.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": _workflow([])},
            )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["service"]["status"], "fail")
        self.assertTrue(checks["service"]["blocking"])
        self.assertIsNone(report["status"])
        self.assertFalse(report["ready"])

    def test_deployment_preflight_uses_current_editor_graph_when_workflow_is_omitted(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            with patch.object(server, "_workflow_payload", return_value=_workflow([])):
                response = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["workflow"]["name"], "Device preflight")
        self.assertEqual(response.json()["workflow"]["node_count"], 1)
        self.assertEqual(len(response.json()["workflow"]["hash"]), 64)

    def test_validated_graph_can_be_staged_and_started_on_runtime(self):
        hardware = _HardwareService()
        workflow = _workflow([])
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            with patch.object(server, "_workflow_payload", return_value=workflow):
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()
                response = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "start": True,
                    },
                )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["started"])
        self.assertEqual(result["deployment"]["state"], "running")
        stage_request = next(
            item for item in hardware.requests
            if item[0] == "POST" and item[1] == "/deployments"
        )
        self.assertIn("from __future__ import annotations", stage_request[3]["script"])
        self.assertEqual(
            stage_request[3]["manifest"]["workflow_hash"],
            preflight["workflow"]["hash"],
        )
        self.assertNotIn(hardware.token, response.text)
        lease_requests = [
            body
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("release", [body["method"] for body in lease_requests])
        self.assertEqual(
            stage_request[3]["manifest"]["target_device_id"],
            device_id,
        )

    def test_preflight_recovers_stale_hardware_deployment_lease(self):
        hardware = _HardwareService(status_overrides={
            "connected": False,
            "error": "serial hardware is leased to a Blacknode deployment",
        })
        workflow = _workflow([])
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            with patch.object(server, "_workflow_payload", return_value=workflow):
                response = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                )

        self.assertEqual(response.status_code, 200)
        hardware_check = next(
            item for item in response.json()["checks"]
            if item["id"] == "hardware"
        )
        self.assertEqual(hardware_check["status"], "pass")
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("resume", rpc_methods)

    def test_preflight_names_running_deployment_that_owns_hardware(self):
        hardware = _HardwareService(status_overrides={
            "connected": False,
            "error": "serial hardware is leased to a Blacknode deployment",
        })
        workflow = _workflow([])
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            hardware.runtime_deployments["leader-live"] = {
                "id": "leader-live",
                "name": "Leader live",
                "state": "running",
                "target_device_id": device_id,
            }
            with patch.object(server, "_workflow_payload", return_value=workflow):
                response = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                )

        self.assertEqual(response.status_code, 200)
        hardware_check = next(
            item for item in response.json()["checks"]
            if item["id"] == "hardware"
        )
        self.assertEqual(hardware_check["status"], "fail")
        self.assertIn("Leader live", hardware_check["message"])
        self.assertIn("Stop that deployment", hardware_check["message"])

    def test_staging_rejects_graph_changed_after_validation(self):
        hardware = _HardwareService()
        original = _workflow([])
        changed = json.loads(json.dumps(original))
        changed["node_meta"]["out"]["params"]["changed"] = True
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            with patch.object(server, "_workflow_payload", return_value=original):
                workflow_hash = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()["workflow"]["hash"]
            with patch.object(server, "_workflow_payload", return_value=changed):
                response = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Changed graph",
                        "workflow_hash": workflow_hash,
                    },
                )

        self.assertEqual(response.status_code, 409)
        self.assertIn("changed after validation", response.json()["detail"])
        self.assertFalse(any(
            method == "POST" and path == "/deployments"
            for method, path, _auth, _body in hardware.requests
        ))

    def test_remote_deployment_controls_proxy_with_saved_token(self):
        hardware = _HardwareService()
        hardware.runtime_deployments["camera-workflow-a1b2c3d4"] = {
            "id": "camera-workflow-a1b2c3d4",
            "name": "Camera workflow",
            "state": "staged",
            "staged_revision": "cafebabecafebabe",
            "active_revision": None,
            "revisions": ["cafebabecafebabe", "feedfacefeedface"],
            "pid": None,
            "exit_code": None,
            "error": "",
            "created_at": "2026-07-23T00:00:00+00:00",
            "updated_at": "2026-07-23T00:00:01+00:00",
        }
        deployment_id = "camera-workflow-a1b2c3d4"
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            listed = self.client.get(f"/devices/{device_id}/deployments")
            started = self.client.post(
                f"/devices/{device_id}/deployments/{deployment_id}/start",
            )
            logs = self.client.get(
                f"/devices/{device_id}/deployments/{deployment_id}/logs",
            )
            stopped = self.client.post(
                f"/devices/{device_id}/deployments/{deployment_id}/stop",
            )
            rolled_back = self.client.post(
                f"/devices/{device_id}/deployments/{deployment_id}/rollback",
                json={},
            )

        self.assertEqual(listed.json()["deployments"][0]["id"], deployment_id)
        self.assertEqual(started.json()["state"], "running")
        self.assertEqual(logs.json()["logs"], "remote output\n")
        self.assertEqual(stopped.json()["state"], "stopped")
        self.assertEqual(rolled_back.json()["state"], "staged")
        remote_requests = [
            item for item in hardware.requests if item[1].startswith("/deployments")
        ]
        self.assertTrue(remote_requests)
        self.assertTrue(all(
            authorization == f"Bearer {hardware.token}"
            for _method, _path, authorization, _body in remote_requests
        ))

    def test_remote_start_rechecks_device_safety(self):
        hardware = _HardwareService(status_overrides={"armed": True})
        deployment_id = "camera-workflow-a1b2c3d4"
        hardware.runtime_deployments[deployment_id] = {
            "id": deployment_id,
            "name": "Camera workflow",
            "state": "staged",
            "staged_revision": "cafebabecafebabe",
            "active_revision": None,
            "revisions": ["cafebabecafebabe"],
            "pid": None,
            "exit_code": None,
            "error": "",
            "created_at": "2026-07-23T00:00:00+00:00",
            "updated_at": "2026-07-23T00:00:01+00:00",
        }
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            response = self.client.post(
                f"/devices/{device_id}/deployments/{deployment_id}/start",
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("disarm", response.json()["detail"].lower())
        self.assertFalse(any(
            path.endswith("/start") for _method, path, _auth, _body in hardware.requests
        ))


def _workflow(required_capabilities: list[str]) -> dict:
    fn = server._NODE_REGISTRY["Output"]
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Device preflight",
        "saved_at": "2026-07-23T00:00:00",
        "entrypoint": {"node_id": "out", "port": "value"},
        "metadata": {"required_capabilities": required_capabilities},
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
            },
        },
        "edges": [],
    }


def _target_package_spec() -> dict[str, str]:
    return {
        "name": "blacknode-perception",
        "git_url": "https://github.com/temiroff/blacknode-perception.git",
        "version": "0.3.0",
    }


if __name__ == "__main__":
    unittest.main()
