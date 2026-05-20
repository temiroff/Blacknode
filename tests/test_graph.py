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


if __name__ == "__main__":
    unittest.main()
