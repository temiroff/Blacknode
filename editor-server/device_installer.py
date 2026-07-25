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
from typing import Any, Callable


class DeviceInstallError(RuntimeError):
    """A remote device probe or installation could not be completed."""


_INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_INSPECTION_MARKER = "__BLACKNODE_RUNTIME_INSPECTION__="
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
side_root = home / "blacknode-runtimes"
if side_root.is_dir():
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
    if instance == "default":
        repo = home / "blacknode-runtime"
        unit = "blacknode-runtime.service"
        fallback_port = 8766
        fallback_token = home / ".blacknode" / "runtime.auth.token"
    else:
        repo = side_root / instance
        unit = f"blacknode-runtime-{instance}.service"
        fallback_port = 0
        fallback_token = home / ".blacknode" / "runtimes" / f"{instance}.auth.token"
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
        "runtime_dir": str(repo),
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
            "Automatic SSH setup requires Paramiko. Reinstall the editor-server "
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
    if clean_action not in {"install", "reuse", "replace", "side_by_side"}:
        connection.close()
        raise DeviceInstallError("Choose install, reuse, replace, or side_by_side.")
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
                    "runtime_dir": str(existing.get("runtime_dir") or ""),
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
if [[ "$instance" == "default" ]]; then
  runtime_dir="$HOME/blacknode-runtime"
  token_file="$HOME/.blacknode/runtime.auth.token"
  service_name="blacknode-runtime.service"
  service_instance=""
else
  [[ "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || {
    echo "Invalid Blacknode runtime instance."
    exit 2
  }
  runtime_dir="$HOME/blacknode-runtimes/$instance"
  token_file="$HOME/.blacknode/runtimes/$instance.auth.token"
  service_name="blacknode-runtime-$instance.service"
  service_instance="$instance"
fi
active_sibling_services=()
if [[ "$action" == "side_by_side" ]] && command -v systemctl >/dev/null 2>&1; then
  mapfile -t active_sibling_services < <(
    systemctl list-units --type=service --state=active --no-legend \
      'blacknode-runtime*.service' 'blacknode-hardware*.service' 2>/dev/null \
      | awk '{print $1}'
  )
fi
install_complete=false
cleanup_install=false
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
  fi
  exit "$exit_code"
}
trap cleanup_failed_install EXIT
case "$runtime_dir" in
  "$HOME/blacknode-runtime"|"$HOME/blacknode-runtimes/"*) ;;
  *) echo "Unsafe runtime directory."; exit 2 ;;
esac
token_dir="$(dirname -- "$token_file")"
progress 14 "Preparing the selected runtime"
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
            "runtime_dir": (
                "~/blacknode-runtime"
                if selected_instance == "default"
                else f"~/blacknode-runtimes/{selected_instance}"
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
                f" && sudo systemctl {systemd_action} {service_name}"
                f' && state="$(sudo systemctl is-active {service_name} || true)"'
                ' && printf "%s\\n" "$state"'
                f' && [ "$state" = "{"inactive" if clean_action == "pause" else "active"}" ]'
            ),
            stdin_text=password + "\n",
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
) -> dict[str, Any]:
    """Restart exactly one Blacknode hardware unit resolved by its HTTP port."""
    selected_port = int(hardware_port)
    if selected_port < 1 or selected_port > 65535:
        raise DeviceInstallError("The robot hardware port is invalid.")
    connection = _connect(
        host,
        port,
        username,
        password,
        expected_fingerprint=host_fingerprint,
        timeout=15.0,
    )
    remote_script_path = f"/tmp/blacknode-hardware-restart-{secrets.token_hex(8)}.sh"
    script = r"""#!/usr/bin/env bash
set -euo pipefail
hardware_port="$1"
[[ "$hardware_port" =~ ^[0-9]{1,5}$ ]] || {
  echo "Invalid robot hardware port."
  exit 2
}
mapfile -t candidate_units < <(
  systemctl list-unit-files 'blacknode-hardware*.service' --no-legend 2>/dev/null \
    | awk '{print $1}'
)
matches=()
for unit in "${candidate_units[@]}"; do
  [[ "$unit" =~ ^blacknode-hardware([-.][A-Za-z0-9_.@-]+)?\.service$ ]] || continue
  exec_start="$(systemctl show "$unit" --property=ExecStart --value 2>/dev/null || true)"
  normalized="${exec_start//\"/}"
  if [[ "$normalized" =~ --port(=|[[:space:]])${hardware_port}([^0-9]|$) ]]; then
    matches+=("$unit")
  fi
done
if [[ "${#matches[@]}" -eq 0 ]]; then
  echo "No Blacknode hardware service owns port $hardware_port."
  exit 3
fi
if [[ "${#matches[@]}" -ne 1 ]]; then
  echo "Multiple Blacknode hardware services claim port $hardware_port."
  exit 4
fi
service_name="${matches[0]}"
sudo -S -p '' systemctl restart "$service_name"
state=""
for _attempt in {1..40}; do
  state="$(systemctl is-active "$service_name" 2>/dev/null || true)"
  [[ "$state" == "active" ]] && break
  sleep 0.25
done
echo "__BLACKNODE_HARDWARE_SERVICE__=$service_name"
echo "__BLACKNODE_HARDWARE_STATE__=$state"
[[ "$state" == "active" ]]
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
            f"bash {remote_script_path} {selected_port}",
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
                "The device did not confirm which robot service was restarted."
            )
        state = state_match.group(1)
        if state != "active":
            raise DeviceInstallError(
                f"{service_match.group(1)} did not return to the active state."
            )
        return {
            "ok": True,
            "hardware_port": selected_port,
            "service_name": service_match.group(1),
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
) -> dict[str, Any]:
    selected_instance = _clean_instance_id(instance_id or "default")
    selected_port = int(runtime_port)
    if selected_port < 1 or selected_port > 65535:
        raise DeviceInstallError("The managed runtime port is invalid.")
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
instance="$1"
runtime_port="$2"
if [[ "$instance" == "default" ]]; then
  runtime_dir="$HOME/blacknode-runtime"
  token_file="$HOME/.blacknode/runtime.auth.token"
  service_name="blacknode-runtime.service"
else
  [[ "$instance" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || exit 2
  runtime_dir="$HOME/blacknode-runtimes/$instance"
  token_file="$HOME/.blacknode/runtimes/$instance.auth.token"
  service_name="blacknode-runtime-$instance.service"
fi
case "$runtime_dir" in
  "$HOME/blacknode-runtime"|"$HOME/blacknode-runtimes/"*) ;;
  *) echo "Unsafe runtime directory."; exit 2 ;;
esac
sudo systemctl stop "$service_name" >/dev/null 2>&1 || true
sudo systemctl disable "$service_name" >/dev/null 2>&1 || true
sudo rm -f -- "/etc/systemd/system/$service_name"
sudo systemctl daemon-reload
if command -v ufw >/dev/null 2>&1 \
  && sudo ufw status 2>/dev/null | grep -qi '^Status: active'; then
  sudo ufw --force delete allow "$runtime_port/tcp" >/dev/null 2>&1 || true
fi
rm -rf -- "$runtime_dir"
rm -f -- "$token_file"
"""
    try:
        inspection = _inspect_connection(connection)
        existing = _find_instance(inspection, selected_instance)
        if existing:
            discovered_port = int(existing.get("port") or 0)
            if discovered_port and discovered_port != selected_port:
                raise DeviceInstallError(
                    "The runtime port changed since this device was installed. "
                    "Inspect and pair it again before uninstalling."
                )
        sftp = connection.client.open_sftp()
        try:
            with sftp.file(remote_script_path, "w") as remote_script:
                remote_script.write(script)
            sftp.chmod(remote_script_path, 0o700)
        finally:
            sftp.close()
        _run(
            connection,
            (
                f"sudo -S -p '' -v && bash {remote_script_path} "
                f"{selected_instance} {selected_port}"
            ),
            stdin_text=password + "\n",
            timeout=120.0,
        )
        return {
            "ok": True,
            "host_fingerprint": connection.fingerprint,
            "instance_id": selected_instance,
            "runtime_port": selected_port,
            "already_absent": not bool(existing),
        }
    finally:
        try:
            _run(connection, f"rm -f -- {remote_script_path}", timeout=10.0)
        except DeviceInstallError:
            pass
        connection.close()
