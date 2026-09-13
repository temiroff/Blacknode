import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "editor-server"))
import server
from blacknode.graph import Graph
from blacknode.node import Bool, Dict, Int, List, Text, node


class ActuatorSetupEditorTests(unittest.TestCase):
    def setUp(self):
        self.meta = {"type": "ActuatorSetup", "params": {
            "profile_id": "so_arm101", "serial_port": "COM3", "baudrate": 1000000}}
        self.patchers = [
            patch.dict(server._session.node_meta, {"setup-test": self.meta}),
            patch.object(server, "_require_app_permission"),
            patch.object(server, "_template_path", side_effect=lambda slug: slug),
            patch.object(server, "_read_workflow_file", side_effect=lambda _path: {
                "name": "Robot controls", "node_meta": {
                    "robot": {"params": {}}, "control": {"params": {"action": "check"}},
                    "servo_1": {"params": {"servo_id": 1}},
                }, "edges": [],
            }),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_controls_use_saved_selection_and_ephemeral_confirmation(self):
        control = Mock(return_value={"ok": False, "report": "Connect one actuator"})
        node = Mock(_bn_actuator_setup_control=control)
        payload = {"scan_token": "single-use", "confirm_isolated": True, "joint_id": "gripper"}
        with patch.dict(server._NODE_REGISTRY, {"ActuatorSetup": node}):
            result = server.control_node("setup-test", server.NodeControlReq(action="assign", payload=payload))
        control.assert_called_once_with(self.meta["params"], "assign", payload)
        self.assertFalse(result["ok"])
        self.assertNotIn("scan_token", self.meta["params"])

    def test_missing_package_has_actionable_error(self):
        with patch.dict(server._NODE_REGISTRY, {"ActuatorSetup": object()}):
            with self.assertRaises(server.HTTPException) as caught:
                server.control_node("setup-test", server.NodeControlReq(action="inspect"))
        self.assertEqual(caught.exception.status_code, 503)

    def test_calibration_handoff_keeps_hardware_and_remains_disarmed(self):
        with patch.object(server, "queue_open_workflow_tab") as queue:
            result = server.control_node("setup-test", server.NodeControlReq(action="calibrate"))
        workflow = queue.call_args.args[0].workflow
        params = workflow["node_meta"]["robot"]["params"]
        self.assertEqual(params["profile_id"], "so_arm101")
        self.assertEqual(params["serial_port"], "COM3")
        self.assertEqual(params["action"], "check")
        self.assertEqual(workflow["node_meta"]["control"]["params"]["action"], "check")
        self.assertTrue(result["ok"])

    def test_monitor_handoff_resolves_profile_specific_target(self):
        targets = [{"id": "correct", "port": "COM3", "name": "Follower"},
                   {"id": "wrong", "port": "COM4", "name": "Leader"}]
        with patch.object(server, "_local_robot_monitor_targets", return_value=targets) as resolve, \
                patch.object(server, "queue_open_workflow_tab") as queue:
            server.control_node("setup-test", server.NodeControlReq(action="monitor"))
        resolve.assert_called_once_with("so_arm101")
        workflow = queue.call_args.args[0].workflow
        self.assertEqual(workflow["node_meta"]["robot"]["params"]["robot_id"], "correct")

    def test_disconnected_monitor_does_not_open_wrong_robot(self):
        with patch.object(server, "_local_robot_monitor_targets", return_value=[]), \
                patch.object(server, "queue_open_workflow_tab") as queue:
            with self.assertRaises(server.HTTPException):
                server.control_node("setup-test", server.NodeControlReq(action="monitor"))
        queue.assert_not_called()


class ActuatorSetupCanvasTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(graph=Graph(), node_meta={}, metadata={}, entrypoint=None)
        for patcher in [patch.object(server, "_session", self.session), patch.object(server, "_save"),
                        patch.object(server, "_require_app_permission"), patch.dict(server._NODE_REGISTRY)]:
            patcher.start()
            self.addCleanup(patcher.stop)
        # Exercise editor routing with the package's public port contract, even
        # in a core-only checkout. Provider behavior is tested by its package.
        @node(name="ActuatorSetup",
              inputs={"profile_id": Text(default=""), "serial_port": Text(default=""), "baudrate": Int(default=1000000)},
              outputs={"ok": Bool, "assigned": Bool, "actuators": List, "profile": Dict, "bus": Dict, "report": Text})
        def scanner(_ctx):
            return {}
        server._NODE_REGISTRY["ActuatorSetup"]._bn_actuator_setup_control = Mock()

        @node(name="ActuatorServoSetup",
              inputs={"bus": Dict, "servo_id": Int(default=1), "profile_id": Text(default="")},
              outputs={"report": Text})
        def servo(_ctx):
            return {}

        self.scanner = server.add_node(server.AddNodeReq(type_name="ActuatorSetup",
            params={"serial_port": "COM3", "baudrate": 1000000}, pos=[80, 80]))["id"]

    def scan(self, *ids):
        return server._sync_actuator_setup_cards(self.scanner, {
            "ok": bool(ids), "actuators": [{"servo_id": value, "model": "Mock"} for value in ids],
            "scan_token": "token", "scanned_at": 123,
        })

    def children(self):
        return {meta["params"]["servo_id"]: key for key, meta in self.session.node_meta.items()
                if meta["type"] == "ActuatorServoSetup"}

    def test_scan_creates_connected_cards_and_rescan_preserves_configuration(self):
        first = self.scan(2, 3, 5)
        children = self.children()
        self.assertEqual(set(children), {2, 3, 5})
        self.session.node_meta[children[2]]["params"]["profile_id"] = "my_robot"
        second = self.scan(2, 5, 6)
        self.assertEqual(self.children()[2], children[2])
        self.assertEqual(self.session.node_meta[children[2]]["params"]["profile_id"], "my_robot")
        self.assertFalse(second["node_outputs"][children[3]]["present"])
        self.assertEqual(second["node_outputs"][children[3]]["scan_token"], "")
        self.assertEqual(len(self.session.graph._edges), 4)
        for edge in self.session.graph._edges:
            self.assertEqual((edge["from"], edge["from_port"], edge["to_port"]), (self.scanner, "bus", "bus"))
        self.assertEqual(first["node_outputs"][children[2]]["actuator"]["servo_id"], 2)
        self.assertNotIn("scan_token", self.session.node_meta[children[2]]["params"])
        graph = second["graph"]
        report = server.validate_bn_workflow({"kind": "blacknode.workflow", "schema_version": 1,
            "name": "USB actuator setup", "entrypoint": {"node_id": self.scanner, "port": "report"},
            "node_meta": {meta["id"]: meta for meta in graph["nodes"]}, "edges": graph["edges"]})
        self.assertTrue(report.ok, report.to_dict())

    def test_child_control_uses_its_own_id_and_connected_scanner(self):
        self.scan(2)
        child = self.children()[2]
        control = Mock(return_value={"ok": False, "report": "Isolate this actuator"})
        with patch.object(server._NODE_REGISTRY["ActuatorSetup"], "_bn_actuator_setup_control", control):
            server.control_node(child, server.NodeControlReq(action="assign", payload={"new_id": 6}))
        self.assertEqual(control.call_args.args[0], {"serial_port": "COM3", "baudrate": 1000000, "servo_id": 2})

    def test_assignment_reuses_selected_card_and_removes_duplicate_destination(self):
        self.scan(1, 6)
        original = self.children()
        control = Mock(return_value={"ok": True, "assigned": True, "new_id": 6,
            "actuators": [{"servo_id": 6}]})
        with patch.object(server._NODE_REGISTRY["ActuatorSetup"], "_bn_actuator_setup_control", control):
            result = server.control_node(original[1], server.NodeControlReq(action="assign"))
        self.assertEqual(self.children(), {6: original[1]})
        self.assertNotIn(original[6], self.session.graph._nodes)
        self.assertIn("setup_canvas", result["outputs"])

    def test_scan_result_cannot_mutate_a_different_workflow(self):
        def changed(*args):
            self.session.graph = Graph()
            return {"ok": True, "actuators": [{"servo_id": 1}]}
        with patch.object(server._NODE_REGISTRY["ActuatorSetup"], "_bn_actuator_setup_control", changed):
            with self.assertRaises(server.HTTPException) as caught:
                server.control_node(self.scanner, server.NodeControlReq(action="scan"))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.children(), {})

    def test_disconnected_servo_cannot_control_any_bus(self):
        child = server.add_node(server.AddNodeReq(type_name="ActuatorServoSetup", params={"servo_id": 1}))["id"]
        with self.assertRaises(server.HTTPException):
            server.control_node(child, server.NodeControlReq(action="scan"))
