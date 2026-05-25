from __future__ import annotations

import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from .runner_template import RUNNER_TEMPLATE


DEFAULT_IMAGE = "blacknode-sandbox:latest"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_LIMIT = "512m"
DEFAULT_CPU_QUOTA = 100000
DEFAULT_PIDS_LIMIT = 100
WORKSPACE_MOUNT = "/workspace"
LAST_EXECUTION_DURATION_SECONDS: float | None = None


class SandboxError(RuntimeError):
    """Base error for learned-node sandbox execution failures."""


class DockerUnavailableError(SandboxError):
    """Raised when Docker or the Docker Python SDK cannot be reached."""


class SandboxExecutionError(SandboxError):
    """Raised when the sandbox container fails without a runner error payload."""


class SandboxTimeoutError(SandboxExecutionError):
    """Raised when a sandbox run exceeds its configured timeout."""


def run_in_container(
    code: str,
    inputs: Mapping[str, Any] | None = None,
    permissions: Mapping[str, Any] | None = None,
    *,
    image: str | None = None,
    timeout: int | None = None,
    memory: str | None = None,
    node_name: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    if _sandbox_disabled():
        raise DockerUnavailableError(
            "Learned node sandbox is disabled by BLACKNODE_SANDBOX_DISABLED"
        )

    sandbox_image = image or os.environ.get("BLACKNODE_SANDBOX_IMAGE", DEFAULT_IMAGE)
    timeout_seconds = _timeout_seconds(timeout)
    memory_limit = memory or os.environ.get("BLACKNODE_SANDBOX_MEMORY", DEFAULT_MEMORY_LIMIT)
    network_mode = "bridge" if bool((permissions or {}).get("network")) else "none"

    with TemporaryDirectory(prefix="blacknode-run-") as temp_dir:
        workspace = Path(temp_dir)
        _prepare_workspace(workspace, code, inputs or {})

        docker_client = client if client is not None else _docker_client()
        _ensure_image(docker_client, sandbox_image)
        container = _start_container(
            docker_client,
            workspace=workspace,
            image=sandbox_image,
            timeout_seconds=timeout_seconds,
            memory_limit=memory_limit,
            network_mode=network_mode,
        )

        started = time.perf_counter()
        try:
            status_code = _wait_for_container(container, timeout_seconds, node_name=node_name)
            return _read_output(workspace / "output.json", container, status_code, node_name=node_name)
        finally:
            global LAST_EXECUTION_DURATION_SECONDS
            LAST_EXECUTION_DURATION_SECONDS = time.perf_counter() - started


def learned_node_runtime_status(*, client: Any | None = None) -> dict[str, Any]:
    """Return Docker sandbox readiness details for ``blacknode doctor``."""
    image = os.environ.get("BLACKNODE_SANDBOX_IMAGE", DEFAULT_IMAGE)
    disabled = _sandbox_disabled()
    status: dict[str, Any] = {
        "disabled": disabled,
        "docker_available": False,
        "image": image,
        "image_present": False,
        "last_execution_duration_seconds": LAST_EXECUTION_DURATION_SECONDS,
        "detail": "",
    }
    if disabled:
        status["detail"] = "disabled by BLACKNODE_SANDBOX_DISABLED"
        return status

    try:
        docker_client = client if client is not None else _docker_client()
    except DockerUnavailableError as exc:
        status["detail"] = str(exc)
        return status

    status["docker_available"] = True
    try:
        docker_client.images.get(image)
    except Exception as exc:
        if _is_image_missing_exception(exc):
            status["detail"] = f"sandbox image missing: {image}"
        else:
            status["detail"] = f"could not inspect sandbox image {image}: {exc}"
    else:
        status["image_present"] = True
        status["detail"] = f"sandbox image present: {image}"
    return status


def _prepare_workspace(workspace: Path, code: str, inputs: Mapping[str, Any]) -> None:
    workspace.chmod(0o777)
    _write_workspace_file(workspace / "node.py", code)
    _write_workspace_file(workspace / "input.json", json.dumps(dict(inputs)))
    _write_workspace_file(workspace / "runner.py", RUNNER_TEMPLATE)


def _write_workspace_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o644)


def _start_container(
    docker_client: Any,
    *,
    workspace: Path,
    image: str,
    timeout_seconds: int,
    memory_limit: str,
    network_mode: str,
) -> Any:
    binds = {
        str(workspace): {
            "bind": WORKSPACE_MOUNT,
            "mode": "rw",
        }
    }
    try:
        host_config = docker_client.api.create_host_config(
            binds=binds,
            network_mode=network_mode,
            mem_limit=memory_limit,
            cpu_quota=DEFAULT_CPU_QUOTA,
            pids_limit=DEFAULT_PIDS_LIMIT,
            cap_drop=["ALL"],
            read_only=True,
            tmpfs={"/tmp": "size=64M"},
            auto_remove=True,
        )
        container = docker_client.api.create_container(
            image=image,
            command=["python", "/workspace/runner.py"],
            volumes=[WORKSPACE_MOUNT],
            host_config=host_config,
            stop_timeout=timeout_seconds,
            detach=True,
        )
        container_id = container["Id"] if isinstance(container, Mapping) else str(container)
        docker_client.api.start(container_id)
        return _ApiContainer(docker_client.api, container_id)
    except Exception as exc:
        raise DockerUnavailableError(f"Docker failed to start sandbox container: {exc}") from exc


def _wait_for_container(container: Any, timeout_seconds: int, *, node_name: str | None = None) -> int:
    try:
        status = container.wait(timeout=timeout_seconds)
    except Exception as exc:
        if _is_timeout_exception(exc):
            _kill_container(container)
            raise SandboxTimeoutError(
                f"{_node_label(node_name)} exceeded {timeout_seconds}s timeout"
            ) from exc
        raise SandboxExecutionError(f"Docker wait failed: {exc}") from exc

    if isinstance(status, Mapping):
        return int(status.get("StatusCode", 0))
    return int(status)


def _read_output(
    output_path: Path,
    container: Any,
    status_code: int,
    *,
    node_name: str | None = None,
) -> dict[str, Any]:
    if output_path.exists():
        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SandboxExecutionError(f"Sandbox produced invalid JSON output: {exc}") from exc
        if isinstance(result, Mapping) and result.get("__error__"):
            message = str(result.get("message") or result.get("type") or "container execution failed")
            traceback_text = str(result.get("traceback") or "").strip()
            suffix = f"\n{traceback_text}" if traceback_text else ""
            raise SandboxExecutionError(f"{_node_label(node_name)} failed in the Docker sandbox: {message}{suffix}")
        return result

    if status_code == 137:
        raise SandboxExecutionError(f"{_node_label(node_name)} exceeded memory limit")
    if status_code != 0:
        logs = _container_logs(container)
        suffix = f": {logs}" if logs else ""
        raise SandboxExecutionError(f"{_node_label(node_name)} exited with status {status_code}{suffix}")
    raise SandboxExecutionError(f"{_node_label(node_name)} did not produce output.json")


def _container_logs(container: Any) -> str:
    try:
        logs = container.logs(stdout=False, stderr=True)
    except Exception:
        return ""
    if isinstance(logs, bytes):
        return logs.decode("utf-8", errors="replace").strip()
    return str(logs).strip()


def _kill_container(container: Any) -> None:
    try:
        container.kill()
    except Exception:
        pass


def _ensure_image(docker_client: Any, image: str) -> None:
    try:
        docker_client.images.get(image)
        return
    except Exception as exc:
        if not _is_image_missing_exception(exc):
            raise DockerUnavailableError(f"Docker failed to inspect sandbox image: {exc}") from exc

    dockerfile = _sandbox_dockerfile()
    if not dockerfile.exists():
        raise DockerUnavailableError(
            "Docker sandbox image is missing and docker/sandbox/Dockerfile was not found. "
            "Run 'blacknode doctor' for diagnostics."
        )

    try:
        docker_client.images.build(
            path=str(_repo_root()),
            dockerfile="docker/sandbox/Dockerfile",
            tag=image,
            rm=True,
        )
    except Exception as exc:
        raise DockerUnavailableError(
            "Docker sandbox image is missing and automatic build failed. "
            "Run 'blacknode doctor' for diagnostics."
        ) from exc


def _docker_client() -> Any:
    try:
        import docker
    except ImportError as exc:
        raise DockerUnavailableError("Docker Python package is not installed") from exc

    if not hasattr(docker, "from_env"):
        raise DockerUnavailableError("Docker Python package is not installed")

    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        raise DockerUnavailableError(
            "Docker is not available - learned nodes require Docker. "
            "Run 'blacknode doctor' for diagnostics."
        ) from exc


def _sandbox_disabled() -> bool:
    raw = os.environ.get("BLACKNODE_SANDBOX_DISABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _node_label(node_name: str | None) -> str:
    if node_name:
        return f"Learned node '{node_name}'"
    return "Learned node"


def _timeout_seconds(explicit_timeout: int | None) -> int:
    raw = explicit_timeout
    if raw is None:
        raw = os.environ.get("BLACKNODE_SANDBOX_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
    timeout_seconds = int(raw)
    if timeout_seconds <= 0:
        raise ValueError("Sandbox timeout must be greater than zero")
    return timeout_seconds


def _is_timeout_exception(exc: BaseException) -> bool:
    timeout_names = {"Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"}
    if type(exc).__name__ in timeout_names or isinstance(exc, TimeoutError):
        return True
    if "timed out" in str(exc).lower():
        return True
    for wrapped in (exc.__cause__, exc.__context__):
        if wrapped is not None and _is_timeout_exception(wrapped):
            return True
    return False


def _is_image_missing_exception(exc: BaseException) -> bool:
    missing_names = {"ImageNotFound", "NotFound"}
    if type(exc).__name__ in missing_names:
        return True
    message = str(exc).lower()
    return "not found" in message or "no such image" in message


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sandbox_dockerfile() -> Path:
    return _repo_root() / "docker" / "sandbox" / "Dockerfile"


class _ApiContainer:
    def __init__(self, api: Any, container_id: str):
        self.api = api
        self.container_id = container_id

    def wait(self, timeout: int) -> Any:
        return self.api.wait(self.container_id, timeout=timeout)

    def kill(self) -> None:
        self.api.kill(self.container_id)

    def logs(self, stdout: bool = False, stderr: bool = True) -> Any:
        return self.api.logs(self.container_id, stdout=stdout, stderr=stderr)
