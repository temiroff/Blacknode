from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from blacknode.mcp import tools as t


class ListNodesTests(unittest.TestCase):
    def test_includes_core_node_types(self):
        result = t.list_nodes()
        self.assertGreater(result["count"], 0)
        names = {entry["type"] for entry in result["nodes"]}
        for expected in ("Text", "Concat", "Output", "LLMAgent"):
            self.assertIn(expected, names)

    def test_groups_by_category(self):
        result = t.list_nodes()
        self.assertIn("Values", result["by_category"])
        self.assertIn("AI", result["by_category"])


class GetNodeSchemaTests(unittest.TestCase):
    def test_concat_ports(self):
        schema = t.get_node_schema("Concat")
        input_names = [port["name"] for port in schema["inputs"]]
        output_names = [port["name"] for port in schema["outputs"]]
        self.assertEqual(input_names, ["a", "b"])
        self.assertEqual(output_names, ["value"])
        self.assertEqual(schema["outputs"][0]["type"], "Text")

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            t.get_node_schema("DoesNotExist")

    def test_subnet_marked_advanced(self):
        schema = t.get_node_schema("Subnet")
        self.assertTrue(schema.get("advanced"))


class CreateWorkflowTests(unittest.TestCase):
    def test_scaffold_contains_output(self):
        wf = t.create_workflow(name="Demo", description="hello")
        self.assertEqual(wf["kind"], "blacknode.workflow")
        self.assertEqual(wf["schema_version"], 1)
        self.assertIn("out", wf["node_meta"])
        self.assertEqual(wf["node_meta"]["out"]["type"], "Output")
        self.assertEqual(wf["entrypoint"], {"node_id": "out", "port": "value"})
        self.assertEqual(wf["metadata"]["description"], "hello")


class AddNodeTests(unittest.TestCase):
    def test_adds_text_node(self):
        wf = t.create_workflow()
        result = t.add_node(wf, "Text", params={"value": "Hi"})
        new_id = result["node_id"]
        self.assertIn(new_id, result["workflow"]["node_meta"])
        node = result["workflow"]["node_meta"][new_id]
        self.assertEqual(node["type"], "Text")
        self.assertEqual(node["params"], {"value": "Hi"})
        self.assertEqual(node["outputs"], ["value"])

    def test_does_not_mutate_input(self):
        wf = t.create_workflow()
        before = len(wf["node_meta"])
        t.add_node(wf, "Text", params={"value": "x"})
        self.assertEqual(len(wf["node_meta"]), before)

    def test_explicit_node_id(self):
        wf = t.create_workflow()
        result = t.add_node(wf, "Text", node_id="greeting")
        self.assertEqual(result["node_id"], "greeting")

    def test_duplicate_id_rejected(self):
        wf = t.create_workflow()
        wf = t.add_node(wf, "Text", node_id="a")["workflow"]
        with self.assertRaises(ValueError):
            t.add_node(wf, "Text", node_id="a")

    def test_unknown_type_rejected(self):
        wf = t.create_workflow()
        with self.assertRaises(ValueError):
            t.add_node(wf, "NotARealNodeType")

    def test_subnet_rejected(self):
        wf = t.create_workflow()
        with self.assertRaises(ValueError):
            t.add_node(wf, "Subnet")


class ConnectNodesTests(unittest.TestCase):
    def _wf_with_two_texts_and_concat(self) -> dict:
        wf = t.create_workflow()
        wf = t.add_node(wf, "Text", params={"value": "a"}, node_id="a")["workflow"]
        wf = t.add_node(wf, "Text", params={"value": "b"}, node_id="b")["workflow"]
        wf = t.add_node(wf, "Concat", node_id="c")["workflow"]
        return wf

    def test_compatible_edge_added(self):
        wf = self._wf_with_two_texts_and_concat()
        result = t.connect_nodes(wf, "a", "value", "c", "a")
        edges = result["workflow"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["from"], "a")
        self.assertEqual(edges[0]["to_port"], "a")

    def test_missing_source_node(self):
        wf = self._wf_with_two_texts_and_concat()
        with self.assertRaises(ValueError):
            t.connect_nodes(wf, "ghost", "value", "c", "a")

    def test_missing_source_port(self):
        wf = self._wf_with_two_texts_and_concat()
        with self.assertRaises(ValueError) as ctx:
            t.connect_nodes(wf, "a", "nope", "c", "a")
        self.assertIn("output port", str(ctx.exception))

    def test_incompatible_types_rejected(self):
        wf = t.create_workflow()
        wf = t.add_node(wf, "Bool", params={"value": True}, node_id="b1")["workflow"]
        wf = t.add_node(wf, "Concat", node_id="c")["workflow"]
        with self.assertRaises(ValueError) as ctx:
            t.connect_nodes(wf, "b1", "value", "c", "a")
        self.assertIn("Incompatible", str(ctx.exception))


class ValidateAndExportTests(unittest.TestCase):
    def _hello_workflow(self) -> dict:
        wf = t.create_workflow(name="Hello")
        wf = t.add_node(wf, "Text", params={"value": "Hello"}, node_id="a")["workflow"]
        wf = t.add_node(wf, "Text", params={"value": " World"}, node_id="b")["workflow"]
        wf = t.add_node(wf, "Concat", node_id="c")["workflow"]
        wf = t.connect_nodes(wf, "a", "value", "c", "a")["workflow"]
        wf = t.connect_nodes(wf, "b", "value", "c", "b")["workflow"]
        wf = t.connect_nodes(wf, "c", "value", "out", "value")["workflow"]
        return wf

    def test_built_workflow_validates(self):
        wf = self._hello_workflow()
        report = t.validate_workflow_tool(wf)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["errors"], [])

    def test_export_python_includes_blacknode_import(self):
        wf = self._hello_workflow()
        source = t.export_python_tool(wf)["source"]
        self.assertIn("import blacknode as bn", source)
        self.assertIn("Concat", source)

    def test_run_workflow_returns_value(self):
        wf = self._hello_workflow()
        result = t.run_workflow_tool(wf)
        self.assertEqual(result.get("value"), "Hello World")
        self.assertTrue(any(e.get("type") == "run_finish" for e in result["events"]))

    def test_invalid_workflow_run_returns_error_payload(self):
        wf = t.create_workflow()
        wf["node_meta"] = {}
        wf.pop("entrypoint", None)
        result = t.run_workflow_tool(wf)
        self.assertFalse(result.get("ok"))
        self.assertIn("error", result)


class ListTemplatesTests(unittest.TestCase):
    def test_returns_shipped_templates(self):
        result = t.list_templates()
        self.assertGreater(result["count"], 0)
        names = {entry["name"] for entry in result["templates"]}
        self.assertIn("Text Pipeline", names)

    def test_loads_template_workflow_by_slug(self):
        workflow = t.load_template_workflow("nvidia-nim-mcp-demo")
        self.assertEqual(workflow["name"], "NVIDIA NIM MCP Demo")
        self.assertTrue(t.validate_workflow_tool(workflow)["ok"])


class CreateEditorWorkflowTabTests(unittest.TestCase):
    def test_posts_editor_action(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {
                        "id": "action-1",
                        "type": "new_workflow_tab",
                        "payload": {"name": "MCP Tab"},
                    },
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.create_editor_workflow_tab("MCP Tab", editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"]["type"], "new_workflow_tab")
        self.assertEqual(requests[0][0].full_url, "http://editor/editor/actions/workflow-tab")
        self.assertEqual(json.loads(requests[0][0].data.decode("utf-8")), {"name": "MCP Tab"})
        self.assertEqual(requests[0][1], 3)

    def test_posts_populated_editor_tab_action(self):
        workflow = t.create_workflow("Demo")
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {
                        "id": "action-2",
                        "type": "open_workflow_tab",
                        "payload": {"name": "Demo"},
                    },
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.open_workflow_in_editor_tab(workflow, editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual(result["action"]["type"], "open_workflow_tab")
        self.assertEqual(requests[0][0].full_url, "http://editor/editor/actions/open-workflow-tab")
        payload = json.loads(requests[0][0].data.decode("utf-8"))
        self.assertEqual(payload["name"], "Demo")
        self.assertEqual(payload["workflow"]["name"], "Demo")
        self.assertTrue(payload["organize"])

    def test_posts_cook_editor_node_action(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {
                        "id": "action-3",
                        "type": "cook_node",
                        "payload": {"node_id": "out", "port": "value"},
                    },
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.cook_editor_node(editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"]["type"], "cook_node")
        self.assertEqual(requests[0][0].full_url, "http://editor/editor/actions/cook-node")
        self.assertEqual(
            json.loads(requests[0][0].data.decode("utf-8")),
            {"node_id": "out", "port": "value"},
        )

    def test_runs_template_in_editor_and_cooks_output(self):
        requests = []

        class FakeResponse:
            def __init__(self, action_type: str):
                self.action_type = action_type

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {
                        "id": self.action_type,
                        "type": self.action_type,
                        "payload": {},
                    },
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            if req.full_url.endswith("/editor/actions/open-workflow-tab"):
                return FakeResponse("open_workflow_tab")
            if req.full_url.endswith("/editor/actions/cook-node"):
                return FakeResponse("cook_node")
            raise AssertionError(f"Unexpected URL: {req.full_url}")

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.run_template_in_editor(
                "nvidia-nim-mcp-demo",
                name="NIM Test",
                editor_url="http://editor",
                cook=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["template"]["name"], "NVIDIA NIM MCP Demo")
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual(result["open"]["action"]["type"], "open_workflow_tab")
        self.assertEqual(result["cook"]["action"]["type"], "cook_node")
        self.assertEqual([req.full_url for req, _ in requests], [
            "http://editor/editor/actions/open-workflow-tab",
            "http://editor/editor/actions/cook-node",
        ])
        open_payload = json.loads(requests[0][0].data.decode("utf-8"))
        self.assertEqual(open_payload["name"], "NIM Test")
        self.assertTrue(open_payload["organize"])
        self.assertEqual(open_payload["workflow"]["name"], "NVIDIA NIM MCP Demo")
        self.assertEqual(
            json.loads(requests[1][0].data.decode("utf-8")),
            {"node_id": "out", "port": "value"},
        )

    def test_gets_editor_graph(self):
        requests = []

        class FakeResponse:
            def __init__(self, body: dict):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(self.body).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            if req.full_url.endswith("/graph"):
                return FakeResponse({
                    "nodes": [{"id": "out", "type": "Output"}],
                    "edges": [],
                })
            return FakeResponse({"ok": True, "errors": [], "warnings": []})

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.get_editor_graph(editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["node_count"], 1)
        self.assertEqual(result["edge_count"], 0)
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual([req.full_url for req, _ in requests], [
            "http://editor/graph",
            "http://editor/validate",
        ])

    def test_saves_editor_workflow(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"ok": True, "slug": "MCP_Saved_Graph"}).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.save_editor_workflow("MCP Saved Graph", editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["slug"], "MCP_Saved_Graph")
        self.assertEqual(requests[0][0].full_url, "http://editor/workflows")
        self.assertEqual(
            json.loads(requests[0][0].data.decode("utf-8")),
            {"name": "MCP Saved Graph", "previous_slug": None},
        )

    def test_lists_saved_workflows(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps([{"slug": "demo", "name": "Demo", "saved_at": ""}]).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.list_saved_workflows(editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["workflows"][0]["slug"], "demo")
        self.assertEqual(requests[0][0].full_url, "http://editor/workflows")

    def test_posts_load_saved_workflow_action(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {
                        "id": "action-4",
                        "type": "load_saved_workflow_tab",
                        "payload": {"slug": "demo", "organize": True},
                    },
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            result = t.load_saved_workflow_in_editor("demo", editor_url="http://editor")

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"]["type"], "load_saved_workflow_tab")
        self.assertEqual(requests[0][0].full_url, "http://editor/editor/actions/load-saved-workflow-tab")
        self.assertEqual(
            json.loads(requests[0][0].data.decode("utf-8")),
            {"slug": "demo", "name": None, "organize": True},
        )

    def test_posts_editor_management_actions(self):
        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "action": {"id": "action", "type": "queued", "payload": {}},
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(t.urllib_request, "urlopen", side_effect=fake_urlopen):
            self.assertTrue(t.organize_editor_graph(editor_url="http://editor")["ok"])
            self.assertTrue(t.rename_editor_tab("Renamed", editor_url="http://editor")["ok"])
            self.assertTrue(t.close_editor_tab(editor_url="http://editor")["ok"])

        self.assertEqual([req.full_url for req, _ in requests], [
            "http://editor/editor/actions/organize-graph",
            "http://editor/editor/actions/rename-tab",
            "http://editor/editor/actions/close-tab",
        ])
        self.assertEqual(json.loads(requests[1][0].data.decode("utf-8")), {"name": "Renamed"})


if __name__ == "__main__":
    unittest.main()
