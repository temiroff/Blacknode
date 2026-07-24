from __future__ import annotations

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
            ["/health", "/status"],
        )
        self.assertIsNone(hardware.requests[0][2])
        self.assertEqual(hardware.requests[1][2], f"Bearer {hardware.token}")

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
        }])

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
