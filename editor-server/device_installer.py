"""Fingerprint-pinned SSH installation for a Blacknode compute device."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import socket
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable


class DeviceInstallError(RuntimeError):
    """A remote device probe or installation could not be completed."""


_INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_INSPECTION_MARKER = "__BLACKNODE_RUNTIME_INSPECTION__="
_HARDWARE_PAIRING_INSPECTION_MARKER = "__BLACKNODE_HARDWARE_PAIRINGS__="
_HARDWARE_ADOPTION_MARKER = "__BLACKNODE_HARDWARE_ADOPTION__="
_HARDWARE_CONFIGURATION_MARKER = "__BLACKNODE_HARDWARE_CONFIGURATION__="
_UPDATE_REPORT_MARKER = "__BLACKNODE_UPDATE_REPORT__="
_INSPECTION_SCRIPT = r"""python3 - <<'PY'
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

home = Path.home()

def command(args, timeout=8.0):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout="",
            stderr=str(exc),
        )

def unit_text(name):
    result = command(["systemctl", "cat", name])
    return result.returncode == 0, result.stdout

def unit_port(text, fallback):
    match = re.search(r"--port(?:=|\s+)[\"']?(\d+)", text)
    return int(match.group(1)) if match else fallback

def listening_ports():
    ports = set()
    for proc_path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(proc_path).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            try:
                ports.add(int(fields[1].rsplit(":", 1)[1], 16))
            except (IndexError, ValueError):
                pass
    result = command(["ss", "-H", "-ltn"])
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            match = re.search(r":(\d+)$", fields[3])
            if match:
                ports.add(int(match.group(1)))
    return ports

def host_environment():
    release = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                release[key] = value.strip().strip("\"'")
    except OSError:
        pass

    nvidia_smi = shutil.which("nvidia-smi") or ""
    gpu_names = []
    driver_version = ""
    driver_cuda_version = ""
    if nvidia_smi:
        result = command([
            nvidia_smi,
            "--query-gpu=name,driver_version",
            "--format=csv,noheader,nounits",
        ])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                name, separator, driver = line.partition(",")
                if name.strip():
                    gpu_names.append(name.strip())
                if separator and not driver_version:
                    driver_version = driver.strip()
        result = command([nvidia_smi])
        match = re.search(r"CUDA Version:\s*([0-9.]+)", result.stdout + result.stderr)
        if match:
            driver_cuda_version = match.group(1)

    nvcc = shutil.which("nvcc") or ""
    cuda_toolkit_version = ""
    if nvcc:
        result = command([nvcc, "--version"])
        match = re.search(r"\brelease\s+([0-9.]+)", result.stdout + result.stderr)
        if match:
            cuda_toolkit_version = match.group(1)
    if not cuda_toolkit_version:
        version_json = Path("/usr/local/cuda/version.json")
        try:
            cuda_payload = json.loads(version_json.read_text(encoding="utf-8"))
            cuda_toolkit_version = str(
                (cuda_payload.get("cuda") or {}).get("version")
                or cuda_payload.get("version")
                or ""
            )
        except (OSError, ValueError, AttributeError):
            pass

    ros_distros = sorted({
        path.parent.name
        for path in Path("/opt/ros").glob("*/setup.bash")
        if path.is_file()
    })
    ros2_path = shutil.which("ros2") or ""
    selected_ros = str(os.environ.get("ROS_DISTRO") or "")
    if not selected_ros and "jazzy" in ros_distros:
        selected_ros = "jazzy"
    if not selected_ros and ros_distros:
        selected_ros = ros_distros[-1]

    docker_path = shutil.which("docker") or ""
    docker_client_version = ""
    docker_server_version = ""
    docker_daemon_running = False
    if docker_path:
        result = command([docker_path, "--version"])
        match = re.search(r"\bversion\s+([^,\s]+)", result.stdout + result.stderr, re.IGNORECASE)
        if match:
            docker_client_version = match.group(1)
        result = command([docker_path, "info", "--format", "{{.ServerVersion}}"])
        if result.returncode == 0:
            docker_daemon_running = True
            docker_server_version = result.stdout.strip()
    docker_service_active = (
        command(["systemctl", "is-active", "--quiet", "docker.service"]).returncode == 0
    )
    docker_service_enabled = (
        command(["systemctl", "is-enabled", "--quiet", "docker.service"]).returncode == 0
    )

    return {
        "policy": "preserve",
        "os": {
            "name": release.get("PRETTY_NAME") or platform.system(),
            "version": release.get("VERSION_ID") or platform.release(),
            "architecture": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "executable": shutil.which("python3") or "python3",
        },
        "nvidia": {
            "available": bool(nvidia_smi or nvcc or Path("/usr/local/cuda").exists()),
            "gpus": gpu_names,
            "driver_version": driver_version,
            "driver_cuda_version": driver_cuda_version,
            "cuda_toolkit_version": cuda_toolkit_version,
            "nvidia_smi": bool(nvidia_smi),
            "nvcc": bool(nvcc),
            "preserved": True,
        },
        "ros2": {
            "available": bool(ros_distros or ros2_path),
            "distributions": ros_distros,
            "selected_distribution": selected_ros,
            "ros2_on_path": bool(ros2_path),
            "preserved": True,
        },
        "docker": {
            "available": bool(docker_path),
            "client_version": docker_client_version,
            "server_version": docker_server_version,
            "daemon_running": docker_daemon_running or docker_service_active,
            "service_enabled": docker_service_enabled,
            "preserved": True,
        },
        "runtime_setup_packages": ["git", "python3-pip", "python3-venv"],
    }

ids = {"default"}
organized_root = home / "Blacknode" / "devices"
legacy_side_root = home / "blacknode-runtimes"
for side_root in (organized_root, legacy_side_root):
    if not side_root.is_dir():
        continue
    ids.update(
        path.name
        for path in side_root.iterdir()
        if path.is_dir() and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", path.name)
    )
for unit_path in glob.glob("/etc/systemd/system/blacknode-runtime-*.service"):
    name = Path(unit_path).name
    instance = name[len("blacknode-runtime-"):-len(".service")]
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", instance):
        ids.add(instance)

instances = []
for instance in sorted(ids, key=lambda value: (value != "default", value)):
    organized_stack = organized_root / instance
    organized_repo = organized_stack / "runtime"
    organized_token = organized_stack / "secrets" / "runtime.auth.token"
    if instance == "default":
        legacy_repo = home / "blacknode-runtime"
        unit = "blacknode-runtime.service"
        fallback_port = 8766
        legacy_token = home / ".blacknode" / "runtime.auth.token"
    else:
        legacy_repo = legacy_side_root / instance
        unit = f"blacknode-runtime-{instance}.service"
        fallback_port = 0
        legacy_token = home / ".blacknode" / "runtimes" / f"{instance}.auth.token"
    organized_present = organized_repo.exists() or organized_token.exists()
    repo = organized_repo if organized_present else legacy_repo
    fallback_token = organized_token if organized_present else legacy_token
    config_path = repo / ".blacknode-runtime" / "runtime.json"
    config = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
    token_path = Path(str(config.get("auth_token_file") or fallback_token)).expanduser()
    service_installed, service_text = unit_text(unit)
    if not repo.exists() and not service_installed and not config_path.exists() and not token_path.exists():
        continue
    port = unit_port(service_text, fallback_port)
    running = command(["systemctl", "is-active", "--quiet", unit]).returncode == 0
    token_available = token_path.is_file()
    healthy = False
    version = ""
    device_id = str(config.get("device_id") or "")
    error = ""
    if token_available:
        try:
            token = token_path.read_text(encoding="utf-8").strip()
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/manifest",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=2.0) as response:
                manifest = json.loads(response.read())
            healthy = (
                manifest.get("service") == "blacknode-runtime"
                and manifest.get("protocol_version") == 1
            )
            version = str(manifest.get("runtime_version") or "")
            device_id = str(manifest.get("device_id") or device_id)
            if not healthy:
                error = "The service responded with an incompatible manifest."
        except Exception as exc:
            error = str(exc)[:240]
    elif running:
        error = "The service is running, but its pairing token is unavailable."
    else:
        error = "The runtime is not running."
    instances.append({
        "instance_id": instance,
        "install_root": str(organized_stack) if organized_present else "",
        "runtime_dir": str(repo),
        "packages_dir": str(repo / "packages"),
        "service_name": unit,
        "port": port,
        "repository": (repo / ".git").is_dir(),
        "configured": config_path.is_file(),
        "service_installed": service_installed,
        "running": running,
        "healthy": healthy,
        "token_available": token_available,
        "runtime_version": version,
        "device_id": device_id,
        "error": error,
        "_token_file": str(token_path),
    })

used = listening_ports()
suggested_port = next((port for port in range(8766, 8866) if port not in used), 0)
used_ids = {item["instance_id"] for item in instances}
counter = 2
while f"instance-{counter}" in used_ids:
    counter += 1
print("__BLACKNODE_RUNTIME_INSPECTION__=" + json.dumps({
    "instances": instances,
    "environment": host_environment(),
    "used_ports": sorted(used),
    "suggested_port": suggested_port,
    "suggested_instance_id": f"instance-{counter}",
}, separators=(",", ":")))
PY"""


def _load_paramiko():
    try:
        import paramiko  # type: ignore
    except ImportError as exc:
        raise DeviceInstallError(
            "Remote SSH setup requires Paramiko. Reinstall the editor-server "
            "requirements, then restart Blacknode."
        ) from exc
    return paramiko


def _fingerprint(key: Any) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _clean_host(host: str, port: int) -> tuple[str, int]:
    clean_host = str(host or "").strip()
    if not clean_host:
        raise DeviceInstallError("Device IP address or hostname is required.")
    if any(character.isspace() for character in clean_host):
        raise DeviceInstallError("Device address must not contain spaces.")
    clean_port = int(port)
    if clean_port < 1 or clean_port > 65535:
        raise DeviceInstallError("SSH port must be between 1 and 65535.")
    return clean_host, clean_port


def _clean_target(host: str, port: int, username: str, password: str) -> tuple[str, int, str, str]:
    clean_host, clean_port = _clean_host(host, port)
    clean_user = str(username or "").strip()
    clean_password = str(password or "")
    if not clean_user:
        raise DeviceInstallError("SSH username is required.")
    if not clean_password:
        raise DeviceInstallError("SSH password is required.")
    if "\n" in clean_password or "\r" in clean_password:
        raise DeviceInstallError("SSH passwords containing line breaks are not supported.")
    return clean_host, clean_port, clean_user, clean_password


def _sudo_input(password: str, *, attempts: int = 32) -> str:
    """Supply nested non-interactive sudo calls without a PTY or password echo."""
    return (str(password) + "\n") * max(1, int(attempts))


@dataclass
class _Connection:
    client: Any
    fingerprint: str

    def close(self) -> None:
        self.client.close()


def _connect(
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    expected_fingerprint: str | None = None,
    timeout: float = 10.0,
) -> _Connection:
    paramiko = _load_paramiko()
    clean_host, clean_port, clean_user, clean_password = _clean_target(
        host, port, username, password
    )
    expected = str(expected_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError("The confirmed SSH host fingerprint is required.")

    class _PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            del client, hostname
            actual = _fingerprint(key)
            if not secrets.compare_digest(expected, actual):
                raise paramiko.SSHException(
                    "The device SSH host key changed. Stop and verify the device."
                )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(_PinnedHostKeyPolicy())
    try:
        client.connect(
            clean_host,
            port=clean_port,
            username=clean_user,
            password=clean_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
        )
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise DeviceInstallError("SSH connection did not become active.")
        fingerprint = _fingerprint(transport.get_remote_server_key())
        if not secrets.compare_digest(expected, fingerprint):
            raise DeviceInstallError(
                "The device SSH host key changed. Stop and verify the device before "
                "trying again."
            )
        return _Connection(client=client, fingerprint=fingerprint)
    except DeviceInstallError:
        client.close()
        raise
    except paramiko.AuthenticationException as exc:
        client.close()
        raise DeviceInstallError(
            f"SSH login was rejected for user '{clean_user}'. Re-enter the SSH "
            "username and password. No inspection or installation commands ran."
        ) from exc
    except (paramiko.SSHException, socket.timeout, OSError) as exc:
        client.close()
        raise DeviceInstallError(f"Could not connect over SSH: {exc}") from exc


def _run(
    connection: _Connection,
    command: str,
    *,
    stdin_text: str = "",
    timeout: float = 30.0,
    on_output: Callable[[str], None] | None = None,
) -> str:
    try:
        stdin, stdout, stderr = connection.client.exec_command(
            command,
            get_pty=False,
        )
        if stdin_text:
            stdin.write(stdin_text)
            stdin.flush()
        stdin.channel.shutdown_write()
        channel = stdout.channel
        deadline = time.monotonic() + timeout
        output = bytearray()
        pending_line = bytearray()

        def append_output(chunk: bytes) -> None:
            output.extend(chunk)
            if on_output is None:
                return
            pending_line.extend(chunk)
            while b"\n" in pending_line:
                raw_line, _, remainder = pending_line.partition(b"\n")
                pending_line[:] = remainder
                try:
                    on_output(raw_line.decode("utf-8", errors="replace").rstrip("\r"))
                except Exception:
                    # UI progress reporting must never interrupt the remote command.
                    pass

        while True:
            read_any = False
            while channel.recv_ready():
                append_output(channel.recv(32768))
                read_any = True
            while channel.recv_stderr_ready():
                append_output(channel.recv_stderr(32768))
                read_any = True
            if len(output) > 512 * 1024:
                del output[: len(output) - 512 * 1024]
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if time.monotonic() >= deadline:
                channel.close()
                raise DeviceInstallError(
                    f"Remote command did not finish within {int(timeout)} seconds."
                )
            if not read_any:
                time.sleep(0.05)
        exit_code = channel.recv_exit_status()
        if on_output is not None and pending_line:
            try:
                on_output(pending_line.decode("utf-8", errors="replace").rstrip("\r"))
            except Exception:
                pass
        output_text = bytes(output).decode("utf-8", errors="replace")
    except Exception as exc:
        if isinstance(exc, DeviceInstallError):
            raise
        raise DeviceInstallError(f"Remote command failed: {exc}") from exc
    if exit_code != 0:
        tail = "\n".join(output_text.strip().splitlines()[-12:])
        raise DeviceInstallError(
            f"Remote command exited with code {exit_code}."
            + (f"\n{tail}" if tail else "")
        )
    return output_text


def probe_device(
    *,
    host: str,
    port: int,
) -> dict[str, Any]:
    paramiko = _load_paramiko()
    clean_host, clean_port = _clean_host(host, port)
    sock = None
    transport = None
    try:
        sock = socket.create_connection((clean_host, clean_port), timeout=10.0)
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=10.0)
        key = transport.get_remote_server_key()
        return {
            "ok": True,
            "host_fingerprint": _fingerprint(key),
            "os": "",
            "architecture": "",
            "hostname": clean_host,
        }
    except (paramiko.SSHException, socket.timeout, OSError) as exc:
        raise DeviceInstallError(f"Could not read the SSH host key: {exc}") from exc
    finally:
        if transport is not None:
            transport.close()
        elif sock is not None:
            sock.close()


def _parse_inspection(output: str) -> dict[str, Any]:
    payload_line = next(
        (
            line[len(_INSPECTION_MARKER):]
            for line in reversed(output.splitlines())
            if line.startswith(_INSPECTION_MARKER)
        ),
        "",
    )
    if not payload_line:
        raise DeviceInstallError("The device did not return a runtime inspection report.")
    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        raise DeviceInstallError("The device returned an invalid runtime inspection report.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("instances"), list):
        raise DeviceInstallError("The device returned an incomplete runtime inspection report.")
    return payload


def _inspect_connection(connection: _Connection) -> dict[str, Any]:
    return _parse_inspection(_run(connection, _INSPECTION_SCRIPT, timeout=45.0))


def _public_inspection(payload: dict[str, Any]) -> dict[str, Any]:
    instances = []
    for item in payload.get("instances", []):
        if not isinstance(item, dict):
            continue
        instances.append({
            key: value
            for key, value in item.items()
            if not str(key).startswith("_")
        })
    return {
        "ok": True,
        "instances": instances,
        "environment": (
            payload.get("environment")
            if isinstance(payload.get("environment"), dict)
            else {}
        ),
        "suggested_port": int(payload.get("suggested_port") or 0),
        "suggested_instance_id": str(payload.get("suggested_instance_id") or "instance-2"),
    }


def _clean_instance_id(value: str, *, allow_default: bool = True) -> str:
    clean = str(value or "").strip().lower()
    if allow_default and clean == "default":
        return clean
    if not _INSTANCE_RE.fullmatch(clean) or clean == "default":
        raise DeviceInstallError(
            "Runtime instance must contain lowercase letters, numbers, or hyphens."
        )
    return clean


def _find_instance(payload: dict[str, Any], instance_id: str) -> dict[str, Any]:
    return next(
        (
            item
            for item in payload.get("instances", [])
            if isinstance(item, dict) and item.get("instance_id") == instance_id
        ),
        {},
    )


def _read_remote_token(connection: _Connection, instance: dict[str, Any]) -> str:
    token_path = str(instance.get("_token_file") or "")
    if not token_path.startswith("/"):
        raise DeviceInstallError("The existing runtime token path is invalid.")
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(token_path, "r") as token_file:
                token = token_file.read(4096)
        finally:
            sftp.close()
    except Exception as exc:
        raise DeviceInstallError("Could not read the existing runtime pairing token.") from exc
    if isinstance(token, bytes):
        token = token.decode("utf-8", errors="strict")
    clean = str(token).strip()
    if len(clean) < 24 or any(character.isspace() for character in clean):
        raise DeviceInstallError("The existing runtime pairing token is invalid.")
    return clean


def discover_hardware_pairings(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    expected_hardware_dir: str = "",
) -> dict[str, Any]:
    """Read installed Hardware service credentials over the verified SSH channel."""

    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    expected_directory_payload = base64.urlsafe_b64encode(
        json.dumps(str(expected_hardware_dir or "")).encode("utf-8")
    ).decode("ascii")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    inspection_command = r"""python3 - __BLACKNODE_EXPECTED_HARDWARE_DIR__ <<'PY'
import base64
import json
import os
import re
import shlex
import subprocess
import sys

expected_directory = json.loads(
    base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8")
)
expected_directory = (
    os.path.abspath(os.path.expanduser(expected_directory))
    if expected_directory
    else ""
)

def command(args):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout="",
            stderr=str(exc),
        )

def argument(argv, name):
    for index, value in enumerate(argv):
        if value == name and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return ""

units = set()
for args in (
    ["systemctl", "list-unit-files", "blacknode-hardware*.service", "--no-legend"],
    [
        "systemctl", "list-units", "--all", "--type=service",
        "blacknode-hardware*.service", "--no-legend",
    ],
):
    result = command(args)
    for line in result.stdout.splitlines():
        unit = line.split(None, 1)[0] if line.split() else ""
        if re.fullmatch(
            r"blacknode-hardware(?:[-.@][A-Za-z0-9_.@-]+)?\.service",
            unit,
        ):
            units.add(unit)

services = []
for unit in sorted(units):
    result = command(["systemctl", "cat", unit])
    if result.returncode != 0:
        continue
    working_directory = ""
    exec_start = ""
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("WorkingDirectory="):
            working_directory = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("ExecStart="):
            exec_start = line.split("=", 1)[1].strip()
    if not working_directory or not exec_start:
        continue
    working_directory = os.path.abspath(os.path.expanduser(working_directory))
    if expected_directory and working_directory != expected_directory:
        continue
    try:
        argv = shlex.split(exec_start)
    except ValueError:
        continue
    service_port = argument(argv, "--port")
    config_path = argument(argv, "--config")
    token_path = argument(argv, "--auth-token-file")
    if not service_port.isdigit() or not config_path or not token_path:
        continue
    services.append({
        "service_name": unit,
        "working_directory": working_directory,
        "port": int(service_port),
        "config_path": os.path.abspath(os.path.expanduser(config_path)),
        "token_path": os.path.abspath(os.path.expanduser(token_path)),
        "active": command(["systemctl", "is-active", "--quiet", unit]).returncode == 0,
    })

print("__BLACKNODE_HARDWARE_PAIRINGS__=" + json.dumps(
    {"services": services},
    separators=(",", ":"),
))
PY"""
    inspection_command = inspection_command.replace(
        "__BLACKNODE_EXPECTED_HARDWARE_DIR__",
        expected_directory_payload,
        1,
    )
    try:
        output = _run(connection, inspection_command, timeout=45.0)
        marker_line = next(
            (
                line[len(_HARDWARE_PAIRING_INSPECTION_MARKER):]
                for line in output.splitlines()
                if line.startswith(_HARDWARE_PAIRING_INSPECTION_MARKER)
            ),
            "",
        )
        if not marker_line:
            raise DeviceInstallError(
                "The device did not return its installed Robot Hardware services."
            )
        try:
            inspection = json.loads(marker_line)
        except json.JSONDecodeError as exc:
            raise DeviceInstallError(
                "The device returned invalid Robot Hardware service information."
            ) from exc
        services = [
            item
            for item in inspection.get("services", [])
            if isinstance(item, dict)
        ]
        pairings: list[dict[str, Any]] = []
        errors: list[str] = []
        sftp = connection.client.open_sftp()
        try:
            def read_remote_text(path: PurePosixPath, limit: int) -> str:
                with sftp.file(str(path), "r") as remote_file:
                    value = remote_file.read(limit + 1)
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="strict")
                text = str(value)
                if len(text.encode("utf-8")) > limit:
                    raise ValueError("file is larger than the allowed limit")
                return text

            for service in services:
                unit = str(service.get("service_name") or "Robot Hardware service")
                try:
                    service_port = int(service.get("port") or 0)
                    working_directory = PurePosixPath(
                        str(service.get("working_directory") or "")
                    )
                    config_path = PurePosixPath(
                        str(service.get("config_path") or "")
                    )
                    token_path = PurePosixPath(
                        str(service.get("token_path") or "")
                    )
                    if (
                        not working_directory.is_absolute()
                        or not config_path.is_absolute()
                        or not token_path.is_absolute()
                        or not 1 <= service_port <= 65535
                    ):
                        raise ValueError("service paths or port are invalid")
                    private_directory = working_directory / ".blacknode-hardware"
                    config_path.relative_to(private_directory)
                    token_path.relative_to(private_directory)
                    if token_path.name != "auth.token":
                        raise ValueError("pairing token path is not an auth.token file")
                    manifest = read_remote_text(
                        working_directory / "pyproject.toml",
                        256 * 1024,
                    )
                    if not re.search(
                        r'(?m)^\s*name\s*=\s*["\']blacknode-hardware["\']\s*$',
                        manifest,
                    ):
                        raise ValueError(
                            "service directory is not a Blacknode Hardware checkout"
                        )
                    config = json.loads(read_remote_text(config_path, 256 * 1024))
                    if not isinstance(config, dict):
                        raise ValueError("robot configuration is not an object")
                    token = read_remote_text(token_path, 4096).strip()
                    if len(token) < 32 or any(
                        character.isspace() for character in token
                    ):
                        raise ValueError("pairing token is invalid")
                    pairings.append({
                        "service_name": unit,
                        "port": service_port,
                        "name": str(
                            config.get("name")
                            or config.get("device_id")
                            or unit
                        ).strip(),
                        "device_id": str(config.get("device_id") or "").strip(),
                        "token": token,
                        "active": bool(service.get("active")),
                    })
                except FileNotFoundError:
                    errors.append(
                        f"{unit}: its saved Hardware package, configuration, or "
                        "pairing token is missing. Reinstall the Hardware package "
                        "and configure this robot again."
                    )
                except (
                    OSError,
                    UnicodeDecodeError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    errors.append(f"{unit}: {exc}")
        finally:
            sftp.close()
        return {
            "pairings": pairings,
            "errors": errors,
            "discovered": len(services),
        }
    except DeviceInstallError:
        raise
    except Exception as exc:
        raise DeviceInstallError(
            "Could not read installed Robot Hardware pairing credentials."
        ) from exc
    finally:
        connection.close()


def adopt_legacy_hardware_services(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
) -> dict[str, Any]:
    """Move legacy default Hardware services into the organized default stack."""

    selected_instance = _clean_instance_id(instance_id or "default")
    if selected_instance != "default":
        return {"ok": True, "adopted": 0}
    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    script = r"""#!/usr/bin/env bash
set -euo pipefail
sudo() {
  command sudo -S -p '' "$@"
}
export -f sudo
target="$HOME/Blacknode/devices/default/hardware"
legacy="$HOME/blacknode-hardware"
target_private="$target/.blacknode-hardware"
legacy_private="$legacy/.blacknode-hardware"
marker="__BLACKNODE_HARDWARE_ADOPTION__="

valid_hardware_checkout() {
  [[ -d "$1/.git" && -f "$1/pyproject.toml" ]] \
    && grep -Eq '^[[:space:]]*name[[:space:]]*=[[:space:]]*["'"'"']blacknode-hardware["'"'"'][[:space:]]*$' \
      "$1/pyproject.toml"
}

valid_hardware_checkout "$target" || {
  echo "The organized Hardware package is missing or invalid: $target" >&2
  exit 4
}
valid_hardware_checkout "$legacy" || {
  printf '%s{"adopted":0}\n' "$marker"
  exit 0
}
[[ -f "$legacy_private/devices.json" ]] || {
  printf '%s{"adopted":0}\n' "$marker"
  exit 0
}

mapfile -t legacy_units < <(
  {
    systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
    systemctl list-units --all --type=service 'blacknode-hardware*.service' \
      --no-legend 2>/dev/null
  } | awk '{print $1}' | sort -u | while read -r unit; do
    [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\.service$ ]] \
      || continue
    directory="$(
      systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
    )"
    [[ "$directory" == "$legacy" ]] || continue
    printf '%s\n' "$unit"
  done
)
if (( ${#legacy_units[@]} == 0 )); then
  printf '%s{"adopted":0}\n' "$marker"
  exit 0
fi
if [[ -e "$target_private" ]] \
  && [[ -n "$(find "$target_private" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "The organized Hardware stack already has robot configuration. Its services must be installed or repaired instead of replacing it with the legacy configuration." >&2
  exit 5
fi

temporary_private="${target_private}.adopting.$$"
cleanup() {
  rm -rf -- "$temporary_private"
}
trap cleanup EXIT
rm -rf -- "$temporary_private"
cp -a -- "$legacy_private" "$temporary_private"
rm -rf -- "$target_private"
mv -- "$temporary_private" "$target_private"
(
  cd "$target"
  BLACKNODE_HARDWARE_INSTANCE="" ./install-service.sh --all
)
for unit in "${legacy_units[@]}"; do
  directory="$(
    systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
  )"
  [[ "$directory" == "$target" ]] || {
    echo "$unit did not move into the organized Hardware stack." >&2
    exit 6
  }
  systemctl is-active --quiet "$unit" || {
    echo "$unit is not running after migration." >&2
    exit 6
  }
done
printf '%s{"adopted":%d}\n' "$marker" "${#legacy_units[@]}"
"""
    remote_script_path = (
        f"/tmp/blacknode-hardware-adopt-{secrets.token_hex(8)}.sh"
    )
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()
        output = _run(
            connection,
            f"bash {remote_script_path}",
            stdin_text=_sudo_input(password, attempts=16),
            timeout=300.0,
        )
        marker_line = next(
            (
                line[len(_HARDWARE_ADOPTION_MARKER):]
                for line in output.splitlines()
                if line.startswith(_HARDWARE_ADOPTION_MARKER)
            ),
            "",
        )
        if not marker_line:
            raise DeviceInstallError(
                "The device did not confirm whether legacy Robot Hardware "
                "services were migrated."
            )
        try:
            result = json.loads(marker_line)
            adopted = int(result.get("adopted") or 0)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeviceInstallError(
                "The device returned invalid Robot Hardware migration information."
            ) from exc
        return {"ok": True, "adopted": max(0, adopted)}
    finally:
        try:
            _run(
                connection,
                f"rm -f -- {remote_script_path}",
                timeout=10.0,
            )
        except DeviceInstallError:
            pass
        connection.close()


def configure_hardware_services(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    runtime_port: int,
) -> dict[str, Any]:
    """Configure connected serial robots in an organized Hardware stack."""

    selected_instance = _clean_instance_id(instance_id or "default")
    selected_runtime_port = int(runtime_port)
    if not 1 <= selected_runtime_port <= 65535:
        raise DeviceInstallError("The managed Runtime port is invalid.")
    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    script = r"""#!/usr/bin/env bash
set -euo pipefail
sudo() {
  command sudo -S -p '' "$@"
}
export -f sudo
instance="$1"
runtime_port="$2"
[[ "$instance" == "default" || "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || {
  echo "Invalid Blacknode Hardware instance." >&2
  exit 2
}
[[ "$runtime_port" =~ ^[0-9]+$ ]] \
  && (( runtime_port >= 1 && runtime_port <= 65535 )) || {
  echo "Invalid Blacknode Runtime port." >&2
  exit 2
}
target="$HOME/Blacknode/devices/$instance/hardware"
service_instance="$instance"
legacy=""
if [[ "$instance" == "default" ]]; then
  service_instance=""
  legacy="$HOME/blacknode-hardware"
fi
[[ -d "$target/.git" && -f "$target/pyproject.toml" ]] \
  && grep -Eq '^[[:space:]]*name[[:space:]]*=[[:space:]]*["'"'"']blacknode-hardware["'"'"'][[:space:]]*$' \
    "$target/pyproject.toml" || {
  echo "The organized Hardware package is missing or invalid: $target" >&2
  exit 4
}
[[ -x "$target/.venv/bin/python" && -x "$target/configure.sh" ]] || {
  echo "The organized Hardware environment is not set up: $target" >&2
  exit 4
}

orphan_units=()
if [[ -n "$legacy" ]]; then
  mapfile -t orphan_units < <(
    {
      systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
      systemctl list-units --all --type=service 'blacknode-hardware*.service' \
        --no-legend 2>/dev/null
    } | awk '{print $1}' | sort -u | while read -r unit; do
      [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\.service$ ]] \
        || continue
      directory="$(
        systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
      )"
      [[ "$directory" == "$legacy" ]] || continue
      printf '%s\n' "$unit"
    done
  )
fi
restore_orphans=false
restore_on_failure() {
  exit_code=$?
  if (( exit_code != 0 )) && [[ "$restore_orphans" == true ]]; then
    for unit in "${orphan_units[@]}"; do
      sudo systemctl start "$unit" >/dev/null 2>&1 || true
    done
  fi
  exit "$exit_code"
}
trap restore_on_failure EXIT
if (( ${#orphan_units[@]} > 0 )); then
  echo "Stopping orphaned legacy Hardware services for a safe serial rescan..."
  for unit in "${orphan_units[@]}"; do
    sudo systemctl stop "$unit"
  done
  restore_orphans=true
fi
(
  cd "$target"
  BLACKNODE_HARDWARE_INSTANCE="$service_instance" \
    BLACKNODE_RUNTIME_PORT="$runtime_port" \
    ./configure.sh --all --install
)

for unit in "${orphan_units[@]}"; do
  directory="$(
    systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
  )"
  if [[ "$directory" == "$legacy" ]]; then
    sudo systemctl disable --now "$unit" >/dev/null 2>&1 || true
    sudo rm -f -- "/etc/systemd/system/$unit" "/run/systemd/system/$unit"
  fi
done
sudo systemctl daemon-reload

configured=0
while read -r unit; do
  [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\.service$ ]] \
    || continue
  directory="$(
    systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
  )"
  [[ "$directory" == "$target" ]] || continue
  systemctl is-active --quiet "$unit" || {
    echo "$unit is not running after configuration." >&2
    exit 6
  }
  configured=$((configured + 1))
done < <(
  {
    systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
    systemctl list-units --all --type=service 'blacknode-hardware*.service' \
      --no-legend 2>/dev/null
  } | awk '{print $1}' | sort -u
)
(( configured > 0 )) || {
  echo "No connected serial robots were configured." >&2
  exit 6
}
restore_orphans=false
trap - EXIT
printf '__BLACKNODE_HARDWARE_CONFIGURATION__={"configured":%d}\n' "$configured"
"""
    remote_script_path = (
        f"/tmp/blacknode-hardware-configure-{secrets.token_hex(8)}.sh"
    )
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()
        output = _run(
            connection,
            (
                f"bash {remote_script_path} "
                f"{selected_instance} {selected_runtime_port}"
            ),
            stdin_text=_sudo_input(password, attempts=32),
            timeout=300.0,
        )
        marker_line = next(
            (
                line[len(_HARDWARE_CONFIGURATION_MARKER):]
                for line in output.splitlines()
                if line.startswith(_HARDWARE_CONFIGURATION_MARKER)
            ),
            "",
        )
        if not marker_line:
            raise DeviceInstallError(
                "The device did not confirm its configured Robot Hardware services."
            )
        try:
            result = json.loads(marker_line)
            configured = int(result.get("configured") or 0)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeviceInstallError(
                "The device returned invalid Robot Hardware configuration information."
            ) from exc
        if configured < 1:
            raise DeviceInstallError(
                "No connected serial robots were configured."
            )
        return {"ok": True, "configured": configured}
    finally:
        try:
            _run(
                connection,
                f"rm -f -- {remote_script_path}",
                timeout=10.0,
            )
        except DeviceInstallError:
            pass
        connection.close()


def install_hardware_environment(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Install the managed Hardware package beside an existing Runtime."""

    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    selected_instance = _clean_instance_id(instance_id or "default")
    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    report(5, "Connecting to the verified device")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    script = r"""#!/usr/bin/env bash
set -euo pipefail
progress() {
  echo "__BLACKNODE_HARDWARE_INSTALL_PROGRESS__=$1|$2"
}
sudo() {
  command sudo -S -p '' "$@"
}
export -f sudo
instance="$1"
[[ "$instance" == "default" || "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || {
  echo "Invalid Blacknode runtime instance."
  exit 2
}
stack_root="$HOME/Blacknode/devices/$instance"
runtime_dir="$stack_root/runtime"
hardware_dir="$stack_root/hardware"
service_instance=""
[[ "$instance" == "default" ]] || service_instance="$instance"
case "$hardware_dir" in
  "$HOME/Blacknode/devices/"*/hardware) ;;
  *) echo "Unsafe Hardware directory."; exit 2 ;;
esac
[[ -d "$runtime_dir/.git" && -f "$runtime_dir/pyproject.toml" ]] || {
  echo "The organized Runtime installation is missing: $runtime_dir"
  exit 3
}
created=false
cleanup_failed_install() {
  exit_code=$?
  if [[ "$exit_code" -ne 0 && "$created" == true ]]; then
    progress 0 "Cleaning the incomplete Hardware package"
    rm -rf -- "$hardware_dir"
  fi
  exit "$exit_code"
}
trap cleanup_failed_install EXIT
if [[ -e "$hardware_dir" ]]; then
  [[ -d "$hardware_dir/.git" && -f "$hardware_dir/pyproject.toml" ]] || {
    echo "The existing Hardware directory is not a valid package checkout:"
    echo "  $hardware_dir"
    exit 4
  }
  origin="$(git -C "$hardware_dir" remote get-url origin 2>/dev/null || true)"
  [[ "$origin" =~ (github\.com[:/])temiroff/blacknode-hardware(\.git)?$ ]] || {
    echo "The existing Hardware checkout has an unrecognized Git origin."
    exit 4
  }
  progress 25 "Using the existing Robot Hardware package"
else
  progress 20 "Downloading the Robot Hardware package"
  mkdir -p "$(dirname -- "$hardware_dir")"
  git clone https://github.com/temiroff/blacknode-hardware.git "$hardware_dir"
  created=true
fi
if ! grep -q 'BLACKNODE_HARDWARE_INSTANCE' "$hardware_dir/install-service.sh" \
  || ! grep -q 'previous_working_directory' "$hardware_dir/install-service.sh"; then
  echo "The downloaded Blacknode Hardware release does not support managed stacks yet."
  exit 4
fi
progress 50 "Setting up the Robot Hardware environment"
(
  cd "$hardware_dir"
  BLACKNODE_HARDWARE_INSTANCE="$service_instance" ./setup_ubuntu.sh
)
progress 88 "Recording the complete device stack"
python3 - "$stack_root/install.json" "$instance" "$runtime_dir" "$hardware_dir" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
try:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    payload = {
        "layout_version": 1,
        "instance_id": sys.argv[2],
        "runtime_dir": sys.argv[3],
        "packages_dir": str(Path(sys.argv[3]) / "packages"),
    }
payload["hardware_dir"] = sys.argv[4]
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
PY
created=false
progress 100 "Robot Hardware package installed"
"""
    remote_script_path = (
        f"/tmp/blacknode-hardware-install-{secrets.token_hex(8)}.sh"
    )
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()
        _run(
            connection,
            f"bash {remote_script_path} {selected_instance}",
            stdin_text=_sudo_input(password, attempts=8),
            timeout=900.0,
            on_output=lambda line: (
                report(int(match.group(1)), match.group(2).strip())
                if (
                    match := re.match(
                        r"^__BLACKNODE_HARDWARE_INSTALL_PROGRESS__="
                        r"(\d{1,3})\|(.*)$",
                        line.strip(),
                    )
                )
                else None
            ),
        )
        return {
            "ok": True,
            "instance_id": selected_instance,
            "hardware_dir": (
                f"~/Blacknode/devices/{selected_instance}/hardware"
            ),
            "stack_mode": "isolated",
        }
    finally:
        try:
            _run(
                connection,
                f"rm -f -- {remote_script_path}",
                timeout=10.0,
            )
        except DeviceInstallError:
            pass
        connection.close()


def inspect_runtime(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
) -> dict[str, Any]:
    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    try:
        report = _public_inspection(_inspect_connection(connection))
        report["host_fingerprint"] = connection.fingerprint
        return report
    finally:
        connection.close()


def install_runtime(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    action: str = "install",
    instance_id: str = "",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    report(2, "Connecting securely")
    expected = str(host_fingerprint or "").strip()
    if not expected:
        raise DeviceInstallError(
            "Check the SSH connection and confirm its host fingerprint first."
        )
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=expected,
        timeout=15.0,
    )
    clean_action = str(action or "").strip().lower()
    if clean_action not in {
        "install",
        "reuse",
        "replace",
        "side_by_side",
        "isolated_stack",
    }:
        connection.close()
        raise DeviceInstallError(
            "Choose install, reuse, replace, side_by_side, or isolated_stack."
        )
    started = time.monotonic()
    token = ""
    remote_token_path = ""
    remote_script_path = ""
    try:
        report(6, "Inspecting existing runtimes")
        inspection = _inspect_connection(connection)
        instances = [
            item for item in inspection.get("instances", [])
            if isinstance(item, dict)
        ]
        remove_old_port = False
        if clean_action == "install":
            if instances:
                raise DeviceInstallError(
                    "An existing runtime was found. Inspect the device and choose "
                    "reuse, replace, or side-by-side installation."
                )
            selected_instance = "default"
            runtime_port = int(inspection.get("suggested_port") or 0)
        elif clean_action in {"reuse", "replace"}:
            selected_instance = _clean_instance_id(instance_id or "default")
            existing = _find_instance(inspection, selected_instance)
            if not existing:
                raise DeviceInstallError(
                    f"Runtime instance '{selected_instance}' is no longer present. "
                    "Inspect the device again."
                )
            runtime_port = int(existing.get("port") or 0)
            if clean_action == "replace" and runtime_port < 1:
                runtime_port = int(inspection.get("suggested_port") or 0)
            if clean_action == "reuse":
                if not existing.get("healthy") or not existing.get("token_available"):
                    raise DeviceInstallError(
                        "The selected runtime is not healthy enough to reuse. "
                        "Choose reinstall or a separate installation."
                    )
                token = _read_remote_token(connection, existing)
                report(100, "Existing runtime paired")
                return {
                    "ok": True,
                    "runtime_token": token,
                    "host_fingerprint": connection.fingerprint,
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                    "action": clean_action,
                    "instance_id": selected_instance,
                    "runtime_port": runtime_port,
                    "service_name": str(existing.get("service_name") or ""),
                    "install_root": str(existing.get("install_root") or ""),
                    "runtime_dir": str(existing.get("runtime_dir") or ""),
                    "packages_dir": str(existing.get("packages_dir") or ""),
                    "stack_mode": "runtime_only",
                    "hardware_dir": "",
                }
            remove_old_port = bool(existing.get("service_installed"))
        else:
            selected_instance = _clean_instance_id(
                instance_id or str(inspection.get("suggested_instance_id") or "instance-2"),
                allow_default=False,
            )
            if _find_instance(inspection, selected_instance):
                raise DeviceInstallError(
                    f"Runtime instance '{selected_instance}' already exists. "
                    "Inspect the device again."
                )
            runtime_port = int(inspection.get("suggested_port") or 0)
        if runtime_port < 1:
            raise DeviceInstallError(
                "No available runtime port was found between 8766 and 8865."
            )

        token = secrets.token_urlsafe(32)
        remote_token_path = f"/tmp/blacknode-runtime-token-{secrets.token_hex(8)}"
        remote_script_path = f"/tmp/blacknode-runtime-install-{secrets.token_hex(8)}.sh"
        report(10, "Preparing runtime installation")
        script = """#!/usr/bin/env bash
set -euo pipefail
progress() {
  echo "__BLACKNODE_INSTALL_PROGRESS__=$1|$2"
}
sudo() {
  command sudo -S -p '' "$@"
}
export -f sudo
action="$1"
instance="$2"
runtime_port="$3"
token_source="$4"
remove_old_port="$5"
[[ "$instance" == "default" || "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || {
  echo "Invalid Blacknode runtime instance."
  exit 2
}
stack_root="$HOME/Blacknode/devices/$instance"
runtime_dir="$stack_root/runtime"
token_file="$stack_root/secrets/runtime.auth.token"
hardware_dir="$stack_root/hardware"
complete_stack=false
if [[ "$action" == "install" || "$action" == "replace" \
  || "$action" == "isolated_stack" ]]; then
  complete_stack=true
fi
if [[ "$instance" == "default" ]]; then
  service_name="blacknode-runtime.service"
  service_instance=""
  legacy_runtime_dir="$HOME/blacknode-runtime"
  legacy_token_file="$HOME/.blacknode/runtime.auth.token"
else
  service_name="blacknode-runtime-$instance.service"
  service_instance="$instance"
  legacy_runtime_dir="$HOME/blacknode-runtimes/$instance"
  legacy_token_file="$HOME/.blacknode/runtimes/$instance.auth.token"
fi
active_sibling_services=()
if [[ "$action" == "side_by_side" || "$action" == "isolated_stack" ]] \
  && command -v systemctl >/dev/null 2>&1; then
  mapfile -t active_sibling_services < <(
    systemctl list-units --type=service --state=active --no-legend \
      'blacknode-runtime*.service' 'blacknode-hardware*.service' 2>/dev/null \
      | awk '{print $1}'
  )
fi
install_complete=false
cleanup_install=false
cleanup_hardware=false
port_guard=""
port_file=""
cleanup_failed_install() {
  exit_code=$?
  if [[ -n "$port_guard" ]]; then
    kill "$port_guard" >/dev/null 2>&1 || true
    wait "$port_guard" >/dev/null 2>&1 || true
  fi
  [[ -z "$port_file" ]] || rm -f -- "$port_file"
  if [[ "$exit_code" -ne 0 && "$install_complete" != true && "$cleanup_install" == true ]]; then
    progress 0 "Cleaning the incomplete runtime"
    sudo systemctl stop "$service_name" >/dev/null 2>&1 || true
    sudo systemctl disable "$service_name" >/dev/null 2>&1 || true
    sudo rm -f -- "/etc/systemd/system/$service_name" >/dev/null 2>&1 || true
    sudo systemctl daemon-reload >/dev/null 2>&1 || true
    rm -rf -- "$runtime_dir"
    rm -f -- "$token_file"
    if [[ "$cleanup_hardware" == true ]]; then
      rm -rf -- "$hardware_dir"
    fi
  fi
  exit "$exit_code"
}
trap cleanup_failed_install EXIT
case "$runtime_dir" in
  "$HOME/Blacknode/devices/"*/runtime) ;;
  *) echo "Unsafe runtime directory."; exit 2 ;;
esac
case "$hardware_dir" in
  "$HOME/Blacknode/devices/"*/hardware) ;;
  *) echo "Unsafe Hardware directory."; exit 2 ;;
esac
case "$legacy_runtime_dir" in
  "$HOME/blacknode-runtime"|"$HOME/blacknode-runtimes/"*) ;;
  *) echo "Unsafe legacy Runtime directory."; exit 2 ;;
esac
token_dir="$(dirname -- "$token_file")"
progress 14 "Preparing the selected runtime"
if [[ "$complete_stack" == true && "$action" != "replace" \
  && -e "$hardware_dir" ]]; then
  echo "The isolated Hardware directory already exists. Preserve or remove it before retrying:"
  echo "  $hardware_dir"
  exit 3
fi
if [[ "$action" == "replace" ]]; then
  cleanup_install=true
  sudo systemctl stop "$service_name" >/dev/null 2>&1 || true
  sudo systemctl disable "$service_name" >/dev/null 2>&1 || true
  sudo rm -f -- "/etc/systemd/system/$service_name"
  sudo systemctl daemon-reload
  if [[ "$remove_old_port" == "1" ]] \
    && command -v ufw >/dev/null 2>&1 \
    && sudo ufw status 2>/dev/null | grep -qi '^Status: active'; then
    sudo ufw --force delete allow "$runtime_port/tcp" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$runtime_dir"
  rm -f -- "$token_file"
  rm -rf -- "$legacy_runtime_dir"
  rm -f -- "$legacy_token_file"
elif [[ -e "$runtime_dir" ]]; then
  echo "The selected runtime directory already exists. Inspect the device again."
  exit 3
else
  cleanup_install=true
fi
progress 20 "Checking the runtime port"
port_file="$(mktemp)"
python3 - "$runtime_port" "$port_file" <<'PY' &
import socket
import sys
import time
from pathlib import Path

port = int(sys.argv[1])
port_file = Path(sys.argv[2])
candidates = [port] + [
    candidate
    for candidate in range(8766, 8866)
    if candidate != port
]
for candidate in candidates:
    sock = socket.socket()
    try:
        sock.bind(("0.0.0.0", candidate))
    except OSError:
        sock.close()
        continue
    port_file.write_text(str(candidate), encoding="utf-8")
    while True:
        time.sleep(60)
raise SystemExit("No available runtime port was found between 8766 and 8865.")
PY
port_guard=$!
for _attempt in {1..100}; do
  [[ -s "$port_file" ]] && break
  if ! kill -0 "$port_guard" >/dev/null 2>&1; then
    wait "$port_guard"
  fi
  sleep 0.05
done
if [[ ! -s "$port_file" ]]; then
  echo "Could not reserve an available runtime port."
  exit 5
fi
runtime_port="$(cat "$port_file")"
echo "__BLACKNODE_RUNTIME_PORT__=$runtime_port"
progress 28 "Updating package indexes"
sudo apt-get update
progress 36 "Checking required system tools"
sudo apt-get install -y git
progress 42 "Creating isolated runtime files"
mkdir -p "$token_dir"
install -m 0600 "$token_source" "$token_file"
mkdir -p "$(dirname -- "$runtime_dir")"
progress 48 "Downloading Blacknode Runtime"
git clone https://github.com/temiroff/blacknode-runtime.git "$runtime_dir"
if [[ -n "$service_instance" ]] \
  && ! grep -q 'BLACKNODE_RUNTIME_INSTANCE' "$runtime_dir/install-service.sh"; then
  progress 54 "Enabling independent runtime support"
  python3 - "$runtime_dir" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
replacement = '''instance="${BLACKNODE_RUNTIME_INSTANCE:-}"
if [[ -n "$instance" && ! "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]]; then
  echo "BLACKNODE_RUNTIME_INSTANCE must contain lowercase letters, numbers, or hyphens."
  exit 2
fi
unit_name="blacknode-runtime${instance:+-$instance}.service"'''
for name in ("install-service.sh", "service.sh"):
    path = root / name
    text = path.read_text(encoding="utf-8")
    old = 'unit_name="blacknode-runtime.service"'
    if old not in text:
        raise SystemExit(f"{name} has an unsupported service layout")
    path.write_text(text.replace(old, replacement, 1), encoding="utf-8")
PY
  if ! grep -q 'BLACKNODE_RUNTIME_INSTANCE' "$runtime_dir/install-service.sh" \
    || ! grep -q 'BLACKNODE_RUNTIME_INSTANCE' "$runtime_dir/service.sh"; then
    echo "Could not enable independent runtime support in the downloaded release."
    rm -rf -- "$runtime_dir"
    rm -f -- "$token_file"
    exit 4
  fi
fi
cd "$runtime_dir"
progress 58 "Creating the Python environment"
BLACKNODE_AUTH_TOKEN_FILE="$token_file" \
BLACKNODE_RUNTIME_PORT="$runtime_port" \
BLACKNODE_RUNTIME_INSTANCE="$service_instance" \
./setup_ubuntu.sh
if [[ -n "$service_instance" ]]; then
  progress 78 "Configuring the independent instance"
  BLACKNODE_RUNTIME_INSTANCE="$service_instance" ./configure.sh \
    --device-id "$(hostname)-$service_instance"
fi
if [[ "$complete_stack" == true && ! -d "$hardware_dir" ]]; then
  progress 72 "Installing the Robot Hardware package"
  mkdir -p "$(dirname -- "$hardware_dir")"
  cleanup_hardware=true
  git clone https://github.com/temiroff/blacknode-hardware.git "$hardware_dir"
  if ! grep -q 'BLACKNODE_HARDWARE_INSTANCE' "$hardware_dir/install-service.sh" \
    || ! grep -q 'previous_working_directory' "$hardware_dir/install-service.sh"; then
    echo "The downloaded Blacknode Hardware release does not support isolated stacks yet."
    exit 4
  fi
  (
    cd "$hardware_dir"
    BLACKNODE_HARDWARE_INSTANCE="$service_instance" ./setup_ubuntu.sh
  )
elif [[ "$complete_stack" == true ]]; then
  [[ -d "$hardware_dir/.git" && -f "$hardware_dir/pyproject.toml" ]] || {
    echo "The existing Hardware directory is not a valid package checkout:"
    echo "  $hardware_dir"
    exit 4
  }
fi
progress 88 "Installing the runtime service"
kill "$port_guard" >/dev/null 2>&1 || true
wait "$port_guard" >/dev/null 2>&1 || true
port_guard=""
rm -f -- "$port_file"
port_file=""
BLACKNODE_RUNTIME_PORT="$runtime_port" \
BLACKNODE_RUNTIME_INSTANCE="$service_instance" \
./install-service.sh
if [[ "${#active_sibling_services[@]}" -gt 0 ]]; then
  progress 92 "Verifying existing runtimes and robot services"
  for sibling_service in "${active_sibling_services[@]}"; do
    if [[ "$sibling_service" != "$service_name" ]] \
      && ! sudo systemctl is-active --quiet "$sibling_service"; then
      sudo systemctl start "$sibling_service"
    fi
  done
fi
if command -v ufw >/dev/null 2>&1 \
  && sudo ufw status 2>/dev/null | grep -qi '^Status: active' \
  && sudo systemctl is-active --quiet blacknode-runtime.service; then
  default_port="$(
    sudo systemctl cat blacknode-runtime.service 2>/dev/null \
      | sed -nE 's/.*--port[= ]"?([0-9]+).*/\\1/p' \
      | tail -n 1
  )"
  if [[ "$default_port" =~ ^[0-9]+$ ]]; then
    sudo ufw allow "$default_port/tcp" comment "Blacknode runtime" >/dev/null
  fi
fi
python3 - "$stack_root/install.json" "$instance" "$runtime_dir" "$hardware_dir" \
  "$service_name" "$action" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps({
    "layout_version": 1,
    "instance_id": sys.argv[2],
    "runtime_dir": sys.argv[3],
    "packages_dir": str(Path(sys.argv[3]) / "packages"),
    "hardware_dir": (
        sys.argv[4]
        if sys.argv[6] in {"install", "replace", "isolated_stack"}
        else ""
    ),
    "runtime_service": sys.argv[5],
}, indent=2) + "\\n", encoding="utf-8")
PY
install_complete=true
progress 96 "Verifying the runtime service"
"""
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_token_path, "w") as remote_token:
                remote_token.write(token + "\n")
            sftp.chmod(remote_token_path, 0o600)
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()

        def remote_output(line: str) -> None:
            nonlocal runtime_port
            port_match = re.match(
                r"^__BLACKNODE_RUNTIME_PORT__=(\d{1,5})$",
                line.strip(),
            )
            if port_match:
                runtime_port = int(port_match.group(1))
                report(22, f"Reserved runtime port {runtime_port}")
                return
            match = re.match(
                r"^__BLACKNODE_INSTALL_PROGRESS__=(\d{1,3})\|(.*)$",
                line.strip(),
            )
            if match:
                report(int(match.group(1)), match.group(2).strip())

        _run(
            connection,
            (
                f"bash {remote_script_path} "
                f"{clean_action} {selected_instance} {runtime_port} {remote_token_path} "
                f"{1 if remove_old_port else 0}"
            ),
            stdin_text=_sudo_input(password),
            timeout=900.0,
            on_output=remote_output,
        )
        service_name = (
            "blacknode-runtime.service"
            if selected_instance == "default"
            else f"blacknode-runtime-{selected_instance}.service"
        )
        report(96, "Runtime service started")
        return {
            "ok": True,
            "runtime_token": token,
            "host_fingerprint": connection.fingerprint,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "action": clean_action,
            "instance_id": selected_instance,
            "runtime_port": runtime_port,
            "service_name": service_name,
            "install_root": f"~/Blacknode/devices/{selected_instance}",
            "runtime_dir": f"~/Blacknode/devices/{selected_instance}/runtime",
            "packages_dir": f"~/Blacknode/devices/{selected_instance}/runtime/packages",
            "stack_mode": (
                "isolated"
                if clean_action in {"install", "replace", "isolated_stack"}
                else "runtime_only"
            ),
            "hardware_dir": (
                f"~/Blacknode/devices/{selected_instance}/hardware"
                if clean_action in {"install", "replace", "isolated_stack"}
                else ""
            ),
        }
    finally:
        if remote_script_path or remote_token_path:
            try:
                _run(
                    connection,
                    f"rm -f -- {remote_script_path} {remote_token_path}",
                    timeout=10.0,
                )
            except DeviceInstallError:
                pass
        connection.close()


def update_managed_services(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    runtime_port: int,
    hardware_ports: list[int],
    hardware_device_ids: dict[int, str] | None = None,
    include_runtime: bool = True,
    stack_mode: str = "runtime_only",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Fast-forward and restart selected managed Runtime and Hardware services."""

    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    selected_instance = _clean_instance_id(instance_id or "default")
    selected_stack_mode = str(stack_mode or "runtime_only").strip().lower()
    if selected_stack_mode not in {"runtime_only", "isolated"}:
        raise DeviceInstallError("The managed stack mode is invalid.")
    selected_runtime_port = int(runtime_port)
    if selected_runtime_port < 1 or selected_runtime_port > 65535:
        raise DeviceInstallError("The managed runtime port is invalid.")
    selected_hardware_ports = sorted({int(value) for value in hardware_ports})
    selected_hardware_targets = [
        {
            "port": value,
            "device_id": str((hardware_device_ids or {}).get(value) or ""),
        }
        for value in selected_hardware_ports
    ]
    if any(value < 1 or value > 65535 for value in selected_hardware_ports):
        raise DeviceInstallError("A robot hardware port is invalid.")
    if not include_runtime and not selected_hardware_ports:
        raise DeviceInstallError("Choose Runtime, Hardware, or both to update.")

    report(3, "Connecting to the verified device")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    remote_script_path = f"/tmp/blacknode-update-{secrets.token_hex(8)}.sh"
    script = r"""#!/usr/bin/env bash
set -euo pipefail
progress() {
  echo "__BLACKNODE_UPDATE_PROGRESS__=$1|$2"
}
sudo() {
  command sudo -S -p '' "$@"
}
export -f sudo

include_runtime="$1"
instance="$2"
runtime_port="$3"
hardware_targets_payload="$4"
stack_mode="$5"
hardware_ports=()
hardware_device_ids=()
while IFS=$'\t' read -r target_port target_device_id; do
  [[ -n "$target_port" ]] || continue
  hardware_ports+=("$target_port")
  hardware_device_ids+=("$target_device_id")
done < <(
  python3 - "$hardware_targets_payload" <<'PY'
import base64
import json
import sys

targets = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
for target in targets:
    print(f"{int(target['port'])}\t{str(target.get('device_id') or '')}")
PY
)
organized_stack="$HOME/Blacknode/devices/$instance"
organized_runtime_dir="$organized_stack/runtime"
organized_hardware_dir="$organized_stack/hardware"
if [[ "$instance" == "default" ]]; then
  legacy_runtime_dir="$HOME/blacknode-runtime"
  legacy_hardware_dir="$HOME/blacknode-hardware"
  runtime_service="blacknode-runtime.service"
else
  [[ "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || {
    echo "Invalid Blacknode runtime instance."
    exit 2
  }
  legacy_runtime_dir="$HOME/blacknode-runtimes/$instance"
  legacy_hardware_dir="$HOME/blacknode-hardware-instances/$instance"
  runtime_service="blacknode-runtime-$instance.service"
fi
runtime_dir="$legacy_runtime_dir"
[[ ! -d "$organized_runtime_dir" ]] || runtime_dir="$organized_runtime_dir"
hardware_repo="$legacy_hardware_dir"
[[ ! -d "$organized_hardware_dir" ]] || hardware_repo="$organized_hardware_dir"

package_version() {
  python3 - "$1" <<'PY'
import sys
import tomllib
from pathlib import Path

path = Path(sys.argv[1]) / "pyproject.toml"
try:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    print(str((payload.get("project") or {}).get("version") or "unknown"))
except Exception:
    print("unknown")
PY
}

validate_checkout() {
  local directory="$1"
  local repository="$2"
  [[ -d "$directory/.git" && -f "$directory/pyproject.toml" ]] || {
    echo "$repository is not an updateable Git checkout: $directory"
    exit 3
  }
  local origin
  origin="$(git -C "$directory" remote get-url origin 2>/dev/null || true)"
  python3 - "$origin" "$repository" <<'PY'
import re
import sys

origin = sys.argv[1].strip().lower().removesuffix(".git").rstrip("/")
repository = sys.argv[2].strip().lower()
if not re.search(rf"(?:github\.com[:/])temiroff/{re.escape(repository)}$", origin):
    raise SystemExit(
        f"Refusing to update {repository}: its origin is not the trusted "
        f"temiroff/{repository} repository."
    )
PY
  if [[ -n "$(git -C "$directory" status --porcelain --untracked-files=normal)" ]]; then
    echo "$repository has local changes. Commit, stash, or remove them before remote update."
    exit 4
  fi
  git -C "$directory" rev-parse --verify '@{upstream}' >/dev/null 2>&1 || {
    echo "$repository does not have an upstream branch configured."
    exit 5
  }
}

resolve_hardware_unit() {
  local hardware_port="$1"
  local matches=()
  local active_matches=()
  local enabled_matches=()
  local unit exec_start unit_definition normalized unit_path
  mapfile -t candidate_units < <(
    {
      systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
      systemctl list-units --all --type=service 'blacknode-hardware*.service' \
        --no-legend 2>/dev/null
      find /etc/systemd/system /run/systemd/system -maxdepth 1 \
        -name 'blacknode-hardware*.service' -printf '%f\n' 2>/dev/null
    } | awk '{print $1}' | sort -u
  )
  for unit in "${candidate_units[@]}"; do
    [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\.service$ ]] || continue
    exec_start="$(systemctl show "$unit" --property=ExecStart --value 2>/dev/null || true)"
    unit_definition=""
    for unit_path in "/etc/systemd/system/$unit" "/run/systemd/system/$unit"; do
      if [[ -f "$unit_path" ]]; then
        unit_definition+="$(command cat "$unit_path")"
        unit_definition+=$'\n'
      fi
    done
    normalized="${exec_start//\"/}"$'\n'"${unit_definition//\"/}"
    if printf '%s\n' "$normalized" \
      | grep -oE -- '--port(=|[[:space:]])[0-9]+' \
      | grep -oE '[0-9]+' \
      | grep -Fxq -- "$hardware_port"; then
      matches+=("$unit")
      systemctl is-active --quiet "$unit" 2>/dev/null \
        && active_matches+=("$unit")
      systemctl is-enabled --quiet "$unit" 2>/dev/null \
        && enabled_matches+=("$unit")
    fi
  done
  if [[ "${#matches[@]}" -eq 0 ]]; then
    echo "No installed or active Blacknode Hardware systemd service matches port $hardware_port. Discovered units: ${candidate_units[*]:-none}." >&2
    return 60
  fi
  if [[ "${#matches[@]}" -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  if [[ "${#active_matches[@]}" -eq 1 ]]; then
    printf '%s\n' "${active_matches[0]}"
    return 0
  fi
  if [[ "${#active_matches[@]}" -gt 1 ]]; then
    echo "Multiple active Blacknode Hardware services claim port $hardware_port: ${active_matches[*]}." >&2
    return 61
  fi
  if [[ "${#enabled_matches[@]}" -eq 1 ]]; then
    printf '%s\n' "${enabled_matches[0]}"
    return 0
  fi
  echo "Could not choose the persistent Hardware service for port $hardware_port. Candidates: ${matches[*]}. Enabled: ${enabled_matches[*]:-none}." >&2
  return 61
}

stop_verified_manual_hardware() {
  local hardware_repo="$1"
  local hardware_port="$2"
  local listener_pids=()
  local pid cmdline
  if command -v ss >/dev/null 2>&1; then
    mapfile -t listener_pids < <(
      ss -H -ltnp "sport = :$hardware_port" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
    )
  elif command -v lsof >/dev/null 2>&1; then
    mapfile -t listener_pids < <(
      lsof -nP -t -iTCP:"$hardware_port" -sTCP:LISTEN 2>/dev/null | sort -u
    )
  fi
  if [[ "${#listener_pids[@]}" -eq 0 ]]; then
    if (echo >/dev/tcp/127.0.0.1/"$hardware_port") >/dev/null 2>&1; then
      echo "Port $hardware_port is owned by a process that SSH cannot identify. Stop the manually running Hardware process and retry Repair Hardware." >&2
      return 1
    fi
    return 0
  fi
  for pid in "${listener_pids[@]}"; do
    [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || {
      echo "Could not verify the process listening on Hardware port $hardware_port." >&2
      return 1
    }
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    if [[ "$cmdline" != *"$hardware_repo/scripts/hardware_service.py"* ]] \
      || [[ ! "$cmdline" =~ --port(=|[[:space:]])${hardware_port}([^0-9]|$) ]]; then
      echo "Refusing to stop unverified process $pid on Hardware port $hardware_port: $cmdline" >&2
      return 1
    fi
  done
  for pid in "${listener_pids[@]}"; do
    echo "Stopping verified manually started Hardware process $pid on port $hardware_port."
    kill -TERM "$pid"
  done
  for _attempt in {1..40}; do
    listening=false
    for pid in "${listener_pids[@]}"; do
      kill -0 "$pid" >/dev/null 2>&1 && listening=true
    done
    [[ "$listening" == false ]] && return 0
    sleep 0.25
  done
  echo "The manually running Hardware process on port $hardware_port did not stop. Stop it from its terminal and retry Repair Hardware." >&2
  return 1
}

install_persistent_hardware_services() {
  [[ -x "$hardware_repo/install-service.sh" ]] || {
    echo "Repair Hardware requires $hardware_repo/install-service.sh." >&2
    return 1
  }
  validate_checkout "$hardware_repo" "blacknode-hardware"
  if [[ -f "$hardware_repo/.blacknode-hardware/devices.json" ]]; then
    python3 - "$hardware_repo/.blacknode-hardware/devices.json" \
      "$hardware_targets_payload" <<'PY'
import base64
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
targets = json.loads(base64.urlsafe_b64decode(sys.argv[2]).decode("utf-8"))
payload = json.loads(path.read_text(encoding="utf-8"))
devices = payload.get("devices") or []
by_id = {
    str(item.get("device_id") or ""): item
    for item in devices
    if isinstance(item, dict) and item.get("device_id")
}
for target in targets:
    device_id = str(target.get("device_id") or "")
    if not device_id:
        raise SystemExit(
            f"Cannot reconcile Hardware port {target['port']}: "
            "the paired robot has no stable device identity."
        )
    device = by_id.get(device_id)
    if device is None:
        raise SystemExit(
            f"Cannot reconcile Hardware port {target['port']}: device identity "
            f"{device_id!r} is not present in {path}."
        )
    device["service_port"] = int(target["port"])
ports = [int(item["service_port"]) for item in devices]
if len(ports) != len(set(ports)):
    raise SystemExit(
        "Cannot reconcile Hardware services because two configured robots "
        "would use the same HTTP port."
    )
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, path)
PY
  fi
  for hardware_port in "${hardware_ports[@]}"; do
    stop_verified_manual_hardware "$hardware_repo" "$hardware_port"
  done
  progress 11 "Installing missing persistent Hardware services"
  if [[ -f "$hardware_repo/.blacknode-hardware/devices.json" ]]; then
    (
      cd "$hardware_repo"
      ./install-service.sh --all
    )
  elif [[ "${#hardware_ports[@]}" -eq 1 ]]; then
    (
      cd "$hardware_repo"
      BLACKNODE_HARDWARE_PORT="${hardware_ports[0]}" ./install-service.sh
    )
  else
    echo "Multiple Hardware ports require a saved multi-robot configuration. Run ./configure.sh --all before Repair Hardware." >&2
    return 1
  fi
}

progress 8 "Resolving selected managed services"
if [[ "$include_runtime" == "1" ]]; then
  [[ -d "$runtime_dir" ]] || {
    echo "The managed runtime directory is missing: $runtime_dir"
    exit 3
  }
fi
repair_hardware=false
for hardware_port in "${hardware_ports[@]}"; do
  if unit="$(resolve_hardware_unit "$hardware_port")"; then
    :
  else
    resolve_status=$?
    if [[ "$resolve_status" -eq 60 ]]; then
      repair_hardware=true
    else
      exit 6
    fi
  fi
done
if [[ "$repair_hardware" == true ]]; then
  install_persistent_hardware_services || exit 6
fi
hardware_units=()
hardware_dirs=()
for hardware_port in "${hardware_ports[@]}"; do
  [[ "$hardware_port" =~ ^[0-9]{1,5}$ ]] || exit 2
  if ! unit="$(resolve_hardware_unit "$hardware_port")"; then
    echo "Repair Hardware did not create exactly one persistent service for port $hardware_port." >&2
    exit 6
  fi
  directory="$(systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true)"
  if [[ -z "$directory" ]]; then
    for unit_path in "/etc/systemd/system/$unit" "/run/systemd/system/$unit"; do
      if [[ -f "$unit_path" ]]; then
        directory="$(
          sed -nE 's/^WorkingDirectory=(.*)$/\1/p' "$unit_path" | tail -n 1
        )"
        [[ -n "$directory" ]] && break
      fi
    done
  fi
  [[ -n "$directory" ]] || {
    echo "$unit does not report its repository WorkingDirectory." >&2
    exit 6
  }
  hardware_units+=("$unit")
  hardware_dirs+=("$directory")
done

progress 15 "Checking trusted clean Git checkouts"
if [[ "$include_runtime" == "1" ]]; then
  validate_checkout "$runtime_dir" "blacknode-runtime"
fi
unique_hardware_dirs=()
for directory in "${hardware_dirs[@]}"; do
  found=false
  for existing in "${unique_hardware_dirs[@]}"; do
    [[ "$existing" == "$directory" ]] && found=true
  done
  if [[ "$found" == false ]]; then
    validate_checkout "$directory" "blacknode-hardware"
    unique_hardware_dirs+=("$directory")
  fi
done

runtime_before_version=""
runtime_before_commit=""
if [[ "$include_runtime" == "1" ]]; then
  runtime_before_version="$(package_version "$runtime_dir")"
  runtime_before_commit="$(git -C "$runtime_dir" rev-parse --short=12 HEAD)"
fi
hardware_before_versions=()
hardware_before_commits=()
for directory in "${hardware_dirs[@]}"; do
  hardware_before_versions+=("$(package_version "$directory")")
  hardware_before_commits+=("$(git -C "$directory" rev-parse --short=12 HEAD)")
done

if [[ "$include_runtime" == "1" ]]; then
  progress 25 "Downloading Runtime updates"
  git -C "$runtime_dir" fetch --prune
fi
for directory in "${unique_hardware_dirs[@]}"; do
  progress 35 "Downloading robot hardware updates"
  git -C "$directory" fetch --prune
done

services=()
if [[ "$include_runtime" == "1" ]]; then
  services+=("$runtime_service")
fi
services+=("${hardware_units[@]}")
restore_services() {
  local unit
  for unit in "${services[@]}"; do
    sudo systemctl start "$unit" >/dev/null 2>&1 || true
  done
}
trap restore_services EXIT

progress 45 "Stopping managed services"
for unit in "${hardware_units[@]}"; do
  sudo systemctl stop "$unit"
done
if [[ "$include_runtime" == "1" ]]; then
  sudo systemctl stop "$runtime_service"
fi

if [[ "$include_runtime" == "1" ]]; then
  progress 55 "Fast-forwarding Blacknode Runtime"
  git -C "$runtime_dir" merge --ff-only '@{upstream}'
  "$runtime_dir/.venv/bin/python" -m pip install -e "$runtime_dir"
fi

for directory in "${unique_hardware_dirs[@]}"; do
  progress 68 "Fast-forwarding Blacknode Hardware"
  git -C "$directory" merge --ff-only '@{upstream}'
  "$directory/.venv/bin/python" -m pip install -e "$directory"
done

progress 80 "Starting the selected updated services"
if [[ "$include_runtime" == "1" ]]; then
  sudo systemctl start "$runtime_service"
fi
for unit in "${hardware_units[@]}"; do
  sudo systemctl start "$unit"
done

for unit in "${services[@]}"; do
  state=""
  for _attempt in {1..60}; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    [[ "$state" == "active" ]] && break
    sleep 0.25
  done
  [[ "$state" == "active" ]] || {
    echo "$unit did not return to the active state."
    exit 7
  }
done
trap - EXIT

progress 90 "Collecting installed versions"
report_file="$(mktemp)"
trap 'rm -f -- "$report_file"' EXIT
if [[ "$include_runtime" == "1" ]]; then
  runtime_after_version="$(package_version "$runtime_dir")"
  runtime_after_commit="$(git -C "$runtime_dir" rev-parse --short=12 HEAD)"
  printf 'runtime\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$runtime_service" "$runtime_port" "$runtime_before_version" "$runtime_after_version" \
    "$runtime_before_commit" "$runtime_after_commit" >> "$report_file"
fi
for index in "${!hardware_units[@]}"; do
  directory="${hardware_dirs[$index]}"
  printf 'hardware\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${hardware_units[$index]}" "${hardware_ports[$index]}" \
    "${hardware_before_versions[$index]}" "$(package_version "$directory")" \
    "${hardware_before_commits[$index]}" "$(git -C "$directory" rev-parse --short=12 HEAD)" \
    >> "$report_file"
done
python3 - "$report_file" <<'PY'
import json
import sys
from pathlib import Path

components = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    kind, service, port, before_version, after_version, before_commit, after_commit = line.split("\t")
    components.append({
        "kind": kind,
        "service_name": service,
        "port": int(port),
        "before": {"version": before_version, "commit": before_commit},
        "after": {"version": after_version, "commit": after_commit},
        "changed": before_commit != after_commit,
        "state": "active",
    })
print("__BLACKNODE_UPDATE_REPORT__=" + json.dumps({
    "ok": True,
    "components": components,
}, separators=(",", ":")))
PY
progress 96 "Managed services updated"
"""
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()

        def remote_output(line: str) -> None:
            match = re.match(
                r"^__BLACKNODE_UPDATE_PROGRESS__=(\d{1,3})\|(.*)$",
                line.strip(),
            )
            if match:
                report(int(match.group(1)), match.group(2).strip())

        targets_payload = base64.urlsafe_b64encode(json.dumps(
            selected_hardware_targets,
            separators=(",", ":"),
        ).encode("utf-8")).decode("ascii")
        arguments = " ".join([
            "1" if include_runtime else "0",
            selected_instance,
            str(selected_runtime_port),
            targets_payload,
            selected_stack_mode,
        ])
        output = _run(
            connection,
            f"bash {remote_script_path} {arguments}",
            stdin_text=_sudo_input(password),
            timeout=900.0,
            on_output=remote_output,
        )
        payload_line = next(
            (
                line[len(_UPDATE_REPORT_MARKER):]
                for line in reversed(output.splitlines())
                if line.startswith(_UPDATE_REPORT_MARKER)
            ),
            "",
        )
        if not payload_line:
            raise DeviceInstallError("The device did not return an update report.")
        try:
            result = json.loads(payload_line)
        except json.JSONDecodeError as exc:
            raise DeviceInstallError("The device returned an invalid update report.") from exc
        if not isinstance(result, dict) or not isinstance(result.get("components"), list):
            raise DeviceInstallError("The device returned an incomplete update report.")
        result["host_fingerprint"] = connection.fingerprint
        return result
    finally:
        try:
            _run(connection, f"rm -f -- {remote_script_path}", timeout=10.0)
        except DeviceInstallError:
            pass
        connection.close()


def inspect_managed_service_updates(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    runtime_port: int,
    hardware_ports: list[int],
    hardware_device_ids: dict[int, str] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Compare installed managed-service commits with their trusted upstreams."""

    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    selected_instance = _clean_instance_id(instance_id or "default")
    selected_runtime_port = int(runtime_port)
    if selected_runtime_port < 1 or selected_runtime_port > 65535:
        raise DeviceInstallError("The managed runtime port is invalid.")
    selected_hardware_ports = sorted({int(value) for value in hardware_ports})
    if any(value < 1 or value > 65535 for value in selected_hardware_ports):
        raise DeviceInstallError("A robot hardware port is invalid.")

    report(5, "Connecting to the verified device")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    arguments = base64.urlsafe_b64encode(json.dumps({
        "instance_id": selected_instance,
        "runtime_port": selected_runtime_port,
        "hardware_targets": [
            {
                "port": value,
                "device_id": str((hardware_device_ids or {}).get(value) or ""),
            }
            for value in selected_hardware_ports
        ],
    }, separators=(",", ":")).encode("utf-8")).decode("ascii")
    script = rf"""python3 - {arguments} <<'PY'
import base64
import json
import re
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

MARKER = "__BLACKNODE_UPDATE_CHECK__="
request = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
home = Path.home()
instance = request["instance_id"]
organized_runtime = home / "Blacknode" / "devices" / instance / "runtime"
if instance == "default":
    legacy_runtime = home / "blacknode-runtime"
    runtime_service = "blacknode-runtime.service"
else:
    legacy_runtime = home / "blacknode-runtimes" / instance
    runtime_service = f"blacknode-runtime-{{instance}}.service"
runtime_dir = organized_runtime if organized_runtime.is_dir() else legacy_runtime

def command(args, timeout=30):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 124, "", str(exc))

def project_version(text):
    try:
        payload = tomllib.loads(text)
        return str((payload.get("project") or {{}}).get("version") or "unknown")
    except Exception:
        return "unknown"

def package_version(directory):
    try:
        return project_version(
            (Path(directory) / "pyproject.toml").read_text(encoding="utf-8")
        )
    except Exception:
        return "unknown"

def resolve_hardware(port, expected_device_id):
    installed = command([
        "systemctl", "list-unit-files", "blacknode-hardware*.service", "--no-legend"
    ])
    active = command([
        "systemctl", "list-units", "--all", "--type=service",
        "blacknode-hardware*.service", "--no-legend",
    ])
    candidate_units = {{
        line.split()[0]
        for line in (installed.stdout + "\n" + active.stdout).splitlines()
        if line.split()
    }}
    candidate_units.update(
        path.name
        for root in (Path("/etc/systemd/system"), Path("/run/systemd/system"))
        for path in root.glob("blacknode-hardware*.service")
    )
    matches = []
    states = {{}}
    definitions = {{}}
    declared_ports = {{}}
    device_ids = {{}}
    for unit in sorted(candidate_units):
        if not re.fullmatch(r"blacknode-hardware(?:[-.@][A-Za-z0-9_.@-]+)?\.service", unit):
            continue
        shown = command(["systemctl", "show", unit, "--property=ExecStart", "--value"])
        definition = ""
        for root in (Path("/etc/systemd/system"), Path("/run/systemd/system")):
            unit_path = root / unit
            if unit_path.is_file():
                try:
                    definition += unit_path.read_text(encoding="utf-8") + "\n"
                except OSError:
                    pass
        definitions[unit] = definition
        normalized = (shown.stdout + "\n" + definition).replace('"', "")
        declared_ports[unit] = sorted({{
            int(value)
            for value in re.findall(r"--port(?:=|\s+)([0-9]+)", normalized)
        }})
        config_match = re.search(r"--config(?:=|\s+)([^\s;]+)", normalized)
        configured_device_id = ""
        if config_match:
            try:
                configured_device_id = str(
                    json.loads(
                        Path(config_match.group(1)).read_text(encoding="utf-8")
                    ).get("device_id") or ""
                )
            except Exception:
                pass
        device_ids[unit] = configured_device_id
        states[unit] = {{
            "active": command(["systemctl", "is-active", unit]).stdout.strip() or "unknown",
            "enabled": command(["systemctl", "is-enabled", unit]).stdout.strip() or "unknown",
        }}
        if int(port) in declared_ports[unit]:
            matches.append(unit)
    resolution_error = ""
    if not matches:
        identity_matches = [
            unit
            for unit in sorted(candidate_units)
            if expected_device_id and device_ids.get(unit) == expected_device_id
        ]
        if identity_matches:
            matches = identity_matches
            configured = sorted({{
                configured_port
                for unit in identity_matches
                for configured_port in declared_ports.get(unit, [])
            }})
            resolution_error = (
                f"The persistent service for robot {{expected_device_id!r}} "
                f"declares port(s) {{configured or ['unknown']}}, while the editor "
                f"is paired to port {{port}}. Repair Hardware will reconcile the "
                "saved service port using this stable robot identity."
            )
        else:
            details = ", ".join(
                f"{{unit}} (ports={{declared_ports.get(unit) or ['unknown']}}, "
                f"device_id={{device_ids.get(unit) or 'unknown'}})"
                for unit in sorted(candidate_units)
            ) or "none"
            raise RuntimeError(
                f"No persistent Hardware service matches port {{port}} or robot "
                f"identity {{expected_device_id or 'not reported'!r}}. "
                f"Discovered units: {{details}}."
            )
    active_matches = [
        unit for unit in matches if states[unit]["active"] == "active"
    ]
    enabled_matches = [
        unit for unit in matches if states[unit]["enabled"] == "enabled"
    ]
    if len(matches) == 1:
        unit = matches[0]
    elif len(active_matches) == 1:
        unit = active_matches[0]
    elif len(active_matches) > 1:
        raise RuntimeError(
            f"Multiple active Blacknode Hardware services claim port {{port}}: "
            + ", ".join(active_matches)
        )
    elif len(enabled_matches) == 1:
        unit = enabled_matches[0]
    else:
        details = ", ".join(
            f"{{candidate}} (active={{states[candidate]['active']}}, "
            f"enabled={{states[candidate]['enabled']}})"
            for candidate in matches
        )
        raise RuntimeError(
            f"Could not choose the persistent Hardware service for port {{port}}. "
            f"Candidates: {{details}}."
        )
    directory = command([
        "systemctl", "show", unit, "--property=WorkingDirectory", "--value"
    ]).stdout.strip()
    if not directory:
        working_directory = re.findall(
            r"^WorkingDirectory=(.+)$",
            definitions.get(unit, ""),
            flags=re.MULTILINE,
        )
        if working_directory:
            directory = working_directory[-1].strip().strip('"')
    if not directory:
        raise RuntimeError(f"{{unit}} does not report its repository WorkingDirectory.")
    return unit, Path(directory), resolution_error

def inspect(kind, repository, service, port, directory):
    component = {{
        "kind": kind,
        "service_name": service,
        "port": int(port),
        "installed": {{"version": package_version(directory), "commit": ""}},
        "latest": {{"version": "unknown", "commit": ""}},
        "update_available": False,
        "can_update": False,
        "dirty": False,
        "state": command(["systemctl", "is-active", service]).stdout.strip() or "unknown",
        "error": "",
    }}
    try:
        if not (directory / ".git").is_dir():
            raise RuntimeError(f"{{repository}} is not an updateable Git checkout.")
        origin = command(["git", "-C", str(directory), "remote", "get-url", "origin"])
        origin_url = origin.stdout.strip()
        normalized = origin_url.lower().removesuffix(".git").rstrip("/")
        if not re.search(
            rf"(?:github\.com[:/])temiroff/{{re.escape(repository)}}$",
            normalized,
        ):
            raise RuntimeError(
                f"origin is not the trusted temiroff/{{repository}} repository"
            )
        current = command(["git", "-C", str(directory), "rev-parse", "HEAD"])
        if current.returncode:
            raise RuntimeError(current.stderr.strip() or "could not read installed commit")
        component["installed"]["commit"] = current.stdout.strip()[:12]
        dirty = command([
            "git", "-C", str(directory), "status", "--porcelain", "--untracked-files=normal"
        ])
        component["dirty"] = bool(dirty.stdout.strip())
        branch = command([
            "git", "-C", str(directory), "rev-parse", "--abbrev-ref", "HEAD",
        ]).stdout.strip()
        upstream = command([
            "git", "-C", str(directory), "config", "--get",
            f"branch.{{branch}}.merge",
        ])
        upstream_ref = upstream.stdout.strip()
        if not upstream_ref.startswith("refs/heads/"):
            raise RuntimeError("the installed branch has no upstream configured")
        latest = command(["git", "ls-remote", origin_url, upstream_ref], timeout=45)
        if latest.returncode or not latest.stdout.strip():
            raise RuntimeError(
                latest.stderr.strip() or "could not read the latest upstream commit"
            )
        latest_commit = latest.stdout.split()[0]
        component["latest"]["commit"] = latest_commit[:12]
        component["update_available"] = current.stdout.strip() != latest_commit
        if not component["update_available"]:
            component["latest"]["version"] = component["installed"]["version"]
        else:
            local_latest = command([
                "git", "-C", str(directory), "show",
                f"{{latest_commit}}:pyproject.toml",
            ])
            if not local_latest.returncode:
                component["latest"]["version"] = project_version(local_latest.stdout)
            if component["latest"]["version"] == "unknown":
                raw_url = (
                    f"https://raw.githubusercontent.com/temiroff/{{repository}}/"
                    f"{{latest_commit}}/pyproject.toml"
                )
                try:
                    with urllib.request.urlopen(raw_url, timeout=15) as response:
                        component["latest"]["version"] = project_version(
                            response.read().decode("utf-8")
                        )
                except Exception:
                    pass
        component["can_update"] = not component["dirty"]
        if component["dirty"]:
            component["error"] = (
                "Local source changes must be committed, stashed, or removed before update."
            )
    except Exception as exc:
        component["error"] = str(exc)
    return component

components = [
    inspect(
        "runtime",
        "blacknode-runtime",
        runtime_service,
        request["runtime_port"],
        runtime_dir,
    )
]
for target in request["hardware_targets"]:
    hardware_port = int(target["port"])
    try:
        service, directory, resolution_error = resolve_hardware(
            hardware_port,
            str(target.get("device_id") or ""),
        )
        component = inspect(
            "hardware",
            "blacknode-hardware",
            service,
            hardware_port,
            directory,
        )
        if resolution_error:
            component["error"] = resolution_error
            component["can_update"] = False
        components.append(component)
    except Exception as exc:
        components.append({{
            "kind": "hardware",
            "service_name": "unresolved",
            "port": int(hardware_port),
            "installed": {{"version": "unknown", "commit": ""}},
            "latest": {{"version": "unknown", "commit": ""}},
            "update_available": False,
            "can_update": False,
            "dirty": False,
            "state": "unknown",
            "error": str(exc),
        }})
print(MARKER + json.dumps({{
    "ok": all(not item["error"] for item in components),
    "components": components,
}}, separators=(",", ":")))
PY"""
    try:
        report(25, "Comparing installed Runtime and Hardware commits")
        output = _run(connection, script, timeout=120.0)
        payload_line = next(
            (
                line[len("__BLACKNODE_UPDATE_CHECK__="):]
                for line in reversed(output.splitlines())
                if line.startswith("__BLACKNODE_UPDATE_CHECK__=")
            ),
            "",
        )
        if not payload_line:
            raise DeviceInstallError("The device did not return a software version report.")
        try:
            result = json.loads(payload_line)
        except json.JSONDecodeError as exc:
            raise DeviceInstallError("The device returned an invalid software version report.") from exc
        if not isinstance(result, dict) or not isinstance(result.get("components"), list):
            raise DeviceInstallError("The device returned an incomplete software version report.")
        result["host_fingerprint"] = connection.fingerprint
        report(90, "Installed and latest versions compared")
        return result
    finally:
        connection.close()


def control_runtime(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    action: str,
) -> dict[str, Any]:
    selected_instance = _clean_instance_id(instance_id or "default")
    clean_action = str(action or "").strip().lower()
    if clean_action not in {"pause", "resume"}:
        raise DeviceInstallError("Runtime action must be pause or resume.")
    service_name = (
        "blacknode-runtime.service"
        if selected_instance == "default"
        else f"blacknode-runtime-{selected_instance}.service"
    )
    systemd_action = "stop" if clean_action == "pause" else "start"
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    try:
        output = _run(
            connection,
            (
                "sudo -S -p '' -v"
                f" && sudo -S -p '' systemctl {systemd_action} {service_name}"
                f' && state="$(sudo -S -p \'\' systemctl is-active {service_name} || true)"'
                ' && printf "%s\\n" "$state"'
                f' && [ "$state" = "{"inactive" if clean_action == "pause" else "active"}" ]'
            ),
            stdin_text=_sudo_input(password),
            timeout=60.0,
        )
        state = output.strip().splitlines()[-1] if output.strip() else ""
        if clean_action == "pause" and state != "inactive":
            raise DeviceInstallError(
                f"{service_name} did not enter the inactive state."
            )
        if clean_action == "resume" and state != "active":
            raise DeviceInstallError(
                f"{service_name} did not enter the active state."
            )
        return {
            "ok": True,
            "action": clean_action,
            "instance_id": selected_instance,
            "service_name": service_name,
            "state": state,
        }
    finally:
        connection.close()


def restart_hardware_service(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    hardware_port: int,
    action: str = "restart",
) -> dict[str, Any]:
    """Control exactly one Blacknode hardware unit resolved by its HTTP port."""
    selected_port = int(hardware_port)
    if selected_port < 1 or selected_port > 65535:
        raise DeviceInstallError("The robot hardware port is invalid.")
    clean_action = str(action or "").strip().lower()
    if clean_action not in {"start", "stop", "restart"}:
        raise DeviceInstallError("Hardware service action must be start, stop, or restart.")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    remote_script_path = f"/tmp/blacknode-hardware-control-{secrets.token_hex(8)}.sh"
    script = r"""#!/usr/bin/env bash
set -euo pipefail
hardware_port="$1"
action="$2"
[[ "$hardware_port" =~ ^[0-9]{1,5}$ ]] || {
  echo "Invalid robot hardware port."
  exit 2
}
[[ "$action" =~ ^(start|stop|restart)$ ]] || {
  echo "Invalid robot hardware service action."
  exit 2
}
mapfile -t candidate_units < <(
  {
    systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
    systemctl list-units --all --type=service 'blacknode-hardware*.service' \
      --no-legend 2>/dev/null
    find /etc/systemd/system /run/systemd/system -maxdepth 1 \
      -name 'blacknode-hardware*.service' -printf '%f\n' 2>/dev/null
  } | awk '{print $1}' | sort -u
)
matches=()
active_matches=()
enabled_matches=()
for unit in "${candidate_units[@]}"; do
  [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\.service$ ]] || continue
  exec_start="$(systemctl show "$unit" --property=ExecStart --value 2>/dev/null || true)"
  unit_definition=""
  for unit_path in "/etc/systemd/system/$unit" "/run/systemd/system/$unit"; do
    if [[ -f "$unit_path" ]]; then
      unit_definition+="$(command cat "$unit_path")"
      unit_definition+=$'\n'
    fi
  done
  normalized="${exec_start//\"/}"$'\n'"${unit_definition//\"/}"
  if printf '%s\n' "$normalized" \
    | grep -oE -- '--port(=|[[:space:]])[0-9]+' \
    | grep -oE '[0-9]+' \
    | grep -Fxq -- "$hardware_port"; then
    matches+=("$unit")
    systemctl is-active --quiet "$unit" 2>/dev/null \
      && active_matches+=("$unit")
    systemctl is-enabled --quiet "$unit" 2>/dev/null \
      && enabled_matches+=("$unit")
  fi
done
if [[ "${#matches[@]}" -eq 0 ]]; then
  echo "No Blacknode hardware service owns port $hardware_port. Discovered units: ${candidate_units[*]:-none}."
  exit 3
fi
if [[ "${#matches[@]}" -eq 1 ]]; then
  service_name="${matches[0]}"
elif [[ "${#active_matches[@]}" -eq 1 ]]; then
  service_name="${active_matches[0]}"
elif [[ "${#active_matches[@]}" -gt 1 ]]; then
  echo "Multiple active Blacknode hardware services claim port $hardware_port: ${active_matches[*]}."
  exit 4
elif [[ "${#enabled_matches[@]}" -eq 1 ]]; then
  service_name="${enabled_matches[0]}"
else
  echo "Could not choose the hardware service for port $hardware_port. Candidates: ${matches[*]}. Enabled: ${enabled_matches[*]:-none}."
  exit 4
fi
sudo -S -p '' systemctl "$action" "$service_name"
expected_state="active"
[[ "$action" == "stop" ]] && expected_state="inactive"
state=""
for _attempt in {1..40}; do
  state="$(systemctl is-active "$service_name" 2>/dev/null || true)"
  [[ "$state" == "$expected_state" ]] && break
  sleep 0.25
done
echo "__BLACKNODE_HARDWARE_SERVICE__=$service_name"
echo "__BLACKNODE_HARDWARE_STATE__=$state"
[[ "$state" == "$expected_state" ]]
"""
    try:
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()
        output = _run(
            connection,
            f"bash {remote_script_path} {selected_port} {clean_action}",
            stdin_text=_sudo_input(password),
            timeout=60.0,
        )
        service_match = re.search(
            r"^__BLACKNODE_HARDWARE_SERVICE__=([A-Za-z0-9_.@-]+\.service)$",
            output,
            re.MULTILINE,
        )
        state_match = re.search(
            r"^__BLACKNODE_HARDWARE_STATE__=([a-z-]+)$",
            output,
            re.MULTILINE,
        )
        if not service_match or not state_match:
            raise DeviceInstallError(
                "The device did not confirm which robot service was controlled."
            )
        state = state_match.group(1)
        expected_state = "inactive" if clean_action == "stop" else "active"
        if state != expected_state:
            raise DeviceInstallError(
                f"{service_match.group(1)} did not enter the {expected_state} state."
            )
        return {
            "ok": True,
            "hardware_port": selected_port,
            "service_name": service_match.group(1),
            "action": clean_action,
            "state": state,
        }
    finally:
        try:
            _run(connection, f"rm -f -- {remote_script_path}", timeout=10.0)
        except DeviceInstallError:
            pass
        connection.close()


def uninstall_runtime(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    host_fingerprint: str,
    instance_id: str,
    runtime_port: int,
    stack_mode: str = "runtime_only",
    hardware_ports: list[int] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    report(2, "Connecting securely")
    selected_instance = _clean_instance_id(instance_id or "default")
    selected_stack_mode = str(stack_mode or "runtime_only").strip().lower()
    if selected_stack_mode not in {"runtime_only", "isolated"}:
        raise DeviceInstallError("The managed stack mode is invalid.")
    selected_port = int(runtime_port)
    if selected_port < 1 or selected_port > 65535:
        raise DeviceInstallError("The managed runtime port is invalid.")
    selected_hardware_ports = sorted({
        int(value)
        for value in (hardware_ports or [])
    })
    if any(value < 1 or value > 65535 for value in selected_hardware_ports):
        raise DeviceInstallError("A Robot Hardware port is invalid.")
    hardware_ports_payload = base64.urlsafe_b64encode(
        json.dumps(selected_hardware_ports, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    remote_script_path = f"/tmp/blacknode-runtime-uninstall-{secrets.token_hex(8)}.sh"
    script = """#!/usr/bin/env bash
set -euo pipefail
progress() {
  echo "__BLACKNODE_UNINSTALL_PROGRESS__=$1|$2"
}
instance="$1"
runtime_port="$2"
stack_mode="$3"
hardware_ports_payload="$4"
mapfile -t selected_hardware_ports < <(
  python3 - "$hardware_ports_payload" <<'PY'
import base64
import json
import sys

for value in json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8")):
    print(int(value))
PY
)
stack_root="$HOME/Blacknode/devices/$instance"
organized_runtime_dir="$stack_root/runtime"
organized_token_file="$stack_root/secrets/runtime.auth.token"
organized_hardware_dir="$stack_root/hardware"
if [[ "$instance" == "default" ]]; then
  legacy_runtime_dir="$HOME/blacknode-runtime"
  legacy_token_file="$HOME/.blacknode/runtime.auth.token"
  legacy_hardware_dir="$HOME/blacknode-hardware"
  service_name="blacknode-runtime.service"
else
  [[ "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || exit 2
  legacy_runtime_dir="$HOME/blacknode-runtimes/$instance"
  legacy_token_file="$HOME/.blacknode/runtimes/$instance.auth.token"
  legacy_hardware_dir="$HOME/blacknode-hardware-instances/$instance"
  service_name="blacknode-runtime-$instance.service"
fi
runtime_dir="$legacy_runtime_dir"
token_file="$legacy_token_file"
if [[ -d "$organized_runtime_dir" || -f "$organized_token_file" ]]; then
  runtime_dir="$organized_runtime_dir"
  token_file="$organized_token_file"
fi
hardware_dir="$legacy_hardware_dir"
[[ ! -d "$organized_hardware_dir" ]] || hardware_dir="$organized_hardware_dir"
case "$runtime_dir" in
  "$HOME/Blacknode/devices/"*/runtime|\
  "$HOME/blacknode-runtime"|\
  "$HOME/blacknode-runtimes/"*) ;;
  *) echo "Unsafe runtime directory."; exit 2 ;;
esac
list_hardware_units() {
  {
    systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null
    systemctl list-units --all --type=service 'blacknode-hardware*.service' \\
      --no-legend 2>/dev/null
    find /etc/systemd/system /run/systemd/system -maxdepth 1 \\
      -name 'blacknode-hardware*.service' -printf '%f\\n' 2>/dev/null
  } | awk '{print $1}' | sort -u
}
hardware_unit_directory() {
  local unit="$1"
  local directory
  directory="$(
    systemctl show "$unit" --property=WorkingDirectory --value 2>/dev/null || true
  )"
  if [[ -z "$directory" ]]; then
    directory="$(
      systemctl cat "$unit" 2>/dev/null \\
        | sed -nE 's/^WorkingDirectory=(.*)$/\\1/p' \\
        | tail -n 1
    )"
  fi
  printf '%s' "$directory"
}
hardware_unit_port() {
  local unit="$1"
  {
    systemctl show "$unit" --property=ExecStart --value 2>/dev/null || true
    systemctl cat "$unit" 2>/dev/null || true
  } | sed -nE 's/.*--port[= ]"?([0-9]+).*/\\1/p' | tail -n 1
}
validate_hardware_directory() {
  case "$1" in
    "$HOME/Blacknode/devices/"*/hardware|\\
    "$HOME/blacknode-hardware"|\\
    "$HOME/blacknode-hardware-instances/"*) return 0 ;;
    *) echo "Refusing to delete an unrecognized Robot Hardware directory: $1" >&2; return 1 ;;
  esac
}
mapfile -t candidate_hardware_units < <(list_hardware_units)
hardware_units=()
declare -A hardware_directories=()
if [[ "$stack_mode" == "isolated" ]]; then
  validate_hardware_directory "$hardware_dir"
  hardware_directories["$hardware_dir"]=1
  for unit in "${candidate_hardware_units[@]}"; do
    [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\\.service$ ]] \\
      || continue
    directory="$(hardware_unit_directory "$unit")"
    [[ "$directory" == "$hardware_dir" ]] || continue
    hardware_units+=("$unit")
  done
else
  if [[ "${#selected_hardware_ports[@]}" -gt 0 && -d "$hardware_dir" ]]; then
    validate_hardware_directory "$hardware_dir"
    hardware_directories["$hardware_dir"]=1
  fi
  for selected_hardware_port in "${selected_hardware_ports[@]}"; do
    matches=()
    for unit in "${candidate_hardware_units[@]}"; do
      [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\\.service$ ]] \\
        || continue
      [[ "$(hardware_unit_port "$unit")" == "$selected_hardware_port" ]] || continue
      matches+=("$unit")
    done
    if [[ "${#matches[@]}" -gt 1 ]]; then
      echo "Multiple Robot Hardware services match port $selected_hardware_port." >&2
      exit 6
    fi
    [[ "${#matches[@]}" -eq 1 ]] || continue
    unit="${matches[0]}"
    directory="$(hardware_unit_directory "$unit")"
    [[ -n "$directory" ]] || {
      echo "$unit does not report its installation directory." >&2
      exit 6
    }
    validate_hardware_directory "$directory"
    hardware_units+=("$unit")
    hardware_directories["$directory"]=1
  done
fi
progress 20 "Stopping Runtime service"
sudo systemctl stop "$service_name" >/dev/null 2>&1 || true
sudo systemctl disable "$service_name" >/dev/null 2>&1 || true
progress 35 "Removing Runtime service"
sudo rm -f -- "/etc/systemd/system/$service_name"
sudo systemctl daemon-reload
if [[ "${#hardware_units[@]}" -gt 0 ]]; then
  progress 48 "Deleting Robot Hardware services"
  for hardware_unit in "${hardware_units[@]}"; do
    hardware_port="$(
      hardware_unit_port "$hardware_unit"
    )"
    sudo systemctl stop "$hardware_unit" >/dev/null 2>&1 || true
    sudo systemctl disable "$hardware_unit" >/dev/null 2>&1 || true
    sudo rm -f -- \\
      "/etc/systemd/system/$hardware_unit" \\
      "/run/systemd/system/$hardware_unit"
    if [[ "$hardware_port" =~ ^[0-9]+$ ]] \\
      && command -v ufw >/dev/null 2>&1 \\
      && sudo ufw status 2>/dev/null | grep -qi '^Status: active'; then
      sudo ufw --force delete allow "$hardware_port/tcp" >/dev/null 2>&1 || true
    fi
  done
  sudo systemctl daemon-reload
fi
progress 70 "Deleting unused Robot Hardware files"
mapfile -t remaining_hardware_units < <(list_hardware_units)
for directory in "${!hardware_directories[@]}"; do
  directory_in_use=false
  for unit in "${remaining_hardware_units[@]}"; do
    [[ "$unit" =~ ^blacknode-hardware([-.@][A-Za-z0-9_.@-]+)?\\.service$ ]] \\
      || continue
    if [[ "$(hardware_unit_directory "$unit")" == "$directory" ]]; then
      directory_in_use=true
      break
    fi
  done
  if [[ "$directory_in_use" == false ]]; then
    rm -rf -- "$directory"
  fi
done
progress 84 "Removing Runtime files and firewall rule"
if command -v ufw >/dev/null 2>&1 \
  && sudo ufw status 2>/dev/null | grep -qi '^Status: active'; then
  sudo ufw --force delete allow "$runtime_port/tcp" >/dev/null 2>&1 || true
fi
rm -rf -- "$runtime_dir"
rm -f -- "$token_file"
if [[ "$runtime_dir" == "$organized_runtime_dir" ]]; then
  rm -f -- "$stack_root/install.json"
  rmdir -- "$stack_root/secrets" "$stack_root" "$HOME/Blacknode/devices" \
    "$HOME/Blacknode" >/dev/null 2>&1 || true
fi
progress 94 "Finalizing deletion"
"""
    try:
        report(10, "Inspecting the managed stack")
        inspection = _inspect_connection(connection)
        existing = _find_instance(inspection, selected_instance)
        if existing:
            discovered_port = int(existing.get("port") or 0)
            if discovered_port and discovered_port != selected_port:
                raise DeviceInstallError(
                    "The runtime port changed since this device was installed. "
                    "Inspect and pair it again before deleting it."
                )
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()

        def remote_output(line: str) -> None:
            match = re.match(
                r"^__BLACKNODE_UNINSTALL_PROGRESS__=(\d{1,3})\|(.*)$",
                line.strip(),
            )
            if match:
                report(int(match.group(1)), match.group(2).strip())

        _run(
            connection,
            (
                f"sudo -S -p '' -v && bash {remote_script_path} "
                f"{selected_instance} {selected_port} {selected_stack_mode} "
                f"{hardware_ports_payload}"
            ),
            stdin_text=password + "\n",
            timeout=120.0,
            on_output=remote_output,
        )
        return {
            "ok": True,
            "host_fingerprint": connection.fingerprint,
            "instance_id": selected_instance,
            "runtime_port": selected_port,
            "already_absent": not bool(existing),
            "stack_mode": selected_stack_mode,
            "hardware_ports": selected_hardware_ports,
        }
    finally:
        try:
            _run(connection, f"rm -f -- {remote_script_path}", timeout=10.0)
        except DeviceInstallError:
            pass
        connection.close()
