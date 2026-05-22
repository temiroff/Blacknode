from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER = ROOT / "editor-server"
if str(EDITOR_SERVER) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER))

from run_store import RunStore, derive_status_from_events  # noqa: E402


class RunStoreLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RunStore(self._tmp.name)

    def test_begin_writes_running_record(self):
        run_id = self.store.begin(node_id="out", port="value", node_type="Output")
        record = self.store.get_run(run_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "running")
        self.assertIsNone(record.get("finished_at"))
        self.assertEqual(record["node_type"], "Output")

    def test_finalize_success_records_value_and_duration(self):
        run_id = self.store.begin(node_id="out", port="value", node_type="Output")
        self.store.record_event(run_id, {"type": "start", "node_id": "out"})
        self.store.record_event(run_id, {"type": "success", "node_id": "out", "value": 42})
        record = self.store.finalize_success(run_id, value=42)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["value"], 42)
        self.assertIsNotNone(record["finished_at"])
        self.assertGreaterEqual(record["duration_ms"], 0.0)

    def test_finalize_error_keeps_error_message(self):
        run_id = self.store.begin(node_id="agent", port="text", node_type="LLMAgent")
        self.store.record_event(run_id, {"type": "error", "node_id": "agent", "error": "boom"})
        record = self.store.finalize_error(run_id, error="boom")
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"], "boom")
        self.assertNotIn("value", record)

    def test_counters_track_node_model_and_tool_events(self):
        run_id = self.store.begin(node_id="out", port="value", node_type="Output")
        for event in (
            {"type": "start", "node_id": "a"},
            {"type": "start", "node_id": "b"},
            {"type": "start", "node_id": "a"},  # duplicate ignored
            {"type": "success", "node_id": "a", "cached": True},
            {"type": "model_call", "node_id": "agent", "model": "nim:foo"},
            {"type": "tool_call", "node_id": "agent", "name": "calc"},
            {"type": "tool_call", "node_id": "agent", "name": "calc"},
        ):
            self.store.record_event(run_id, event)
        record = self.store.finalize_success(run_id)
        self.assertEqual(record["node_count"], 2)
        self.assertEqual(record["cached_nodes"], 1)
        self.assertEqual(record["model_calls"], 1)
        self.assertEqual(record["tool_calls"], 2)

    def test_list_returns_most_recent_first(self):
        first = self.store.begin(node_id="a", port="value", node_type="Text")
        self.store.finalize_success(first, value="x")
        second = self.store.begin(node_id="b", port="value", node_type="Concat")
        self.store.finalize_success(second, value="y")
        listed = self.store.list_runs()
        self.assertEqual([r["run_id"] for r in listed[:2]], [second, first])
        self.assertNotIn("events", listed[0])

    def test_get_run_includes_events(self):
        run_id = self.store.begin(node_id="out", port="value", node_type="Output")
        self.store.record_event(run_id, {"type": "start", "node_id": "out"})
        self.store.finalize_success(run_id)
        record = self.store.get_run(run_id)
        self.assertIn("events", record)
        self.assertEqual(record["events"][0]["type"], "start")

    def test_run_can_store_workflow_snapshot(self):
        workflow = {
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": "Snapshot",
            "node_meta": {"out": {"id": "out", "type": "Output"}},
            "edges": [],
            "entrypoint": {"node_id": "out", "port": "value"},
        }
        run_id = self.store.begin(node_id="out", port="value", node_type="Output", workflow=workflow)
        self.store.finalize_success(run_id)

        record = self.store.get_run(run_id)
        self.assertEqual(record["workflow"]["name"], "Snapshot")
        self.assertEqual(record["workflow"]["entrypoint"], {"node_id": "out", "port": "value"})
        self.assertTrue(self.store.list_runs()[0]["has_workflow"])

    def test_delete_run_removes_file(self):
        run_id = self.store.begin(node_id="out", port="value", node_type="Output")
        self.store.finalize_success(run_id)
        self.assertTrue(self.store.delete_run(run_id))
        self.assertIsNone(self.store.get_run(run_id))


class RunStoreRetentionTests(unittest.TestCase):
    def test_prune_keeps_only_latest_max_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(tmp, max_runs=3)
            ids = []
            for i in range(5):
                run_id = store.begin(node_id=f"n{i}", port="value", node_type="Text")
                store.finalize_success(run_id, value=i)
                ids.append(run_id)
            remaining = {r["run_id"] for r in store.list_runs()}
            self.assertEqual(len(remaining), 3)
            self.assertTrue(remaining.issubset(set(ids[-3:])))


class DeriveStatusTests(unittest.TestCase):
    def test_no_done_event_is_running(self):
        self.assertEqual(derive_status_from_events([{"type": "start"}]), "running")

    def test_done_without_error_is_success(self):
        events = [{"type": "start"}, {"type": "done", "value": 1}]
        self.assertEqual(derive_status_from_events(events), "success")

    def test_error_event_marks_failure(self):
        events = [{"type": "start"}, {"type": "error", "error": "x"}, {"type": "done", "error": "x"}]
        self.assertEqual(derive_status_from_events(events), "error")


if __name__ == "__main__":
    unittest.main()
