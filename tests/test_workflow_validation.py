from __future__ import annotations

import unittest

from blacknode.workflow import validate_workflow


def node(
    node_id: str,
    type_name: str,
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    input_types: dict[str, str] | None = None,
    output_types: dict[str, str] | None = None,
    params: dict | None = None,
    subgraph: dict | None = None,
) -> dict:
    meta = {
        "id": node_id,
        "type": type_name,
        "params": params or {},
        "pos": [0, 0],
        "inputs": inputs or [],
        "outputs": outputs or [],
        "input_types": input_types or {},
        "output_types": output_types or {},
        "input_defaults": {},
    }
    if subgraph is not None:
        meta["subgraph"] = subgraph
    return meta


def workflow(node_meta: dict[str, dict], edges: list[dict], **extra) -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Test",
        "saved_at": "2026-05-20T12:00:00",
        "node_meta": node_meta,
        "edges": edges,
        **extra,
    }


def error_codes(report) -> set[str]:
    return {issue.code for issue in report.errors}


class WorkflowValidationTests(unittest.TestCase):
    def test_valid_workflow(self):
        data = workflow(
            {
                "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}),
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
        )

        report = validate_workflow(data)

        self.assertTrue(report.ok, report.to_dict())

    def test_missing_source_node(self):
        data = workflow(
            {"out": node("out", "Output", inputs=["value"], input_types={"value": "Any"})},
            [{"from": "missing", "from_port": "value", "to": "out", "to_port": "value"}],
        )

        report = validate_workflow(data)

        self.assertIn("missing_source_node", error_codes(report))

    def test_invalid_ports(self):
        data = workflow(
            {
                "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}),
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [{"from": "text", "from_port": "missing", "to": "out", "to_port": "also_missing"}],
        )

        report = validate_workflow(data)

        self.assertIn("invalid_source_port", error_codes(report))
        self.assertIn("invalid_target_port", error_codes(report))

    def test_incompatible_port_types(self):
        data = workflow(
            {
                "text": node("text", "Text", outputs=["value"], output_types={"value": "Text"}),
                "flag": node("flag", "Bool", inputs=["value"], output_types={}, input_types={"value": "Bool"}),
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [
                {"from": "text", "from_port": "value", "to": "flag", "to_port": "value"},
                {"from": "flag", "from_port": "value", "to": "out", "to_port": "value"},
            ],
        )

        report = validate_workflow(data)

        self.assertIn("incompatible_port_types", error_codes(report))

    def test_duplicate_node_ids(self):
        data = workflow(
            {
                "text_a": node("same", "Text", outputs=["value"], output_types={"value": "Text"}),
                "text_b": node("same", "Text", outputs=["value"], output_types={"value": "Text"}),
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [],
        )

        report = validate_workflow(data)

        codes = error_codes(report)
        self.assertIn("duplicate_node_id", codes)
        self.assertIn("node_id_mismatch", codes)

    def test_missing_output_node(self):
        data = workflow(
            {"text": node("text", "Text", outputs=["value"], output_types={"value": "Text"})},
            [],
        )

        report = validate_workflow(data)

        self.assertIn("missing_output_node", error_codes(report))

    def test_missing_subgraph_output_node(self):
        data = workflow(
            {
                "subnet": node(
                    "subnet",
                    "Subnet",
                    inputs=[],
                    outputs=["value"],
                    output_types={"value": "Text"},
                    subgraph={"node_meta": {}, "edges": []},
                ),
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [{"from": "subnet", "from_port": "value", "to": "out", "to_port": "value"}],
        )

        report = validate_workflow(data)

        self.assertIn("missing_subgraph_output_node", error_codes(report))

    def test_runtime_status_is_not_portable(self):
        text = node("text", "Text", outputs=["value"], output_types={"value": "Text"})
        text["cookResult"] = "hello"
        data = workflow(
            {
                "text": text,
                "out": node("out", "Output", inputs=["value"], input_types={"value": "Any"}),
            },
            [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
        )

        report = validate_workflow(data)

        self.assertIn("runtime_status_in_workflow", error_codes(report))


if __name__ == "__main__":
    unittest.main()
