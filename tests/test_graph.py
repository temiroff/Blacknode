from __future__ import annotations

import unittest

import blacknode as bn


class GraphCookTests(unittest.TestCase):
    def test_top_level_cook_runs_fresh_each_time(self):
        calls = {"count": 0}

        @bn.node(inputs=[], outputs=["value:Int"], name="FreshCookCounter")
        def counter(ctx: dict) -> dict:
            calls["count"] += 1
            return {"value": calls["count"]}

        graph = bn.Graph()
        node = graph.node("FreshCookCounter")

        self.assertEqual(graph.cook(node, "value"), 1)
        self.assertEqual(graph.cook(node, "value"), 2)

    def test_runtime_context_reaches_nodes_without_serializing(self):
        @bn.node(inputs=[], outputs=["value:Text"], name="RuntimeContextProbe")
        def probe(ctx: dict) -> dict:
            return {"value": ctx["__probe__"]()}

        graph = bn.Graph()
        graph.set_runtime_context(__probe__=lambda: "live service")
        node = graph.node("RuntimeContextProbe")

        self.assertEqual(graph.cook(node, "value"), "live service")
        self.assertNotIn("runtime_context", graph.to_dict())


if __name__ == "__main__":
    unittest.main()
