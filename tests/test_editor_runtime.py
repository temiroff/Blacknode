from __future__ import annotations

import json
import sys
import tempfile
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


class EditorRuntimeTests(unittest.TestCase):
    def test_streamed_cook_injects_process_local_runtime_services(self):
        node_id = "runtime-context-test"

        def runtime_context_node(ctx):
            callback = ctx.get("__runtime_callback__")
            return {"value": callback() if callable(callback) else "missing"}

        original_context = dict(server._session.graph._runtime_context)
        server._session.node_meta[node_id] = {
            "id": node_id,
            "type": "RuntimeContextTest",
            "params": {},
        }
        server._session.graph._nodes[node_id] = {
            "type": "RuntimeContextTest",
            "params": {},
        }
        server._session.graph._dirty.add(node_id)
        server._session.graph.set_runtime_context(
            __runtime_callback__=lambda: "delegated",
        )
        try:
            with patch.dict(
                server._NODE_REGISTRY,
                {"RuntimeContextTest": runtime_context_node},
            ):
                events = [
                    json.loads(line)
                    for line in server._cook_trace(node_id, "value")
                ]
        finally:
            server._session.node_meta.pop(node_id, None)
            server._session.graph._nodes.pop(node_id, None)
            server._session.graph._dirty.discard(node_id)
            for cache_key in list(server._session.graph._cache):
                if cache_key[0] == node_id:
                    server._session.graph._cache.pop(cache_key, None)
            server._session.graph.set_runtime_context(**original_context)

        success = next(event for event in events if event.get("type") == "success")
        self.assertEqual(success["value"], "delegated")

    def test_robot_calibration_runtime_is_managed_through_generic_node(self):
        self.assertEqual(
            server._RUNTIME_MODULES["robot_calibration_control"],
            "blacknode.pkg.blacknode_robot.calibration_control",
        )
        self.assertEqual(
            server._RUNTIME_REGISTRY_ANCHORS["robot_calibration_control"],
            "RobotCalibrationControl",
        )

    def test_isaac_runtime_is_managed_through_registered_bridge_state(self):
        self.assertEqual(server._RUNTIME_MODULES["isaac"], "blacknode.pkg.blacknode_isaac.runtime")
        self.assertEqual(server._RUNTIME_REGISTRY_ANCHORS["isaac"], "IsaacPolicyBridge")

    def test_newton_runtime_is_managed_through_registered_simulation_state(self):
        self.assertEqual(server._RUNTIME_MODULES["newton"], "blacknode.pkg.blacknode_newton.runtime")
        self.assertEqual(server._RUNTIME_REGISTRY_ANCHORS["newton"], "NewtonSimulation")

    def test_viewer_runtime_is_managed_through_generic_viewer_node(self):
        self.assertEqual(
            server._RUNTIME_MODULES["viewer"],
            "blacknode.pkg.blacknode_cuda.viewer_runtime",
        )
        self.assertEqual(server._RUNTIME_REGISTRY_ANCHORS["viewer"], "Viewer")

    def test_leader_follower_runtime_is_managed_and_normalized(self):
        self.assertEqual(
            server._RUNTIME_MODULES["ros2_live"],
            "blacknode.pkg.blacknode_skills.follow.leader_follower_runtime",
        )
        with patch.object(
            server,
            "_runtime_callable",
            side_effect=[
                lambda: [{"run_id": "leader_follower", "armed": False}],
                lambda: {
                    "ok": True,
                    "stopped": 1,
                    "report": "stopped 1 leader-follower controller(s)",
                },
            ],
        ):
            status = server._runtime_module_status("ros2_live", "unused")
            stopped = server._stop_runtime_module("ros2_live", "unused")

        self.assertTrue(status["active"])
        self.assertEqual(
            status["managed_runs"][0]["run_id"],
            "leader_follower",
        )
        self.assertEqual(stopped["stopped"]["managed_runs"], 1)

    def test_robot_runtime_helpers_follow_registered_launcher_state(self):
        status_fn = lambda: {"ok": True, "active": True, "managed_runs": [{"run_id": "robot"}]}
        stop_fn = lambda: {"ok": True, "stopped": {"managed_runs": 1}}
        anchor = SimpleNamespace(__globals__={
            "runtime_status": status_fn,
            "stop_runtime_services": stop_fn,
        })
        with (
            patch.dict(server._NODE_REGISTRY, {"RobotDriverLauncher": anchor}),
            patch.object(server, "_RUNTIME_REGISTRY_ANCHORS", {"robot": "RobotDriverLauncher"}),
        ):
            self.assertIs(server._runtime_callable("robot", "unused", "runtime_status"), status_fn)
            self.assertIs(server._runtime_callable("robot", "unused", "stop_runtime_services"), stop_fn)

    def test_export_workflow_infers_entrypoint_for_multi_output_image_graph(self):
        workflow = {
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": "Vision Export",
            "node_meta": {
                "stream_out": {
                    "id": "stream_out",
                    "type": "OutputImage",
                    "params": {},
                    "pos": [0, 0],
                    "inputs": ["image"],
                    "outputs": ["image"],
                    "input_types": {"image": "Image"},
                    "output_types": {"image": "Image"},
                    "input_defaults": {},
                },
                "overlay_out": {
                    "id": "overlay_out",
                    "type": "OutputImage",
                    "params": {},
                    "pos": [0, 0],
                    "inputs": ["image"],
                    "outputs": ["image"],
                    "input_types": {"image": "Image"},
                    "output_types": {"image": "Image"},
                    "input_defaults": {},
                },
                "detection_out": {
                    "id": "detection_out",
                    "type": "Output",
                    "params": {},
                    "pos": [0, 0],
                    "inputs": ["value"],
                    "outputs": [],
                    "input_types": {"value": "Any"},
                    "output_types": {},
                    "input_defaults": {},
                },
            },
            "edges": [],
        }

        result = server._workflow_for_export(workflow)

        self.assertEqual(result["entrypoint"], {"node_id": "overlay_out", "port": "image"})

    def test_runtime_status_aggregates_package_runtime_modules(self):
        def fake_status(label, _module_name):
            if label == "ros2":
                return {
                    "ok": True,
                    "active": True,
                    "streams": [{"stream_id": "camera"}],
                    "managed_runs": [{"run_id": "camera_run"}],
                    "detached_count": 1,
                }
            return {
                "ok": True,
                "active": True,
                "cv2_streams": [{"stream_id": "cube"}],
                "reasoning_streams": [{"stream_id": "reason"}],
            }

        with (
            patch.object(server, "_RUNTIME_MODULES", {"ros2": "ros_runtime", "vision": "vision_runtime"}),
            patch.object(server, "_runtime_module_status", side_effect=fake_status),
        ):
            result = server._runtime_status()

        self.assertTrue(result["ok"])
        self.assertTrue(result["active"])
        self.assertEqual(result["streams"], [{"stream_id": "camera", "runtime": "ros2"}])
        self.assertEqual(result["cv2_streams"], [{"stream_id": "cube", "runtime": "vision"}])
        self.assertEqual(result["reasoning_streams"], [{"stream_id": "reason", "runtime": "vision"}])
        self.assertEqual(result["managed_runs"], [{"run_id": "camera_run", "runtime": "ros2"}])
        self.assertEqual(result["detached_count"], 1)

    def test_runtime_status_normalizes_nonfinite_sensor_values(self):
        with patch.object(
            server,
            "_runtime_status",
            return_value={"ranges": [1.0, float("nan"), float("inf")]},
        ):
            response = TestClient(server.app).get("/runtime/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ranges": [1.0, None, None]})

    def test_remote_ros2_action_routes_through_paired_runtime_and_reports_live_outputs(self):
        calls = []

        class FakeRuntimeClient:
            def manifest(self):
                return {
                    "features": ["remote_ros2_topic_stream_v1"],
                    "packages": [{"name": "blacknode-ros2", "version": "0.5.19"}],
                    "node_types": ["ROS2"],
                }

            def start_ros2_topic(self, stream_id, payload):
                calls.append(("start", stream_id, payload))
                return {"outputs": {
                    "running": True,
                    "message": {"ranges": [1.0]},
                    "messages": [{"ranges": [1.0]}],
                    "stream": {
                        "kind": "blacknode.message-stream",
                        "protocol": "ros2",
                        "topic": "/scan",
                    },
                    "status": {"kind": "blacknode.stream-status", "state": "ready"},
                    "received": 1,
                    "backend": "native",
                    "report": "streaming",
                }}

            def ros2_topic_status(self, stream_id):
                calls.append(("status", stream_id))
                return {"outputs": {
                    "running": True,
                    "message": {"ranges": [2.0]},
                    "messages": [{"ranges": [2.0]}],
                    "stream": {
                        "kind": "blacknode.message-stream",
                        "protocol": "ros2",
                        "topic": "/scan",
                    },
                    "status": {"kind": "blacknode.stream-status", "state": "ready"},
                    "received": 2,
                    "backend": "native",
                    "report": "streaming",
                }}

            def stop_ros2_topic(self, stream_id):
                calls.append(("stop", stream_id))
                return {"outputs": {"running": False, "stream": {}, "status": {}, "report": "stopped"}}

        registry = SimpleNamespace(runtime_client=lambda device_id: FakeRuntimeClient())
        request = {
            "node_id": "scan-node",
            "device_id": "jetson",
            "action": "start",
            "topic": "/scan",
            "message_type": "sensor_msgs/msg/LaserScan",
            "node_name": "blacknode_scan",
            "history": 10,
            "timeout": 10.0,
            "stale_after_seconds": 1.0,
        }
        server._remote_ros2_runs.clear()
        try:
            with patch.object(server, "_device_registry", registry):
                started = server._remote_ros2_action(request)
                streamed = server._message_stream_reader(started["outputs"]["stream"])
                runtime = server._remote_ros2_runtime_status()
                stopped = server._remote_ros2_action({**request, "action": "stop"})

            self.assertTrue(started["outputs"]["running"])
            self.assertEqual(started["outputs"]["backend"], "remote:jetson")
            self.assertEqual(started["outputs"]["stream"]["device_id"], "jetson")
            self.assertEqual(streamed["message"], {"ranges": [2.0]})
            self.assertEqual(runtime["node_outputs"][0]["node_id"], "scan-node")
            self.assertEqual(runtime["node_outputs"][0]["outputs"]["received"], 2)
            self.assertFalse(stopped["outputs"]["running"])
            self.assertEqual(
                [call[0] for call in calls],
                ["start", "status", "status", "stop"],
            )
        finally:
            server._remote_ros2_runs.clear()

    def test_remote_ros2_preflight_syncs_missing_device_package(self):
        synced = []

        class FakeRuntimeClient:
            def manifest(self):
                return {
                    "features": ["remote_ros2_topic_stream_v1"],
                    "packages": [{"name": "blacknode-runtime", "version": "0.4.1"}],
                    "node_types": [],
                }

            def sync_packages(self, specs):
                synced.extend(specs)
                return {"ok": True}

        server._ensure_remote_ros2_ready(FakeRuntimeClient())

        self.assertEqual([item["name"] for item in synced], ["blacknode-ros2"])
        self.assertEqual(synced[0]["components"], ["core", "topics"])
        self.assertTrue(synced[0]["update"])

    def test_stop_runtime_services_aggregates_package_runtime_modules(self):
        def fake_stop(label, _module_name):
            if label == "ros2":
                return {
                    "ok": True,
                    "stopped": {"streams": 1, "managed_runs": 1, "detached": 0},
                    "report": "stopped ros",
                }
            return {
                "ok": True,
                "stopped": {"cv2_streams": 2, "reasoning_streams": 1},
                "report": "stopped cv2 and reasoning",
            }

        with (
            patch.object(server, "_RUNTIME_MODULES", {"ros2": "ros_runtime", "vision": "vision_runtime"}),
            patch.object(server, "_stop_runtime_module", side_effect=fake_stop),
        ):
            result = server._stop_runtime_services()

        self.assertTrue(result["ok"])
        self.assertEqual(result["stopped"], {
            "streams": 1,
            "managed_runs": 1,
            "detached": 0,
            "cv2_streams": 2,
            "reasoning_streams": 1,
        })
        self.assertIn("stopped ros", result["report"])
        self.assertIn("stopped cv2 and reasoning", result["report"])

    def test_stop_runtime_services_tolerates_nested_package_counter(self):
        with (
            patch.object(server, "_RUNTIME_MODULES", {"ros2_live": "ros2_live_runtime"}),
            patch.object(server, "_stop_runtime_module", return_value={
                "ok": True,
                "stopped": {"streams": 1, "managed_runs": {"ok": True, "stopped": 2}},
            }),
        ):
            result = server._stop_runtime_services()

        self.assertTrue(result["ok"])
        self.assertEqual(result["stopped"]["streams"], 1)
        self.assertEqual(result["stopped"]["managed_runs"], 2)

    def test_runtime_stop_endpoint_stops_cook_and_runtime_helpers(self):
        runtime_result = {
            "ok": True,
            "stopped": {"streams": 1, "managed_runs": 1, "detached": 0},
            "report": "stopped 1 stream(s), 1 ROS 2 run process(es), 0 detached ROS 2 process(es)",
        }
        with (
            patch.object(server, "_stop_active_cook") as stop_cook,
            patch.object(server, "_begin_fresh_cook") as fresh_cook,
            patch.object(server, "_stop_runtime_services", return_value=runtime_result),
        ):
            response = TestClient(server.app).post("/runtime/stop")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), runtime_result)
        stop_cook.assert_called_once()
        fresh_cook.assert_called_once()

    def test_episode_recorder_control_does_not_cook_graph(self):
        server._session.node_meta["recorder-control-test"] = {
            "id": "recorder-control-test", "type": "EpisodeRecorder",
            "params": {"run_id": "episode-test"},
        }
        control = lambda run_id, action: {"running": False, "frame_count": 12, "report": f"{run_id}:{action}"}
        try:
            with (
                patch.object(server, "_runtime_callable", return_value=control),
                patch.object(server, "_prepare_cook") as prepare_cook,
            ):
                response = TestClient(server.app).post(
                    "/nodes/recorder-control-test/control", json={"action": "save"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["outputs"]["frame_count"], 12)
            prepare_cook.assert_not_called()
        finally:
            server._session.node_meta.pop("recorder-control-test", None)

    def test_connected_servo_command_routes_only_through_live_motion_control(self):
        servo_id = "servo-control-test"
        motion_id = "motion-control-test"
        server._session.node_meta[servo_id] = {
            "id": servo_id,
            "type": "RobotServo",
            "params": {"servo_id": 2, "joint_name": "shoulder_lift"},
        }
        server._session.node_meta[motion_id] = {
            "id": motion_id,
            "type": "ROS2JointSliders",
            "params": {"run_id": "arm-live"},
        }
        edge = {
            "from": servo_id,
            "from_port": "command",
            "to": motion_id,
            "to_port": "command",
        }
        server._session.graph._edges.append(edge)
        command = {
            "kind": "blacknode.joint-command-request",
            "schema_version": 1,
            "joint_name": "shoulder_lift",
            "servo_id": 2,
            "position_rad": 0.25,
            "issued_at": 123.0,
            "requires_motion_authorization": True,
        }
        routed = []

        def move(run_id, request):
            routed.append((run_id, request))
            return {"ok": True, "commanded": True, "report": "moved shoulder_lift"}

        try:
            with patch.object(server, "_runtime_callable", return_value=move):
                response = TestClient(server.app).post(
                    f"/nodes/{motion_id}/control",
                    json={
                        "action": "joint-command",
                        "payload": {"source_node_id": servo_id, "command": command},
                    },
                )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["outputs"]["commanded"])
            self.assertEqual(routed, [("arm-live", command)])

            server._session.graph._edges.remove(edge)
            disconnected = TestClient(server.app).post(
                f"/nodes/{motion_id}/control",
                json={
                    "action": "joint-command",
                    "payload": {"source_node_id": servo_id, "command": command},
                },
            )
            self.assertEqual(disconnected.status_code, 409)
        finally:
            server._session.node_meta.pop(servo_id, None)
            server._session.node_meta.pop(motion_id, None)
            if edge in server._session.graph._edges:
                server._session.graph._edges.remove(edge)
            for key in [key for key in server._session.graph._cache if key[0] == motion_id]:
                server._session.graph._cache.pop(key, None)

    def test_robot_servo_arms_and_commands_directly_from_its_own_control(self):
        node_id = "standalone-servo-test"
        server._session.node_meta[node_id] = {
            "id": node_id,
            "type": "RobotServo",
            "params": {
                "robot_id": "local-usb-test-arm",
                "profile_id": "test_arm",
                "servo_id": 2,
                "joint_name": "shoulder_lift",
            },
        }
        command = {
            "kind": "blacknode.joint-command-request",
            "schema_version": 1,
            "joint_name": "shoulder_lift",
            "servo_id": 2,
            "position_rad": 0.25,
            "issued_at": 123.0,
            "requires_motion_authorization": True,
        }
        calls = []

        def arm(run_id, context):
            calls.append(("arm", run_id, context))
            return {"ok": True, "armed": True, "report": "armed"}

        def move(run_id, request):
            calls.append(("move", run_id, request))
            return {
                "ok": True,
                "armed": True,
                "commanded": True,
                "report": "moved shoulder_lift",
            }

        def disarm(run_id):
            calls.append(("disarm", run_id))
            return {"ok": True, "armed": False, "report": "disarmed"}

        functions = {
            "arm_servo_motion": arm,
            "command_servo_motion": move,
            "disarm_servo_motion": disarm,
        }

        def runtime_callable(_label, _module, function_name):
            return functions.get(function_name)

        target = {
            "available": True,
            "raw_mode": False,
            "hardware_id": "usb:test-arm",
            "hardware": {"recommended": {"path": "COM7"}},
            "profile": {"id": "test_arm", "joints": []},
            "calibration": {
                "profile_id": "test_arm",
                "hardware_id": "usb:test-arm",
                "joints": {},
            },
        }
        try:
            with (
                patch.object(server, "_runtime_callable", side_effect=runtime_callable),
                patch.object(server, "_local_robot_monitor_target", return_value=target),
            ):
                client = TestClient(server.app)
                armed = client.post(
                    f"/nodes/{node_id}/control",
                    json={
                        "action": "arm",
                        "payload": {
                            "robot_id": "local-usb-test-arm",
                            "profile_id": "test_arm",
                        },
                    },
                )
                moved = client.post(
                    f"/nodes/{node_id}/control",
                    json={"action": "joint-command", "payload": {"command": command}},
                )
                disarmed = client.post(
                    f"/nodes/{node_id}/control",
                    json={"action": "disarm"},
                )

            self.assertEqual(armed.status_code, 200)
            self.assertTrue(armed.json()["outputs"]["armed"])
            self.assertEqual(moved.status_code, 200)
            self.assertTrue(moved.json()["outputs"]["commanded"])
            self.assertEqual(disarmed.status_code, 200)
            self.assertFalse(disarmed.json()["outputs"]["armed"])
            self.assertEqual(calls[0][0:2], ("arm", f"robot-servo:{node_id}"))
            self.assertEqual(calls[1], ("move", f"robot-servo:{node_id}", command))
            self.assertEqual(calls[2], ("disarm", f"robot-servo:{node_id}"))
        finally:
            server._session.node_meta.pop(node_id, None)

    def test_act_training_control_reports_progress_and_stops_without_cooking_graph(self):
        node_id = "training-control-test"
        server._session.node_meta[node_id] = {
            "id": node_id, "type": "ACTTraining", "params": {"run_id": "act-test"},
        }
        server._session.graph._dirty.add(node_id)
        calls: list[tuple[str, str]] = []

        def control(run_id, action):
            calls.append((run_id, action))
            return {
                "ok": True, "running": action == "status", "phase": "training" if action == "status" else "stopped",
                "step": 12, "status": {"steps": 100}, "dashboard": "data:image/svg+xml;base64,test",
                "checkpoint": "", "report": f"{run_id}:{action}",
            }

        try:
            with (
                patch.object(server, "_runtime_callable", return_value=control),
                patch.object(server, "_prepare_cook") as prepare_cook,
            ):
                client = TestClient(server.app)
                status = client.post(f"/nodes/{node_id}/control", json={"action": "status"})
                stopped = client.post(f"/nodes/{node_id}/control", json={"action": "stop"})
            self.assertEqual(status.status_code, 200)
            self.assertTrue(status.json()["outputs"]["running"])
            self.assertEqual(stopped.status_code, 200)
            self.assertEqual(stopped.json()["outputs"]["phase"], "stopped")
            self.assertEqual(calls, [("act-test", "status"), ("act-test", "stop")])
            self.assertNotIn(node_id, server._session.graph._dirty)
            prepare_cook.assert_not_called()
        finally:
            server._session.node_meta.pop(node_id, None)
            server._session.graph._dirty.discard(node_id)
            for key in [key for key in server._session.graph._cache if key[0] == node_id]:
                server._session.graph._cache.pop(key, None)

    def test_trajectory_smoother_control_recomputes_only_smoother(self):
        node_id = "smoother-control-test"
        server._session.node_meta[node_id] = {
            "id": node_id, "type": "TrajectorySmoother",
            "params": {"method": "gaussian", "strength": 2.5,
                       "preview_source": "leader", "preview_joint": "elbow"},
        }
        server._session.graph._dirty.add(node_id)
        apply = lambda node_id, method, strength, **preview: {
            "stream": {"token": "smoothed"}, "preview": "image",
            "report": f"{node_id}:{method}:{strength}:{preview['preview_source']}:{preview['preview_joint']}",
        }
        try:
            with (
                patch.object(server, "_runtime_callable", return_value=apply),
                patch.object(server, "_prepare_cook") as prepare_cook,
            ):
                response = TestClient(server.app).post(
                    f"/nodes/{node_id}/control", json={"action": "apply"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertIn("gaussian:2.5:leader:elbow", response.json()["outputs"]["report"])
            self.assertEqual(server._session.graph._cache[(node_id, "stream")], {"token": "smoothed"})
            self.assertNotIn(node_id, server._session.graph._dirty)
            prepare_cook.assert_not_called()
        finally:
            server._session.node_meta.pop(node_id, None)
            server._session.graph._dirty.discard(node_id)
            for key in [key for key in server._session.graph._cache if key[0] == node_id]:
                server._session.graph._cache.pop(key, None)

    def test_dataset_media_endpoint_serves_only_runtime_registered_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "episode.mp4"
            video.write_bytes(b"synthetic-mp4")
            with patch.object(server, "_runtime_callable", return_value=lambda token: video if token == "known" else None):
                client = TestClient(server.app)
                response = client.get("/dataset/media/known")
                api_response = client.get("/api/dataset/media/known")
                missing = client.get("/dataset/media/unknown")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"synthetic-mp4")
        self.assertEqual(api_response.content, b"synthetic-mp4")
        self.assertEqual(missing.status_code, 404)

    def test_directory_picker_endpoint_returns_native_selection(self):
        with patch.object(server, "_pick_directory", return_value=r"E:\RobotData") as picker:
            response = TestClient(server.app).post(
                "/filesystem/pick-directory", json={"initial_path": r"C:\Users\robot"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"selected": r"E:\RobotData", "cancelled": False})
        picker.assert_called_once_with(r"C:\Users\robot", "")

    def test_file_picker_endpoint_returns_filtered_native_selection(self):
        with patch.object(server, "_pick_file", return_value=r"E:\Scenes\robot.usd") as picker:
            response = TestClient(server.app).post(
                "/filesystem/pick-file",
                json={
                    "initial_path": r"E:\Scenes",
                    "title": "Open USD scene",
                    "extensions": [".usd", ".usda", ".usdc"],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"selected": r"E:\Scenes\robot.usd", "cancelled": False})
        picker.assert_called_once_with(
            r"E:\Scenes", "Open USD scene", [".usd", ".usda", ".usdc"]
        )

    def test_filesystem_browser_lists_directories_and_filtered_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "robot.usd").write_text("#usda 1.0", encoding="utf-8")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            response = TestClient(server.app).post(
                "/filesystem/browse",
                json={"path": str(root), "extensions": [".usd", ".usda", ".usdc"]},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(Path(payload["path"]), root.resolve())
        self.assertTrue(payload["roots"])
        self.assertEqual(
            [(entry["name"], entry["is_directory"]) for entry in payload["entries"]],
            [("assets", True), ("robot.usd", False)],
        )

    def test_dataset_frame_endpoint_returns_synchronized_robot_values(self):
        frame = {
            "frame_index": 12,
            "timestamp": 0.4,
            "leader": {"joint": 0.1},
            "observation": {"joint": 0.09},
            "action": {"joint": 0.1},
        }
        with patch.object(server, "_runtime_callable", return_value=lambda token, index: frame if (token, index) == ("known", 12) else None):
            client = TestClient(server.app)
            response = client.get("/dataset/frame/known?index=12")
            missing = client.get("/dataset/frame/unknown?index=12")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), frame)
        self.assertEqual(missing.status_code, 404)

    def test_dataset_trim_endpoint_forwards_confirmed_frame_and_side(self):
        def trim(token, frame_index, side):
            if token != "known":
                raise ValueError("replay selection expired")
            return {"ok": True, "frames": 8, "removed_frames": 4,
                    "frame_index": frame_index, "side": side}

        with patch.object(server, "_runtime_callable", return_value=trim):
            client = TestClient(server.app)
            response = client.post(
                "/dataset/trim", json={"token": "known", "frame_index": 4, "side": "before"},
            )
            expired = client.post(
                "/dataset/trim", json={"token": "expired", "frame_index": 4, "side": "after"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_frames"], 4)
        self.assertEqual(response.json()["frame_index"], 4)
        self.assertEqual(response.json()["side"], "before")
        self.assertEqual(expired.status_code, 409)

    def test_dataset_replay_event_endpoint_forwards_browser_playback(self):
        publish = lambda token, index, event: {
            "ok": True, "token": token, "frame_index": index, "event": event,
            "publishers": 1, "subscribers": 1,
        }
        with patch.object(server, "_runtime_callable", return_value=publish):
            response = TestClient(server.app).post(
                "/dataset/replay-event",
                json={"token": "episode", "frame_index": 12, "event": "seek"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["frame_index"], 12)
        self.assertEqual(response.json()["event"], "seek")


if __name__ == "__main__":
    unittest.main()
