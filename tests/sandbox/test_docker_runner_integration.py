from __future__ import annotations

import os
import unittest
from pathlib import Path

from blacknode.sandbox import docker_runner


ROOT = Path(__file__).resolve().parents[2]
RUN_DOCKER_TESTS = os.environ.get("BLACKNODE_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_DOCKER_TESTS, "set BLACKNODE_INTEGRATION_TESTS=1 to run Docker tests")
class DockerRunnerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import docker

        if not hasattr(docker, "from_env"):
            raise RuntimeError("Docker Python package is not installed")

        cls.client = docker.from_env()
        cls.client.ping()
        cls.client.images.build(
            path=str(ROOT),
            dockerfile="docker/sandbox/Dockerfile",
            tag=docker_runner.DEFAULT_IMAGE,
            rm=True,
        )

    def test_hello_world_node_runs_end_to_end(self):
        result = docker_runner.run_in_container(
            "def run():\n"
            "    return {'ok': True}\n",
            inputs={},
            permissions={"network": False},
            client=self.client,
        )

        self.assertEqual(result, {"ok": True})

    def test_no_network_node_cannot_reach_internet(self):
        with self.assertRaises(docker_runner.SandboxExecutionError) as ctx:
            docker_runner.run_in_container(
                "import requests\n"
                "\n"
                "def run():\n"
                "    response = requests.get('http://example.com', timeout=5)\n"
                "    return {'status': response.status_code}\n",
                inputs={},
                permissions={"network": False},
                client=self.client,
                timeout=10,
                node_name="NoNetworkProbe",
            )

        self.assertIn("NoNetworkProbe", str(ctx.exception))

    def test_network_enabled_node_can_reach_internet(self):
        result = docker_runner.run_in_container(
            "import requests\n"
            "\n"
            "def run():\n"
            "    response = requests.get('http://example.com', timeout=10)\n"
            "    return {'status': response.status_code}\n",
            inputs={},
            permissions={"network": True},
            client=self.client,
            timeout=15,
        )

        self.assertNotIn("__error__", result)
        self.assertIsInstance(result["status"], int)

    def test_timeout_stops_long_running_node(self):
        with self.assertRaises(docker_runner.SandboxTimeoutError):
            docker_runner.run_in_container(
                "import time\n"
                "\n"
                "def run():\n"
                "    time.sleep(60)\n"
                "    return {'ok': True}\n",
                inputs={},
                permissions={"network": False},
                client=self.client,
                timeout=1,
            )

    def test_memory_limit_prevents_large_allocation(self):
        try:
            result = docker_runner.run_in_container(
                "def run():\n"
                "    data = bytearray(1024 * 1024 * 1024)\n"
                "    return {'size': len(data)}\n",
                inputs={},
                permissions={"network": False},
                client=self.client,
                memory="64m",
                timeout=20,
            )
        except docker_runner.SandboxExecutionError as exc:
            self.assertIn("memory", str(exc).lower())
        else:
            self.assertLess(result["size"], 1024 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
