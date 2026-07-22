"""Graph deployment: snapshotting, classification, and process lifecycle.

Deployments spawn real detached processes, so the tests that need one use a
trivially short script rather than a real graph. The graph-shaped tests stay
pure: classification and entrypoint inference never start anything.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

import blacknode  # noqa: F401,E402  triggers package discovery
from blacknode.deployments import (  # noqa: E402
    KIND_JOB,
    KIND_SERVICE,
    STATE_EXITED,
    STATE_FAILED,
    STATE_RUNNING,
    STATE_STOPPED,
    DeploymentError,
    DeploymentStore,
    classify,
    process_alive,
    resolve_entrypoint,
)
from blacknode.node import Any as AnyPort  # noqa: E402
from blacknode.node import Bool, Enum, Image, Text, _NODE_REGISTRY  # noqa: E402
from blacknode.node import node as bn_node  # noqa: E402
from blacknode.workflow import WorkflowRunError  # noqa: E402


# A live-capable node defined here rather than borrowed from a package: core
# ships none, and reaching for blacknode-perception's camera made these tests
# fail wherever packages are not installed - which is exactly how core CI runs.
LIVE_NODE = "DeploymentTestLiveSource"

if LIVE_NODE not in _NODE_REGISTRY:
    @bn_node(
        name=LIVE_NODE,
        live=True,
        inputs={"trigger": AnyPort, "action": Enum(["start", "stop"], default="start")},
        outputs={"preview": Image, "streaming": Bool, "report": Text},
    )
    def _deployment_test_live_source(ctx: dict) -> dict:
        return {"preview": "", "streaming": True, "report": "test live source"}


def node(node_id: str, node_type: str, params: dict | None = None) -> dict:
    """Build valid node_meta straight from the registry."""
    fn = _NODE_REGISTRY[node_type]
    return {
        "id": node_id,
        "type": node_type,
        "params": dict(params or {}),
        "pos": [0, 0],
        "inputs": list(getattr(fn, "_bn_inputs", [])),
        "outputs": list(getattr(fn, "_bn_outputs", [])),
        "input_types": dict(getattr(fn, "_bn_input_types", {})),
        "output_types": dict(getattr(fn, "_bn_output_types", {})),
        "input_defaults": dict(getattr(fn, "_bn_input_defaults", {})),
    }


def workflow(node_meta: dict, edges: list | None = None, **extra) -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Test graph",
        "node_meta": node_meta,
        "edges": edges or [],
        **extra,
    }


class ClassificationTests(unittest.TestCase):
    def test_graph_with_a_live_node_is_a_service(self):
        wf = workflow({"cam": node("cam", LIVE_NODE)})
        self.assertEqual(classify(wf), KIND_SERVICE)

    def test_graph_without_live_nodes_is_a_job(self):
        wf = workflow({"out": node("out", "Output")})
        self.assertEqual(classify(wf), KIND_JOB)

    def test_a_live_node_set_to_stop_does_not_make_a_service(self):
        # Deploying a graph whose stream node is set to 'stop' should not
        # produce a process that hangs forever waiting on nothing.
        wf = workflow({"cam": node("cam", LIVE_NODE, {"action": "stop"})})
        self.assertEqual(classify(wf), KIND_JOB)


class EntrypointTests(unittest.TestCase):
    def test_explicit_entrypoint_wins(self):
        wf = workflow(
            {"a": node("a", "Output"), "b": node("b", "Output")},
            entrypoint={"node_id": "b", "port": "value"},
        )
        self.assertEqual(resolve_entrypoint(wf), {"node_id": "b", "port": "value"})

    def test_single_output_node_is_used(self):
        wf = workflow({"out": node("out", "Output")})
        self.assertEqual(resolve_entrypoint(wf), {"node_id": "out", "port": "value"})

    def test_publisher_graph_with_no_output_node_still_resolves(self):
        # The flagship case: publish a camera and leave it running. There is
        # no Output node, so workflow.infer_entrypoint would refuse.
        wf = workflow({"cam": node("cam", LIVE_NODE)})
        resolved = resolve_entrypoint(wf)
        self.assertEqual(resolved["node_id"], "cam")
        self.assertTrue(resolved["port"])

    def test_live_sink_is_preferred_over_a_dead_end(self):
        wf = workflow(
            {
                "cam": node("cam", LIVE_NODE),
                "note": node("note", "Text"),
            },
        )
        self.assertEqual(resolve_entrypoint(wf)["node_id"], "cam")

    def test_ambiguous_graph_explains_how_to_fix_it(self):
        wf = workflow({
            "a": node("a", LIVE_NODE),
            "b": node("b", LIVE_NODE),
        })
        with self.assertRaises(WorkflowRunError) as ctx:
            resolve_entrypoint(wf)
        self.assertIn("entrypoint", str(ctx.exception))

    def test_empty_graph_is_rejected(self):
        with self.assertRaises(WorkflowRunError):
            resolve_entrypoint(workflow({}))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DeploymentStore(Path(self._tmp.name) / "deployments")

    def tearDown(self):
        try:
            self.store.stop_all()
        finally:
            self._tmp.cleanup()

    def test_snapshot_is_frozen_at_deploy_time(self):
        wf = workflow({"out": node("out", "Output")}, name="Original")
        record = self.store.create(wf, name="Original", autostart=False)

        wf["node_meta"]["extra"] = node("extra", "Output")
        wf["name"] = "Edited after deploy"

        snapshot = self.store.snapshot(record["id"])
        self.assertEqual(snapshot["name"], "Original")
        self.assertNotIn("extra", snapshot["node_meta"])
        self.assertEqual(record["node_count"], 1)

    def test_same_graph_hashes_the_same_and_a_change_does_not(self):
        wf = workflow({"out": node("out", "Output")})
        first = self.store.create(wf, autostart=False)
        second = self.store.create(wf, autostart=False)
        self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])
        self.assertNotEqual(first["id"], second["id"])

        changed = json.loads(json.dumps(wf))
        changed["node_meta"]["out"]["params"]["label"] = "different"
        third = self.store.create(changed, autostart=False)
        self.assertNotEqual(first["snapshot_hash"], third["snapshot_hash"])

    def test_undeployable_graph_is_reported_not_raised_as_a_crash(self):
        with self.assertRaises(DeploymentError):
            self.store.create(workflow({}), autostart=False)

    def test_created_without_autostart_is_stopped_and_startable(self):
        record = self.store.create(workflow({"out": node("out", "Output")}), autostart=False)
        self.assertEqual(record["state"], STATE_STOPPED)
        self.assertIsNone(record["pid"])

    def test_deleting_removes_the_record_and_its_directory(self):
        record = self.store.create(workflow({"out": node("out", "Output")}), autostart=False)
        directory = self.store.root / record["id"]
        self.assertTrue(directory.exists())

        self.assertTrue(self.store.delete(record["id"]))
        self.assertFalse(directory.exists())
        self.assertIsNone(self.store.get(record["id"]))
        self.assertFalse(self.store.delete(record["id"]))

    def test_list_is_newest_first(self):
        first = self.store.create(workflow({"out": node("out", "Output")}), name="first", autostart=False)
        time.sleep(0.01)
        second = self.store.create(workflow({"out": node("out", "Output")}), name="second", autostart=False)
        ids = [item["id"] for item in self.store.list()]
        self.assertEqual(ids.index(second["id"]), 0)
        self.assertIn(first["id"], ids)


class ProcessLifecycleTests(unittest.TestCase):
    """Exercise real spawn/stop/reconcile against a stand-in script."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DeploymentStore(Path(self._tmp.name) / "deployments")

    def tearDown(self):
        try:
            self.store.stop_all()
        finally:
            self._tmp.cleanup()

    def _record_with_script(self, source: str, *, kind: str) -> dict:
        record = self.store.create(
            workflow({"out": node("out", "Output")}),
            name=kind,
            autostart=False,
        )
        # Replace the generated graph script: this test is about supervision,
        # not about cooking a graph.
        self.store.script_path(record["id"]).write_text(source, encoding="utf-8")
        record["kind"] = kind
        self.store._write(record)
        return record

    def test_a_finished_job_reads_as_exited_not_failed(self):
        record = self._record_with_script("print('done')\n", kind=KIND_JOB)
        started = self.store.start(record["id"])
        self.assertEqual(started["state"], STATE_RUNNING)

        final = self._await_settled(record["id"])
        self.assertEqual(final["state"], STATE_EXITED)
        self.assertIn("done", self.store.logs(record["id"]))

    def test_a_service_that_ends_on_its_own_reads_as_failed(self):
        # A service is supposed to stay up; ending is a fault worth surfacing.
        record = self._record_with_script("print('bye')\n", kind=KIND_SERVICE)
        self.store.start(record["id"])

        final = self._await_settled(record["id"])
        self.assertEqual(final["state"], STATE_FAILED)
        self.assertTrue(final["error"])

    def test_a_crashing_job_reports_its_exit_code(self):
        record = self._record_with_script("import sys; sys.exit(3)\n", kind=KIND_JOB)
        self.store.start(record["id"])

        final = self._await_settled(record["id"])
        self.assertEqual(final["state"], STATE_FAILED)
        self.assertEqual(final["exit_code"], 3)

    def test_a_running_service_survives_and_stops_on_request(self):
        record = self._record_with_script(
            "import time\nwhile True: time.sleep(0.1)\n", kind=KIND_SERVICE
        )
        started = self.store.start(record["id"])
        pid = started["pid"]
        self.assertTrue(process_alive(pid))

        # Still running a moment later: it is a service, not a one-shot.
        time.sleep(0.6)
        self.assertEqual(self.store.get(record["id"])["state"], STATE_RUNNING)

        stopped = self.store.stop(record["id"])
        self.assertEqual(stopped["state"], STATE_STOPPED)
        self.assertIsNone(stopped["pid"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process_alive(pid):
            time.sleep(0.1)
        self.assertFalse(process_alive(pid))

    def test_state_is_rederived_from_the_os_after_a_restart(self):
        record = self._record_with_script("print('quick')\n", kind=KIND_JOB)
        self.store.start(record["id"])
        self._await_settled(record["id"])

        # A fresh store has no Popen handles, exactly like a restarted editor
        # server. It must still not report a dead deployment as running.
        reopened = DeploymentStore(self.store.root)
        current = reopened.get(record["id"])
        self.assertNotEqual(current["state"], STATE_RUNNING)
        self.assertIsNone(current["pid"])

    def test_starting_an_unknown_deployment_is_an_error(self):
        with self.assertRaises(DeploymentError):
            self.store.start("does-not-exist")

    def _await_settled(self, deployment_id: str, timeout: float = 20.0) -> dict:
        deadline = time.monotonic() + timeout
        record = self.store.get(deployment_id)
        while time.monotonic() < deadline and record["state"] == STATE_RUNNING:
            time.sleep(0.1)
            record = self.store.get(deployment_id)
        self.assertNotEqual(record["state"], STATE_RUNNING, "deployment never settled")
        return record


class ProcessProbeTests(unittest.TestCase):
    def test_probing_never_kills_the_process_being_probed(self):
        # os.kill(pid, 0) routes to TerminateProcess on Windows, so a naive
        # liveness probe would kill what it inspects. This must not.
        own = __import__("os").getpid()
        for _ in range(3):
            self.assertTrue(process_alive(own))

    def test_absent_and_invalid_pids_are_not_alive(self):
        self.assertFalse(process_alive(0))
        self.assertFalse(process_alive(-1))


if __name__ == "__main__":
    unittest.main()
