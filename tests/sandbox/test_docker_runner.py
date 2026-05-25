from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from blacknode.sandbox import docker_runner
from blacknode.sandbox.runner_template import RUNNER_TEMPLATE


class FakeContainer:
    def __init__(self, workspace: Path, *, status_code: int = 0, output: dict | None = None):
        self.workspace = workspace
        self.status_code = status_code
        self.output = output if output is not None else {"ok": True}
        self.killed = False
        self.node_source = ""
        self.input_payload = {}
        self.runner_source = ""

    def wait(self, timeout: int):
        self.node_source = (self.workspace / "node.py").read_text(encoding="utf-8")
        self.input_payload = json.loads((self.workspace / "input.json").read_text(encoding="utf-8"))
        self.runner_source = (self.workspace / "runner.py").read_text(encoding="utf-8")
        (self.workspace / "output.json").write_text(json.dumps(self.output), encoding="utf-8")
        return {"StatusCode": self.status_code}

    def kill(self):
        self.killed = True

    def logs(self, stdout: bool = False, stderr: bool = True):
        return b"container stderr"


class TimeoutContainer(FakeContainer):
    def wait(self, timeout: int):
        raise TimeoutError("still running")


class WrappedTimeoutContainer(FakeContainer):
    def wait(self, timeout: int):
        raise RuntimeError("NpipeHTTPConnectionPool: Read timed out.")


class MissingOutputContainer(FakeContainer):
    def wait(self, timeout: int):
        return {"StatusCode": self.status_code}


class FakeApi:
    def __init__(self, container_factory):
        self.container_factory = container_factory
        self.host_config_kwargs = None
        self.create_container_kwargs = None
        self.started_container = None
        self.killed_container = None
        self.container = None
        self.workspace_exists_at_run = False

    def create_host_config(self, **kwargs):
        self.host_config_kwargs = kwargs
        return {"host_config": kwargs}

    def create_container(self, **kwargs):
        self.create_container_kwargs = kwargs
        workspace = Path(next(iter(self.host_config_kwargs["binds"].keys())))
        self.workspace_exists_at_run = workspace.exists()
        self.container = self.container_factory(workspace)
        return {"Id": "container-1"}

    def start(self, container_id: str):
        self.started_container = container_id

    def wait(self, container_id: str, timeout: int):
        return self.container.wait(timeout)

    def kill(self, container_id: str):
        self.killed_container = container_id
        self.container.kill()

    def logs(self, container_id: str, stdout: bool = False, stderr: bool = True):
        return self.container.logs(stdout=stdout, stderr=stderr)


class FakeImages:
    def __init__(self, missing: bool = False, build_fails: bool = False):
        self.missing = missing
        self.build_fails = build_fails
        self.get_calls = []
        self.build_kwargs = None

    def get(self, image: str):
        self.get_calls.append(image)
        if self.missing:
            raise RuntimeError("image not found")
        return {"tag": image}

    def build(self, **kwargs):
        self.build_kwargs = kwargs
        if self.build_fails:
            raise RuntimeError("build failed")
        self.missing = False
        return ({"image": kwargs["tag"]}, [])


class FakeDockerClient:
    def __init__(self, container_factory, *, missing_image: bool = False, build_fails: bool = False):
        self.api = FakeApi(container_factory)
        self.images = FakeImages(missing=missing_image, build_fails=build_fails)


class DockerRunnerTests(unittest.TestCase):
    def test_runs_container_with_expected_sandbox_configuration(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace))

        result = docker_runner.run_in_container(
            "def run():\n    return {'ok': True}\n",
            {"value": 3},
            {"network": False},
            client=client,
        )

        self.assertEqual(result, {"ok": True})
        create_kwargs = client.api.create_container_kwargs
        host_kwargs = client.api.host_config_kwargs
        self.assertEqual(create_kwargs["image"], "blacknode-sandbox:latest")
        self.assertEqual(create_kwargs["command"], ["python", "/workspace/runner.py"])
        self.assertEqual(create_kwargs["volumes"], ["/workspace"])
        self.assertEqual(create_kwargs["stop_timeout"], 30)
        self.assertTrue(create_kwargs["detach"])
        self.assertEqual(client.api.started_container, "container-1")
        self.assertEqual(host_kwargs["network_mode"], "none")
        self.assertEqual(host_kwargs["mem_limit"], "512m")
        self.assertEqual(host_kwargs["cpu_quota"], 100000)
        self.assertEqual(host_kwargs["pids_limit"], 100)
        self.assertEqual(host_kwargs["cap_drop"], ["ALL"])
        self.assertTrue(host_kwargs["read_only"])
        self.assertEqual(host_kwargs["tmpfs"], {"/tmp": "size=64M"})
        self.assertTrue(host_kwargs["auto_remove"])
        _host_workspace, mount = next(iter(host_kwargs["binds"].items()))
        self.assertTrue(client.api.workspace_exists_at_run)
        self.assertEqual(mount, {"bind": "/workspace", "mode": "rw"})

        container = client.api.container
        self.assertEqual(container.node_source, "def run():\n    return {'ok': True}\n")
        self.assertEqual(container.input_payload, {"value": 3})
        self.assertEqual(container.runner_source, RUNNER_TEMPLATE)

    def test_network_permission_uses_bridge_mode(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace))

        docker_runner.run_in_container(
            "def run():\n    return {'ok': True}\n",
            {},
            {"network": True},
            client=client,
        )

        self.assertEqual(client.api.host_config_kwargs["network_mode"], "bridge")

    def test_env_overrides_image_timeout_and_memory(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace))

        with patch.dict(
            docker_runner.os.environ,
            {
                "BLACKNODE_SANDBOX_IMAGE": "custom-sandbox:test",
                "BLACKNODE_SANDBOX_TIMEOUT": "7",
                "BLACKNODE_SANDBOX_MEMORY": "128m",
            },
        ):
            docker_runner.run_in_container("def run():\n    return {'ok': True}\n", client=client)

        self.assertEqual(client.api.create_container_kwargs["image"], "custom-sandbox:test")
        self.assertEqual(client.api.create_container_kwargs["stop_timeout"], 7)
        self.assertEqual(client.api.host_config_kwargs["mem_limit"], "128m")

    def test_timeout_stops_container_and_raises(self):
        client = FakeDockerClient(lambda workspace: TimeoutContainer(workspace))

        with self.assertRaises(docker_runner.SandboxTimeoutError) as ctx:
            docker_runner.run_in_container(
                "def run():\n    return {'ok': True}\n",
                client=client,
                timeout=1,
                node_name="SlowNode",
            )

        self.assertIn("Learned node 'SlowNode' exceeded 1s timeout", str(ctx.exception))
        self.assertTrue(client.api.container.killed)
        self.assertEqual(client.api.killed_container, "container-1")

    def test_wrapped_timeout_text_kills_container_and_raises(self):
        client = FakeDockerClient(lambda workspace: WrappedTimeoutContainer(workspace))

        with self.assertRaises(docker_runner.SandboxTimeoutError):
            docker_runner.run_in_container(
                "def run():\n    return {'ok': True}\n",
                client=client,
                timeout=1,
            )

        self.assertTrue(client.api.container.killed)

    def test_missing_image_builds_from_local_dockerfile(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace), missing_image=True)

        docker_runner.run_in_container("def run():\n    return {'ok': True}\n", client=client)

        self.assertEqual(client.images.get_calls, ["blacknode-sandbox:latest"])
        self.assertEqual(client.images.build_kwargs["dockerfile"], "docker/sandbox/Dockerfile")
        self.assertEqual(client.images.build_kwargs["tag"], "blacknode-sandbox:latest")
        self.assertTrue(client.images.build_kwargs["rm"])

    def test_missing_image_build_failure_reports_doctor_error(self):
        client = FakeDockerClient(
            lambda workspace: FakeContainer(workspace),
            missing_image=True,
            build_fails=True,
        )

        with self.assertRaises(docker_runner.DockerUnavailableError) as ctx:
            docker_runner.run_in_container("def run():\n    return {'ok': True}\n", client=client)

        self.assertIn("blacknode doctor", str(ctx.exception))

    def test_runner_error_payload_raises_with_traceback(self):
        client = FakeDockerClient(
            lambda workspace: FakeContainer(
                workspace,
                status_code=1,
                output={
                    "__error__": True,
                    "type": "RuntimeError",
                    "message": "boom",
                    "traceback": "Traceback line",
                },
            )
        )

        with self.assertRaises(docker_runner.SandboxExecutionError) as ctx:
            docker_runner.run_in_container(
                "def run():\n    raise RuntimeError('boom')\n",
                client=client,
                node_name="BrokenNode",
            )

        message = str(ctx.exception)
        self.assertIn("Learned node 'BrokenNode' failed in the Docker sandbox: boom", message)
        self.assertIn("Traceback line", message)

    def test_nonzero_without_output_raises_with_logs(self):
        client = FakeDockerClient(lambda workspace: MissingOutputContainer(workspace, status_code=2))

        with self.assertRaises(docker_runner.SandboxExecutionError) as ctx:
            docker_runner.run_in_container("def run():\n    return {'ok': True}\n", client=client)

        self.assertIn("status 2", str(ctx.exception))
        self.assertIn("container stderr", str(ctx.exception))

    def test_sandbox_disabled_refuses_execution(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace))

        with patch.dict(docker_runner.os.environ, {"BLACKNODE_SANDBOX_DISABLED": "1"}):
            with self.assertRaises(docker_runner.DockerUnavailableError) as ctx:
                docker_runner.run_in_container("def run():\n    return {'ok': True}\n", client=client)

        self.assertIn("BLACKNODE_SANDBOX_DISABLED", str(ctx.exception))
        self.assertIsNone(client.api.create_container_kwargs)

    def test_runtime_status_reports_image_present(self):
        client = FakeDockerClient(lambda workspace: FakeContainer(workspace))

        status = docker_runner.learned_node_runtime_status(client=client)

        self.assertTrue(status["docker_available"])
        self.assertTrue(status["image_present"])
        self.assertIn("blacknode-sandbox:latest", status["detail"])

    def test_missing_docker_sdk_reports_clear_error(self):
        with patch.dict("sys.modules", {"docker": object()}):
            with self.assertRaises(docker_runner.DockerUnavailableError):
                docker_runner._docker_client()


if __name__ == "__main__":
    unittest.main()
