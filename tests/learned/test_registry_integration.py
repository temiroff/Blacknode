from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

import blacknode as bn
from blacknode.learned import registry


RUN_DOCKER_TESTS = os.environ.get("BLACKNODE_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_DOCKER_TESTS, "set BLACKNODE_INTEGRATION_TESTS=1 to run Docker tests")
class LearnedRegistryIntegrationTests(unittest.TestCase):
    def test_manual_hello_world_loads_registers_and_cooks_via_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "HelloWorld"
            node_dir.mkdir()
            (node_dir / "node.py").write_text(
                "def run():\n    return {'ok': True}\n",
                encoding="utf-8",
            )
            (node_dir / "manifest.json").write_text(
                json.dumps({
                    "name": "HelloWorld",
                    "description": "Return a fixed hello-world proof value.",
                    "inputs": [],
                    "outputs": ["ok:Bool"],
                    "permissions": {"network": False},
                    "created_at": "2026-05-24T18:00:00Z",
                    "created_by": "test",
                    "schema_version": 1,
                }),
                encoding="utf-8",
            )

            registry.register_one("HelloWorld", learned_dir=tmp)
            self.addCleanup(registry.unregister_one, "HelloWorld")

            fn = bn._NODE_REGISTRY["HelloWorld"]
            self.assertEqual(fn._bn_category, "Learned")
            self.assertEqual(fn._bn_source, "learned")

            graph = bn.Graph()
            node = graph.node("HelloWorld")

            self.assertTrue(graph.cook(node, "ok"))


if __name__ == "__main__":
    unittest.main()
