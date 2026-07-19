from __future__ import annotations

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
    def test_isaac_runtime_is_managed_through_registered_bridge_state(self):
        self.assertEqual(server._RUNTIME_MODULES["isaac"], "blacknode.pkg.blacknode_isaac.runtime")
        self.assertEqual(server._RUNTIME_REGISTRY_ANCHORS["isaac"], "IsaacPolicyBridge")

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
        picker.assert_called_once_with(r"C:\Users\robot")

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
