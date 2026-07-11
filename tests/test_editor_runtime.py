from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


class EditorRuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
