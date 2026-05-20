from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
