from __future__ import annotations

import unittest

from blacknode.node import _NODE_REGISTRY


class NvidiaNodeTests(unittest.TestCase):
    def test_blueprint_plan_selects_video_and_retrieval_stack(self):
        result = _NODE_REGISTRY["NVIDIABlueprintPlan"]({
            "goal": "Build video search with retrieval and benchmark deployment latency."
        })

        self.assertIn("NVIDIA NIM", result["technologies"])
        self.assertIn("Cosmos", result["technologies"])
        self.assertIn("NeMo Retriever", result["technologies"])
        self.assertIn("TensorRT-LLM", result["technologies"])
        self.assertIn("nvidia-nim-benchmark", result["blueprint"]["recommended_templates"])

    def test_nim_docker_command_returns_cross_platform_commands(self):
        result = _NODE_REGISTRY["NIMDockerCommand"]({
            "image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:latest",
            "container_name": "demo-nim",
            "port": 9000,
            "cache_dir": ".cache/nim",
            "ngc_api_key_env": "NGC_API_KEY",
        })

        self.assertIn("docker run", result["powershell"])
        self.assertIn("--gpus all", result["powershell"])
        self.assertIn("demo-nim", result["bash"])
        self.assertEqual(result["endpoint_url"], "http://127.0.0.1:9000/v1")


if __name__ == "__main__":
    unittest.main()
