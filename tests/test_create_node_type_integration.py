from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import blacknode as bn
from blacknode.learned import registry
from blacknode.mcp import tools as t


RUN_DOCKER_TESTS = os.environ.get("BLACKNODE_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_DOCKER_TESTS, "set BLACKNODE_INTEGRATION_TESTS=1 to run Docker tests")
class CreateNodeTypeIntegrationTests(unittest.TestCase):
    def tearDown(self):
        registry.unregister_one("McpDockerEcho")

    def test_create_node_type_then_cook_via_graph_and_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {
                    "BLACKNODE_LEARNED_DIR": str(Path(tmp)),
                    "BLACKNODE_CONFIG_DIR": str(Path(tmp) / "config"),
                    "BLACKNODE_LEARNED_NODES_CONSENT": "1",
                },
                clear=False,
            ), patch.object(t, "_notify_learned_node_event"):
                result = t.create_node_type(
                    name="McpDockerEcho",
                    description="Echo text through a learned Docker-backed node.",
                    inputs=["text:Text"],
                    outputs=["result:Text"],
                    code="def run(text):\n    return {'result': text + '!'}\n",
                    requires_network=False,
                )

                self.assertEqual(result["status"], "created")
                self.assertIn("McpDockerEcho", bn._NODE_REGISTRY)

                graph = bn.Graph()
                node = graph.node("McpDockerEcho", text="hello")
                self.assertEqual(graph.cook(node, "result"), "hello!")


if __name__ == "__main__":
    unittest.main()
