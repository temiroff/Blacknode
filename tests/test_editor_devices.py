from __future__ import annotations

import base64
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
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
import device_installer  # noqa: E402
import local_runtime  # noqa: E402
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
        runtime_features: list[str] | None = None,
        torque_readback_available: bool = True,
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
        self.runtime_workflows: dict[str, dict] = {}
        self.runtime_telemetry: dict[str, dict] = {}
        self.runtime_services: dict[str, dict] = {}
        self.runtime_packages = [
            {"name": "blacknode-runtime", "version": "0.2.0"},
        ]
        self.runtime_node_types = ["Output", "OutputImage"]
        self.runtime_features = runtime_features or [
            "manifest_v1",
            "deployment_bundle_v1",
            "process_supervision_v1",
            "rollback_v1",
            "package_sync_v1",
            "package_refresh_v1",
            "component_sync_v1",
            "deployment_ownership_v1",
            "deployment_workflow_v1",
            "deployment_motion_control_v1",
            "ros2_diagnostics_v1",
            "managed_ros2_services_v1",
        ]
        self.ros2_diagnostics_payload = {
            "ok": True,
            "available": True,
            "checked_at": "2026-07-27T00:00:00+00:00",
            "summary": "Found 2 nodes, 2 topics, and 1 service.",
            "nodes": ["/leader", "/follower"],
            "topics": [
                "/leader/joint_states [sensor_msgs/msg/JointState]",
                "/follower/joint_states [sensor_msgs/msg/JointState]",
            ],
            "services": ["/leader/get_parameters"],
            "topic_details": [],
            "warnings": [],
        }
        self.torque_readback_available = torque_readback_available

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
                "features": self.runtime_features,
                "python": {"version": "3.12.3"},
                "blacknode": {"installed": True, "version": "0.3.0"},
                "packages": self.runtime_packages,
                "node_types": self.runtime_node_types,
            })
        if path == "/packages/sync":
            installed = []
            already_present = []
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
                if existing is not None:
                    already_present.append(dict(existing))
                indexed = package_index.get(name) or {}
                self.runtime_node_types = sorted(set(
                    self.runtime_node_types + list(indexed.get("node_types") or [])
                ))
            return _JsonResponse({
                "ok": True,
                "installed": installed,
                "already_present": already_present,
                "messages": [],
            })
        if path == "/diagnostics/ros2":
            return _JsonResponse(self.ros2_diagnostics_payload)
        if path.startswith("/services/"):
            parts = path.strip("/").split("/")
            service_id = parts[1]
            action = parts[2] if len(parts) > 2 else ""
            service = self.runtime_services.get(service_id)
            if request.method == "GET" and action == "logs":
                return _JsonResponse({
                    "id": service_id,
                    "logs": "managed camera provider output\n",
                })
            if request.method == "GET" and not action:
                if service is None:
                    raise urllib.error.HTTPError(
                        request.full_url, 404, "Not found", {}, None
                    )
                return _JsonResponse(service)
            if action == "start":
                service = {
                    "id": service_id,
                    "name": body.get("name") or service_id,
                    "state": "running",
                    "command": body["command"],
                    "interfaces": body.get("interfaces") or [],
                    "pid": 5678,
                    "error": "",
                    "diagnostics": {
                        "ok": True,
                        "checked_at": "2026-07-27T00:00:00+00:00",
                        "missing": [],
                        "interfaces": [
                            {
                                **item,
                                "ready": True,
                                "publishers": 1,
                            }
                            for item in (body.get("interfaces") or [])
                        ],
                    },
                }
                self.runtime_services[service_id] = service
                return _JsonResponse(service)
            if action == "stop":
                if service is None:
                    raise urllib.error.HTTPError(
                        request.full_url, 404, "Not found", {}, None
                    )
                service.update(
                    state="stopped",
                    pid=None,
                    diagnostics={
                        "ok": False,
                        "missing": [
                            item["topic"]
                            for item in service.get("interfaces") or []
                            if item.get("required", True)
                        ],
                        "interfaces": [],
                    },
                )
                return _JsonResponse(service)
            raise AssertionError(f"Unexpected fake service action: {action}")
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
                "target_device_id": (
                    body.get("manifest", {}).get("target_device_id")
                    or (existing or {}).get("target_device_id")
                    or ""
                ),
                "project_id": (
                    body.get("manifest", {}).get("project_id")
                    or (existing or {}).get("project_id")
                    or ""
                ),
                "workflow_slug": (
                    body.get("manifest", {}).get("workflow_slug")
                    or (existing or {}).get("workflow_slug")
                    or ""
                ),
                "state": "staged",
                "staged_revision": revision,
                "active_revision": existing.get("active_revision") if existing else None,
                "revisions": revisions,
                "pid": None,
                "exit_code": None,
                "error": "",
                "motion_armed": False,
                "motion_control_count": len(
                    body.get("manifest", {}).get("motion_controls") or []
                ),
                "created_at": "2026-07-23T00:00:00+00:00",
                "updated_at": "2026-07-23T00:00:01+00:00",
            }
            self.runtime_deployments[deployment_id] = record
            if isinstance(body.get("workflow"), dict):
                self.runtime_workflows[deployment_id] = body["workflow"]
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
            if request.method == "GET" and action == "telemetry":
                return _JsonResponse(self.runtime_telemetry.get(deployment_id, {
                    "available": False,
                    "deployment_id": deployment_id,
                    "stream": "robot-state",
                    "stale": True,
                    "message": "Waiting for telemetry.",
                }))
            if request.method == "GET" and action == "workflow":
                return _JsonResponse({
                    "id": deployment_id,
                    "revision": record["active_revision"] or record["staged_revision"],
                    "source": "snapshot",
                    "workflow": self.runtime_workflows[deployment_id],
                })
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
            elif action == "control":
                armed = body.get("command") == "arm"
                record["motion_armed"] = armed
                return _JsonResponse({
                    "ok": True,
                    "id": deployment_id,
                    "armed": armed,
                    "topic": "/blacknode/leader_follower/test/control",
                    "node_id": "follow",
                    "deployment": record,
                })
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
            elif method == "disable_torque":
                self.status_payload["armed"] = False
                if self.torque_readback_available:
                    self.status_payload["torque_enabled"] = False
                else:
                    self.status_payload["torque_enabled"] = None
                    self.status_payload["torque_report_error"] = (
                        "Could not read the physical torque-enable register for "
                        "servo_2 (servo 2)."
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
        self._original_project_store = server._project_store
        server._device_registry = device_registry.DeviceRegistry(self.registry_path)
        server._project_store = server.ProjectStore(
            Path(self._tmp.name) / ".blacknode" / "projects.json"
        )

    def tearDown(self):
        server._device_registry = self._original_registry
        server._project_store = self._original_project_store
        self._tmp.cleanup()

    def test_existing_robot_profile_opens_as_editable_joint_graph(self):
        robots_root = Path(self._tmp.name) / "robots"
        profile_dir = robots_root / "editable_arm"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text(json.dumps({
            "id": "editable_arm",
            "display_name": "Editable arm",
            "protocol": "custom",
            "driver": {"script": "arm_driver.py", "baudrate": 115200},
            "joints": [
                {"id": "second", "display_name": "Second", "servo_id": 2, "min_deg": -20, "max_deg": 20},
                {"id": "first", "display_name": "First", "servo_id": 1, "min_deg": -10, "max_deg": 10},
            ],
        }), encoding="utf-8")

        with patch.dict("os.environ", {"BLACKNODE_ROBOTS_DIR": str(robots_root)}):
            response = self.client.get("/graph/profiles/editable_arm/editor")

        self.assertEqual(response.status_code, 200)
        graph = response.json()
        joint_nodes = [node for node in graph["nodes"] if node["type"] == "RobotJointDefinition"]
        self.assertEqual(
            [node["params"]["joint_id"] for node in joint_nodes],
            ["first", "second"],
        )
        definition = next(node for node in graph["nodes"] if node["type"] == "RobotDefinition")
        save = next(node for node in graph["nodes"] if node["type"] == "RobotProfileSave")
        self.assertEqual(definition["params"]["profile_id"], "editable_arm")
        self.assertEqual(definition["params"]["baudrate"], 115200)
        self.assertTrue(save["params"]["overwrite"])

    def test_runtime_inspection_keeps_remote_token_paths_private(self):
        output = (
            "remote preface\n"
            "__BLACKNODE_RUNTIME_INSPECTION__="
            + json.dumps({
                "instances": [{
                    "instance_id": "default",
                    "port": 8766,
                    "_token_file": "/home/robot/.blacknode/runtime.auth.token",
                }],
                "environment": {
                    "policy": "preserve",
                    "docker": {"available": True, "server_version": "27.5.1"},
                },
                "ros2_graph": {
                    "available": True,
                    "state": "available",
                    "distribution": "humble",
                    "domain_id": "0",
                    "read_only": True,
                    "daemon_used": False,
                    "topics": [
                        "/scan [sensor_msgs/msg/LaserScan]",
                        "/controller/cmd_vel [geometry_msgs/msg/Twist]",
                    ],
                    "nodes": ["/controller"],
                    "services": ["/controller/get_parameters"],
                    "errors": [],
                },
                "suggested_port": 8767,
                "suggested_instance_id": "instance-2",
            })
        )

        private = device_installer._parse_inspection(output)
        public = device_installer._public_inspection(private)

        self.assertEqual(private["instances"][0]["_token_file"], "/home/robot/.blacknode/runtime.auth.token")
        self.assertNotIn("_token_file", public["instances"][0])
        self.assertNotIn("auth.token", json.dumps(public))
        self.assertEqual(public["environment"]["docker"]["server_version"], "27.5.1")
        self.assertTrue(public["ros2_graph"]["read_only"])
        self.assertFalse(public["ros2_graph"]["daemon_used"])
        self.assertEqual(
            public["ros2_graph"]["topics"],
            [
                "/scan [sensor_msgs/msg/LaserScan]",
                "/controller/cmd_vel [geometry_msgs/msg/Twist]",
            ],
        )
        self.assertEqual(public["suggested_port"], 8767)

    def test_remote_ros_inspection_never_starts_a_daemon_or_sends_messages(self):
        script = device_installer._INSPECTION_SCRIPT

        self.assertIn("--no-daemon", script)
        self.assertNotIn("ros2 topic echo", script)
        self.assertNotIn("ros2 topic pub", script)
        self.assertNotIn("ros2 service call", script)
        self.assertNotIn("ros2 action send_goal", script)

    def test_runtime_instance_ids_reject_shell_metacharacters(self):
        self.assertEqual(device_installer._clean_instance_id("instance-2"), "instance-2")
        with self.assertRaises(device_installer.DeviceInstallError):
            device_installer._clean_instance_id("instance-2; rm -rf")

    def test_nested_sudo_input_is_non_interactive_and_reusable(self):
        sudo_input = device_installer._sudo_input("ssh-password", attempts=3)

        self.assertEqual(sudo_input, "ssh-password\n" * 3)
        with self.assertRaises(device_installer.DeviceInstallError):
            device_installer._clean_target(
                "192.168.1.87",
                22,
                "robot",
                "line-one\nline-two",
            )

    def test_runtime_control_uses_password_stdin_for_every_sudo(self):
        commands = []
        stdin_values = []
        connection = SimpleNamespace(close=lambda: None)

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            stdin_values.append(kwargs.get("stdin_text"))
            return "inactive\n"

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.control_runtime(
                host="192.168.1.87",
                port=22,
                username="alex",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                action="pause",
            )

        self.assertEqual(result["state"], "inactive")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].count("sudo -S -p ''"), 3)
        self.assertNotIn(" && sudo systemctl", commands[0])
        self.assertNotIn("$(sudo systemctl", commands[0])
        self.assertEqual(
            stdin_values,
            [device_installer._sudo_input("ssh-password")],
        )

    def test_ssh_authentication_failure_is_clear_and_non_mutating(self):
        class AuthenticationException(Exception):
            pass

        class SSHException(Exception):
            pass

        class MissingHostKeyPolicy:
            pass

        class SSHClient:
            def set_missing_host_key_policy(self, _policy):
                return None

            def connect(self, *_args, **_kwargs):
                raise AuthenticationException("Authentication failed")

            def close(self):
                return None

        fake_paramiko = SimpleNamespace(
            AuthenticationException=AuthenticationException,
            SSHException=SSHException,
            MissingHostKeyPolicy=MissingHostKeyPolicy,
            SSHClient=SSHClient,
        )

        with patch.object(device_installer, "_load_paramiko", return_value=fake_paramiko):
            with self.assertRaisesRegex(
                device_installer.DeviceInstallError,
                "SSH login was rejected for user 'alex'",
            ):
                device_installer._connect(
                    "192.168.1.87",
                    22,
                    "alex",
                    "wrong-password",
                    expected_fingerprint="SHA256:trusted-device-key",
                )

    def test_remote_install_exports_a_non_interactive_sudo_wrapper(self):
        script = next(
            value
            for value in device_installer.install_runtime.__code__.co_consts
            if (
                isinstance(value, str)
                and value.startswith("#!/usr/bin/env bash")
                and "__BLACKNODE_INSTALL_PROGRESS__" in value
            )
        )

        self.assertIn("command sudo -S -p '' \"$@\"", script)
        self.assertIn("export -f sudo", script)
        self.assertIn('__BLACKNODE_RUNTIME_PORT__=$runtime_port', script)
        self.assertIn('"$remove_old_port" == "1"', script)
        self.assertIn("sock.bind((\"0.0.0.0\", candidate))", script)
        self.assertIn("'blacknode-runtime*.service' 'blacknode-hardware*.service'", script)
        self.assertIn('sudo systemctl start "$sibling_service"', script)
        self.assertIn('stack_root="$HOME/Blacknode/devices/$instance"', script)
        self.assertIn('runtime_dir="$stack_root/runtime"', script)
        self.assertIn('hardware_dir="$stack_root/hardware"', script)
        self.assertIn('"$action" == "install" || "$action" == "replace"', script)
        self.assertNotIn('"$action" == "runtime_only" ]]; then\n  complete_stack=true', script)
        self.assertIn('"$action" == "replace" || "$action" == "replace_runtime"', script)
        self.assertIn('if [[ "$complete_stack" == true && ! -d "$hardware_dir" ]]', script)
        self.assertIn('"packages_dir": str(Path(sys.argv[3]) / "packages")', script)
        self.assertIn(
            'sys.argv[6] in {"install", "replace", "isolated_stack"}',
            script,
        )
        self.assertIn('BLACKNODE_HARDWARE_INSTANCE="$service_instance"', script)
        self.assertIn("does not support isolated stacks yet", script)
        self.assertIn(
            'if [[ "$action" == "runtime_only" || "$action" == "replace_runtime" ]]',
            script,
        )
        self.assertIn('sudo ufw allow from "$candidate_source" to any port "$runtime_port"', script)
        self.assertIn('"firewall_source": sys.argv[7]', script)
        self.assertIn('delivery_mode="pc_assisted"', script)
        self.assertIn('--disable-pip-version-check --no-index', script)
        self.assertIn('rm -rf -- "$core_dir" "$python_dir" "$bundle_dir"', script)
        self.assertIn('__BLACKNODE_HARDWARE_PRESERVED__=1', script)
        self.assertNotIn("keep_sudo_alive", script)

        self.assertIn(
            "fallback_port = 0",
            device_installer._INSPECTION_SCRIPT,
        )
        self.assertIn(
            'organized_root = home / "Blacknode" / "devices"',
            device_installer._INSPECTION_SCRIPT,
        )
        self.assertIn(
            'legacy_side_root = home / "blacknode-runtimes"',
            device_installer._INSPECTION_SCRIPT,
        )

    def test_remote_install_embedded_python_blocks_compile(self):
        script = next(
            value
            for value in device_installer.install_runtime.__code__.co_consts
            if (
                isinstance(value, str)
                and value.startswith("#!/usr/bin/env bash")
                and "__BLACKNODE_INSTALL_PROGRESS__" in value
            )
        )
        python_blocks = re.findall(
            r"(?ms)^[^\n]*<<'PY'(?:\s*&)?\n(.*?)^PY$",
            script,
        )

        self.assertEqual(len(python_blocks), 5)
        for index, python_block in enumerate(python_blocks, start=1):
            compile(python_block, f"<remote-install-python-{index}>", "exec")

    def test_windows_editor_builds_and_reuses_linux_arm64_runtime_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python_archive = root / "python.tar.gz"
            runtime_archive = root / "runtime.tar.gz"
            core_archive = root / "core.tar.gz"
            wheelhouse = root / "wheels"
            wheelhouse.mkdir()
            python_archive.write_bytes(b"linux-python")
            runtime_archive.write_bytes(b"runtime-source")
            core_archive.write_bytes(b"core-source")
            (wheelhouse / "dependency-1.0-py3-none-any.whl").write_bytes(b"wheel")
            progress = []
            with (
                patch.dict(
                    os.environ,
                    {"BLACKNODE_DEVICE_INSTALL_CACHE": str(root / "cache")},
                ),
                patch.object(
                    device_installer,
                    "_standalone_python",
                    return_value=(python_archive, "3.11.14", "a" * 64),
                ),
                patch.object(
                    device_installer,
                    "_repository_snapshot",
                    side_effect=[
                        (runtime_archive, "b" * 40),
                        (core_archive, "c" * 40),
                    ],
                ),
                patch.object(
                    device_installer,
                    "_prepare_wheelhouse",
                    return_value=wheelhouse,
                ),
            ):
                bundle = device_installer._prepare_runtime_bundle(
                    "aarch64",
                    lambda percent, message: progress.append((percent, message)),
                )

            self.assertEqual(bundle.architecture, "aarch64")
            self.assertEqual(bundle.python_version, "3.11.14")
            with tarfile.open(bundle.path, "r:gz") as archive:
                names = set(archive.getnames())
                manifest_file = archive.extractfile("manifest.json")
                self.assertIsNotNone(manifest_file)
                manifest = json.loads(manifest_file.read().decode("utf-8"))
            self.assertIn("python.tar.gz", names)
            self.assertIn("runtime-source.tar.gz", names)
            self.assertIn("core-source.tar.gz", names)
            self.assertIn("wheelhouse/dependency-1.0-py3-none-any.whl", names)
            self.assertEqual(manifest["delivery_mode"], "pc_assisted")
            self.assertEqual(manifest["architecture"], "aarch64")
            self.assertTrue(any("verified" in message.lower() for _, message in progress))

            with (
                patch.dict(
                    os.environ,
                    {"BLACKNODE_DEVICE_INSTALL_CACHE": str(root / "cache")},
                ),
                patch.object(
                    device_installer,
                    "_standalone_python",
                    side_effect=device_installer.DeviceInstallError("editor offline"),
                ),
            ):
                cached = device_installer._prepare_runtime_bundle(
                    "arm64",
                    lambda _percent, _message: None,
                )
            self.assertEqual(cached.path, bundle.path)

    def test_pc_assisted_runtime_rejects_unsupported_device_architecture(self):
        with self.assertRaisesRegex(
            device_installer.DeviceInstallError,
            "does not support Linux architecture 'armv7l'",
        ):
            device_installer._target_architecture("armv7l")

    def test_pc_assisted_linux_lock_excludes_windows_packages(self):
        dependency_lock = (
            EDITOR_SERVER_DIR / "device-runtime-requirements.lock"
        ).read_text(encoding="utf-8")
        source_lock = device_installer._runtime_source_lock()

        self.assertIn("pydantic-core==", dependency_lock)
        self.assertIn("docker==", dependency_lock)
        self.assertNotIn("pywin32", dependency_lock.lower())
        self.assertEqual(
            source_lock["runtime"]["repository"],
            "temiroff/blacknode-runtime",
        )
        self.assertRegex(source_lock["core"]["commit"], r"^[0-9a-f]{40}$")

    def test_hardware_pairing_discovery_reads_only_verified_service_files(self):
        token = "hardware-pairing-token-1234567890"
        files = {
            "/home/alex/Blacknode/devices/default/hardware/pyproject.toml": (
                '[project]\nname = "blacknode-hardware"\nversion = "0.1.2"\n'
            ),
            (
                "/home/alex/Blacknode/devices/default/hardware/"
                ".blacknode-hardware/devices/follower/device.json"
            ): json.dumps({
                "name": "Follower arm",
                "device_id": "follower-device",
            }),
            (
                "/home/alex/Blacknode/devices/default/hardware/"
                ".blacknode-hardware/devices/follower/auth.token"
            ): token,
        }

        class Sftp:
            def file(self, path, _mode):
                return io.StringIO(files[path])

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []

        def fake_run(_connection, command, **_kwargs):
            commands.append(command)
            return (
                "__BLACKNODE_HARDWARE_PAIRINGS__="
                + json.dumps({
                    "services": [{
                        "service_name": "blacknode-hardware-follower.service",
                        "working_directory": (
                            "/home/alex/Blacknode/devices/default/hardware"
                        ),
                        "port": 8765,
                        "config_path": (
                            "/home/alex/Blacknode/devices/default/hardware/"
                            ".blacknode-hardware/devices/follower/device.json"
                        ),
                        "token_path": (
                            "/home/alex/Blacknode/devices/default/hardware/"
                            ".blacknode-hardware/devices/follower/auth.token"
                        ),
                        "active": True,
                    }],
                })
            )

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.discover_hardware_pairings(
                host="192.168.1.87",
                port=22,
                username="alex",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                expected_hardware_dir=(
                    "~/Blacknode/devices/default/hardware"
                ),
            )

        self.assertEqual(result["discovered"], 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["pairings"], [{
            "service_name": "blacknode-hardware-follower.service",
            "port": 8765,
            "name": "Follower arm",
            "device_id": "follower-device",
            "token": token,
            "active": True,
        }])
        self.assertNotIn(token, commands[0])
        self.assertIn("systemctl\", \"cat\"", commands[0])
        remote_python = commands[0].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        compile(remote_python, "<hardware-pairing-discovery>", "exec")

    def test_hardware_environment_can_be_added_to_runtime_only_device(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        stdin_values = []
        progress = []

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            stdin_values.append(kwargs.get("stdin_text"))
            if "on_output" in kwargs:
                kwargs["on_output"](
                    "__BLACKNODE_HARDWARE_INSTALL_PROGRESS__=50|"
                    "Setting up the Robot Hardware environment"
                )
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.install_hardware_environment(
                host="192.168.1.87",
                port=22,
                username="alex",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                progress=progress.append,
            )

        self.assertEqual(
            result["hardware_dir"],
            "~/Blacknode/devices/default/hardware",
        )
        self.assertEqual(result["stack_mode"], "isolated")
        self.assertTrue(any(item["progress"] == 50 for item in progress))
        self.assertIn("bash /tmp/blacknode-hardware-install-", commands[0])
        self.assertEqual(stdin_values[0], "ssh-password\n" * 8)
        self.assertNotIn("ssh-password", uploaded[0])
        self.assertIn(
            'hardware_dir="$stack_root/hardware"',
            uploaded[0],
        )
        self.assertIn(
            "git clone https://github.com/temiroff/blacknode-robot.git",
            uploaded[0],
        )
        self.assertNotIn(
            "github.com/temiroff/blacknode-hardware.git",
            uploaded[0],
        )
        self.assertIn(
            'BLACKNODE_HARDWARE_INSTANCE="$service_instance" bash ./setup_ubuntu.sh',
            uploaded[0],
        )
        remote_python = uploaded[0].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        compile(remote_python, "<hardware-environment-install>", "exec")

    def test_default_stack_can_adopt_recognized_legacy_hardware_services(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        stdin_values = []

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            stdin_values.append(kwargs.get("stdin_text"))
            if "blacknode-hardware-adopt-" in command and command.startswith("bash "):
                return "__BLACKNODE_HARDWARE_ADOPTION__={\"adopted\":2}"
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.adopt_legacy_hardware_services(
                host="192.168.1.87",
                port=22,
                username="alex",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
            )

        self.assertEqual(result["adopted"], 2)
        self.assertEqual(stdin_values[0], "ssh-password\n" * 16)
        self.assertNotIn("ssh-password", uploaded[0])
        self.assertIn('target="$HOME/Blacknode/devices/default/hardware"', uploaded[0])
        self.assertIn('legacy="$HOME/blacknode-hardware"', uploaded[0])
        self.assertIn("valid_target_checkout", uploaded[0])
        self.assertIn("valid_legacy_checkout", uploaded[0])
        self.assertIn("blacknode-robot", uploaded[0])
        self.assertIn("blacknode-hardware", uploaded[0])
        self.assertIn('cp -a -- "$legacy_private" "$temporary_private"', uploaded[0])
        self.assertIn(
            'BLACKNODE_HARDWARE_INSTANCE="" bash ./install-service.sh --all',
            uploaded[0],
        )
        self.assertIn(
            '[[ "$directory" == "$legacy" ]] || continue',
            uploaded[0],
        )

    def test_default_stack_can_configure_connected_serial_robots(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        stdin_values = []

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            stdin_values.append(kwargs.get("stdin_text"))
            if (
                "blacknode-hardware-configure-" in command
                and command.startswith("bash ")
            ):
                return (
                    "__BLACKNODE_HARDWARE_CONFIGURATION__="
                    "{\"configured\":2}"
                )
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.configure_hardware_services(
                host="192.168.1.87",
                port=22,
                username="alex",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                runtime_port=8766,
            )

        self.assertEqual(result["configured"], 2)
        self.assertEqual(stdin_values[0], "ssh-password\n" * 32)
        self.assertNotIn("ssh-password", uploaded[0])
        self.assertIn(
            'target="$HOME/Blacknode/devices/$instance/hardware"',
            uploaded[0],
        )
        self.assertIn(
            '[[ "$directory" == "$legacy" ]] || continue',
            uploaded[0],
        )
        self.assertIn(
            'BLACKNODE_RUNTIME_PORT="$runtime_port"',
            uploaded[0],
        )
        self.assertIn("./configure.sh --all --install", uploaded[0])
        self.assertIn(
            'sudo systemctl stop "$unit"',
            uploaded[0],
        )
        self.assertIn(
            'systemctl is-active --quiet "$unit"',
            uploaded[0],
        )
        self.assertIn(" default 8766", commands[0])

    def test_runtime_reinstall_uses_next_port_and_preserves_hardware(self):
        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        inspection = {
            "instances": [{
                "instance_id": "instance-2",
                "port": 0,
                "healthy": False,
                "token_available": False,
            }],
            "suggested_port": 8768,
            "environment": {"os": {"architecture": "aarch64"}},
        }
        commands = []
        bundle = device_installer._RuntimeBundle(
            path=Path("cached-runtime-bundle.tar.gz"),
            architecture="aarch64",
            python_version="3.11.14",
            runtime_commit="a" * 40,
            core_commit="b" * 40,
        )

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            if "on_output" in kwargs:
                kwargs["on_output"]("__BLACKNODE_RUNTIME_PORT__=8769")
                kwargs["on_output"]("__BLACKNODE_HARDWARE_PRESERVED__=1")
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_inspect_connection", return_value=inspection),
            patch.object(device_installer, "_prepare_runtime_bundle", return_value=bundle),
            patch.object(device_installer, "_upload_sftp_file"),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.install_runtime(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                action="replace_runtime",
                instance_id="instance-2",
            )

        self.assertEqual(result["runtime_port"], 8769)
        self.assertEqual(result["stack_mode"], "isolated")
        self.assertEqual(
            result["hardware_dir"],
            "~/Blacknode/devices/instance-2/hardware",
        )
        self.assertIn("replace_runtime instance-2 8768", commands[0])

    def test_runtime_only_install_records_restricted_compute_stack(self):
        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        bundle = device_installer._RuntimeBundle(
            path=Path("cached-runtime-bundle.tar.gz"),
            architecture="aarch64",
            python_version="3.11.14",
            runtime_commit="a" * 40,
            core_commit="b" * 40,
        )

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            if "on_output" in kwargs:
                kwargs["on_output"]("__BLACKNODE_RUNTIME_PORT__=8766")
                kwargs["on_output"]("__BLACKNODE_FIREWALL_SOURCE__=192.168.1.20")
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(
                device_installer,
                "_inspect_connection",
                return_value={
                    "instances": [],
                    "suggested_port": 8766,
                    "environment": {"os": {"architecture": "aarch64"}},
                },
            ),
            patch.object(device_installer, "_prepare_runtime_bundle", return_value=bundle),
            patch.object(device_installer, "_upload_sftp_file"),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.install_runtime(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                action="runtime_only",
            )

        self.assertEqual(result["stack_mode"], "runtime_only")
        self.assertEqual(result["hardware_dir"], "")
        self.assertEqual(result["firewall_source"], "192.168.1.20")
        self.assertEqual(result["delivery_mode"], "pc_assisted")
        self.assertEqual(result["python_version"], "3.11.14")
        self.assertEqual(
            result["python_dir"],
            "~/Blacknode/devices/default/python",
        )
        self.assertIn("runtime_only default 8766", commands[0])

    def test_default_isolated_stack_uninstall_streams_remote_cleanup_progress(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        inspection = {
            "instances": [{
                "instance_id": "default",
                "port": 8766,
                "healthy": True,
            }],
        }

        def fake_run(_connection, command, **kwargs):
            if "sudo -S -p '' -v" in command:
                kwargs["on_output"](
                    "__BLACKNODE_UNINSTALL_PROGRESS__=60|"
                    "Stopping isolated Robot Hardware services"
                )
            return ""

        progress = []
        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_inspect_connection", return_value=inspection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.uninstall_runtime(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                runtime_port=8766,
                stack_mode="isolated",
                hardware_ports=[8765, 8767],
                progress=progress.append,
            )

        self.assertEqual(result["instance_id"], "default")
        self.assertEqual(result["stack_mode"], "isolated")
        self.assertTrue(any(item["progress"] == 60 for item in progress))
        self.assertEqual(result["hardware_ports"], [8765, 8767])
        self.assertIn('progress 48 "Deleting Robot Hardware services"', uploaded[0])
        self.assertIn('progress 70 "Deleting unused Robot Hardware files"', uploaded[0])
        self.assertIn('Refusing to delete an unrecognized Robot Hardware directory', uploaded[0])
        self.assertNotIn("ssh-password", uploaded[0])

    def test_robot_service_restart_resolves_exact_systemd_unit_by_port(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []

        def fake_run(_connection, command, **_kwargs):
            commands.append(command)
            if command.startswith("bash "):
                return (
                    "__BLACKNODE_HARDWARE_SERVICE__="
                    "blacknode-hardware-follower.service\n"
                    "__BLACKNODE_HARDWARE_STATE__=active\n"
                )
            return ""

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.restart_hardware_service(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                hardware_port=8767,
            )

        self.assertEqual(result, {
            "ok": True,
            "hardware_port": 8767,
            "service_name": "blacknode-hardware-follower.service",
            "action": "restart",
            "state": "active",
        })
        self.assertIn(" 8767 restart", commands[0])
        self.assertIn("systemctl list-unit-files 'blacknode-hardware*.service'", uploaded[0])
        self.assertIn('systemctl "$action" "$service_name"', uploaded[0])
        self.assertNotIn("ssh-password", uploaded[0])

    def test_managed_update_uses_trusted_clean_checkouts_and_returns_versions(self):
        uploaded = []

        class RemoteFile(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                uploaded.append(self.getvalue())
                self.close()
                return False

        class Sftp:
            def file(self, _path, _mode):
                return RemoteFile()

            def chmod(self, _path, _mode):
                return None

            def close(self):
                return None

        connection = SimpleNamespace(
            client=SimpleNamespace(open_sftp=lambda: Sftp()),
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        remote_report = {
            "ok": True,
            "components": [{
                "kind": "runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "before": {"version": "0.3.8", "commit": "111111111111"},
                "after": {"version": "0.3.9", "commit": "222222222222"},
                "changed": True,
                "state": "active",
            }],
        }

        def fake_run(_connection, command, **kwargs):
            commands.append(command)
            if command.startswith("bash "):
                kwargs["on_output"]("__BLACKNODE_UPDATE_PROGRESS__=55|Updating runtime")
                return (
                    "__BLACKNODE_UPDATE_REPORT__="
                    + json.dumps(remote_report, separators=(",", ":"))
                    + "\n"
                )
            return ""

        progress = []
        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.update_managed_services(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                runtime_port=8766,
                hardware_ports=[8767],
                hardware_device_ids={8767: "follower-device"},
                progress=progress.append,
            )

        self.assertEqual(result["components"][0]["after"]["version"], "0.3.9")
        self.assertEqual(result["host_fingerprint"], "SHA256:trusted-device-key")
        self.assertIn(" default 8766 ", commands[0])
        targets = json.loads(base64.urlsafe_b64decode(
            commands[0].split()[-2]
        ).decode("utf-8"))
        self.assertEqual(targets, [{
            "port": 8767,
            "device_id": "follower-device",
        }])
        self.assertEqual(commands[0].split()[-1], "runtime_only")
        self.assertIn("status --porcelain --untracked-files=normal", uploaded[0])
        self.assertIn("merge --ff-only '@{upstream}'", uploaded[0])
        self.assertIn("temiroff/{repository}", uploaded[0])
        self.assertIn('sudo systemctl stop "$unit"', uploaded[0])
        self.assertIn('progress 8 "Resolving selected managed services"', uploaded[0])
        self.assertIn("./install-service.sh --all", uploaded[0])
        self.assertIn('device["service_port"] = int(target["port"])', uploaded[0])
        self.assertIn("stop_verified_manual_hardware", uploaded[0])
        self.assertIn("Refusing to stop unverified process", uploaded[0])
        self.assertIn('active_matches+=("$unit")', uploaded[0])
        self.assertIn('enabled_matches+=("$unit")', uploaded[0])
        self.assertIn('"/etc/systemd/system/$unit"', uploaded[0])
        self.assertIn("Discovered units:", uploaded[0])
        self.assertIn(
            "Repair Hardware did not create exactly one persistent service",
            uploaded[0],
        )
        self.assertNotIn("ssh-password", uploaded[0])
        self.assertTrue(any(item["progress"] == 55 for item in progress))

    def test_managed_update_check_compares_upstream_without_changing_source(self):
        connection = SimpleNamespace(
            fingerprint="SHA256:trusted-device-key",
            close=lambda: None,
        )
        commands = []
        report = {
            "ok": True,
            "components": [{
                "kind": "runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "installed": {"version": "0.3.8", "commit": "111111111111"},
                "latest": {"version": "0.3.9", "commit": "222222222222"},
                "update_available": True,
                "can_update": True,
                "dirty": False,
                "state": "active",
                "error": "",
            }],
        }

        def fake_run(_connection, command, **_kwargs):
            commands.append(command)
            return (
                "__BLACKNODE_UPDATE_CHECK__="
                + json.dumps(report, separators=(",", ":"))
                + "\n"
            )

        with (
            patch.object(device_installer, "_connect", return_value=connection),
            patch.object(device_installer, "_run", side_effect=fake_run),
        ):
            result = device_installer.inspect_managed_service_updates(
                host="192.168.1.87",
                port=22,
                username="robot",
                password="ssh-password",
                host_fingerprint="SHA256:trusted-device-key",
                instance_id="default",
                runtime_port=8766,
                hardware_ports=[8767],
                hardware_device_ids={8767: "follower-device"},
            )

        self.assertTrue(result["components"][0]["update_available"])
        self.assertIn('"git", "ls-remote"', commands[0])
        self.assertIn('"ls-remote", "--symref"', commands[0])
        self.assertIn("temiroff/blacknode-hardware", commands[0])
        self.assertIn('"migration_required": False', commands[0])
        self.assertIn("Migration required:", commands[0])
        self.assertIn(
            'if not request["hardware_targets"] and hardware_dir.is_dir():',
            commands[0],
        )
        self.assertIn('"configured"', commands[0])
        self.assertIn("raw.githubusercontent.com", commands[0])
        self.assertIn('"status", "--porcelain"', commands[0])
        self.assertNotIn('"fetch"', commands[0])
        self.assertNotIn('"merge"', commands[0])
        self.assertIn('states[unit]["active"] == "active"', commands[0])
        self.assertIn('unit_path.read_text(encoding="utf-8")', commands[0])
        self.assertIn("Discovered units:", commands[0])
        self.assertIn(
            'component["latest"]["version"] = component["installed"]["version"]',
            commands[0],
        )
        self.assertIn('"show",', commands[0])
        self.assertIn("Repair Hardware will reconcile", commands[0])
        remote_python = commands[0].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        compile(remote_python, "<managed-update-check>", "exec")

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

    def test_node_defs_discover_profiles_saved_after_package_load(self):
        robots_root = Path(self._tmp.name) / "robots"

        def robot_node(ctx):
            return ctx

        robot_node._bn_inputs = ["profile_id"]
        robot_node._bn_outputs = ["robot"]
        robot_node._bn_input_types = {"profile_id": "Text"}
        robot_node._bn_output_types = {"robot": "Dict"}
        robot_node._bn_input_defaults = {"profile_id": "auto"}
        robot_node._bn_input_choices = {
            "profile_id": ["auto", "so_arm101"],
        }

        with (
            patch.dict(server._NODE_REGISTRY, {"Robot": robot_node}),
            patch.dict(
                os.environ,
                {"BLACKNODE_ROBOTS_DIR": str(robots_root)},
            ),
        ):
            before = self.client.get("/node-defs").json()

            profile_dir = robots_root / "new_workshop_arm"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "id": "new_workshop_arm",
                    "display_name": "New workshop arm",
                    "joints": [{"id": "joint", "servo_id": 1}],
                }),
                encoding="utf-8",
            )

            after = self.client.get("/node-defs").json()

        self.assertNotIn(
            "new_workshop_arm",
            before["Robot"]["input_choices"]["profile_id"],
        )
        self.assertIn(
            "new_workshop_arm",
            after["Robot"]["input_choices"]["profile_id"],
        )
        self.assertNotIn(
            "auto",
            after["Robot"]["input_choices"]["profile_id"],
        )
        self.assertEqual(
            robot_node._bn_input_choices["profile_id"],
            ["auto", "so_arm101"],
        )

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

    def test_managed_device_can_discover_and_pair_hardware_without_exposing_token(self):
        runtime_token = "runtime-pairing-token-1234567890"
        hardware_token = "hardware-pairing-token-1234567890"
        host = server._device_registry.pair_host(
            name="alex-desktop",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime_token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "alex",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "install_root": "~/Blacknode/devices/default",
                "runtime_dir": "~/Blacknode/devices/default/runtime",
                "packages_dir": "~/Blacknode/devices/default/runtime/packages",
                "stack_mode": "isolated",
                "hardware_dir": "~/Blacknode/devices/default/hardware",
            },
        )
        hardware = _HardwareService(
            hardware_token,
            status_overrides={"device_id": "follower-device"},
        )
        discovery = {
            "discovered": 1,
            "errors": [],
            "pairings": [{
                "service_name": "blacknode-hardware-follower.service",
                "port": 8765,
                "name": "Follower arm",
                "device_id": "follower-device",
                "token": hardware_token,
                "active": True,
            }],
        }

        with (
            patch.object(
                server,
                "discover_hardware_pairings",
                return_value=discovery,
            ) as discover,
            patch(
                "device_registry.urllib.request.urlopen",
                side_effect=hardware,
            ),
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/robots/discover",
                json={"password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["robots"][0]["name"], "Follower arm")
        self.assertEqual(
            response.json()["robots"][0]["base_url"],
            "http://192.168.1.87:8765",
        )
        self.assertNotIn(hardware_token, response.text)
        self.assertNotIn("ssh-password", response.text)
        discover.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="alex",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            expected_hardware_dir="~/Blacknode/devices/default/hardware",
        )
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["devices"]["follower-device"]["token"],
            hardware_token,
        )

    def test_robot_discovery_adopts_legacy_default_services_before_pairing(self):
        runtime_token = "runtime-pairing-token-1234567890"
        hardware_token = "hardware-pairing-token-1234567890"
        host = server._device_registry.pair_host(
            name="alex-desktop",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime_token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "alex",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "install_root": "~/Blacknode/devices/default",
                "runtime_dir": "~/Blacknode/devices/default/runtime",
                "packages_dir": "~/Blacknode/devices/default/runtime/packages",
                "stack_mode": "isolated",
                "hardware_dir": "~/Blacknode/devices/default/hardware",
            },
        )
        hardware = _HardwareService(
            hardware_token,
            status_overrides={"device_id": "follower-device"},
        )
        empty_discovery = {
            "discovered": 0,
            "errors": [],
            "pairings": [],
        }
        migrated_discovery = {
            "discovered": 1,
            "errors": [],
            "pairings": [{
                "service_name": "blacknode-hardware-follower.service",
                "port": 8765,
                "name": "Follower arm",
                "device_id": "follower-device",
                "token": hardware_token,
                "active": True,
            }],
        }

        with (
            patch.object(
                server,
                "discover_hardware_pairings",
                side_effect=[empty_discovery, migrated_discovery],
            ) as discover,
            patch.object(
                server,
                "adopt_legacy_hardware_services",
                return_value={"ok": True, "adopted": 1},
            ) as adopt,
            patch(
                "device_registry.urllib.request.urlopen",
                side_effect=hardware,
            ),
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/robots/discover",
                json={"password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["robots"][0]["name"], "Follower arm")
        self.assertIn(
            "Moved 1 existing Robot Hardware service into this device stack.",
            response.json()["summary"],
        )
        self.assertEqual(discover.call_count, 2)
        adopt.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="alex",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            instance_id="default",
        )
        self.assertNotIn(hardware_token, response.text)
        self.assertNotIn("ssh-password", response.text)

    def test_robot_discovery_configures_connected_robots_when_no_services_exist(self):
        runtime_token = "runtime-pairing-token-1234567890"
        hardware_token = "hardware-pairing-token-1234567890"
        host = server._device_registry.pair_host(
            name="alex-desktop",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime_token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "alex",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "install_root": "~/Blacknode/devices/default",
                "runtime_dir": "~/Blacknode/devices/default/runtime",
                "packages_dir": "~/Blacknode/devices/default/runtime/packages",
                "stack_mode": "isolated",
                "hardware_dir": "~/Blacknode/devices/default/hardware",
            },
        )
        hardware = _HardwareService(
            hardware_token,
            status_overrides={"device_id": "follower-device"},
        )
        empty_discovery = {
            "discovered": 0,
            "errors": [],
            "pairings": [],
        }
        configured_discovery = {
            "discovered": 1,
            "errors": [],
            "pairings": [{
                "service_name": "blacknode-hardware-follower.service",
                "port": 8765,
                "name": "Follower arm",
                "device_id": "follower-device",
                "token": hardware_token,
                "active": True,
            }],
        }

        with (
            patch.object(
                server,
                "discover_hardware_pairings",
                side_effect=[empty_discovery, configured_discovery],
            ) as discover,
            patch.object(
                server,
                "adopt_legacy_hardware_services",
                return_value={"ok": True, "adopted": 0},
            ) as adopt,
            patch.object(
                server,
                "configure_hardware_services",
                return_value={"ok": True, "configured": 1},
            ) as configure,
            patch(
                "device_registry.urllib.request.urlopen",
                side_effect=hardware,
            ),
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/robots/discover",
                json={"password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["robots"][0]["name"], "Follower arm")
        self.assertIn(
            "Configured 1 connected robot in this device stack.",
            response.json()["summary"],
        )
        self.assertEqual(discover.call_count, 2)
        adopt.assert_called_once()
        configure.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="alex",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            instance_id="default",
            runtime_port=8766,
        )
        self.assertNotIn(hardware_token, response.text)
        self.assertNotIn("ssh-password", response.text)

    def test_runtime_only_device_can_install_managed_hardware_package(self):
        managed = {
            "ssh_host": "192.168.1.87",
            "ssh_port": 22,
            "ssh_username": "alex",
            "host_fingerprint": "SHA256:trusted-device-key",
            "instance_id": "default",
            "runtime_port": 8766,
            "service_name": "blacknode-runtime.service",
            "install_root": "~/Blacknode/devices/default",
            "runtime_dir": "~/Blacknode/devices/default/runtime",
            "packages_dir": "~/Blacknode/devices/default/runtime/packages",
            "stack_mode": "runtime_only",
            "hardware_dir": "",
        }
        host = {
            "id": "alex-computer",
            "name": "alex-desktop",
            "runtime_url": "http://192.168.1.87:8766",
            "managed_runtime": managed,
            "robots": [],
        }
        installed = {
            "ok": True,
            "instance_id": "default",
            "hardware_dir": "~/Blacknode/devices/default/hardware",
            "stack_mode": "isolated",
        }
        updated_host = {
            **host,
            "managed_runtime": {
                **managed,
                "hardware_dir": installed["hardware_dir"],
                "stack_mode": "isolated",
            },
        }

        with (
            patch.object(
                server._device_registry,
                "get_host_public",
                return_value=host,
            ),
            patch.object(
                server,
                "install_hardware_environment",
                return_value=installed,
            ) as install,
            patch.object(
                server._device_registry,
                "set_host_management",
                return_value=updated_host,
            ) as save,
        ):
            result = server._install_device_host_hardware_payload(
                host["id"],
                server.DiscoverHostRobotsReq(password="ssh-password"),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["device"]["managed_runtime"]["hardware_dir"],
            "~/Blacknode/devices/default/hardware",
        )
        install.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="alex",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            instance_id="default",
            progress=None,
        )
        self.assertEqual(
            save.call_args.args[1]["stack_mode"],
            "isolated",
        )

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
        self.assertEqual(response.json()["runtime"]["state"], "running")
        self.assertTrue(runtime_status.json()["ok"])
        self.assertEqual(runtime_status.json()["state"], "running")
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

    def test_compute_device_is_paired_before_robots_and_keeps_tokens_private(self):
        runtime = _HardwareService("runtime-token")
        robot = _HardwareService(
            "robot-token",
            status_overrides={"device_id": "workshop-arm"},
        )

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return robot(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=route):
            paired_host = self.client.post("/device-hosts", json={
                "name": "Jetson Orin",
                "runtime_url": "http://192.168.1.87:8766",
                "runtime_token": runtime.token,
            })
            host_id = paired_host.json()["device"]["id"]
            paired_robot = self.client.post(
                f"/device-hosts/{host_id}/robots",
                json={
                    "name": "Follower arm",
                    "base_url": "http://192.168.1.87:8765",
                    "token": robot.token,
                },
            )
            listed = self.client.get("/device-hosts")

        self.assertEqual(paired_host.status_code, 200)
        self.assertEqual(paired_host.json()["device"]["robots"], [])
        self.assertEqual(paired_host.json()["runtime"]["state"], "running")
        self.assertNotIn(runtime.token, paired_host.text)
        self.assertEqual(paired_robot.status_code, 200)
        self.assertEqual(paired_robot.json()["robot"]["host_id"], host_id)
        self.assertNotIn(robot.token, paired_robot.text)
        self.assertEqual(len(listed.json()["devices"]), 1)
        host = listed.json()["devices"][0]
        self.assertEqual(host["name"], "Jetson Orin")
        self.assertEqual(host["robots"][0]["name"], "Follower arm")
        self.assertNotIn(runtime.token, listed.text)
        self.assertNotIn(robot.token, listed.text)

        legacy_robots = self.client.get("/devices").json()["devices"]
        self.assertEqual([item["id"] for item in legacy_robots], ["workshop-arm"])
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 2)
        self.assertEqual(saved["hosts"][host_id]["runtime_token"], runtime.token)
        self.assertEqual(saved["devices"]["workshop-arm"]["token"], robot.token)

    def test_local_compute_device_pairs_over_loopback_without_ssh_management(self):
        runtime = _HardwareService("local-runtime-token")

        with patch("device_registry.urllib.request.urlopen", side_effect=runtime):
            paired = self.client.post("/device-hosts", json={
                "name": "Local computer",
                "runtime_url": "http://127.0.0.1:8766",
                "runtime_token": runtime.token,
            })
            listed = self.client.get("/device-hosts")

        self.assertEqual(paired.status_code, 200)
        device = paired.json()["device"]
        self.assertEqual(device["name"], "Local computer")
        self.assertEqual(device["runtime_url"], "http://127.0.0.1:8766")
        self.assertNotIn("managed_runtime", device)
        self.assertNotIn(runtime.token, paired.text)
        self.assertEqual(
            listed.json()["devices"][0]["runtime_url"],
            "http://127.0.0.1:8766",
        )
        self.assertNotIn(runtime.token, listed.text)
        manifest_requests = [
            request for request in runtime.requests if request[1] == "/manifest"
        ]
        self.assertTrue(manifest_requests)
        self.assertTrue(all(
            authorization == f"Bearer {runtime.token}"
            for _method, _path, authorization, _body in manifest_requests
        ))

    def test_local_compute_device_install_stream_configures_complete_stack(self):
        install_result = {
            "ok": True,
            "runtime_token": "generated-local-runtime-token-" + "x" * 24,
            "runtime_url": "http://127.0.0.1:8766",
            "manifest": {
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "workstation-local",
                "runtime_version": "0.3.10",
            },
            "runtime_port": 8766,
            "runtime_dir": r"E:\Blacknode\blacknode-runtime",
            "service_name": "blacknode-runtime-local-process",
            "instance_id": "local",
            "stack_mode": "runtime_only",
            "hardware_dir": r"E:\Blacknode\blacknode-robot",
            "hardware_port": 8765,
            "hardware_service_name": "blacknode-hardware-local-awaiting-device",
            "hardware_state": "awaiting_device",
            "hardware_configured": False,
            "hardware_pid_file": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\hardware.pid",
            "hardware_token_file": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\auth.token",
            "hardware_log_path": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\hardware.log",
            "hardware_owned_install": True,
            "management_mode": "local",
            "config_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.json",
            "pid_file": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.pid",
            "log_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.log",
            "owned_install": True,
            "elapsed_seconds": 8.2,
        }

        def install(**kwargs):
            kwargs["progress"]({
                "progress": 82,
                "message": "Starting the local Runtime",
            })
            return install_result

        with patch.object(server, "install_local_runtime", side_effect=install) as local_install:
            response = self.client.post(
                "/device-hosts/local-install-stream",
                json={
                    "name": "Local computer",
                    "install_dir": r"E:\Blacknode",
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line]
        self.assertTrue(any(
            event.get("progress") == 82
            and event.get("message") == "Starting the local Runtime"
            for event in events
        ))
        self.assertEqual(events[-1]["type"], "done")
        device = events[-1]["result"]["device"]
        self.assertEqual(device["runtime_url"], "http://127.0.0.1:8766")
        self.assertEqual(device["managed_runtime"]["management_mode"], "local")
        self.assertEqual(
            device["managed_runtime"]["runtime_dir"],
            r"E:\Blacknode\blacknode-runtime",
        )
        self.assertEqual(
            device["managed_runtime"]["hardware_dir"],
            r"E:\Blacknode\blacknode-robot",
        )
        self.assertEqual(device["managed_runtime"]["hardware_port"], 8765)
        self.assertEqual(
            device["managed_runtime"]["hardware_state"],
            "awaiting_device",
        )
        self.assertNotIn(install_result["runtime_token"], response.text)
        local_install.assert_called_once()
        self.assertEqual(
            local_install.call_args.kwargs["install_dir"],
            r"E:\Blacknode",
        )

    def test_local_uninstall_removes_read_only_git_pack_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "blacknode-runtime"
            pack_dir = checkout / ".git" / "objects" / "pack"
            pack_dir.mkdir(parents=True)
            pack_file = pack_dir / "pack-test.idx"
            pack_file.write_bytes(b"git index")
            os.chmod(pack_file, stat.S_IREAD)

            local_runtime._remove_tree(checkout)

            self.assertFalse(checkout.exists())

    def test_windows_background_services_use_pythonw(self):
        with tempfile.TemporaryDirectory() as temporary:
            scripts = Path(temporary) / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            python = scripts / "python.exe"
            pythonw = scripts / "pythonw.exe"
            python.touch()
            pythonw.touch()

            with patch.object(local_runtime.os, "name", "nt"):
                selected = local_runtime._background_python(python)

            self.assertEqual(selected, pythonw)

    def test_local_package_inspection_does_not_start_stopped_services(self):
        with tempfile.TemporaryDirectory() as temporary:
            stack = Path(temporary)
            runtime_dir = stack / "blacknode-runtime"
            hardware_dir = stack / "blacknode-robot"
            (runtime_dir / "scripts").mkdir(parents=True)
            (hardware_dir / "scripts").mkdir(parents=True)
            (runtime_dir / "scripts" / "runtime_service.py").write_text(
                "# runtime\n",
                encoding="utf-8",
            )
            (hardware_dir / "scripts" / "hardware_service.py").write_text(
                "# hardware\n",
                encoding="utf-8",
            )
            (runtime_dir / "pyproject.toml").write_text(
                '[project]\nname = "blacknode-runtime"\nversion = "0.3.9"\n',
                encoding="utf-8",
            )
            (hardware_dir / "pyproject.toml").write_text(
                '[project]\nname = "blacknode-robot"\nversion = "0.4.0"\n',
                encoding="utf-8",
            )
            runtime_state = runtime_dir / ".blacknode-runtime"
            hardware_state = hardware_dir / ".blacknode-hardware"
            runtime_state.mkdir()
            hardware_state.mkdir()
            managed = {
                "runtime_dir": str(runtime_dir),
                "runtime_port": 8766,
                "config_path": str(runtime_state / "runtime.json"),
                "pid_file": str(runtime_state / "runtime.pid"),
                "hardware_dir": str(hardware_dir),
                "hardware_port": 8765,
                "hardware_token_file": str(hardware_state / "auth.token"),
                "hardware_pid_file": str(hardware_state / "hardware.pid"),
            }
            with (
                patch.object(local_runtime, "_spawn_runtime") as spawn_runtime,
                patch.object(local_runtime, "_spawn_hardware") as spawn_hardware,
            ):
                runtime_report = local_runtime.inspect_local_runtime(managed)
                hardware_report = local_runtime.inspect_local_hardware(managed)

            self.assertEqual(runtime_report["state"], "stopped")
            self.assertEqual(runtime_report["installed_version"], "0.3.9")
            self.assertEqual(hardware_report["state"], "stopped")
            self.assertEqual(hardware_report["installed_version"], "0.4.0")
            spawn_runtime.assert_not_called()
            spawn_hardware.assert_not_called()

    def test_local_runtime_status_reports_unattached_managed_hardware_service(self):
        runtime = _HardwareService("local-runtime-token")
        host = server._device_registry.pair_host(
            name="Local computer",
            runtime_url="http://127.0.0.1:8766",
            runtime_token=runtime.token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "workstation-local",
            },
            managed_runtime={
                "management_mode": "local",
                "instance_id": "local",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime-local-process",
                "runtime_dir": r"E:\Blacknode\blacknode-runtime",
                "stack_mode": "runtime_only",
                "hardware_dir": r"E:\Blacknode\blacknode-robot",
                "hardware_port": 8765,
                "hardware_service_name": "blacknode-hardware-local-awaiting-device",
                "hardware_state": "awaiting_device",
                "hardware_configured": False,
                "hardware_pid_file": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\hardware.pid",
                "hardware_token_file": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\auth.token",
                "hardware_log_path": r"E:\Blacknode\blacknode-robot\.blacknode-hardware\hardware.log",
                "hardware_owned_install": True,
                "config_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.json",
                "pid_file": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.pid",
                "log_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.log",
                "owned_install": True,
            },
        )
        safe_status = {
            "device_id": "workstation-hardware-awaiting-device",
            "software_version": "0.2.0",
            "connected": False,
            "armed": False,
        }
        with (
            patch.object(
                server,
                "inspect_local_hardware",
                return_value={
                    "ok": True,
                    "kind": "hardware",
                    "state": "running",
                    "installed": True,
                    "installed_version": "0.2.0",
                    "service_url": "http://127.0.0.1:8765",
                    "service_name": "blacknode-hardware-local-awaiting-device",
                    "status": safe_status,
                },
            ) as inspect_hardware,
            patch.object(
                server,
                "inspect_local_runtime",
                return_value={
                    "ok": True,
                    "kind": "runtime",
                    "state": "running",
                    "installed": True,
                    "installed_version": "0.3.10",
                    "manifest": {
                        "service": "blacknode-runtime",
                        "protocol_version": 1,
                        "runtime_version": "0.3.10",
                    },
                },
            ) as inspect_runtime,
            patch.object(server, "ensure_local_runtime") as ensure_runtime,
        ):
            response = self.client.get(
                f"/device-hosts/{host['id']}/runtime-status",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["hardware"], {
            "ok": True,
            "kind": "hardware",
            "installed": True,
            "installed_version": "0.2.0",
            "service_url": "http://127.0.0.1:8765",
            "service_name": "blacknode-hardware-local-awaiting-device",
            "state": "running",
            "status": safe_status,
        })
        self.assertTrue(inspect_hardware.called)
        self.assertTrue(inspect_runtime.called)
        ensure_runtime.assert_not_called()

    def test_local_package_version_check_needs_no_ssh_and_keeps_services_stopped(self):
        managed = {
            "management_mode": "local",
            "runtime_dir": r"E:\Blacknode\blacknode-runtime",
            "hardware_dir": r"E:\Blacknode\blacknode-robot",
        }
        host = {
            "id": "local-computer",
            "name": "Local computer",
            "managed_runtime": managed,
            "robots": [],
        }
        checked = {
            "ok": True,
            "components": [
                {
                    "kind": "runtime",
                    "installed": {"version": "0.3.9", "commit": "aaa"},
                    "latest": {"version": "0.3.10", "commit": "bbb"},
                    "update_available": True,
                    "error": "",
                    "state": "stopped",
                },
                {
                    "kind": "hardware",
                    "installed": {"version": "0.1.1", "commit": "ccc"},
                    "latest": {"version": "0.1.1", "commit": "ccc"},
                    "update_available": False,
                    "error": "",
                    "state": "stopped",
                },
            ],
        }
        with (
            patch.object(server._device_registry, "get_host_public", return_value=host),
            patch.object(
                server,
                "inspect_local_package_updates",
                return_value=checked,
            ) as inspect,
            patch.object(server, "ensure_local_runtime") as ensure,
        ):
            result = server._check_device_host_updates_payload(
                host["id"],
                server.UpdateManagedDeviceReq(password=""),
            )

        self.assertTrue(result["ok"])
        self.assertIn("1 of 2 packages", result["summary"])
        inspect.assert_called_once()
        ensure.assert_not_called()

    def test_local_package_restart_stops_and_starts_only_selected_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            stack = Path(temporary)
            runtime_dir = stack / "blacknode-runtime"
            hardware_dir = stack / "blacknode-robot"
            (runtime_dir / "scripts").mkdir(parents=True)
            (hardware_dir / "scripts").mkdir(parents=True)
            (runtime_dir / "scripts" / "runtime_service.py").write_text(
                "# runtime\n",
                encoding="utf-8",
            )
            (hardware_dir / "scripts" / "hardware_service.py").write_text(
                "# hardware\n",
                encoding="utf-8",
            )
            (runtime_dir / "pyproject.toml").write_text(
                '[project]\nname = "blacknode-runtime"\nversion = "0.3.9"\n',
                encoding="utf-8",
            )
            (hardware_dir / "pyproject.toml").write_text(
                '[project]\nname = "blacknode-robot"\nversion = "0.4.0"\n',
                encoding="utf-8",
            )
            managed = {
                "runtime_dir": str(runtime_dir),
                "hardware_dir": str(hardware_dir),
            }
            with (
                patch.object(
                    local_runtime,
                    "inspect_local_runtime",
                    return_value={"state": "running"},
                ),
                patch.object(
                    local_runtime,
                    "inspect_local_hardware",
                    return_value={"state": "running"},
                ),
                patch.object(
                    local_runtime,
                    "stop_local_runtime",
                    return_value={"state": "inactive"},
                ) as stop_runtime,
                patch.object(
                    local_runtime,
                    "ensure_local_runtime",
                    return_value={"state": "active"},
                ) as start_runtime,
                patch.object(
                    local_runtime,
                    "stop_local_hardware",
                    return_value={"state": "inactive"},
                ) as stop_hardware,
                patch.object(
                    local_runtime,
                    "ensure_local_hardware",
                    return_value={"state": "active"},
                ) as start_hardware,
            ):
                runtime_result = local_runtime.manage_local_package(
                    managed,
                    kind="runtime",
                    action="restart",
                    core_root=stack,
                )
                self.assertTrue(runtime_result["restarted"])
                stop_runtime.assert_called_once()
                start_runtime.assert_called_once()
                stop_hardware.assert_not_called()
                start_hardware.assert_not_called()

                stop_runtime.reset_mock()
                start_runtime.reset_mock()
                hardware_result = local_runtime.manage_local_package(
                    managed,
                    kind="hardware",
                    action="restart",
                    core_root=stack,
                )
                self.assertTrue(hardware_result["restarted"])
                stop_hardware.assert_called_once()
                start_hardware.assert_called_once()
                stop_runtime.assert_not_called()
                start_runtime.assert_not_called()

    def test_local_package_action_is_independent_and_needs_no_ssh(self):
        managed = {
            "management_mode": "local",
            "runtime_dir": r"E:\Blacknode\blacknode-runtime",
            "hardware_dir": r"E:\Blacknode\blacknode-robot",
        }
        host = {
            "id": "local-computer",
            "name": "Local computer",
            "managed_runtime": managed,
            "robots": [],
        }
        with (
            patch.object(server._device_registry, "get_host_public", return_value=host),
            patch.object(
                server,
                "manage_local_package",
                return_value={"ok": True, "kind": "hardware", "action": "restart"},
            ) as manage,
            patch.object(
                server,
                "_device_host_runtime_status",
                return_value={"ok": True, "runtime_url": "http://127.0.0.1:8766"},
            ),
        ):
            result = server._manage_local_package_payload(
                host["id"],
                "hardware",
                server.LocalPackageActionReq(action="restart"),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "hardware")
        self.assertEqual(manage.call_args.kwargs["kind"], "hardware")
        self.assertEqual(manage.call_args.kwargs["action"], "restart")

    def test_remote_hardware_package_stop_controls_exact_robot_services(self):
        managed = {
            "ssh_host": "192.168.1.87",
            "ssh_port": 22,
            "ssh_username": "robot",
            "host_fingerprint": "SHA256:trusted-device-key",
            "instance_id": "default",
            "runtime_port": 8766,
            "service_name": "blacknode-runtime.service",
            "install_root": "~/Blacknode/devices/default",
            "runtime_dir": "~/Blacknode/devices/default/runtime",
            "packages_dir": "~/Blacknode/devices/default/runtime/packages",
        }
        host = {
            "id": "robot-computer",
            "name": "Robot computer",
            "managed_runtime": managed,
            "robots": [{
                "id": "follower",
                "name": "Follower",
                "base_url": "http://192.168.1.87:8767",
            }],
        }
        with (
            patch.object(server._device_registry, "get_host_public", return_value=host),
            patch.object(server, "_control_robot_lifecycle_payload") as safe_stop,
            patch.object(server, "restart_hardware_service", return_value={
                "ok": True,
                "hardware_port": 8767,
                "service_name": "blacknode-hardware-follower.service",
                "action": "stop",
                "state": "inactive",
            }) as control_service,
            patch.object(server._device_registry, "set_device_paused") as set_paused,
            patch.object(server._device_registry, "set_host_management", return_value=host) as set_management,
        ):
            result = server._manage_remote_hardware_package_payload(
                host["id"],
                server.RemoteHardwarePackageActionReq(
                    action="stop",
                    password="ssh-password",
                ),
            )

        self.assertEqual(result["state"], "stopped")
        safe_stop.assert_called_once()
        self.assertEqual(control_service.call_args.kwargs["hardware_port"], 8767)
        self.assertEqual(control_service.call_args.kwargs["action"], "stop")
        set_paused.assert_called_once_with("follower", True)
        self.assertEqual(
            set_management.call_args.args[1]["hardware_state"],
            "stopped",
        )

    def test_local_compute_device_pause_resume_and_uninstall_use_local_process(self):
        token = "generated-local-runtime-token-" + "x" * 24
        host = server._device_registry.pair_host(
            name="Local computer",
            runtime_url="http://127.0.0.1:8766",
            runtime_token=token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "workstation-local",
            },
            managed_runtime={
                "management_mode": "local",
                "instance_id": "local",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime-local-process",
                "runtime_dir": r"E:\Blacknode\blacknode-runtime",
                "stack_mode": "runtime_only",
                "hardware_dir": "",
                "config_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.json",
                "pid_file": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.pid",
                "log_path": r"E:\Blacknode\blacknode-runtime\.blacknode-runtime\runtime.log",
                "owned_install": True,
            },
        )
        paused = {
            "ok": True,
            "action": "pause",
            "state": "inactive",
            "service_name": "blacknode-runtime-local-process",
        }
        resumed = {
            "ok": True,
            "action": "resume",
            "state": "active",
            "service_name": "blacknode-runtime-local-process",
        }
        with (
            patch.object(
                server._device_registry,
                "host_client",
                return_value=SimpleNamespace(list_deployments=lambda: {"deployments": []}),
            ),
            patch.object(server, "stop_local_runtime", return_value=paused) as stop,
        ):
            pause_response = self.client.post(
                f"/device-hosts/{host['id']}/lifecycle-stream",
                json={"action": "pause", "password": ""},
            )
        self.assertEqual(pause_response.status_code, 200)
        self.assertTrue(stop.called)

        with patch.object(server, "ensure_local_runtime", return_value=resumed) as start:
            resume_response = self.client.post(
                f"/device-hosts/{host['id']}/lifecycle-stream",
                json={"action": "resume", "password": ""},
            )
        self.assertEqual(resume_response.status_code, 200)
        self.assertTrue(start.called)

        uninstall_result = {
            "ok": True,
            "instance_id": "local",
            "runtime_port": 8766,
            "already_absent": False,
            "stack_mode": "runtime_only",
            "source_preserved": False,
        }
        with patch.object(
            server,
            "uninstall_local_runtime",
            return_value=uninstall_result,
        ) as uninstall:
            uninstall_response = self.client.post(
                f"/device-hosts/{host['id']}/uninstall-stream",
                json={"password": ""},
            )
        self.assertEqual(uninstall_response.status_code, 200)
        uninstall_events = [
            json.loads(line)
            for line in uninstall_response.text.splitlines()
            if line
        ]
        self.assertEqual(
            uninstall_events[-1]["result"]["summary"],
            "Local Runtime installation deleted",
        )
        self.assertTrue(uninstall.called)
        self.assertEqual(self.client.get("/device-hosts").json()["devices"], [])

    def test_existing_robot_pairings_are_grouped_into_compute_devices(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            robot = self.client.post("/devices", json={
                "name": "Existing arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]

        listed = self.client.get("/device-hosts")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["devices"]), 1)
        host = listed.json()["devices"][0]
        self.assertEqual(host["runtime_url"], "http://192.168.1.87:8766")
        self.assertEqual(host["robots"][0]["id"], robot["id"])
        self.assertEqual(host["robots"][0]["host_id"], host["id"])

    def test_automatic_install_requires_fingerprint_and_does_not_return_password_or_token(self):
        runtime = _HardwareService("generated-runtime-token")
        install_result = {
            "ok": True,
            "runtime_token": runtime.token,
            "host_fingerprint": "SHA256:trusted-device-key",
            "elapsed_seconds": 12.3,
            "action": "runtime_only",
            "instance_id": "default",
            "runtime_port": 8766,
            "service_name": "blacknode-runtime.service",
            "install_root": "~/Blacknode/devices/default",
            "runtime_dir": "~/Blacknode/devices/default/runtime",
            "packages_dir": "~/Blacknode/devices/default/runtime/packages",
            "firewall_source": "192.168.1.20",
            "delivery_mode": "pc_assisted",
            "core_dir": "~/Blacknode/devices/default/core",
            "python_dir": "~/Blacknode/devices/default/python",
            "python_version": "3.11.15",
            "stack_mode": "runtime_only",
            "hardware_dir": "",
        }
        with (
            patch.object(server, "install_runtime", return_value=install_result) as install,
            patch("device_registry.urllib.request.urlopen", side_effect=runtime),
        ):
            response = self.client.post("/device-hosts/install", json={
                "name": "Robot computer",
                "host": "192.168.1.87",
                "port": 22,
                "username": "robot",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
            })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["runtime"]["ok"])
        self.assertEqual(
            response.json()["install"]["host_fingerprint"],
            "SHA256:trusted-device-key",
        )
        self.assertNotIn("runtime_token", response.json()["install"])
        self.assertNotIn("ssh-password", response.text)
        self.assertNotIn(runtime.token, response.text)
        managed = response.json()["device"]["managed_runtime"]
        self.assertEqual(managed["instance_id"], "default")
        self.assertEqual(managed["runtime_port"], 8766)
        self.assertEqual(
            managed["install_root"],
            "~/Blacknode/devices/default",
        )
        self.assertEqual(
            managed["packages_dir"],
            "~/Blacknode/devices/default/runtime/packages",
        )
        self.assertEqual(managed["firewall_source"], "192.168.1.20")
        self.assertEqual(managed["delivery_mode"], "pc_assisted")
        self.assertEqual(managed["core_dir"], "~/Blacknode/devices/default/core")
        self.assertEqual(managed["python_dir"], "~/Blacknode/devices/default/python")
        self.assertEqual(managed["python_version"], "3.11.15")
        self.assertEqual(managed["stack_mode"], "runtime_only")
        self.assertEqual(managed["hardware_dir"], "")
        self.assertEqual(install.call_args.kwargs["action"], "runtime_only")

    def test_automatic_install_stream_reports_progress_and_finishes_pairing(self):
        runtime = _HardwareService("generated-runtime-token")
        install_result = {
            "ok": True,
            "runtime_token": runtime.token,
            "host_fingerprint": "SHA256:trusted-device-key",
            "elapsed_seconds": 12.3,
            "action": "side_by_side",
            "instance_id": "instance-2",
            "runtime_port": 8767,
            "service_name": "blacknode-runtime-instance-2.service",
            "runtime_dir": "~/blacknode-runtimes/instance-2",
        }

        def fake_install_runtime(**kwargs):
            kwargs["progress"]({
                "progress": 48,
                "message": "Downloading Blacknode Runtime",
            })
            return install_result

        with (
            patch.object(server, "install_runtime", side_effect=fake_install_runtime),
            patch("device_registry.urllib.request.urlopen", side_effect=runtime),
        ):
            response = self.client.post("/device-hosts/install-stream", json={
                "name": "Independent runtime",
                "host": "192.168.1.87",
                "port": 22,
                "username": "robot",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
                "action": "side_by_side",
                "instance_id": "instance-2",
            })

        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0], {
            "type": "progress",
            "progress": 48,
            "message": "Downloading Blacknode Runtime",
        })
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["result"]["device"]["managed_runtime"]["instance_id"], "instance-2")
        self.assertNotIn("ssh-password", response.text)
        self.assertNotIn(runtime.token, response.text)

    def test_automatic_isolated_stack_records_separate_hardware_installation(self):
        runtime = _HardwareService("isolated-runtime-token")
        install_result = {
            "ok": True,
            "runtime_token": runtime.token,
            "host_fingerprint": "SHA256:trusted-device-key",
            "elapsed_seconds": 20.0,
            "action": "isolated_stack",
            "instance_id": "instance-2",
            "runtime_port": 8768,
            "service_name": "blacknode-runtime-instance-2.service",
            "runtime_dir": "~/blacknode-runtimes/instance-2",
            "stack_mode": "isolated",
            "hardware_dir": "~/blacknode-hardware-instances/instance-2",
        }
        with (
            patch.object(server, "install_runtime", return_value=install_result),
            patch("device_registry.urllib.request.urlopen", side_effect=runtime),
        ):
            response = self.client.post("/device-hosts/install", json={
                "name": "Isolated robot stack",
                "host": "192.168.1.87",
                "port": 22,
                "username": "robot",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
                "action": "isolated_stack",
                "instance_id": "instance-2",
            })

        self.assertEqual(response.status_code, 200)
        managed = response.json()["device"]["managed_runtime"]
        self.assertEqual(managed["stack_mode"], "isolated")
        self.assertEqual(
            managed["hardware_dir"],
            "~/blacknode-hardware-instances/instance-2",
        )
        self.assertEqual(response.json()["device"]["robots"], [])
        self.assertNotIn(runtime.token, response.text)
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        saved_management = next(iter(saved["hosts"].values()))["managed_runtime"]
        self.assertEqual(saved_management["stack_mode"], "isolated")

    def test_ssh_inspection_reports_existing_instances_without_credentials(self):
        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "instances": [{
                "instance_id": "default",
                "runtime_dir": "/home/robot/blacknode-runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "repository": True,
                "configured": True,
                "service_installed": True,
                "running": True,
                "healthy": True,
                "token_available": True,
                "runtime_version": "0.3.0",
                "device_id": "robot-computer",
                "error": "",
            }],
            "environment": {
                "policy": "preserve",
                "os": {
                    "name": "Ubuntu 24.04.2 LTS",
                    "version": "24.04",
                    "architecture": "aarch64",
                },
                "python": {
                    "version": "3.12.3",
                    "executable": "/usr/bin/python3",
                },
                "nvidia": {
                    "available": True,
                    "gpus": ["NVIDIA Jetson GPU"],
                    "driver_version": "550.54",
                    "driver_cuda_version": "12.4",
                    "cuda_toolkit_version": "12.6",
                    "nvidia_smi": True,
                    "nvcc": True,
                    "preserved": True,
                },
                "ros2": {
                    "available": True,
                    "distributions": ["jazzy"],
                    "selected_distribution": "jazzy",
                    "ros2_on_path": False,
                    "preserved": True,
                },
                "docker": {
                    "available": True,
                    "client_version": "27.5.1",
                    "server_version": "27.5.1",
                    "daemon_running": False,
                    "service_enabled": False,
                    "preserved": True,
                },
                "runtime_setup_packages": ["git", "python3-pip", "python3-venv"],
            },
            "suggested_port": 8767,
            "suggested_instance_id": "instance-2",
        }
        with patch.object(server, "inspect_runtime", return_value=inspection) as inspect:
            response = self.client.post("/device-hosts/inspect", json={
                "host": "192.168.1.87",
                "port": 22,
                "username": "robot",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["instances"][0]["port"], 8766)
        self.assertEqual(response.json()["suggested_port"], 8767)
        self.assertEqual(
            response.json()["environment"]["nvidia"]["cuda_toolkit_version"],
            "12.6",
        )
        self.assertFalse(response.json()["environment"]["docker"]["daemon_running"])
        self.assertNotIn("ssh-password", response.text)
        inspect.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="robot",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
        )

    def test_ssh_inspection_classifies_live_ros_graph_without_installing(self):
        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "instances": [],
            "environment": {
                "policy": "preserve",
                "ros2": {
                    "available": True,
                    "distributions": ["humble"],
                    "selected_distribution": "humble",
                    "ros2_on_path": False,
                    "preserved": True,
                },
            },
            "ros2_graph": {
                "available": True,
                "state": "available",
                "distribution": "humble",
                "domain_id": "0",
                "read_only": True,
                "daemon_used": False,
                "topics": [
                    "/scan [sensor_msgs/msg/LaserScan]",
                    "/odom [nav_msgs/msg/Odometry]",
                    "/controller/cmd_vel [geometry_msgs/msg/Twist]",
                ],
                "nodes": ["/controller"],
                "services": ["/controller/get_parameters"],
                "errors": [],
            },
            "suggested_port": 8766,
            "suggested_instance_id": "instance-2",
        }
        received = []

        def classify(ctx):
            received.append(ctx)
            return {
                "found": True,
                "capabilities": [{
                    "kind": "blacknode.robot-capability-candidate",
                    "schema_version": 1,
                    "capability": "mobile_base",
                    "confidence": "high",
                    "score": 95,
                    "state_topics": ["/odom"],
                    "command_topics": ["/controller/cmd_vel"],
                    "safe_to_read": True,
                    "requires_confirmation": True,
                    "evidence": [],
                }],
                "unclassified": [],
                "inventory": {
                    "topics": inspection["ros2_graph"]["topics"],
                    "nodes": ["/controller"],
                    "services": ["/controller/get_parameters"],
                },
                "report": "Generic ROS 2 capability discovery",
            }

        with (
            patch.object(server, "inspect_runtime", return_value=inspection),
            patch.dict(
                server._NODE_REGISTRY,
                {"RobotROSCapabilityDiscover": classify},
            ),
        ):
            response = self.client.post("/device-hosts/inspect", json={
                "host": "192.168.55.1",
                "port": 22,
                "username": "ubuntu",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
            })

        self.assertEqual(response.status_code, 200)
        graph = response.json()["ros2_graph"]
        self.assertTrue(graph["read_only"])
        self.assertFalse(graph["daemon_used"])
        self.assertEqual(graph["capabilities"][0]["capability"], "mobile_base")
        self.assertTrue(graph["capabilities"][0]["requires_confirmation"])
        self.assertEqual(received[0]["nodes"], ["/controller"])
        self.assertNotIn("ssh-password", response.text)

    def test_manual_device_can_enable_ssh_management_after_pairing(self):
        runtime = _HardwareService("runtime-token")
        with patch("device_registry.urllib.request.urlopen", side_effect=runtime):
            paired = self.client.post("/device-hosts", json={
                "name": "Manually paired computer",
                "runtime_url": "http://192.168.1.87:8766",
                "runtime_token": runtime.token,
            }).json()["device"]

        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "instances": [{
                "instance_id": "default",
                "runtime_dir": "/home/robot/blacknode-runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "service_installed": True,
                "running": True,
                "healthy": True,
                "device_id": "alex-desktop",
            }],
        }
        with patch.object(
            server,
            "inspect_runtime",
            return_value=inspection,
        ) as inspect:
            response = self.client.post(
                f"/device-hosts/{paired['id']}/management",
                json={
                    "host": "192.168.1.87",
                    "port": 22,
                    "username": "robot",
                    "password": "ssh-password",
                    "host_fingerprint": "SHA256:trusted-device-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        managed = response.json()["device"]["managed_runtime"]
        self.assertEqual(managed["instance_id"], "default")
        self.assertEqual(managed["runtime_port"], 8766)
        self.assertEqual(managed["service_name"], "blacknode-runtime.service")
        self.assertEqual(managed["ssh_username"], "robot")
        self.assertNotIn("ssh-password", response.text)
        inspect.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="robot",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
        )

        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        saved_host = saved["hosts"][paired["id"]]
        self.assertEqual(
            saved_host["managed_runtime"]["host_fingerprint"],
            "SHA256:trusted-device-key",
        )
        self.assertNotIn("password", json.dumps(saved_host).lower())

    def test_ssh_management_recovers_identity_for_a_legacy_paired_runtime(self):
        runtime = _HardwareService("runtime-token")
        with patch("device_registry.urllib.request.urlopen", side_effect=runtime):
            paired = self.client.post("/device-hosts", json={
                "name": "Legacy paired computer",
                "runtime_url": "http://192.168.1.87:8766",
                "runtime_token": runtime.token,
            }).json()["device"]

        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        saved["hosts"][paired["id"]]["remote_device_id"] = ""
        self.registry_path.write_text(json.dumps(saved), encoding="utf-8")
        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "instances": [{
                "instance_id": "default",
                "runtime_dir": "/home/robot/blacknode-runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "service_installed": True,
                "running": True,
                "healthy": True,
                "device_id": "alex-desktop",
            }],
        }

        with (
            patch.object(server, "inspect_runtime", return_value=inspection),
            patch("device_registry.urllib.request.urlopen", side_effect=runtime),
        ):
            response = self.client.post(
                f"/device-hosts/{paired['id']}/management",
                json={
                    "host": "192.168.1.87",
                    "port": 22,
                    "username": "robot",
                    "password": "ssh-password",
                    "host_fingerprint": "SHA256:trusted-device-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        updated = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            updated["hosts"][paired["id"]]["remote_device_id"],
            "alex-desktop",
        )

    def test_ssh_management_rejects_a_different_runtime_identity(self):
        runtime = _HardwareService("runtime-token")
        with patch("device_registry.urllib.request.urlopen", side_effect=runtime):
            paired = self.client.post("/device-hosts", json={
                "name": "Manually paired computer",
                "runtime_url": "http://192.168.1.87:8766",
                "runtime_token": runtime.token,
            }).json()["device"]

        inspection = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "instances": [{
                "instance_id": "default",
                "runtime_dir": "/home/robot/blacknode-runtime",
                "service_name": "blacknode-runtime.service",
                "port": 8766,
                "service_installed": True,
                "running": True,
                "healthy": True,
                "device_id": "different-computer",
            }],
        }
        with patch.object(server, "inspect_runtime", return_value=inspection):
            response = self.client.post(
                f"/device-hosts/{paired['id']}/management",
                json={
                    "host": "192.168.1.99",
                    "port": 22,
                    "username": "robot",
                    "password": "ssh-password",
                    "host_fingerprint": "SHA256:trusted-device-key",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("no installed Blacknode runtime service", response.text)
        listed = self.client.get("/device-hosts").json()["devices"][0]
        self.assertNotIn("managed_runtime", listed)
        self.assertNotIn("ssh-password", response.text)

    def test_managed_runtime_uninstall_removes_only_selected_registry_tree(self):
        runtime = _HardwareService("generated-runtime-token")
        install_result = {
            "ok": True,
            "runtime_token": runtime.token,
            "host_fingerprint": "SHA256:trusted-device-key",
            "elapsed_seconds": 12.3,
            "action": "side_by_side",
            "instance_id": "instance-2",
            "runtime_port": 8767,
            "service_name": "blacknode-runtime-instance-2.service",
            "runtime_dir": "~/blacknode-runtimes/instance-2",
        }
        with (
            patch.object(server, "install_runtime", return_value=install_result),
            patch("device_registry.urllib.request.urlopen", side_effect=runtime),
        ):
            installed = self.client.post("/device-hosts/install", json={
                "name": "Independent runtime",
                "host": "192.168.1.87",
                "port": 22,
                "username": "robot",
                "password": "ssh-password",
                "host_fingerprint": "SHA256:trusted-device-key",
                "action": "side_by_side",
                "instance_id": "instance-2",
            })
        host_id = installed.json()["device"]["id"]
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            attached = self.client.post(
                f"/device-hosts/{host_id}/robots",
                json={
                    "name": "Follower",
                    "base_url": "http://192.168.1.87:8765",
                    "token": hardware.token,
                },
            )
        self.assertEqual(attached.status_code, 200)
        with patch.object(server, "uninstall_runtime", return_value={
            "ok": True,
            "instance_id": "instance-2",
            "runtime_port": 8767,
            "already_absent": False,
        }) as uninstall:
            response = self.client.post(
                f"/device-hosts/{host_id}/uninstall",
                json={"password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/device-hosts").json()["devices"], [])
        self.assertNotIn("ssh-password", response.text)
        uninstall.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="robot",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            instance_id="instance-2",
            runtime_port=8767,
            firewall_source="",
            stack_mode="runtime_only",
            hardware_ports=[8765],
            progress=None,
        )

    def test_managed_runtime_uninstall_stream_reports_progress_until_registry_cleanup(self):
        host = server._device_registry.pair_host(
            name="Isolated robot stack",
            runtime_url="http://192.168.1.87:8768",
            runtime_token="runtime-token",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "robot-computer-instance-2",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "instance-2",
                "runtime_port": 8768,
                "service_name": "blacknode-runtime-instance-2.service",
                "runtime_dir": "~/blacknode-runtimes/instance-2",
                "stack_mode": "isolated",
                "hardware_dir": "~/blacknode-hardware-instances/instance-2",
            },
        )

        def uninstall(**kwargs):
            kwargs["progress"]({
                "progress": 60,
                "message": "Stopping isolated Robot Hardware services",
            })
            return {
                "ok": True,
                "instance_id": "instance-2",
                "runtime_port": 8768,
                "already_absent": False,
                "stack_mode": "isolated",
            }

        with patch.object(server, "uninstall_runtime", side_effect=uninstall):
            response = self.client.post(
                f"/device-hosts/{host['id']}/uninstall-stream",
                json={"password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line]
        progress = [event for event in events if event["type"] == "progress"]
        self.assertEqual(progress[0]["progress"], 1)
        self.assertTrue(any(event["progress"] == 60 for event in progress))
        self.assertEqual(progress[-1], {
            "type": "progress",
            "progress": 100,
            "message": "Device deleted",
        })
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["result"]["summary"], "Device deleted")
        self.assertEqual(self.client.get("/device-hosts").json()["devices"], [])

    def test_device_can_be_renamed_without_repairing_or_exposing_tokens(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device = self.client.post("/devices", json={
                "name": "Leader",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]

        response = self.client.patch(
            f"/devices/{device['id']}",
            json={"name": "Leader — 31481"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device"]["name"], "Leader — 31481")
        self.assertNotIn(hardware.token, response.text)
        listed = self.client.get("/devices").json()["devices"]
        self.assertEqual(listed[0]["name"], "Leader — 31481")
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["devices"][device["id"]]["token"], hardware.token)
        self.assertEqual(
            self.client.patch(
                f"/devices/{device['id']}",
                json={"name": "  "},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                "/devices/missing",
                json={"name": "Missing"},
            ).status_code,
            404,
        )

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
        status_requests = [
            request for request in hardware.requests
            if request[1] == "/status"
        ]
        rpc_requests = [
            request for request in hardware.requests
            if request[1] == "/rpc"
        ]
        self.assertTrue(status_requests)
        self.assertEqual(status_requests[-1][2], f"Bearer {hardware.token}")
        self.assertTrue(rpc_requests)
        self.assertEqual(rpc_requests[-1][3]["method"], "stop")

    def test_robot_attachments_are_managed_in_ui_api_and_check_live_ros_topic(self):
        hardware = _HardwareService()
        attachment_payload = {
            "attachment_id": "front_camera",
            "display_name": "Front camera",
            "attachment_type": "camera",
            "capability": "camera",
            "provider_package": "blacknode-perception",
            "provider_component": "camera",
            "provider_adapter": "ros2",
            "topic": "/camera/image_raw",
            "message_type": "sensor_msgs/msg/Image",
            "parent_frame": "base_link",
            "frame_id": "camera_link",
            "x_m": 0.2,
            "y_m": 0.0,
            "z_m": 0.4,
            "roll_rad": 0.0,
            "pitch_rad": 0.1,
            "yaw_rad": 0.0,
            "hardware_id": "camera-serial-1",
            "required": True,
            "enabled": True,
        }
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            created = self.client.post(
                f"/devices/{paired['id']}/attachments",
                json=attachment_payload,
            )
            listed = self.client.get(
                f"/devices/{paired['id']}/attachments",
            )
            missing = self.client.post(
                f"/devices/{paired['id']}/attachments/front_camera/check",
            )

            hardware.ros2_diagnostics_payload["topics"].append(
                "/camera/image_raw [sensor_msgs/msg/Image]"
            )
            hardware.ros2_diagnostics_payload["topic_details"] = [{
                "topic": "/camera/image_raw",
                "ok": True,
                "stdout": (
                    "Type: sensor_msgs/msg/Image\n\n"
                    "Publisher count: 1\n\nSubscription count: 0\n"
                ),
                "stderr": "",
            }]
            streaming = self.client.post(
                f"/devices/{paired['id']}/attachments/front_camera/check",
            )
            updated = self.client.put(
                f"/devices/{paired['id']}/attachments/front_camera",
                json={
                    **attachment_payload,
                    "display_name": "Wrist camera",
                },
            )
            re_paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            })
            invalid_id_change = self.client.put(
                f"/devices/{paired['id']}/attachments/front_camera",
                json={
                    **attachment_payload,
                    "attachment_id": "different_camera",
                },
            )
            deleted = self.client.delete(
                f"/devices/{paired['id']}/attachments/front_camera",
            )

        self.assertEqual(created.status_code, 200)
        attachment = created.json()["attachment"]
        self.assertEqual(attachment["kind"], "blacknode.robot-attachment")
        self.assertEqual(attachment["interfaces"][0]["topic"], "/camera/image_raw")
        self.assertEqual(
            attachment["mount"]["translation_m"],
            [0.2, 0.0, 0.4],
        )
        self.assertEqual(
            attachment["hardware_identity"]["id"],
            "camera-serial-1",
        )
        self.assertEqual(len(listed.json()["attachments"]), 1)
        self.assertEqual(missing.json()["check"]["status"], "missing")
        self.assertFalse(missing.json()["check"]["ok"])
        self.assertEqual(streaming.json()["check"]["status"], "streaming")
        self.assertTrue(streaming.json()["check"]["ok"])
        self.assertEqual(streaming.json()["check"]["publisher_count"], 1)
        self.assertEqual(
            updated.json()["attachment"]["display_name"],
            "Wrist camera",
        )
        self.assertEqual(len(re_paired.json()["device"]["attachments"]), 1)
        self.assertEqual(invalid_id_change.status_code, 400)
        self.assertIn("stable", invalid_id_change.json()["detail"].lower())
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["device"]["attachments"], [])
        self.assertNotIn(hardware.token, created.text)
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["devices"][paired["id"]]["attachments"],
            [],
        )

    def test_robot_attachment_rejects_invalid_ros_message_type(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            response = self.client.post(
                f"/devices/{paired['id']}/attachments",
                json={
                    "attachment_id": "front_camera",
                    "display_name": "Front camera",
                    "attachment_type": "camera",
                    "capability": "camera",
                    "provider_package": "blacknode-perception",
                    "provider_component": "camera",
                    "provider_adapter": "ros2",
                    "topic": "/camera/image_raw",
                    "message_type": "Image",
                    "parent_frame": "base_link",
                    "frame_id": "camera_link",
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(
                "sensor_msgs/msg/image",
                response.json()["detail"].lower(),
            )

    def test_managed_blacknode_rgbd_attachment_starts_outside_deployments(self):
        hardware = _HardwareService()
        payload = {
            "attachment_id": "front_rgbd",
            "display_name": "Front RGB-D",
            "attachment_type": "depth_camera",
            "capability": "depth_camera",
            "provider_package": "blacknode-perception",
            "provider_component": "depth",
            "provider_adapter": "ros2",
            "provider_profile": "blacknode_rgbd",
            "topic": "/camera/rgb/image_raw",
            "message_type": "sensor_msgs/msg/Image",
            "camera_info_topic": "/camera/rgb/camera_info",
            "depth_topic": "/camera/depth/image_raw",
            "point_cloud_topic": "",
            "launch_arguments": ["rgb_device:=0", "depth_device:=1"],
            "parent_frame": "base_link",
            "frame_id": "depth_camera_link",
            "required": True,
            "enabled": True,
        }
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            created = self.client.post(
                f"/devices/{paired['id']}/attachments",
                json=payload,
            )
            started = self.client.post(
                f"/devices/{paired['id']}/attachments/front_rgbd/start",
            )
            checked = self.client.post(
                f"/devices/{paired['id']}/attachments/front_rgbd/check",
            )
            stopped = self.client.post(
                f"/devices/{paired['id']}/attachments/front_rgbd/stop",
            )

        attachment = created.json()["attachment"]
        self.assertEqual(len(attachment["interfaces"]), 3)
        self.assertEqual(
            attachment["interfaces"][2]["topic"],
            "/camera/depth/image_raw",
        )
        self.assertTrue(attachment["interfaces"][2]["required"])
        service = started.json()["service"]
        self.assertEqual(
            service["command"],
            {
                "verb": "launch",
                "package": "perception_camera",
                "target": "rgbd_camera.launch.py",
                "arguments": [
                    "rgb_device:=0",
                    "depth_device:=1",
                    "rgb_topic:=/camera/rgb/image_raw",
                    "rgb_info_topic:=/camera/rgb/camera_info",
                    "depth_topic:=/camera/depth/image_raw",
                    "rgb_frame_id:=depth_camera_link",
                    "depth_frame_id:=depth_camera_link",
                ],
            },
        )
        self.assertEqual(started.json()["check"]["status"], "streaming")
        self.assertEqual(checked.json()["check"]["service_state"], "running")
        self.assertEqual(stopped.json()["service"]["state"], "stopped")
        self.assertEqual(hardware.runtime_deployments, {})
        self.assertIn(
            "blacknode-perception",
            {
                item["name"]
                for item in hardware.runtime_packages
            },
        )

    def test_managed_usb_attachment_uses_bundled_camera_provider(self):
        service_id, payload = server._attachment_service_payload({
            "id": "wrist_camera",
            "display_name": "Wrist camera",
            "service": {
                "id": "wrist-camera",
                "profile": "usb_cam",
                "launch_arguments": ["device:=2"],
            },
            "interfaces": [
                {
                    "kind": "topic",
                    "topic": "/wrist/image_raw",
                    "message_type": "sensor_msgs/msg/Image",
                    "frame_id": "wrist_camera_link",
                },
                {
                    "kind": "topic",
                    "role": "camera_info",
                    "topic": "/wrist/camera_info",
                    "message_type": "sensor_msgs/msg/CameraInfo",
                    "required": False,
                },
            ],
        })

        self.assertEqual(service_id, "wrist-camera")
        self.assertEqual(payload["command"], {
            "verb": "launch",
            "package": "perception_camera",
            "target": "usb_camera.launch.py",
            "arguments": [
                "device:=2",
                "image_topic:=/wrist/image_raw",
                "camera_info_topic:=/wrist/camera_info",
                "frame_id:=wrist_camera_link",
            ],
        })
        self.assertEqual(payload["wait_seconds"], 15.0)

    def test_attachment_check_surfaces_provider_log_for_missing_stream(self):
        check = server._attachment_service_check(
            {
                "display_name": "Wrist camera",
                "interfaces": [{
                    "kind": "topic",
                    "topic": "/camera/image_raw",
                    "message_type": "sensor_msgs/msg/Image",
                }],
            },
            {
                "state": "running",
                "error": "",
                "diagnostics": {
                    "ok": False,
                    "missing": ["/camera/image_raw"],
                    "interfaces": [],
                },
            },
            provider_logs=(
                "starting provider\n"
                "RuntimeError: Could not open camera device 0\n"
            ),
        )

        self.assertFalse(check["ok"])
        self.assertIn("/camera/image_raw", check["message"])
        self.assertIn("Could not open camera device 0", check["message"])

    def test_attachment_provider_setup_failure_is_actionable(self):
        class FailingSetupRuntime:
            def sync_packages(self, packages):
                self.packages = packages
                return {
                    "ok": True,
                    "messages": [
                        "warning: package setup script failed; rerun setup"
                    ],
                }

        runtime = FailingSetupRuntime()
        with self.assertRaisesRegex(
            device_registry.DeviceRegistryError,
            "device setup failed",
        ):
            server._sync_attachment_provider_package(
                runtime,
                {
                    "provider": {
                        "package": "blacknode-perception",
                        "component": "camera",
                        "adapter": "ros2",
                    },
                    "service": {"profile": "usb_cam"},
                },
            )
        self.assertEqual(
            runtime.packages[0]["components"],
            ["camera"],
        )

    def test_retired_depth_attachment_profile_migrates_to_blacknode_rgbd(self):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps({
            "schema_version": 2,
            "hosts": {},
            "devices": {
                "camera-robot": {
                    "id": "camera-robot",
                    "name": "Camera robot",
                    "base_url": "http://127.0.0.1:8765",
                    "token": "secret",
                    "attachments": [{
                        "id": "front_depth",
                        "attachment_type": "depth_camera",
                        "provider": {
                            "package": "blacknode-perception",
                            "component": "depth",
                            "adapter": "ros2",
                            "profile": "retired_depth_profile",
                        },
                        "service": {
                            "id": "front-depth",
                            "profile": "retired_depth_profile",
                        },
                    }],
                },
            },
        }), encoding="utf-8")

        attachment = server._device_registry.get_public(
            "camera-robot"
        )["attachments"][0]
        self.assertEqual(
            attachment["provider"]["profile"],
            "blacknode_rgbd",
        )
        self.assertEqual(
            attachment["service"]["profile"],
            "blacknode_rgbd",
        )

    def test_device_status_keeps_last_verified_hardware_version(self):
        hardware = _HardwareService(status_overrides={
            "software_version": "0.1.1",
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            self.assertEqual(paired["software_version"], "0.1.1")
            hardware.status_payload.pop("software_version")
            status = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["software_version"], "0.1.1")
        self.assertTrue(status.json()["software_version_cached"])
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["devices"][paired["id"]]["software_version"],
            "0.1.1",
        )

    def test_release_torque_requires_no_running_deployment_and_verifies_register_state(self):
        hardware = _HardwareService(status_overrides={
            "connected": True,
            "armed": False,
            "torque_enabled": True,
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            released = self.client.post(
                f"/devices/{paired['id']}/release-torque",
            )

        self.assertEqual(released.status_code, 200)
        self.assertFalse(released.json()["status"]["torque_enabled"])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("disable_torque", rpc_methods)

    def test_release_torque_reports_when_register_readback_is_unavailable(self):
        hardware = _HardwareService(
            status_overrides={
                "connected": True,
                "armed": False,
                "torque_enabled": None,
            },
            torque_readback_available=False,
        )
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            released = self.client.post(
                f"/devices/{paired['id']}/release-torque",
            )

        self.assertEqual(released.status_code, 200)
        payload = released.json()
        self.assertIsNone(payload["status"]["torque_enabled"])
        self.assertIn("servo_2", payload["verification_warning"])

    def test_managed_device_pause_stops_deployments_and_disarms_then_resumes(self):
        hardware = _HardwareService("hardware-token")
        runtime = _HardwareService("runtime-token")
        runtime.runtime_deployments["live"] = {
            "id": "live",
            "name": "Live workflow",
            "state": "running",
            "target_device_id": "alex-desktop",
        }
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime.token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "robot-computer",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "runtime_dir": "~/blacknode-runtime",
            },
        )
        server._device_registry.pair(
            name="Workshop arm",
            base_url="http://192.168.1.87:8765",
            token=hardware.token,
            host_id=host["id"],
            status=hardware.status_payload,
        )

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return hardware(request, timeout)

        with (
            patch("device_registry.urllib.request.urlopen", side_effect=route),
            patch.object(server, "control_runtime", side_effect=[
                {
                    "ok": True,
                    "action": "pause",
                    "state": "inactive",
                    "service_name": "blacknode-runtime.service",
                },
                {
                    "ok": True,
                    "action": "resume",
                    "state": "active",
                    "service_name": "blacknode-runtime.service",
                },
            ]) as control,
        ):
            paused = self.client.post(
                f"/device-hosts/{host['id']}/lifecycle",
                json={"action": "pause", "password": "ssh-password"},
            )
            paused_robot = self.client.get("/devices/alex-desktop/status")
            resumed = self.client.post(
                f"/device-hosts/{host['id']}/lifecycle",
                json={"action": "resume", "password": "ssh-password"},
            )

        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["device"]["paused"])
        self.assertEqual(runtime.runtime_deployments["live"]["state"], "stopped")
        self.assertTrue(paused_robot.json()["paused"])
        self.assertFalse(resumed.json()["device"]["paused"])
        self.assertEqual([call.kwargs["action"] for call in control.call_args_list], ["pause", "resume"])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("stop", rpc_methods)
        self.assertIn("resume", rpc_methods)

    def test_robot_can_be_paused_without_stopping_its_compute_runtime(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            robot = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            paused = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "pause"},
            )
            status = self.client.get(f"/devices/{robot['id']}/status")
            resumed = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "resume"},
            )

        self.assertTrue(paused.json()["status"]["paused"])
        self.assertTrue(status.json()["paused"])
        self.assertFalse(resumed.json()["status"]["paused"])

    def test_robot_pause_stops_every_running_deployment_for_that_robot(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            robot = self.client.post("/devices", json={
                "name": "Follower",
                "base_url": "http://192.168.1.87:8767",
                "token": hardware.token,
            }).json()["device"]
            for deployment_id in ("follower-old", "follower-new"):
                hardware.runtime_deployments[deployment_id] = {
                    "id": deployment_id,
                    "name": deployment_id,
                    "state": "running",
                    "target_device_id": robot["id"],
                }

            paused = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "pause"},
            )

        self.assertEqual(paused.status_code, 200)
        self.assertEqual(
            set(paused.json()["stopped_deployments"]),
            {"follower-old", "follower-new"},
        )
        self.assertEqual(
            {
                item["state"]
                for item in hardware.runtime_deployments.values()
            },
            {"stopped"},
        )

    def test_robot_pause_still_disarms_when_deployment_runtime_is_unreachable(self):
        hardware = _HardwareService(status_overrides={
            "deployment_lease": {
                "id": "live",
                "name": "Live workflow",
                "state": "running",
            },
        })
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8766",
            runtime_token="runtime-token",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "robot-computer",
            },
        )
        robot = server._device_registry.pair(
            name="Follower",
            base_url="http://192.168.1.87:8767",
            token=hardware.token,
            host_id=host["id"],
            status=hardware.status_payload,
        )

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                raise urllib.error.URLError("timed out")
            return hardware(request, timeout)

        with patch("device_registry.urllib.request.urlopen", side_effect=route):
            response = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "pause"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["status"]["paused"])
        self.assertIn("8766", payload["warnings"][0])
        self.assertIn("continued with the robot hardware stop request", payload["warnings"][0])
        self.assertIn("physical torque cannot be verified", payload["warnings"][0])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertIn("stop", rpc_methods)

    def test_managed_device_lifecycle_stream_reports_real_progress(self):
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8768",
            runtime_token="runtime-token",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "robot-computer-instance-2",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "instance-2",
                "runtime_port": 8768,
                "service_name": "blacknode-runtime-instance-2.service",
                "runtime_dir": "~/blacknode-runtimes/instance-2",
            },
        )
        runtime = SimpleNamespace(list_deployments=lambda: {"deployments": []})
        with (
            patch.object(server._device_registry, "host_client", return_value=runtime),
            patch.object(server, "control_runtime", return_value={
                "ok": True,
                "action": "pause",
                "state": "inactive",
                "service_name": "blacknode-runtime-instance-2.service",
            }),
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/lifecycle-stream",
                json={"action": "pause", "password": "ssh-password"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line]
        progress = [event for event in events if event["type"] == "progress"]
        self.assertGreaterEqual(len(progress), 3)
        self.assertEqual(progress[0]["progress"], 1)
        self.assertEqual(progress[-1]["progress"], 100)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["result"]["device"]["paused"])

    def test_managed_runtime_update_can_run_when_hardware_is_not_selected(self):
        hardware = _HardwareService(status_overrides={
            "software_version": "0.1.1",
            "torque_enabled": False,
        })
        runtime = _HardwareService("runtime-token")
        runtime.runtime_packages.append({
            "name": "blacknode-skills",
            "version": "0.2.2",
            "source": "workspace",
        })
        runtime.runtime_deployments["live"] = {
            "id": "live",
            "name": "Live workflow",
            "state": "running",
            "target_device_id": "alex-desktop",
        }
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime.token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "runtime_dir": "~/blacknode-runtime",
            },
        )
        server._device_registry.pair(
            name="Follower",
            base_url="http://192.168.1.87:8767",
            token=hardware.token,
            host_id=host["id"],
            status=hardware.status_payload,
        )

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return hardware(request, timeout)

        update_result = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "components": [
                {
                    "kind": "runtime",
                    "service_name": "blacknode-runtime.service",
                    "port": 8766,
                    "before": {"version": "0.3.8", "commit": "111111111111"},
                    "after": {"version": "0.3.9", "commit": "222222222222"},
                    "changed": True,
                    "state": "active",
                },
            ],
        }
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=route),
            patch.object(
                server,
                "update_managed_services",
                return_value=update_result,
            ) as update,
            patch.object(
                server,
                "_runtime_extension_update_specs",
                return_value=([
                    {
                        "name": "blacknode-skills",
                        "git_url": (
                            "https://github.com/temiroff/blacknode-skills.git"
                        ),
                        "update": True,
                    },
                ], []),
            ),
            patch.object(
                server,
                "control_runtime",
                return_value={
                    "ok": True,
                    "state": "active",
                    "service_name": "blacknode-runtime.service",
                },
            ) as control,
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/update-stream",
                json={"password": "ssh-password", "scope": "runtime"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line]
        self.assertEqual(events[-1]["type"], "done")
        result = events[-1]["result"]
        self.assertEqual(
            result["update"]["components"][0]["reported_version"],
            "0.1.0",
        )
        self.assertEqual(result["scope"], "runtime")
        self.assertEqual(runtime.runtime_deployments["live"]["state"], "stopped")
        self.assertFalse(result["robots"][0]["status"]["armed"])
        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs["hardware_ports"], [])
        self.assertTrue(update.call_args.kwargs["include_runtime"])
        sync_request = next(
            item
            for item in runtime.requests
            if item[0] == "POST" and item[1] == "/packages/sync"
        )
        self.assertEqual(sync_request[3]["packages"][0]["update"], True)
        self.assertEqual(control.call_count, 2)
        self.assertEqual(
            result["extension_packages"]["already_present"][0]["name"],
            "blacknode-skills",
        )
        self.assertIn("workflow package", result["summary"])
        self.assertNotIn("ssh-password", response.text)

    def test_managed_runtime_update_falls_back_to_verified_ssh_when_api_times_out(self):
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8766",
            runtime_token="runtime-token",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "runtime_dir": "~/blacknode-runtime",
            },
        )

        class _UnavailableRuntime:
            def list_deployments(self):
                raise device_registry.DeviceRegistryError(
                    "Could not reach http://192.168.1.87:8766: timed out."
                )

            def manifest(self):
                return {
                    "service": "blacknode-runtime",
                    "protocol_version": 1,
                    "runtime_version": "0.3.9",
                    "device_id": "alex-desktop",
                }

        update_result = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "components": [
                {
                    "kind": "runtime",
                    "service_name": "blacknode-runtime.service",
                    "port": 8766,
                    "before": {"version": "0.3.8", "commit": "111111111111"},
                    "after": {"version": "0.3.9", "commit": "222222222222"},
                    "changed": True,
                    "state": "active",
                },
            ],
        }
        progress: list[dict] = []
        with (
            patch.object(
                server._device_registry,
                "host_client",
                return_value=_UnavailableRuntime(),
            ),
            patch.object(server.time, "sleep"),
            patch.object(
                server,
                "control_runtime",
                return_value={
                    "ok": True,
                    "action": "pause",
                    "state": "inactive",
                    "service_name": "blacknode-runtime.service",
                },
            ) as control,
            patch.object(
                server,
                "update_managed_services",
                return_value=update_result,
            ) as update,
        ):
            result = server._update_device_host_payload(
                host["id"],
                server.UpdateManagedDeviceReq(
                    password="ssh-password",
                    scope="runtime",
                ),
                progress.append,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("verified SSH service identity", result["warnings"][0])
        control.assert_called_once()
        self.assertEqual(control.call_args.kwargs["action"], "pause")
        update.assert_called_once()
        self.assertEqual(result["runtime"]["runtime_version"], "0.3.9")
        self.assertEqual(progress[-1]["progress"], 100)

    def test_runtime_extension_update_specs_refresh_installed_packages(self):
        package = SimpleNamespace(
            name="blacknode-skills",
            path=Path("packages/blacknode-skills"),
        )
        with (
            patch.object(server, "installed_packages", return_value=[package]),
            patch.object(
                server,
                "_package_git_source",
                return_value="https://github.com/temiroff/blacknode-skills.git",
            ),
        ):
            specs, warnings = server._runtime_extension_update_specs({
                "packages": [
                    {
                        "name": "blacknode-runtime",
                        "version": "0.3.15",
                        "source": "runtime",
                    },
                    {
                        "name": "blacknode-skills",
                        "version": "0.2.3",
                        "source": "workspace",
                    },
                ],
            })

        self.assertEqual(warnings, [])
        self.assertEqual(specs, [{
            "name": "blacknode-skills",
            "git_url": "https://github.com/temiroff/blacknode-skills.git",
            "update": True,
        }])

    def test_managed_update_check_reports_installed_latest_and_live_versions(self):
        hardware = _HardwareService(status_overrides={
            "software_version": "0.1.0",
        })
        runtime = _HardwareService("runtime-token")
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8766",
            runtime_token=runtime.token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "default",
                "runtime_port": 8766,
                "service_name": "blacknode-runtime.service",
                "runtime_dir": "~/blacknode-runtime",
            },
        )
        server._device_registry.pair(
            name="Follower",
            base_url="http://192.168.1.87:8767",
            token=hardware.token,
            host_id=host["id"],
            status=hardware.status_payload,
        )

        def route(request, timeout=0):
            if urllib.parse.urlsplit(request.full_url).port == 8766:
                return runtime(request, timeout)
            return hardware(request, timeout)

        checked = {
            "ok": True,
            "host_fingerprint": "SHA256:trusted-device-key",
            "components": [
                {
                    "kind": "runtime",
                    "service_name": "blacknode-runtime.service",
                    "port": 8766,
                    "installed": {"version": "0.3.8", "commit": "111111111111"},
                    "latest": {"version": "0.3.9", "commit": "222222222222"},
                    "update_available": True,
                    "can_update": True,
                    "dirty": False,
                    "state": "active",
                    "error": "",
                },
                {
                    "kind": "hardware",
                    "service_name": "blacknode-hardware-follower.service",
                    "port": 8767,
                    "installed": {"version": "0.1.0", "commit": "333333333333"},
                    "latest": {"version": "0.1.0", "commit": "333333333333"},
                    "update_available": False,
                    "can_update": True,
                    "dirty": False,
                    "state": "active",
                    "error": "",
                },
            ],
        }
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=route),
            patch.object(
                server,
                "inspect_managed_service_updates",
                return_value=checked,
            ) as inspect,
        ):
            response = self.client.post(
                f"/device-hosts/{host['id']}/update-check-stream",
                json={"password": "ssh-password"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line]
        result = events[-1]["result"]
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn("1 of 2 services", result["summary"])
        self.assertEqual(
            result["check"]["components"][0]["reported_version"],
            "0.1.0",
        )
        self.assertEqual(
            result["check"]["components"][1]["reported_version"],
            "0.1.0",
        )
        inspect.assert_called_once()
        self.assertEqual(inspect.call_args.kwargs["hardware_ports"], [8767])
        self.assertNotIn("ssh-password", response.text)

    def test_managed_update_check_describes_runtime_only_dirty_checkout(self):
        runtime = _HardwareService("runtime-token")
        host = server._device_registry.pair_host(
            name="Second Runtime",
            runtime_url="http://192.168.1.87:8768",
            runtime_token=runtime.token,
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "alex-desktop-instance-2",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "instance-2",
                "runtime_port": 8768,
                "service_name": "blacknode-runtime-instance-2.service",
                "runtime_dir": "~/blacknode-runtimes/instance-2",
            },
        )
        checked = {
            "ok": False,
            "host_fingerprint": "SHA256:trusted-device-key",
            "components": [{
                "kind": "runtime",
                "service_name": "blacknode-runtime-instance-2.service",
                "port": 8768,
                "installed": {"version": "0.3.8", "commit": "111111111111"},
                "latest": {"version": "0.3.9", "commit": "222222222222"},
                "update_available": True,
                "can_update": False,
                "dirty": True,
                "state": "active",
                "error": (
                    "Local source changes must be committed, stashed, or "
                    "removed before update."
                ),
            }],
        }
        with (
            patch.object(
                server._device_registry,
                "host_client",
                return_value=SimpleNamespace(manifest=lambda: {
                    "runtime_version": "0.3.8",
                }),
            ),
            patch.object(
                server,
                "inspect_managed_service_updates",
                return_value=checked,
            ) as inspect,
        ):
            result = server._check_device_host_updates_payload(
                host["id"],
                server.UpdateManagedDeviceReq(password="ssh-password"),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["summary"],
            "Checked 1 service; 1 needs attention before Runtime can be updated.",
        )
        inspect.assert_called_once()
        self.assertEqual(inspect.call_args.kwargs["hardware_ports"], [])

    def test_managed_robot_service_can_be_restarted_by_exact_hardware_port(self):
        hardware = _HardwareService()
        host = server._device_registry.pair_host(
            name="Robot computer",
            runtime_url="http://192.168.1.87:8768",
            runtime_token="runtime-token",
            manifest={
                "service": "blacknode-runtime",
                "protocol_version": 1,
                "device_id": "robot-computer-instance-2",
            },
            managed_runtime={
                "ssh_host": "192.168.1.87",
                "ssh_port": 22,
                "ssh_username": "robot",
                "host_fingerprint": "SHA256:trusted-device-key",
                "instance_id": "instance-2",
                "runtime_port": 8768,
                "service_name": "blacknode-runtime-instance-2.service",
                "runtime_dir": "~/blacknode-runtimes/instance-2",
            },
        )
        robot = server._device_registry.pair(
            name="Follower",
            base_url="http://192.168.1.87:8767",
            token=hardware.token,
            host_id=host["id"],
            status=hardware.status_payload,
        )
        with (
            patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            patch.object(server, "restart_hardware_service", return_value={
                "ok": True,
                "hardware_port": 8767,
                "service_name": "blacknode-hardware-follower.service",
                "state": "active",
            }) as restart,
        ):
            response = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "restart", "password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "restart")
        self.assertFalse(payload["status"]["armed"])
        self.assertFalse(payload["status"]["paused"])
        self.assertIn("blacknode-hardware-follower.service", payload["summary"])
        self.assertNotIn("ssh-password", response.text)
        restart.assert_called_once_with(
            host="192.168.1.87",
            port=22,
            username="robot",
            password="ssh-password",
            host_fingerprint="SHA256:trusted-device-key",
            hardware_port=8767,
        )

    def test_robot_service_restart_is_blocked_while_deployment_is_active(self):
        hardware = _HardwareService(status_overrides={
            "deployment_lease": {
                "id": "live",
                "name": "Live workflow",
                "state": "running",
            },
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            robot = self.client.post("/devices", json={
                "name": "Follower",
                "base_url": "http://192.168.1.87:8767",
                "token": hardware.token,
            }).json()["device"]
            response = self.client.post(
                f"/devices/{robot['id']}/lifecycle",
                json={"action": "restart", "password": "ssh-password"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Stop the robot's active deployment", response.text)

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
            "motion_armed": False,
            "motion_control_count": 0,
        })
        self.assertFalse(payload["connected"])
        self.assertEqual(payload["connection_state"], "disconnected")
        self.assertFalse(payload["connection_reported"])
        self.assertNotIn("error", payload)
        self.assertIn("Leader live", payload["notice"])
        self.assertIn("treats the robot as disconnected", payload["notice"])
        self.assertIn("Stop the deployment", payload["notice"])
        rpc_methods = [
            body["method"]
            for method, path, _auth, body in hardware.requests
            if method == "POST" and path == "/rpc"
        ]
        self.assertNotIn("resume", rpc_methods)

    def test_device_status_uses_active_deployment_connection_telemetry(self):
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
            hardware.runtime_telemetry["leader-live"] = {
                "available": True,
                "stale": False,
                "payload": {"connected": True, "torque_enabled": True},
            }
            response = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["connection_state"], "connected")
        self.assertTrue(payload["connection_reported"])
        self.assertTrue(payload["torque_enabled"])
        self.assertFalse(payload["armed"])
        self.assertEqual(payload["deployment_lease"]["state"], "running")

    def test_device_status_uses_noninvasive_serial_presence_during_deployment(self):
        hardware = _HardwareService(status_overrides={
            "connected": True,
            "connection_present": True,
            "connection_reported": True,
            "connection_source": "device_path",
            "leased_to_deployment": True,
            "error": "serial hardware is leased to a Blacknode deployment",
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Follower arm",
                "base_url": "http://192.168.1.87:8767",
                "token": hardware.token,
            }).json()["device"]
            hardware.runtime_deployments["follower-live"] = {
                "id": "follower-live",
                "name": "Follower live",
                "state": "running",
                "target_device_id": paired["id"],
            }
            response = self.client.get(f"/devices/{paired['id']}/status")

        payload = response.json()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["connection_state"], "connected")
        self.assertTrue(payload["connection_reported"])
        self.assertEqual(payload["connection_source"], "device_path")
        self.assertIn("serial device path is present", payload["notice"])

    def test_device_status_reports_running_monitor_without_motion_lease(self):
        hardware = _HardwareService(status_overrides={
            "connected": True,
            "leased_to_deployment": False,
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Leader arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            hardware.runtime_deployments["leader-monitor"] = {
                "id": "leader-monitor",
                "name": "Leader monitor",
                "state": "running",
                "target_device_id": paired["id"],
            }
            response = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["running_deployment"], {
            "id": "leader-monitor",
            "name": "Leader monitor",
            "state": "running",
            "motion_armed": False,
            "motion_control_count": 0,
        })
        self.assertNotIn("deployment_lease", payload)
        self.assertIn("does not report that it owns motion control", payload["notice"])

    def test_robot_monitor_uses_hardware_positions_while_idle(self):
        hardware = _HardwareService(status_overrides={
            "connected": True,
            "positions": {
                "shoulder": 12.5,
                "elbow": -3.0,
            },
            "torque_enabled": False,
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Leader arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            response = self.client.get(f"/devices/{paired['id']}/monitor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "hardware")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["payload"]["joints"], [
            {"name": "shoulder", "position": 12.5, "velocity": 0.0},
            {"name": "elbow", "position": -3.0, "velocity": 0.0},
        ])

    def test_robot_monitor_switches_to_running_deployment_telemetry(self):
        hardware = _HardwareService(status_overrides={
            "connected": False,
            "leased_to_deployment": True,
            "error": "serial hardware is leased to a Blacknode deployment",
            "calibrated": True,
            "calibration": {
                "name": "Follower calibration",
                "profile_id": "so_arm101_v002",
                "hardware_id": "FOLLOWER-42",
                "joint_count": 6,
            },
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Follower arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            hardware.runtime_deployments["follower-live"] = {
                "id": "follower-live",
                "name": "Follower live",
                "state": "running",
                "target_device_id": paired["id"],
            }
            hardware.runtime_telemetry["follower-live"] = {
                "available": True,
                "deployment_id": "follower-live",
                "stream": "robot-state",
                "sequence": 42,
                "sent_at": "2026-07-25T12:00:00+00:00",
                "received_at": "2026-07-25T12:00:00.010000+00:00",
                "age_seconds": 0.01,
                "stale": False,
                "payload": {
                    "kind": "blacknode.device-state",
                    "schema_version": 1,
                    "device_id": "follower-arm",
                    "connected": True,
                    "armed": True,
                    "torque_enabled": True,
                    "joint_state": {
                        "kind": "blacknode.joint-state",
                        "schema_version": 1,
                        "position_unit": "radian",
                        "velocity_unit": "radian/s",
                        "positions": {"gripper": 0.13962634015954636},
                        "velocities": {"gripper": 0.03490658503988659},
                        "efforts": {},
                        "limits": {},
                    },
                    "faults": [],
                },
            }
            response = self.client.get(f"/devices/{paired['id']}/monitor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "deployment")
        self.assertEqual(payload["source_label"], "Follower live")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["sequence"], 42)
        self.assertEqual(payload["payload"]["joints"][0]["velocity"], 2.0)
        self.assertTrue(payload["payload"]["calibrated"])
        self.assertEqual(payload["payload"]["calibration"], {
            "name": "Follower calibration",
            "profile_id": "so_arm101_v002",
            "hardware_id": "FOLLOWER-42",
            "joint_count": 6,
        })

    def test_robot_monitor_websocket_streams_selected_robot(self):
        hardware = _HardwareService(status_overrides={
            "positions": {"shoulder": 5.0},
            "torque_enabled": False,
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            with self.client.websocket_connect(
                f"/api/devices/{paired['id']}/monitor/ws"
            ) as websocket:
                payload = websocket.receive_json()

        self.assertEqual(payload["robot_id"], paired["id"])
        self.assertEqual(payload["source"], "hardware")
        self.assertEqual(payload["payload"]["joints"][0]["position"], 5.0)

    def test_robot_monitor_websocket_stops_sampling_after_disconnect(self):
        samples = []

        def snapshot(device_id, _profile_id="auto"):
            samples.append(time.monotonic())
            return {
                "type": "robot_telemetry",
                "robot_id": device_id,
                "available": True,
                "stale": False,
                "payload": {
                    "connected": True,
                    "position_unit": "degree",
                    "velocity_unit": "degree/s",
                    "joints": [],
                },
            }

        with patch.object(server, "_device_monitor_snapshot", side_effect=snapshot):
            with self.client.websocket_connect(
                "/api/devices/local-usb-disconnect/monitor/ws"
            ) as websocket:
                websocket.receive_json()
            time.sleep(0.25)
            settled_count = len(samples)
            time.sleep(0.25)

        self.assertEqual(len(samples), settled_count)

    def test_device_status_reports_stopped_deployment_as_inactive(self):
        hardware = _HardwareService(status_overrides={
            "connected": True,
            "leased_to_deployment": False,
        })
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            paired = self.client.post("/devices", json={
                "name": "Leader arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]
            hardware.runtime_deployments["leader-stored"] = {
                "id": "leader-stored",
                "name": "Leader workflow",
                "state": "stopped",
                "target_device_id": paired["id"],
                "created_at": "2026-07-24T00:00:00+00:00",
                "updated_at": "2026-07-25T00:00:00+00:00",
            }
            response = self.client.get(f"/devices/{paired['id']}/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["connection_state"], "connected")
        self.assertEqual(payload["inactive_deployment"], {
            "id": "leader-stored",
            "name": "Leader workflow",
            "state": "stopped",
        })
        self.assertEqual(payload["stored_deployment"], {
            "id": "leader-stored",
            "name": "Leader workflow",
            "state": "stopped",
        })
        self.assertIn("stopped on the Runtime", payload["notice"])
        self.assertIn("can be restarted", payload["notice"].lower())
        self.assertNotIn("running_deployment", payload)

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

    def test_deployment_preflight_accepts_a_ready_attachment_capability(self):
        hardware = _HardwareService()
        hardware.ros2_diagnostics_payload["topics"].append(
            "/camera/image_raw [sensor_msgs/msg/Image]"
        )
        hardware.ros2_diagnostics_payload["topic_details"] = [{
            "topic": "/camera/image_raw",
            "ok": True,
            "stdout": (
                "Type: sensor_msgs/msg/Image\n\n"
                "Publisher count: 1\n\nSubscription count: 0\n"
            ),
            "stderr": "",
        }]
        attachment = {
            "attachment_id": "front_camera",
            "display_name": "Front camera",
            "attachment_type": "camera",
            "capability": "camera",
            "provider_package": "blacknode-perception",
            "provider_component": "camera",
            "provider_adapter": "ros2",
            "provider_profile": "existing_topics",
            "topic": "/camera/image_raw",
            "message_type": "sensor_msgs/msg/Image",
            "parent_frame": "base_link",
            "frame_id": "camera_link",
            "required": True,
            "enabled": True,
        }

        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            self.client.post(
                f"/devices/{device_id}/attachments",
                json=attachment,
            )
            checked = self.client.post(
                f"/devices/{device_id}/attachments/front_camera/check",
            )
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": _workflow(["camera"])},
            )

        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json()["check"]["ok"])
        self.assertEqual(response.status_code, 200)
        checks = {item["id"]: item for item in response.json()["checks"]}
        self.assertEqual(checks["capabilities"]["status"], "pass")
        self.assertFalse(checks["capabilities"]["blocking"])
        self.assertIn("camera", checks["capabilities"]["message"])

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
            feedback_workflow = json.loads(json.dumps(workflow))
            feedback_workflow["metadata"]["required_capabilities"] = [
                "position_feedback",
                "servo_bus",
            ]
            feedback_preflight = self.client.post(
                "/devices/paired/deployment-preflight",
                json={"workflow": feedback_workflow},
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
        self.assertEqual(feedback_preflight.status_code, 200)
        feedback_checks = {
            item["id"]: item
            for item in feedback_preflight.json()["checks"]
        }
        self.assertEqual(feedback_checks["calibration"]["status"], "fail")
        self.assertTrue(feedback_checks["calibration"]["blocking"])
        self.assertEqual(
            feedback_checks["calibration"]["action"],
            "choose_matching_hardware",
        )
        self.assertIn(
            "different physical robot",
            feedback_checks["calibration"]["message"],
        )

    def test_inactive_calibration_message_reports_missing_servo_topology(self):
        workflow = {
            "metadata": {
                "device_calibration": {
                    "profile_id": "so_arm101_v002",
                    "hardware_id": "5B41531481",
                },
            },
        }
        profile = {
            "id": "so_arm101_v002",
            "joints": [
                {"id": f"joint_{servo_id}", "servo_id": servo_id}
                for servo_id in range(1, 7)
            ],
        }
        calibration = {
            "profile_id": "so_arm101_v002",
            "hardware_id": "5B41531481",
            "joints": {},
        }
        with patch.object(
            server,
            "_selected_local_calibration",
            return_value=(profile, calibration),
        ):
            message = server._inactive_calibration_message(
                workflow,
                {
                    "joint_names": [
                        "servo_1",
                        "servo_3",
                        "servo_4",
                        "servo_5",
                        "servo_6",
                    ],
                },
            )

        self.assertIn("saved but not active", message)
        self.assertIn("5 of 6 expected servos", message)
        self.assertIn("missing servo ID: 2", message)
        self.assertIn("feedback-only workflow may run", message)

    def test_hardware_monitor_exposes_servo_debug_fields_and_calibrated_limits(self):
        status = {
            "device_id": "robot-device",
            "connected": True,
            "armed": False,
            "torque_enabled": False,
            "joint_names": ["servo_2"],
            "positions": {"servo_2": 12.5},
            "raw_positions": {"servo_2": 2190},
            "limits": {"servo_2": {"min": -180.0, "max": 180.0}},
            "calibrated": True,
            "calibration": {
                "profile_id": "so_arm101",
                "hardware_id": "SERIAL-42",
                "topology": {"2": "shoulder_lift"},
                "joints": {
                    "shoulder_lift": {
                        "safe_min_deg": -70.0,
                        "safe_max_deg": 80.0,
                    },
                },
            },
            "temperatures_c": {"servo_2": 41.5},
            "voltage_v": 12.2,
            "voltages_v": {"servo_2": 12.2},
            "hardware_error_flags": {"servo_2": 1},
            "hardware_errors": {"servo_2": ["voltage"]},
            "servo_status": {"servo_2": 1},
            "bus": {
                "operation_count": 20,
                "timeout_count": 0,
                "serial_packet_error_count": 0,
                "hardware_error_flags": {"servo_2": 1},
                "hardware_errors": {"servo_2": ["voltage"]},
                "servo_status": {"servo_2": 1},
                "voltages_v": {"servo_2": 12.2},
            },
            "error": "",
        }
        with (
            patch.object(
                server._device_registry,
                "get_public",
                return_value={"id": "robot", "name": "Robot"},
            ),
            patch.object(
                server,
                "_deployment_aware_device_status",
                return_value=status,
            ),
        ):
            snapshot = server._device_monitor_snapshot("robot")

        payload = snapshot["payload"]
        joint = payload["joints"][0]
        self.assertEqual(joint["servo_id"], 2)
        self.assertEqual(joint["semantic_name"], "shoulder_lift")
        self.assertEqual(joint["raw_position"], 2190)
        self.assertEqual(joint["lower_limit"], -70.0)
        self.assertEqual(joint["upper_limit"], 80.0)
        self.assertTrue(payload["calibrated"])
        self.assertEqual(payload["temperatures_c"]["servo_2"], 41.5)
        self.assertEqual(payload["voltage_v"], 12.2)
        self.assertTrue(joint["communication_ok"])
        self.assertEqual(joint["temperature_c"], 41.5)
        self.assertEqual(joint["voltage_v"], 12.2)
        self.assertEqual(joint["hardware_error_flags"], 1)
        self.assertEqual(joint["hardware_errors"], ["voltage"])
        self.assertEqual(joint["servo_status"], 1)
        self.assertEqual(payload["bus"]["operation_count"], 20)

    def test_robot_monitor_targets_include_local_usb_robots(self):
        local = {
            "id": "local-usb-abc",
            "name": "Workshop arm · COM4",
            "kind": "local_usb",
            "available": True,
            "profile_id": "workshop_arm",
            "hardware_id": "SERIAL-42",
            "port": "COM4",
        }
        with patch.object(
            server,
            "_local_robot_monitor_targets",
            return_value=[local],
        ):
            response = self.client.get("/robot-monitor-targets")

        self.assertEqual(response.status_code, 200)
        targets = response.json()["targets"]
        self.assertIn(local, targets)

    def test_robot_monitor_targets_accept_none_for_raw_usb_discovery(self):
        raw = {
            "id": "local-usb-raw",
            "name": "Raw servos · COM4",
            "kind": "local_usb",
            "available": True,
            "profile_id": "",
            "requested_profile_id": "none",
            "raw_mode": True,
            "hardware_id": "SERIAL-42",
            "port": "COM4",
        }
        with patch.object(
            server,
            "_local_robot_monitor_targets",
            return_value=[raw],
        ) as targets:
            response = self.client.get(
                "/robot-monitor-targets?profile_id=none"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile_id"], "none")
        self.assertIn(raw, response.json()["targets"])
        targets.assert_called_once_with("none")

    def test_local_usb_raw_monitor_maps_uncalibrated_ticks(self):
        def raw_monitor(_ctx):
            return {
                "available": True,
                "position_unit": "ticks",
                "velocity_unit": "ticks/s",
                "torque_enabled": False,
                "joints": [{
                    "name": "servo_2",
                    "semantic_name": "Servo 2",
                    "servo_id": 2,
                    "position": 833.0,
                    "velocity": 0.0,
                    "raw_position": 833,
                    "communication_ok": True,
                    "voltage_v": 11.9,
                    "temperature_c": 32.0,
                    "hardware_error_flags": 1,
                    "hardware_errors": ["voltage"],
                }],
                "warnings": [
                    "servo_2 (servo 2) hardware warning 0x01: voltage"
                ],
                "errors": [],
                "diagnostics": {
                    "operation_count": 3,
                    "scan_miss_count": 30,
                    "serial_packet_error_count": 0,
                },
                "provider": {
                    "package": "blacknode-drivers",
                    "component": "feetech",
                },
                "report": "Raw read-only scan found servo ID 2.",
            }

        target = {
            "id": "local-usb-raw",
            "name": "Raw servos · COM4",
            "kind": "local_usb",
            "available": True,
            "raw_mode": True,
            "hardware_id": "SERIAL-42",
            "port": "COM4",
            "hardware": {"recommended": {"path": "COM4"}},
        }
        with patch.dict(
            server._NODE_REGISTRY,
            {"RobotRawMonitor": raw_monitor},
        ):
            snapshot = server._local_robot_monitor_snapshot(target)

        self.assertTrue(snapshot["available"])
        payload = snapshot["payload"]
        self.assertTrue(payload["raw_mode"])
        self.assertFalse(payload["calibrated"])
        self.assertEqual(payload["position_unit"], "ticks")
        self.assertEqual(payload["joints"][0]["raw_position"], 833)
        self.assertEqual(payload["bus"]["scan_miss_count"], 30)
        self.assertEqual(
            payload["faults"][0]["details"]["joint"],
            "servo_2",
        )

    def test_local_usb_monitor_maps_provider_diagnostics(self):
        def control(_ctx):
            return {
                "data_ready": True,
                "command_ok": True,
                "torque_enabled": False,
                "pose": {
                    "shoulder_pan": -7.56,
                    "shoulder_lift": -106.79,
                },
                "warnings": [
                    "shoulder_lift (servo 2) hardware warning 0x01: voltage"
                ],
                "servos": {
                    "shoulder_pan": {
                        "servo_id": 1,
                        "communication_ok": True,
                        "ticks": 1962,
                        "position_deg": -7.56,
                        "torque_enabled": False,
                        "voltage_v": 11.9,
                        "temperature_c": 35.0,
                        "servo_status": 0,
                        "hardware_error_flags": 0,
                        "hardware_errors": [],
                    },
                    "shoulder_lift": {
                        "servo_id": 2,
                        "communication_ok": True,
                        "ticks": 833,
                        "position_deg": -106.79,
                        "torque_enabled": False,
                        "voltage_v": 11.9,
                        "temperature_c": 32.0,
                        "servo_status": 1,
                        "hardware_error_flags": 1,
                        "hardware_errors": ["voltage"],
                    },
                },
                "diagnostics": {
                    "operation_count": 3,
                    "serial_packet_error_count": 0,
                },
                "report": "Live local USB telemetry.",
            }

        target = {
            "id": "local-usb-abc",
            "name": "Workshop arm · COM4",
            "kind": "local_usb",
            "available": True,
            "profile_id": "workshop_arm",
            "hardware_id": "SERIAL-42",
            "port": "COM4",
            "profile": {
                "id": "workshop_arm",
                "display_name": "Workshop arm",
                "joints": [{
                    "id": "shoulder_pan",
                    "display_name": "Shoulder pan",
                    "servo_id": 1,
                    "safe_min_deg": -110.0,
                    "safe_max_deg": 110.0,
                }, {
                    "id": "shoulder_lift",
                    "display_name": "Shoulder lift",
                    "servo_id": 2,
                    "safe_min_deg": -110.0,
                    "safe_max_deg": 110.0,
                }],
            },
            "hardware": {"recommended": {"path": "COM4"}},
            "calibration": {
                "profile_id": "workshop_arm",
                "hardware_id": "SERIAL-42",
            },
        }
        with patch.dict(
            server._NODE_REGISTRY,
            {"RobotCalibrationControl": control},
        ):
            snapshot = server._local_robot_monitor_snapshot(target)

        self.assertTrue(snapshot["available"])
        self.assertFalse(snapshot["stale"])
        payload = snapshot["payload"]
        self.assertFalse(payload["torque_enabled"])
        self.assertEqual(len(payload["faults"]), 1)
        self.assertEqual(
            payload["faults"][0]["details"]["joint"],
            "shoulder_lift",
        )
        healthy_joint = next(
            item for item in payload["joints"]
            if item["name"] == "shoulder_pan"
        )
        self.assertEqual(healthy_joint["hardware_error_flags"], 0)
        self.assertEqual(healthy_joint["hardware_errors"], [])
        joint = next(
            item for item in payload["joints"]
            if item["name"] == "shoulder_lift"
        )
        self.assertEqual(joint["servo_id"], 2)
        self.assertEqual(joint["raw_position"], 833)
        self.assertEqual(joint["voltage_v"], 11.9)
        self.assertEqual(joint["temperature_c"], 32.0)
        self.assertEqual(joint["hardware_error_flags"], 1)
        self.assertEqual(joint["hardware_errors"], ["voltage"])
        self.assertEqual(payload["bus"]["serial_packet_error_count"], 0)

    def test_local_usb_monitor_serializes_reads_and_keeps_last_good_pose(self):
        device_id = "local-usb-stable"
        target = {"id": device_id}
        good = {
            "type": "robot_telemetry",
            "robot_id": device_id,
            "available": True,
            "stale": False,
            "payload": {
                "connected": True,
                "joints": [{"name": "shoulder", "position": 12.5}],
            },
        }
        failed = {
            "type": "robot_telemetry",
            "robot_id": device_id,
            "available": False,
            "stale": True,
            "message": "serial port is temporarily busy",
        }
        with server._robot_monitor_cache_lock:
            server._robot_monitor_snapshot_cache.pop(device_id, None)
            server._robot_monitor_device_locks.pop(device_id, None)
        try:
            with (
                patch.object(
                    server,
                    "_local_robot_monitor_target",
                    return_value=target,
                ),
                patch.object(
                    server,
                    "_local_robot_monitor_snapshot",
                    return_value=good,
                ) as snapshot,
            ):
                first = server._device_monitor_snapshot(device_id)
                second = server._device_monitor_snapshot(device_id)

            self.assertTrue(first["available"])
            self.assertEqual(second["payload"]["joints"][0]["position"], 12.5)
            snapshot.assert_called_once_with(target)

            with server._robot_monitor_cache_lock:
                server._robot_monitor_snapshot_cache[device_id]["sampled_at"] = 0.0
            with (
                patch.object(
                    server,
                    "_local_robot_monitor_target",
                    return_value=target,
                ),
                patch.object(
                    server,
                    "_local_robot_monitor_snapshot",
                    return_value=failed,
                ),
            ):
                retry = server._device_monitor_snapshot(device_id)

            self.assertTrue(retry["available"])
            self.assertTrue(retry["stale"])
            self.assertEqual(
                retry["payload"]["joints"][0]["position"],
                12.5,
            )
            self.assertIn("keeping the last good", retry["message"])
            self.assertIn("temporarily busy", retry["transient_error"])
        finally:
            with server._robot_monitor_cache_lock:
                server._robot_monitor_snapshot_cache.pop(device_id, None)
                server._robot_monitor_device_locks.pop(device_id, None)

    def test_deployment_monitor_preserves_semantic_joint_servo_ids(self):
        payload = server._monitor_payload_from_device_state({
            "kind": "blacknode.device-state",
            "connected": True,
            "armed": False,
            "torque_enabled": False,
            "joint_state": {
                "position_unit": "radian",
                "velocity_unit": "radian/s",
                "positions": {"shoulder_lift": 0.25},
                "velocities": {"shoulder_lift": 0.1},
                "limits": {
                    "shoulder_lift": {"lower": -1.0, "upper": 1.0},
                },
            },
            "values": {
                "servo_ids": {"shoulder_lift": 2},
                "raw_positions": {"shoulder_lift": 2190},
                "calibrated": True,
                "bus": {
                    "operation_count": 20,
                    "timeout_count": 0,
                    "serial_packet_error_count": 0,
                    "hardware_error_flags": {"shoulder_lift": 1},
                    "hardware_errors": {"shoulder_lift": ["voltage"]},
                    "servo_status": {"shoulder_lift": 1},
                    "voltages_v": {"shoulder_lift": 11.9},
                },
            },
            "temperatures_c": {"shoulder_lift": 32.0},
            "voltage_v": 11.9,
        })

        joint = payload["joints"][0]
        self.assertEqual(joint["name"], "shoulder_lift")
        self.assertEqual(joint["servo_id"], 2)
        self.assertEqual(joint["raw_position"], 2190)
        self.assertTrue(joint["communication_ok"])
        self.assertEqual(joint["temperature_c"], 32.0)
        self.assertEqual(joint["voltage_v"], 11.9)
        self.assertEqual(joint["hardware_error_flags"], 1)
        self.assertEqual(joint["hardware_errors"], ["voltage"])
        self.assertEqual(joint["servo_status"], 1)
        self.assertEqual(payload["bus"]["timeout_count"], 0)
        self.assertTrue(payload["calibrated"])

    def test_monitor_metadata_merges_status_summary_with_live_calibration(self):
        payload = server._monitor_payload_with_status_metadata(
            {
                "calibrated": False,
                "calibration": {
                    "profile_id": "",
                    "topology": {"1": "shoulder_pan", "2": "shoulder_lift"},
                },
            },
            {
                "calibrated": True,
                "calibration": {
                    "name": "Workshop arm",
                    "profile_id": "so_arm101_v002",
                    "hardware_id": "SERIAL-42",
                },
            },
        )

        self.assertTrue(payload["calibrated"])
        self.assertEqual(payload["calibration"]["name"], "Workshop arm")
        self.assertEqual(payload["calibration"]["profile_id"], "so_arm101_v002")
        self.assertEqual(payload["calibration"]["hardware_id"], "SERIAL-42")
        self.assertEqual(payload["calibration"]["joint_count"], 2)

        unknown = server._monitor_payload_with_status_metadata(
            {"calibration": {"profile_id": "so_arm101_v002"}},
            {},
        )
        self.assertNotIn("calibrated", unknown)

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
                r"Update blacknode-robot.*service\.sh restart",
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
            "update": True,
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
            "components": ["follow"],
            "adapters": [{"component": "follow", "adapter": "ros2"}],
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

    def test_preflight_returns_one_click_repair_for_disabled_editor_adapter(self):
        hardware = _HardwareService()
        dependency_report = {
            "ok": False,
            "code": "missing_adapters",
            "message": (
                "Required adapters need attention: "
                "blacknode-drivers/feetech@ros2 (adapter is disabled)"
            ),
            "missing_packages": [],
            "missing_components": [],
            "missing_adapters": [{
                "package": "blacknode-drivers",
                "component": "feetech",
                "adapter": "ros2",
                "reason": "adapter is disabled",
            }],
        }

        with (
            patch("device_registry.urllib.request.urlopen", side_effect=hardware),
            patch.object(
                server,
                "_workflow_dependency_report",
                return_value=dependency_report,
            ),
        ):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            response = self.client.post(
                f"/devices/{device_id}/deployment-preflight",
                json={"workflow": _workflow([])},
            )

        self.assertEqual(response.status_code, 200)
        dependency_check = next(
            item
            for item in response.json()["checks"]
            if item["id"] == "local_dependencies"
        )
        self.assertEqual(
            dependency_check["action"],
            "enable_editor_dependencies",
        )
        self.assertEqual(dependency_check["action_data"], {
            "components": [],
            "adapters": [{
                "package": "blacknode-drivers",
                "component": "feetech",
                "adapter": "ros2",
            }],
        })
        self.assertTrue(dependency_check["blocking"])

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
        attachment_payload = {
            "attachment_id": "front_camera",
            "display_name": "Front camera",
            "attachment_type": "camera",
            "capability": "camera",
            "provider_package": "blacknode-perception",
            "provider_component": "camera",
            "provider_adapter": "ros2",
            "topic": "/camera/image_raw",
            "message_type": "sensor_msgs/msg/Image",
            "parent_frame": "base_link",
            "frame_id": "camera_link",
            "required": True,
            "enabled": True,
        }
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            self.client.post(
                f"/devices/{device_id}/attachments",
                json=attachment_payload,
            )
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
        self.assertEqual(stage_request[3]["workflow"], workflow)
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
        staged_attachments = stage_request[3]["manifest"]["robot_attachments"]
        self.assertEqual(len(staged_attachments), 1)
        self.assertEqual(staged_attachments[0]["id"], "front_camera")
        self.assertEqual(
            staged_attachments[0]["interfaces"][0]["topic"],
            "/camera/image_raw",
        )
        self.assertNotIn("last_check", staged_attachments[0])
        self.assertFalse(stage_request[3]["manifest"]["telemetry_required"])

    def test_deployment_stream_reports_package_upload_and_start_progress(self):
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
                    f"/devices/{device_id}/deployments-stream",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "start": True,
                    },
                )

        self.assertEqual(response.status_code, 200)
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]
        progress = [event for event in events if event["type"] == "progress"]
        self.assertEqual(progress[0]["progress"], 1)
        self.assertEqual(progress[-1]["progress"], 100)
        messages = [event["message"] for event in progress]
        self.assertTrue(any("Synchronizing 1 required" in item for item in messages))
        self.assertIn("Uploading the workflow bundle", messages)
        self.assertTrue(any("replacing the previous workflow" in item for item in messages))
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["result"]["started"])
        self.assertEqual(events[-1]["result"]["deployment"]["state"], "running")

    def test_leader_follower_deployment_declares_one_remote_armed_gate(self):
        workflow = _workflow([])
        workflow["node_meta"]["follow"] = {
            "id": "follow",
            "type": "ROS2LeaderFollower",
            "params": {
                "run_id": "so-arm follower",
                "control_topic": "",
                "armed": False,
            },
        }

        self.assertEqual(
            server._workflow_motion_controls(workflow),
            [{
                "kind": "ros2_leader_follower",
                "node_id": "follow",
                "run_id": "so-arm follower",
                "topic": "/blacknode/leader_follower/so_arm_follower/control",
            }],
        )

    def test_joint_controller_declares_one_remote_armed_gate(self):
        workflow = _workflow([])
        workflow["node_meta"]["controller"] = {
            "id": "controller",
            "type": "ROS2JointController",
            "params": {
                "run_id": "joint controller",
                "control_topic": "",
                "armed": False,
            },
        }

        controls = server._workflow_motion_controls(workflow)

        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["node_id"], "controller")
        self.assertEqual(
            controls[0]["topic"],
            "/blacknode/leader_follower/joint_controller/control",
        )

    def test_remote_leader_follower_export_is_forced_disarmed(self):
        workflow = _workflow([])
        workflow["edges"] = [
            {
                "from": "armed",
                "from_port": "value",
                "to": "follow",
                "to_port": "armed",
            },
            {
                "from": "dynamic",
                "from_port": "value",
                "to": "follow",
                "to_port": "armed",
            },
        ]
        workflow["node_meta"].update({
            "armed": {
                "id": "armed",
                "type": "Bool",
                "params": {"value": True},
            },
            "dynamic": {
                "id": "dynamic",
                "type": "PythonFn",
                "params": {},
            },
            "follow": {
                "id": "follow",
                "type": "ROS2LeaderFollower",
                "params": {"armed": True},
            },
        })

        controlled = server._disarm_workflow_motion_controls(workflow)

        self.assertEqual(controlled, ["follow"])
        self.assertFalse(workflow["node_meta"]["armed"]["params"]["value"])
        self.assertFalse(workflow["node_meta"]["follow"]["params"]["armed"])
        self.assertEqual(len(workflow["edges"]), 1)
        self.assertEqual(workflow["edges"][0]["from"], "armed")
        self.assertEqual(
            workflow["metadata"]["deployment_motion_default"],
            "disarmed",
        )

    def test_joint_controller_export_is_forced_disarmed(self):
        workflow = _workflow([])
        workflow["node_meta"]["controller"] = {
            "id": "controller",
            "type": "ROS2JointController",
            "params": {"armed": True},
        }

        controlled = server._disarm_workflow_motion_controls(workflow)

        self.assertEqual(controlled, ["controller"])
        self.assertFalse(
            workflow["node_meta"]["controller"]["params"]["armed"]
        )

    def test_send_and_run_stops_but_retains_older_target_deployments(self):
        hardware = _HardwareService()
        workflow = _workflow([])
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Follower",
                "base_url": "http://192.168.1.87:8767",
                "token": hardware.token,
            }).json()["device"]["id"]
            hardware.runtime_deployments["follower-old"] = {
                "id": "follower-old",
                "name": "Follower old",
                "state": "running",
                "target_device_id": device_id,
            }
            with patch.object(server, "_workflow_payload", return_value=workflow):
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()
                response = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Follower replacement",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "start": True,
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["superseded_deployments"], ["follower-old"])
        self.assertEqual(payload["cleanup_warnings"], [])
        self.assertEqual(
            hardware.runtime_deployments["follower-old"]["state"],
            "stopped",
        )
        self.assertEqual(payload["deployment"]["state"], "running")
        replacement_id = payload["deployment"]["id"]
        self.assertEqual(
            set(hardware.runtime_deployments),
            {"follower-old", replacement_id},
        )
        deployment_requests = [
            (method, path)
            for method, path, _auth, _body in hardware.requests
            if path.startswith("/deployments/")
        ]
        self.assertIn(
            ("POST", "/deployments/follower-old/stop"),
            deployment_requests,
        )
        self.assertNotIn(
            ("DELETE", "/deployments/follower-old"),
            deployment_requests,
        )

    def test_robot_deployment_manifest_requires_fresh_telemetry(self):
        workflow = _workflow(["joint_group", "position_feedback"])

        self.assertTrue(server._workflow_requires_deployment_telemetry(workflow))

        robot_node_workflow = _workflow([])
        robot_node_workflow["node_meta"]["robot"] = {
            "id": "robot",
            "type": "Robot",
            "params": {},
        }
        self.assertTrue(
            server._workflow_requires_deployment_telemetry(robot_node_workflow)
        )

        controller_workflow = _workflow([])
        controller_workflow["node_meta"]["controller"] = {
            "id": "controller",
            "type": "ROS2JointController",
            "params": {},
        }
        self.assertTrue(
            server._workflow_requires_deployment_telemetry(controller_workflow)
        )

    def test_project_owned_deployment_requires_linked_workflow_and_device(self):
        hardware = _HardwareService()
        workflow = _workflow([])
        workflow_slug = "camera-workflow"
        workflows_dir = Path(self._tmp.name) / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / f"{workflow_slug}.json").write_text(
            json.dumps(workflow),
            encoding="utf-8",
        )
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            project = server._project_store.create(
                name="Camera Project",
                workflow_slugs=[workflow_slug],
            )
            with (
                patch.object(server, "_WORKFLOWS_DIR", str(workflows_dir)),
                patch.object(server, "_workflow_payload", return_value=workflow),
            ):
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()
                unlinked = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "project_id": project["id"],
                        "workflow_slug": workflow_slug,
                    },
                )
                server._project_store.update(
                    project["id"],
                    device_ids=[device_id],
                )
                staged = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "project_id": project["id"],
                        "workflow_slug": workflow_slug,
                    },
                )

        self.assertEqual(unlinked.status_code, 409)
        self.assertIn("not linked", unlinked.json()["detail"])
        self.assertEqual(staged.status_code, 200)
        deployment = staged.json()["deployment"]
        self.assertEqual(deployment["project_id"], project["id"])
        self.assertEqual(deployment["workflow_slug"], workflow_slug)
        stage_request = next(
            item for item in hardware.requests
            if item[0] == "POST" and item[1] == "/deployments"
        )
        self.assertEqual(
            stage_request[3]["manifest"]["project_id"],
            project["id"],
        )
        self.assertEqual(
            stage_request[3]["manifest"]["workflow_slug"],
            workflow_slug,
        )

    def test_project_owned_deployment_requires_updated_target_runtime(self):
        hardware = _HardwareService(runtime_features=[
            "manifest_v1",
            "deployment_bundle_v1",
            "process_supervision_v1",
            "rollback_v1",
            "package_sync_v1",
        ])
        workflow = _workflow([])
        workflow_slug = "camera-workflow"
        workflows_dir = Path(self._tmp.name) / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / f"{workflow_slug}.json").write_text(
            json.dumps(workflow),
            encoding="utf-8",
        )
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Workshop arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            project = server._project_store.create(
                name="Camera Project",
                workflow_slugs=[workflow_slug],
                device_ids=[device_id],
            )
            with (
                patch.object(server, "_WORKFLOWS_DIR", str(workflows_dir)),
                patch.object(server, "_workflow_payload", return_value=workflow),
            ):
                preflight = self.client.post(
                    f"/devices/{device_id}/deployment-preflight",
                    json={},
                ).json()
                response = self.client.post(
                    f"/devices/{device_id}/deployments",
                    json={
                        "name": "Camera workflow",
                        "workflow_hash": preflight["workflow"]["hash"],
                        "project_id": project["id"],
                        "workflow_slug": workflow_slug,
                    },
                )

        self.assertEqual(response.status_code, 409)
        self.assertIn("0.3.8", response.json()["detail"])
        self.assertFalse(any(
            method == "POST" and path == "/deployments"
            for method, path, _auth, _body in hardware.requests
        ))

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
        self.assertIn("treats the robot as disconnected", hardware_check["message"])
        self.assertIn("Stop the deployment", hardware_check["message"])

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
        hardware.runtime_workflows["camera-workflow-a1b2c3d4"] = _workflow([])
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
            captured = self.client.get(
                f"/devices/{device_id}/deployments/{deployment_id}/workflow",
            )
            armed = self.client.post(
                f"/devices/{device_id}/deployments/{deployment_id}/motion",
                json={"armed": True},
            )
            diagnostics = self.client.get(
                f"/devices/{device_id}/ros2-diagnostics",
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
        self.assertEqual(captured.json()["workflow"]["name"], "Device preflight")
        self.assertTrue(armed.json()["armed"])
        self.assertIn("2 nodes", diagnostics.json()["summary"])
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

    def test_remote_deployments_are_scoped_to_the_selected_robot(self):
        hardware = _HardwareService()
        with patch("device_registry.urllib.request.urlopen", side_effect=hardware):
            device_id = self.client.post("/devices", json={
                "name": "Follower arm",
                "base_url": "http://192.168.1.87:8765",
                "token": hardware.token,
            }).json()["device"]["id"]
            common = {
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
            hardware.runtime_deployments.update({
                "follower": {
                    **common,
                    "id": "follower",
                    "name": "Follower",
                    "target_device_id": device_id,
                },
                "leader": {
                    **common,
                    "id": "leader",
                    "name": "Leader",
                    "target_device_id": "another-robot",
                },
                "legacy": {
                    **common,
                    "id": "legacy",
                    "name": "Legacy deployment",
                    "target_device_id": "",
                },
            })

            listed = self.client.get(f"/devices/{device_id}/deployments")
            wrong_target = self.client.post(
                f"/devices/{device_id}/deployments/leader/start",
            )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            {item["id"] for item in listed.json()["deployments"]},
            {"follower", "legacy"},
        )
        self.assertEqual(wrong_target.status_code, 404)
        self.assertIn("does not belong to this robot", wrong_target.json()["detail"])
        self.assertFalse(any(
            path == "/deployments/leader/start"
            for _method, path, _authorization, _body in hardware.requests
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
