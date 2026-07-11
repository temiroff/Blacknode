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
