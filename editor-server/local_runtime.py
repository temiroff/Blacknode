"""Install and manage an isolated Blacknode stack on the editor computer."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


_RUNTIME_REPOSITORY = "https://github.com/temiroff/blacknode-runtime.git"
_HARDWARE_REPOSITORY = "https://github.com/temiroff/blacknode-hardware.git"


class LocalRuntimeError(RuntimeError):
    """A local Runtime installation or lifecycle action failed."""


def default_local_runtime_dir() -> Path:
    return Path.home() / "Blacknode"


def _report(
    progress: Callable[[dict[str, Any]], None] | None,
    percent: int,
    message: str,
) -> None:
    if progress is not None:
        progress({
            "progress": max(0, min(100, int(percent))),
            "message": str(message),
        })


def _runtime_python(runtime_dir: Path) -> Path:
    return runtime_dir / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )


def _hardware_python(hardware_dir: Path) -> Path:
    return hardware_dir / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )


def _background_python(python: Path) -> Path:
    """Use the windowless venv launcher for persistent Windows services."""
    if os.name != "nt":
        return python
    pythonw = python.with_name("pythonw.exe")
    return pythonw if pythonw.is_file() else python


def _validate_runtime_checkout(runtime_dir: Path) -> None:
    pyproject = runtime_dir / "pyproject.toml"
    service_script = runtime_dir / "scripts" / "runtime_service.py"
    if not pyproject.is_file() or not service_script.is_file():
        raise LocalRuntimeError(
            f"{runtime_dir} is not an empty folder or a Blacknode Runtime checkout."
        )
    try:
        manifest = pyproject.read_text(encoding="utf-8")
    except OSError as exc:
        raise LocalRuntimeError(f"Could not inspect {pyproject}: {exc}") from exc
    if 'name = "blacknode-runtime"' not in manifest:
        raise LocalRuntimeError(f"{runtime_dir} is not a Blacknode Runtime checkout.")


def _validate_hardware_checkout(hardware_dir: Path) -> None:
    pyproject = hardware_dir / "pyproject.toml"
    service_script = hardware_dir / "scripts" / "hardware_service.py"
    if not pyproject.is_file() or not service_script.is_file():
        raise LocalRuntimeError(
            f"{hardware_dir} is not an empty folder or a Blacknode Hardware checkout."
        )
    try:
        manifest = pyproject.read_text(encoding="utf-8")
    except OSError as exc:
        raise LocalRuntimeError(f"Could not inspect {pyproject}: {exc}") from exc
    if 'name = "blacknode-hardware"' not in manifest:
        raise LocalRuntimeError(f"{hardware_dir} is not a Blacknode Hardware checkout.")


def _resolve_install_dir(value: str, core_root: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise LocalRuntimeError("Choose the local stack installation folder.")
    runtime_dir = Path(raw).expanduser().resolve()
    core_dir = Path(core_root).resolve()
    anchor = Path(runtime_dir.anchor).resolve()
    if runtime_dir in {anchor, Path.home().resolve(), core_dir}:
        raise LocalRuntimeError(
            "Choose a dedicated subfolder for the local stack installation."
        )
    if runtime_dir.exists() and not runtime_dir.is_dir():
        raise LocalRuntimeError(f"The stack installation path is not a folder: {runtime_dir}")
    return runtime_dir


def _run(args: list[str], *, cwd: Path | None = None, timeout: float = 900.0) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
    except FileNotFoundError as exc:
        raise LocalRuntimeError(f"Required command is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LocalRuntimeError(
            f"Local Runtime setup did not finish within {int(timeout)} seconds."
        ) from exc
    if completed.returncode:
        output = "\n".join(
            (completed.stdout + "\n" + completed.stderr).strip().splitlines()[-16:]
        )
        raise LocalRuntimeError(
            f"Local Runtime setup command failed with code {completed.returncode}."
            + (f"\n{output}" if output else "")
        )
    return completed.stdout


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def _select_port(preferred: int = 8766, reserved: set[int] | None = None) -> int:
    reserved_ports = reserved or set()
    for port in range(max(1, int(preferred)), 8866):
        if port not in reserved_ports and _port_available(port):
            return port
    raise LocalRuntimeError("No available local Runtime port was found from 8766 to 8865.")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _checkout_version(checkout_dir: Path) -> str:
    try:
        payload = tomllib.loads(
            (checkout_dir / "pyproject.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"
    project = payload.get("project")
    if not isinstance(project, dict):
        return "unknown"
    return str(project.get("version") or "unknown")


def _version_from_pyproject_text(value: str) -> str:
    try:
        payload = tomllib.loads(value)
    except tomllib.TOMLDecodeError:
        return "unknown"
    project = payload.get("project")
    return (
        str(project.get("version") or "unknown")
        if isinstance(project, dict)
        else "unknown"
    )


def _remove_tree(path: Path) -> None:
    """Remove one verified installation tree, clearing Windows read-only bits."""
    if not path.exists():
        return

    def make_writable_and_retry(function, target, _error_info) -> None:
        last_error: OSError | None = None
        for delay in (0.0, 0.1, 0.3, 0.8):
            if delay:
                time.sleep(delay)
            try:
                os.chmod(
                    target,
                    stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
                )
                function(target)
                return
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _process_command(pid: int) -> str:
    if pid < 1:
        return ""
    if os.name == "nt":
        command = (
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\" "
            "| Select-Object -ExpandProperty CommandLine)"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""
    proc_command = Path(f"/proc/{pid}/cmdline")
    if proc_command.is_file():
        try:
            return proc_command.read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            return ""
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _read_pid(pid_file: Path) -> int:
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _pid_is_expected(pid: int, runtime_dir: Path, config_path: Path) -> bool:
    command = _process_command(pid)
    if not command:
        return False
    normalized = command.casefold() if os.name == "nt" else command
    runtime_marker = str(runtime_dir / "scripts" / "runtime_service.py")
    config_marker = str(config_path)
    if os.name == "nt":
        runtime_marker = runtime_marker.casefold()
        config_marker = config_marker.casefold()
    return runtime_marker in normalized and config_marker in normalized


def _pid_is_hardware(
    pid: int,
    hardware_dir: Path,
    token_path: Path,
) -> bool:
    command = _process_command(pid)
    if not command:
        return False
    normalized = command.casefold() if os.name == "nt" else command
    hardware_marker = str(hardware_dir / "scripts" / "hardware_service.py")
    token_marker = str(token_path)
    if os.name == "nt":
        hardware_marker = hardware_marker.casefold()
        token_marker = token_marker.casefold()
    return hardware_marker in normalized and token_marker in normalized


def _spawn_runtime(runtime_dir: Path, config_path: Path, port: int) -> int:
    python = _background_python(_runtime_python(runtime_dir))
    service_script = runtime_dir / "scripts" / "runtime_service.py"
    if not python.is_file() or not service_script.is_file() or not config_path.is_file():
        raise LocalRuntimeError("The local Runtime installation is incomplete.")
    state_dir = runtime_dir / ".blacknode-runtime"
    state_dir.mkdir(parents=True, exist_ok=True)
    pid_file = state_dir / "runtime.pid"
    existing_pid = _read_pid(pid_file)
    if existing_pid and _pid_is_expected(existing_pid, runtime_dir, config_path):
        return existing_pid
    if existing_pid:
        try:
            os.kill(existing_pid, 0)
        except OSError:
            pass
        else:
            raise LocalRuntimeError(
                f"PID {existing_pid} no longer belongs to this Runtime; "
                f"remove the stale file after inspecting it: {pid_file}"
            )
        pid_file.unlink(missing_ok=True)
    if not _port_available(port):
        raise LocalRuntimeError(
            f"Local port {port} is already in use. Stop that process or choose another "
            "installation after it releases the port."
        )
    log_path = state_dir / "runtime.log"
    log_handle = log_path.open("a", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    process_options: dict[str, Any]
    if os.name == "nt":
        process_options = {
            "creationflags": (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        }
    else:
        process_options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            [
                str(python),
                "-u",
                str(service_script),
                "--config",
                str(config_path),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(runtime_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            **process_options,
        )
    finally:
        log_handle.close()
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    return int(process.pid)


def _request_manifest(port: int, token: str, *, timeout: float = 1.0) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/manifest",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if (
        not isinstance(payload, dict)
        or payload.get("service") != "blacknode-runtime"
        or payload.get("protocol_version") != 1
    ):
        raise LocalRuntimeError("The local port returned an incompatible service.")
    return payload


def _spawn_hardware(hardware_dir: Path, token_path: Path, port: int) -> int:
    python = _background_python(_hardware_python(hardware_dir))
    service_script = hardware_dir / "scripts" / "hardware_service.py"
    if not python.is_file() or not service_script.is_file() or not token_path.is_file():
        raise LocalRuntimeError("The local Robot Hardware installation is incomplete.")
    state_dir = hardware_dir / ".blacknode-hardware"
    state_dir.mkdir(parents=True, exist_ok=True)
    pid_file = state_dir / "hardware.pid"
    existing_pid = _read_pid(pid_file)
    if existing_pid and _pid_is_hardware(existing_pid, hardware_dir, token_path):
        return existing_pid
    if existing_pid:
        try:
            os.kill(existing_pid, 0)
        except OSError:
            pass
        else:
            raise LocalRuntimeError(
                f"PID {existing_pid} no longer belongs to this Robot Hardware service; "
                f"remove the stale file after inspecting it: {pid_file}"
            )
        pid_file.unlink(missing_ok=True)
    if not _port_available(port):
        raise LocalRuntimeError(
            f"Local Robot Hardware port {port} is already in use."
        )
    log_path = state_dir / "hardware.log"
    log_handle = log_path.open("a", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    process_options: dict[str, Any]
    if os.name == "nt":
        process_options = {
            "creationflags": (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        }
    else:
        process_options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            [
                str(python),
                "-u",
                str(service_script),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--device-id",
                f"{socket.gethostname()}-hardware-awaiting-device",
                "--auth-token-file",
                str(token_path),
                "--require-auth",
            ],
            cwd=str(hardware_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            **process_options,
        )
    finally:
        log_handle.close()
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    return int(process.pid)


def _request_hardware_status(
    port: int,
    token: str,
    *,
    timeout: float = 1.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise LocalRuntimeError("Robot Hardware returned an invalid status.")
    if payload.get("connected") is not False or payload.get("armed") is not False:
        raise LocalRuntimeError(
            "Robot Hardware did not start in the required disconnected, disarmed state."
        )
    return payload


def _wait_for_hardware_status(
    port: int,
    token: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return _request_hardware_status(port, token)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, LocalRuntimeError) as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise LocalRuntimeError(
        "Robot Hardware started but did not confirm its safe awaiting-device state."
        + (f" {last_error}" if last_error else "")
    )


def _wait_for_manifest(port: int, token: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return _request_manifest(port, token)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, LocalRuntimeError) as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise LocalRuntimeError(
        "The local Runtime process started but did not pass its authenticated check."
        + (f" {last_error}" if last_error else "")
    )


def install_local_runtime(
    *,
    install_dir: str,
    core_root: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    install_root = _resolve_install_dir(install_dir, core_root)
    if (
        install_root.name.casefold() == "blacknode-runtime"
        and (install_root / "pyproject.toml").is_file()
    ):
        runtime_dir = install_root
        install_root = install_root.parent
    else:
        runtime_dir = install_root / "blacknode-runtime"
    hardware_dir = install_root / "blacknode-hardware"
    _report(progress, 4, "Checking the local robot stack folder")

    runtime_existed = runtime_dir.exists() and any(runtime_dir.iterdir())
    if runtime_existed:
        _validate_runtime_checkout(runtime_dir)
        runtime_owned = bool(
            _load_json(runtime_dir / ".blacknode-runtime" / "editor-managed.json").get(
                "owned_install"
            )
        )
        _report(progress, 10, "Using the existing Runtime checkout")
    else:
        runtime_dir.parent.mkdir(parents=True, exist_ok=True)
        _report(progress, 9, "Downloading Blacknode Runtime")
        _run(["git", "clone", _RUNTIME_REPOSITORY, str(runtime_dir)], timeout=300)
        _validate_runtime_checkout(runtime_dir)
        runtime_owned = True

    runtime_python = _runtime_python(runtime_dir)
    if not runtime_python.is_file():
        _report(progress, 18, "Creating the local Runtime environment")
        _run([sys.executable, "-m", "venv", str(runtime_dir / ".venv")], timeout=180)
    _report(progress, 25, "Installing Blacknode Runtime")
    _run(
        [str(runtime_python), "-m", "pip", "install", "-e", str(runtime_dir)],
        timeout=900,
    )

    hardware_existed = hardware_dir.exists() and any(hardware_dir.iterdir())
    if hardware_existed:
        _validate_hardware_checkout(hardware_dir)
        hardware_owned = bool(
            _load_json(
                hardware_dir / ".blacknode-hardware" / "editor-managed.json"
            ).get("owned_install")
        )
        _report(progress, 34, "Using the existing Robot Hardware checkout")
    else:
        hardware_dir.parent.mkdir(parents=True, exist_ok=True)
        _report(progress, 33, "Downloading Blacknode Robot Hardware")
        _run(["git", "clone", _HARDWARE_REPOSITORY, str(hardware_dir)], timeout=300)
        _validate_hardware_checkout(hardware_dir)
        hardware_owned = True

    hardware_python = _hardware_python(hardware_dir)
    if not hardware_python.is_file():
        _report(progress, 41, "Creating the Robot Hardware environment")
        _run([sys.executable, "-m", "venv", str(hardware_dir / ".venv")], timeout=180)
    _report(progress, 48, "Installing Blacknode Robot Hardware")
    _run(
        [str(hardware_python), "-m", "pip", "install", "-e", str(hardware_dir)],
        timeout=900,
    )

    _report(progress, 57, "Connecting Runtime to this Blacknode workspace")
    _run(
        [
            str(runtime_python),
            "-m",
            "pip",
            "install",
            "-e",
            str(Path(core_root).resolve()),
        ],
        timeout=900,
    )

    private_dir = runtime_dir / ".blacknode-runtime"
    private_dir.mkdir(parents=True, exist_ok=True)
    token_path = private_dir / "auth.token"
    token = token_path.read_text(encoding="utf-8").strip() if token_path.is_file() else ""
    if len(token) < 32:
        token = secrets.token_urlsafe(32)
        token_path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
    metadata_path = private_dir / "editor-managed.json"
    previous = _load_json(metadata_path)
    preferred_port = int(previous.get("runtime_port") or 8766)
    config_path = private_dir / "runtime.json"
    existing_pid = _read_pid(private_dir / "runtime.pid")
    existing_running = bool(
        existing_pid and _pid_is_expected(existing_pid, runtime_dir, config_path)
    )
    runtime_port = (
        preferred_port
        if existing_running or _port_available(preferred_port)
        else 0
    )

    hardware_private_dir = hardware_dir / ".blacknode-hardware"
    hardware_private_dir.mkdir(parents=True, exist_ok=True)
    hardware_token_path = hardware_private_dir / "auth.token"
    hardware_token = (
        hardware_token_path.read_text(encoding="utf-8").strip()
        if hardware_token_path.is_file()
        else ""
    )
    if len(hardware_token) < 32:
        hardware_token = secrets.token_urlsafe(32)
        hardware_token_path.write_text(hardware_token + "\n", encoding="utf-8")
        try:
            os.chmod(hardware_token_path, 0o600)
        except OSError:
            pass
    hardware_metadata_path = hardware_private_dir / "editor-managed.json"
    previous_hardware = _load_json(hardware_metadata_path)
    preferred_hardware_port = int(previous_hardware.get("hardware_port") or 8765)
    hardware_pid_file = hardware_private_dir / "hardware.pid"
    existing_hardware_pid = _read_pid(hardware_pid_file)
    existing_hardware_running = bool(
        existing_hardware_pid
        and _pid_is_hardware(
            existing_hardware_pid,
            hardware_dir,
            hardware_token_path,
        )
    )
    hardware_port = (
        preferred_hardware_port
        if existing_hardware_running or _port_available(preferred_hardware_port)
        else _select_port(8765)
    )
    if not runtime_port:
        runtime_port = _select_port(8766, reserved={hardware_port})
    if hardware_port == runtime_port:
        runtime_port = _select_port(runtime_port + 1, reserved={hardware_port})

    state_path = private_dir / "state"
    config_path.write_text(
        json.dumps({
            "device_id": f"{socket.gethostname()}-local",
            "auth_token_file": str(token_path),
            "state_dir": str(state_path),
            "hardware_url": f"http://127.0.0.1:{hardware_port}",
            "blacknode_root": str(Path(core_root).resolve()),
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _report(progress, 68, f"Configured Robot Hardware port {hardware_port}")
    hardware_pid = _spawn_hardware(
        hardware_dir,
        hardware_token_path,
        hardware_port,
    )
    hardware_metadata_path.write_text(
        json.dumps({
            "schema_version": 1,
            "owned_install": hardware_owned,
            "hardware_port": hardware_port,
            "pid": hardware_pid,
            "token_file": str(hardware_token_path),
            "log_path": str(hardware_private_dir / "hardware.log"),
            "configured": False,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _report(progress, 78, "Verifying safe Robot Hardware state")
    hardware_status = _wait_for_hardware_status(hardware_port, hardware_token)

    _report(progress, 84, f"Starting local Runtime on port {runtime_port}")
    pid = _spawn_runtime(runtime_dir, config_path, runtime_port)
    metadata = {
        "schema_version": 1,
        "owned_install": runtime_owned,
        "runtime_port": runtime_port,
        "pid": pid,
        "config_path": str(config_path),
        "log_path": str(private_dir / "runtime.log"),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _report(progress, 94, "Verifying the complete local robot stack")
    manifest = _wait_for_manifest(runtime_port, token)
    return {
        "ok": True,
        "runtime_token": token,
        "runtime_url": f"http://127.0.0.1:{runtime_port}",
        "manifest": manifest,
        "runtime_port": runtime_port,
        "runtime_dir": str(runtime_dir),
        "service_name": "blacknode-runtime-local-process",
        "instance_id": "local",
        "stack_mode": "runtime_only",
        "hardware_dir": str(hardware_dir),
        "hardware_port": hardware_port,
        "hardware_service_name": "blacknode-hardware-local-awaiting-device",
        "hardware_state": "awaiting_device",
        "hardware_configured": False,
        "hardware_pid_file": str(hardware_pid_file),
        "hardware_token_file": str(hardware_token_path),
        "hardware_log_path": str(hardware_private_dir / "hardware.log"),
        "hardware_owned_install": hardware_owned,
        "hardware_status": hardware_status,
        "management_mode": "local",
        "config_path": str(config_path),
        "pid_file": str(private_dir / "runtime.pid"),
        "log_path": str(private_dir / "runtime.log"),
        "owned_install": runtime_owned,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }


def ensure_local_hardware(managed: dict[str, Any]) -> dict[str, Any]:
    hardware_dir = Path(str(managed.get("hardware_dir") or "")).expanduser().resolve()
    token_path = Path(
        str(managed.get("hardware_token_file") or "")
    ).expanduser().resolve()
    port = int(managed.get("hardware_port") or 0)
    _validate_hardware_checkout(hardware_dir)
    if token_path.parent != hardware_dir / ".blacknode-hardware" or port < 1:
        raise LocalRuntimeError("The saved local Robot Hardware identity is incomplete.")
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise LocalRuntimeError("The local Robot Hardware pairing token is invalid.")
    pid = _spawn_hardware(hardware_dir, token_path, port)
    status = _wait_for_hardware_status(port, token)
    return {
        "ok": True,
        "state": "active",
        "hardware_state": "awaiting_device",
        "service_name": "blacknode-hardware-local-awaiting-device",
        "pid": pid,
        "status": status,
    }


def inspect_local_hardware(managed: dict[str, Any]) -> dict[str, Any]:
    """Inspect the saved Hardware package without starting its service."""
    hardware_dir = Path(str(managed.get("hardware_dir") or "")).expanduser().resolve()
    token_path = Path(
        str(managed.get("hardware_token_file") or "")
    ).expanduser().resolve()
    pid_file = Path(
        str(managed.get("hardware_pid_file") or "")
    ).expanduser().resolve()
    port = int(managed.get("hardware_port") or 0)
    _validate_hardware_checkout(hardware_dir)
    if (
        token_path.parent != hardware_dir / ".blacknode-hardware"
        or pid_file.parent != hardware_dir / ".blacknode-hardware"
        or port < 1
    ):
        raise LocalRuntimeError("The saved local Hardware package identity is incomplete.")
    installed = _hardware_python(hardware_dir).is_file()
    pid = _read_pid(pid_file)
    running = bool(
        installed
        and pid
        and _pid_is_hardware(pid, hardware_dir, token_path)
    )
    result: dict[str, Any] = {
        "ok": running,
        "kind": "hardware",
        "state": "running" if running else "stopped",
        "installed": installed,
        "installed_version": _checkout_version(hardware_dir),
        "service_name": "blacknode-hardware-local-awaiting-device",
        "service_url": f"http://127.0.0.1:{port}",
        "pid": pid if running else 0,
    }
    if not installed:
        result["error"] = "The Hardware package environment is not installed."
        return result
    if not running:
        result["error"] = "The Hardware package service is stopped."
        return result
    try:
        token = token_path.read_text(encoding="utf-8").strip()
        result["status"] = _request_hardware_status(port, token)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, LocalRuntimeError) as exc:
        result["ok"] = False
        result["state"] = "unreachable"
        result["error"] = f"The Hardware package service is unreachable: {exc}"
    return result


def stop_local_hardware(managed: dict[str, Any]) -> dict[str, Any]:
    hardware_dir = Path(str(managed.get("hardware_dir") or "")).expanduser().resolve()
    token_path = Path(
        str(managed.get("hardware_token_file") or "")
    ).expanduser().resolve()
    pid_file = Path(
        str(managed.get("hardware_pid_file") or "")
    ).expanduser().resolve()
    _validate_hardware_checkout(hardware_dir)
    if (
        token_path.parent != hardware_dir / ".blacknode-hardware"
        or pid_file.parent != hardware_dir / ".blacknode-hardware"
    ):
        raise LocalRuntimeError("The saved local Robot Hardware identity is incomplete.")
    pid = _read_pid(pid_file)
    if not pid:
        return {
            "ok": True,
            "state": "inactive",
            "service_name": "blacknode-hardware-local-awaiting-device",
        }
    if not _pid_is_hardware(pid, hardware_dir, token_path):
        try:
            os.kill(pid, 0)
        except OSError:
            pid_file.unlink(missing_ok=True)
        else:
            raise LocalRuntimeError(
                f"Refusing to stop PID {pid}; it is not the saved Robot Hardware process."
            )
        return {
            "ok": True,
            "state": "inactive",
            "service_name": "blacknode-hardware-local-awaiting-device",
        }
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        os.kill(pid, 15)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
    pid_file.unlink(missing_ok=True)
    return {
        "ok": True,
        "state": "inactive",
        "service_name": "blacknode-hardware-local-awaiting-device",
    }


def ensure_local_runtime(managed: dict[str, Any]) -> dict[str, Any]:
    hardware = None
    if managed.get("hardware_dir"):
        hardware = ensure_local_hardware(managed)
    runtime_dir = Path(str(managed.get("runtime_dir") or "")).expanduser().resolve()
    config_path = Path(str(managed.get("config_path") or "")).expanduser().resolve()
    port = int(managed.get("runtime_port") or 0)
    _validate_runtime_checkout(runtime_dir)
    if config_path.parent != runtime_dir / ".blacknode-runtime" or port < 1:
        raise LocalRuntimeError("The saved local Runtime identity is incomplete.")
    pid = _spawn_runtime(runtime_dir, config_path, port)
    return {
        "ok": True,
        "action": "resume",
        "state": "active",
        "service_name": "blacknode-runtime-local-process",
        "pid": pid,
        "hardware": hardware,
    }


def inspect_local_runtime(managed: dict[str, Any]) -> dict[str, Any]:
    """Inspect the saved Runtime package without starting its service."""
    runtime_dir = Path(str(managed.get("runtime_dir") or "")).expanduser().resolve()
    config_path = Path(str(managed.get("config_path") or "")).expanduser().resolve()
    pid_file = Path(str(managed.get("pid_file") or "")).expanduser().resolve()
    port = int(managed.get("runtime_port") or 0)
    _validate_runtime_checkout(runtime_dir)
    if (
        config_path.parent != runtime_dir / ".blacknode-runtime"
        or pid_file.parent != runtime_dir / ".blacknode-runtime"
        or port < 1
    ):
        raise LocalRuntimeError("The saved local Runtime package identity is incomplete.")
    installed = _runtime_python(runtime_dir).is_file()
    pid = _read_pid(pid_file)
    running = bool(
        installed
        and pid
        and _pid_is_expected(pid, runtime_dir, config_path)
    )
    result: dict[str, Any] = {
        "ok": running,
        "kind": "runtime",
        "state": "running" if running else "stopped",
        "installed": installed,
        "installed_version": _checkout_version(runtime_dir),
        "service_name": "blacknode-runtime-local-process",
        "service_url": f"http://127.0.0.1:{port}",
        "pid": pid if running else 0,
    }
    if not installed:
        result["error"] = "The Runtime package environment is not installed."
        return result
    if not running:
        result["error"] = "The Runtime package service is stopped."
        return result
    config = _load_json(config_path)
    token_path = Path(str(config.get("auth_token_file") or "")).expanduser().resolve()
    try:
        token = token_path.read_text(encoding="utf-8").strip()
        result["manifest"] = _request_manifest(port, token)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, LocalRuntimeError) as exc:
        result["ok"] = False
        result["state"] = "unreachable"
        result["error"] = f"The Runtime package service is unreachable: {exc}"
    return result


def _inspect_local_checkout_update(
    *,
    checkout_dir: Path,
    kind: str,
    service_name: str,
    port: int,
) -> dict[str, Any]:
    component: dict[str, Any] = {
        "kind": kind,
        "service_name": service_name,
        "port": int(port),
        "installed": {
            "version": _checkout_version(checkout_dir),
            "commit": "unknown",
        },
        "latest": {"version": "unknown", "commit": "unknown"},
        "update_available": False,
        "can_update": False,
        "dirty": False,
        "state": "unknown",
        "error": "",
    }
    try:
        component["installed"]["commit"] = _run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout_dir,
            timeout=20,
        ).strip()
        component["dirty"] = bool(
            _run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=checkout_dir,
                timeout=20,
            ).strip()
        )
        remote = _run(
            ["git", "ls-remote", "--symref", "origin", "HEAD"],
            cwd=checkout_dir,
            timeout=60,
        )
        upstream_ref = ""
        latest_commit = ""
        for line in remote.splitlines():
            if line.startswith("ref:") and line.endswith("\tHEAD"):
                upstream_ref = line.split()[1]
            elif line.endswith("\tHEAD"):
                latest_commit = line.split()[0]
        if not upstream_ref or not latest_commit:
            raise LocalRuntimeError("The package origin did not report its default branch.")
        _run(
            ["git", "fetch", "--quiet", "origin", upstream_ref],
            cwd=checkout_dir,
            timeout=180,
        )
        fetched_commit = _run(
            ["git", "rev-parse", "FETCH_HEAD"],
            cwd=checkout_dir,
            timeout=20,
        ).strip()
        if fetched_commit:
            latest_commit = fetched_commit
        latest_pyproject = _run(
            ["git", "show", f"{latest_commit}:pyproject.toml"],
            cwd=checkout_dir,
            timeout=20,
        )
        component["latest"] = {
            "version": _version_from_pyproject_text(latest_pyproject),
            "commit": latest_commit,
        }
        component["update_available"] = (
            component["installed"]["commit"] != latest_commit
        )
        component["can_update"] = not component["dirty"]
        if component["dirty"]:
            component["error"] = (
                "Local source changes must be committed, stashed, or removed "
                "before update."
            )
    except LocalRuntimeError as exc:
        component["error"] = str(exc)
    return component


def inspect_local_package_updates(
    managed: dict[str, Any],
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Compare both local package checkouts with their upstream default branches."""
    components: list[dict[str, Any]] = []
    runtime_dir = Path(str(managed.get("runtime_dir") or "")).expanduser().resolve()
    _validate_runtime_checkout(runtime_dir)
    runtime_status = inspect_local_runtime(managed)
    _report(progress, 20, "Checking the Runtime package")
    runtime_component = _inspect_local_checkout_update(
        checkout_dir=runtime_dir,
        kind="runtime",
        service_name=str(
            managed.get("service_name") or "blacknode-runtime-local-process"
        ),
        port=int(managed.get("runtime_port") or 0),
    )
    runtime_component["state"] = runtime_status["state"]
    runtime_component["reported_version"] = (
        (runtime_status.get("manifest") or {}).get("runtime_version")
        or runtime_status["installed_version"]
    )
    runtime_component["environment_installed"] = runtime_status["installed"]
    if not runtime_status["installed"] and not runtime_component["error"]:
        runtime_component["error"] = (
            "The Runtime package environment is not installed. Reinstall it to run "
            "the service."
        )
    components.append(runtime_component)

    hardware_value = str(managed.get("hardware_dir") or "").strip()
    if hardware_value:
        hardware_dir = Path(hardware_value).expanduser().resolve()
        _validate_hardware_checkout(hardware_dir)
        hardware_status = inspect_local_hardware(managed)
        _report(progress, 55, "Checking the Hardware package")
        hardware_component = _inspect_local_checkout_update(
            checkout_dir=hardware_dir,
            kind="hardware",
            service_name=str(
                managed.get("hardware_service_name")
                or "blacknode-hardware-local-awaiting-device"
            ),
            port=int(managed.get("hardware_port") or 0),
        )
        hardware_component["state"] = hardware_status["state"]
        hardware_component["reported_version"] = (
            (hardware_status.get("status") or {}).get("software_version")
            or hardware_status["installed_version"]
        )
        hardware_component["environment_installed"] = hardware_status["installed"]
        if not hardware_status["installed"] and not hardware_component["error"]:
            hardware_component["error"] = (
                "The Hardware package environment is not installed. Reinstall it to run "
                "the service."
            )
        components.append(hardware_component)
    return {"ok": not any(item["error"] for item in components), "components": components}


def manage_local_package(
    managed: dict[str, Any],
    *,
    kind: str,
    action: str,
    core_root: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run, stop, restart, update, reinstall, or delete one local package environment."""
    clean_kind = str(kind or "").strip().lower()
    clean_action = str(action or "").strip().lower()
    if clean_kind not in {"runtime", "hardware"}:
        raise LocalRuntimeError("Package must be runtime or hardware.")
    if clean_action not in {
        "run", "stop", "restart", "update", "reinstall", "delete",
    }:
        raise LocalRuntimeError(
            "Package action must be run, stop, restart, update, reinstall, or delete."
        )

    is_runtime = clean_kind == "runtime"
    checkout_dir = Path(
        str(managed.get("runtime_dir" if is_runtime else "hardware_dir") or "")
    ).expanduser().resolve()
    if is_runtime:
        _validate_runtime_checkout(checkout_dir)
        current = inspect_local_runtime(managed)
    else:
        _validate_hardware_checkout(checkout_dir)
        current = inspect_local_hardware(managed)
    was_active = current.get("state") in {"running", "unreachable"}

    runtime_only_management = dict(managed)
    runtime_only_management["hardware_dir"] = ""

    def stop_selected() -> None:
        if is_runtime:
            stop_local_runtime(runtime_only_management)
        else:
            stop_local_hardware(managed)

    def run_selected() -> dict[str, Any]:
        return (
            ensure_local_runtime(runtime_only_management)
            if is_runtime
            else ensure_local_hardware(managed)
        )

    if clean_action == "run":
        _report(progress, 45, f"Starting the {clean_kind.title()} package service")
        result = run_selected()
        _report(progress, 100, f"{clean_kind.title()} package service is running")
        return {"ok": True, "kind": clean_kind, "action": clean_action, "result": result}
    if clean_action == "stop":
        _report(progress, 45, f"Stopping the {clean_kind.title()} package service")
        result = stop_selected()
        _report(progress, 100, f"{clean_kind.title()} package service is stopped")
        return {"ok": True, "kind": clean_kind, "action": clean_action, "result": result}
    if clean_action == "restart":
        _report(progress, 30, f"Stopping the {clean_kind.title()} package service")
        stop_selected()
        _report(progress, 65, f"Starting the {clean_kind.title()} package service")
        result = run_selected()
        _report(progress, 100, f"{clean_kind.title()} package service restarted")
        return {
            "ok": True,
            "kind": clean_kind,
            "action": clean_action,
            "restarted": True,
            "result": result,
        }

    _report(progress, 20, f"Stopping the {clean_kind.title()} package service")
    stop_selected()
    environment_dir = checkout_dir / ".venv"
    if clean_action == "delete":
        _report(progress, 65, f"Deleting the {clean_kind.title()} package environment")
        if environment_dir.is_dir():
            _remove_tree(environment_dir)
        _report(progress, 100, f"{clean_kind.title()} package environment deleted")
        return {
            "ok": True,
            "kind": clean_kind,
            "action": clean_action,
            "source_preserved": True,
            "configuration_preserved": True,
        }

    if clean_action == "update":
        _report(progress, 35, f"Downloading {clean_kind.title()} package updates")
        component = _inspect_local_checkout_update(
            checkout_dir=checkout_dir,
            kind=clean_kind,
            service_name=str(
                managed.get("service_name" if is_runtime else "hardware_service_name")
                or ""
            ),
            port=int(
                managed.get("runtime_port" if is_runtime else "hardware_port") or 0
            ),
        )
        if component["error"]:
            raise LocalRuntimeError(str(component["error"]))
        if component["update_available"]:
            _run(
                ["git", "merge", "--ff-only", str(component["latest"]["commit"])],
                cwd=checkout_dir,
                timeout=180,
            )

    python = _runtime_python(checkout_dir) if is_runtime else _hardware_python(checkout_dir)
    if not python.is_file():
        _report(progress, 55, f"Creating the {clean_kind.title()} package environment")
        _run([sys.executable, "-m", "venv", str(environment_dir)], timeout=180)
    _report(progress, 70, f"Installing the {clean_kind.title()} package")
    _run([str(python), "-m", "pip", "install", "-e", str(checkout_dir)], timeout=900)
    if is_runtime:
        _report(progress, 82, "Connecting Runtime to this Blacknode workspace")
        _run(
            [str(python), "-m", "pip", "install", "-e", str(Path(core_root).resolve())],
            timeout=900,
        )
    restarted = False
    if was_active:
        _report(progress, 92, f"Restarting the {clean_kind.title()} package service")
        run_selected()
        restarted = True
    _report(progress, 100, f"{clean_kind.title()} package {clean_action} complete")
    return {
        "ok": True,
        "kind": clean_kind,
        "action": clean_action,
        "restarted": restarted,
        "installed_version": _checkout_version(checkout_dir),
    }


def stop_local_runtime(managed: dict[str, Any]) -> dict[str, Any]:
    hardware = None
    if managed.get("hardware_dir"):
        hardware = stop_local_hardware(managed)
    runtime_dir = Path(str(managed.get("runtime_dir") or "")).expanduser().resolve()
    config_path = Path(str(managed.get("config_path") or "")).expanduser().resolve()
    pid_file = Path(str(managed.get("pid_file") or "")).expanduser().resolve()
    _validate_runtime_checkout(runtime_dir)
    if (
        config_path.parent != runtime_dir / ".blacknode-runtime"
        or pid_file.parent != runtime_dir / ".blacknode-runtime"
    ):
        raise LocalRuntimeError("The saved local Runtime identity is incomplete.")
    pid = _read_pid(pid_file)
    if not pid:
        return {
            "ok": True,
            "action": "pause",
            "state": "inactive",
            "service_name": "blacknode-runtime-local-process",
            "hardware": hardware,
        }
    if not _pid_is_expected(pid, runtime_dir, config_path):
        try:
            os.kill(pid, 0)
        except OSError:
            pid_file.unlink(missing_ok=True)
        else:
            raise LocalRuntimeError(
                f"Refusing to stop PID {pid}; it is not the saved Blacknode Runtime process."
            )
        return {
            "ok": True,
            "action": "pause",
            "state": "inactive",
            "service_name": "blacknode-runtime-local-process",
            "hardware": hardware,
        }
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        os.kill(pid, 15)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
    pid_file.unlink(missing_ok=True)
    return {
        "ok": True,
        "action": "pause",
        "state": "inactive",
        "service_name": "blacknode-runtime-local-process",
        "hardware": hardware,
    }


def uninstall_local_runtime(
    managed: dict[str, Any],
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    runtime_dir = Path(str(managed.get("runtime_dir") or "")).expanduser().resolve()
    hardware_dir_value = str(managed.get("hardware_dir") or "").strip()
    hardware_dir = (
        Path(hardware_dir_value).expanduser().resolve()
        if hardware_dir_value
        else None
    )
    runtime_was_present = runtime_dir.exists()
    hardware_was_present = hardware_dir is not None and hardware_dir.exists()
    _report(progress, 25, "Stopping the local Runtime and Robot Hardware")
    if runtime_was_present:
        runtime_management = dict(managed)
        if not hardware_was_present:
            runtime_management["hardware_dir"] = ""
        stop_local_runtime(runtime_management)
    elif hardware_was_present:
        stop_local_hardware(managed)

    if hardware_dir is not None:
        _report(progress, 55, "Removing local Robot Hardware files")
        if bool(managed.get("hardware_owned_install")) and hardware_dir.exists():
            _validate_hardware_checkout(hardware_dir)
            if hardware_dir in {
                Path(hardware_dir.anchor).resolve(),
                Path.home().resolve(),
            }:
                raise LocalRuntimeError("Refusing to remove a broad Robot Hardware path.")
            _remove_tree(hardware_dir)
        else:
            hardware_private_dir = hardware_dir / ".blacknode-hardware"
            if hardware_private_dir.is_dir():
                _remove_tree(hardware_private_dir)
    _report(progress, 75, "Removing local Runtime files")
    if bool(managed.get("owned_install")) and runtime_dir.exists():
        _validate_runtime_checkout(runtime_dir)
        if runtime_dir in {Path(runtime_dir.anchor).resolve(), Path.home().resolve()}:
            raise LocalRuntimeError("Refusing to remove a broad local Runtime path.")
        _remove_tree(runtime_dir)
    else:
        private_dir = runtime_dir / ".blacknode-runtime"
        if private_dir.is_dir():
            _remove_tree(private_dir)
    return {
        "ok": True,
        "instance_id": "local",
        "runtime_port": int(managed.get("runtime_port") or 0),
        "already_absent": not runtime_was_present and not hardware_was_present,
        "stack_mode": "runtime_only",
        "source_preserved": (
            not bool(managed.get("owned_install"))
            or (
                hardware_dir is not None
                and not bool(managed.get("hardware_owned_install"))
            )
        ),
    }
