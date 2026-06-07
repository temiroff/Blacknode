from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import blacknode as bn
from blacknode.node import _NODE_REGISTRY
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


class EditorGraphRunTests(unittest.TestCase):
    def setUp(self):
        self.calls = {"source": 0, "left": 0, "right": 0}

        @bn.node(inputs=[], outputs=["value:Int"], name="GraphRunTestSource")
        def source(ctx: dict) -> dict:
            self.calls["source"] += 1
            return {"value": 7}

        @bn.node(inputs=["value:Int"], outputs=["value:Int"], name="GraphRunTestLeaf")
        def leaf(ctx: dict) -> dict:
            name = str(ctx["name"])
            self.calls[name] += 1
            if ctx.get("fail"):
                raise RuntimeError(f"{name} failed")
            return {"value": int(ctx["value"]) + int(ctx.get("offset", 0))}

        self.addCleanup(_NODE_REGISTRY.pop, "GraphRunTestSource", None)
        self.addCleanup(_NODE_REGISTRY.pop, "GraphRunTestLeaf", None)

    def _session(self, *, fail_left: bool = False):
        session = server.Session()
        source = session.graph.node("GraphRunTestSource")
        left = session.graph.node("GraphRunTestLeaf", name="left", offset=1, fail=fail_left)
        right = session.graph.node("GraphRunTestLeaf", name="right", offset=2)
        source.out("value") >> left.inp("value")
        source.out("value") >> right.inp("value")
        session.node_meta = {
            source._id: {"type": "GraphRunTestSource"},
            left._id: {"type": "GraphRunTestLeaf"},
            right._id: {"type": "GraphRunTestLeaf"},
        }
        return session, left._id, right._id

    def test_multi_target_run_cooks_all_leaves_and_reuses_upstream_cache(self):
        session, left_id, right_id = self._session()

        with patch.object(server, "_session", session):
            server._begin_fresh_cook()
            events = [
                json.loads(line)
                for line in server._cook_trace(
                    left_id,
                    "value",
                    targets=[(left_id, "value"), (right_id, "value")],
                )
            ]

        self.assertEqual(self.calls, {"source": 1, "left": 1, "right": 1})
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["port"], "leaves")
        self.assertNotIn("error", done)
        self.assertEqual(done["value"][f"{left_id}.value"], 8)
        self.assertEqual(done["value"][f"{right_id}.value"], 9)
        self.assertTrue(any(
            event.get("type") == "success"
            and event.get("node_id") not in {left_id, right_id}
            and event.get("cached")
            for event in events
        ))

    def test_failed_leaf_does_not_prevent_other_terminal_leaf(self):
        session, left_id, right_id = self._session(fail_left=True)

        with patch.object(server, "_session", session):
            server._begin_fresh_cook()
            events = [
                json.loads(line)
                for line in server._cook_trace(
                    left_id,
                    "value",
                    targets=[(left_id, "value"), (right_id, "value")],
                )
            ]

        self.assertEqual(self.calls, {"source": 1, "left": 1, "right": 1})
        done = events[-1]
        self.assertIn(f"{left_id}.value", done["error"])
        self.assertEqual(done["value"][f"{right_id}.value"], 9)
        self.assertEqual(
            [target["status"] for target in done["targets"]],
            ["error", "success"],
        )

    def test_graph_stream_endpoint_runs_the_complete_target_list(self):
        session, left_id, right_id = self._session()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(server, "_session", session),
            patch.object(server, "_run_store", server.RunStore(tmp)),
        ):
            response = TestClient(server.app).post(
                "/cook-graph-stream",
                json={
                    "targets": [
                        {"node_id": left_id, "port": "value"},
                        {"node_id": right_id, "port": "value"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual(events[-1]["port"], "leaves")
        self.assertEqual(self.calls, {"source": 1, "left": 1, "right": 1})
        self.assertTrue(response.headers.get("X-Blacknode-Run-Id"))


if __name__ == "__main__":
    unittest.main()
