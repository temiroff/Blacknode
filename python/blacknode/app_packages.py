from __future__ import annotations

import json
import os
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from .app_deployments import AppDeploymentError, load_app_deployment


APP_PACKAGE_KIND = "blacknode.app-package"
APP_PACKAGE_SCHEMA_VERSION = 1

_CORE_FILES = ("pyproject.toml", "README.md", "LICENSE")
_CORE_PREFIXES = ("python/blacknode/",)
_SERVER_FILES = {
    "editor-server/requirements.txt",
}
_SERVER_SUFFIXES = (".py",)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise AppDeploymentError(f"Could not inspect release files in {repo}: {detail or exc}") from exc
    return result.stdout


def _tracked_files(repo: Path) -> list[Path]:
    values = _git(repo, "ls-files", "-z").split(b"\0")
    return [Path(value.decode("utf-8")) for value in values if value]


def _git_revision(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").decode("ascii", errors="replace").strip()


def _require_clean_tracked_files(repo: Path) -> None:
    status = _git(repo, "status", "--porcelain", "--untracked-files=no").decode(
        "utf-8", errors="replace"
    ).strip()
    if status:
        raise AppDeploymentError(
            f"Release source has uncommitted tracked changes: {repo}. "
            "Commit or restore them before packaging the App."
        )


def _safe_files(root: Path, paths: Iterable[Path]) -> list[Path]:
    resolved_root = root.resolve()
    safe: list[Path] = []
    for relative in paths:
        source = (root / relative).resolve()
        if resolved_root not in source.parents or not source.is_file():
            continue
        safe.append(relative)
    return sorted(safe, key=lambda value: value.as_posix())


def _package_sources(packages_root: Path, required: Iterable[str]) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    if packages_root.is_dir():
        for candidate in packages_root.iterdir():
            manifest = candidate / "blacknode-package.toml"
            if not manifest.is_file():
                continue
            try:
                package = tomllib.loads(manifest.read_text(encoding="utf-8")).get("package", {})
            except (OSError, tomllib.TOMLDecodeError):
                continue
            name = str(package.get("name") or "").strip()
            if name:
                discovered[name] = candidate
    missing = sorted(set(required) - set(discovered))
    if missing:
        raise AppDeploymentError(
            "Required package source is missing from "
            f"{packages_root}: {', '.join(missing)}"
        )
    return {name: discovered[name] for name in sorted(set(required))}


def _initial_component_state(package_sources: Mapping[str, Path]) -> dict[str, Any]:
    """Start an App package with every optional package surface disabled.

    The installer then enables exactly the components and adapters declared by
    the workflows, including their dependency graph. This prevents unrelated
    default components from pulling hardware stacks that the App does not use.
    """
    packages: dict[str, dict[str, bool]] = {}
    for name, package_dir in package_sources.items():
        manifest = tomllib.loads((package_dir / "blacknode-package.toml").read_text(encoding="utf-8"))
        component_values = manifest.get("components", {})
        if not isinstance(component_values, Mapping):
            continue
        overrides: dict[str, bool] = {}
        for component_name, component_value in component_values.items():
            overrides[str(component_name)] = False
            if not isinstance(component_value, Mapping):
                continue
            adapters = component_value.get("adapters", {})
            if isinstance(adapters, Mapping):
                for adapter_name in adapters:
                    overrides[f"{component_name}@{adapter_name}"] = False
        if overrides:
            packages[name] = overrides
    return {"schema_version": 1, "packages": packages}


def _infer_node_component_requirements(
    manifest: dict[str, Any],
    package_sources: Mapping[str, Path],
) -> None:
    node_types = {
        str(node.get("type") or "")
        for app in manifest.get("apps", [])
        if isinstance(app, Mapping)
        for node in (
            app.get("workflow", {}).get("node_meta", {}).values()
            if isinstance(app.get("workflow"), Mapping)
            and isinstance(app.get("workflow", {}).get("node_meta"), Mapping)
            else []
        )
        if isinstance(node, Mapping) and str(node.get("type") or "")
    }
    components = set(str(value) for value in manifest.get("required_components", []))
    adapters = set(str(value) for value in manifest.get("required_adapters", []))
    for package_name, package_dir in package_sources.items():
        package_manifest = tomllib.loads(
            (package_dir / "blacknode-package.toml").read_text(encoding="utf-8")
        )
        component_values = package_manifest.get("components", {})
        if not isinstance(component_values, Mapping):
            continue
        for component_name, component_value in component_values.items():
            if not isinstance(component_value, Mapping):
                continue
            owned_nodes = component_value.get("node-types", [])
            if isinstance(owned_nodes, list) and node_types.intersection(map(str, owned_nodes)):
                components.add(f"{package_name}/{component_name}")
            adapter_values = component_value.get("adapters", {})
            if not isinstance(adapter_values, Mapping):
                continue
            for adapter_name, adapter_value in adapter_values.items():
                if not isinstance(adapter_value, Mapping):
                    continue
                adapter_nodes = adapter_value.get("node-types", [])
                if isinstance(adapter_nodes, list) and node_types.intersection(map(str, adapter_nodes)):
                    components.add(f"{package_name}/{component_name}")
                    adapters.add(f"{package_name}/{component_name}@{adapter_name}")
    manifest["required_components"] = sorted(components)
    manifest["required_adapters"] = sorted(adapters)


def _write_text(archive: zipfile.ZipFile, name: str, value: str, *, executable: bool = False) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
    archive.writestr(info, value.replace("\r\n", "\n").encode("utf-8"))


def _copy_file(archive: zipfile.ZipFile, source: Path, destination: str) -> None:
    info = zipfile.ZipInfo(destination)
    info.create_system = 3
    info.external_attr = 0o644 << 16
    archive.writestr(info, source.read_bytes())


def _bundle_setup_script() -> str:
    return '''from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGES = ROOT / "packages"
DEPLOYMENT = ROOT / "deployment.blacknode-app.json"


def requirement_parts(value: str, *, adapter: bool = False) -> tuple[str, ...]:
    package, separator, rest = value.partition("/")
    if not separator or not package or not rest:
        raise ValueError(f"Invalid package requirement: {value}")
    if not adapter:
        return package, rest
    component, separator, adapter_name = rest.partition("@")
    if not separator or not component or not adapter_name:
        raise ValueError(f"Invalid adapter requirement: {value}")
    return package, component, adapter_name


def main() -> int:
    if sys.version_info < (3, 11):
        print("Blacknode Apps require Python 3.11 or newer.", file=sys.stderr)
        return 1
    manifest = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
    package_dirs = sorted(path.parent for path in PACKAGES.glob("*/blacknode-package.toml"))
    for package_dir in package_dirs:
        requirements = package_dir / "requirements.txt"
        if requirements.is_file():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
                check=True,
            )

    os.environ["BLACKNODE_PACKAGE_PATH"] = str(PACKAGES)
    from blacknode.packages import (
        discover_packages,
        ensure_adapter_enabled,
        ensure_component_enabled,
        install_prerequisites,
    )

    report = discover_packages([PACKAGES])
    failures = report.get("failed", [])
    if failures:
        details = "; ".join(f"{item['name']}: {item['error']}" for item in failures)
        raise RuntimeError(f"Bundled package discovery failed: {details}")
    for value in manifest.get("required_components", []):
        ensure_component_enabled(*requirement_parts(str(value)))
    for value in manifest.get("required_adapters", []):
        ensure_adapter_enabled(*requirement_parts(str(value), adapter=True))

    warnings: list[str] = []
    for package_dir in package_dirs:
        warnings.extend(install_prerequisites(package_dir))
    if warnings:
        print("App prerequisites need attention:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)
        return 1
    final_report = discover_packages([PACKAGES])
    final_failures = final_report.get("failed", [])
    if final_failures:
        details = "; ".join(f"{item['name']}: {item['error']}" for item in final_failures)
        raise RuntimeError(f"Bundled package activation failed: {details}")
    from blacknode.app_deployments import load_app_deployment
    load_app_deployment(DEPLOYMENT)
    print("Blacknode App installation is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _run_app_script() -> str:
    return '''from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def open_when_ready(url: str) -> None:
    health = url.rstrip("/").split("/app/", 1)[0] + "/healthz"
    for _attempt in range(120):
        try:
            with urllib.request.urlopen(health, timeout=1):
                webbrowser.open(url)
                return
        except Exception:
            time.sleep(.25)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run this Blacknode App package")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    deployment_path = ROOT / "deployment.blacknode-app.json"
    manifest = json.loads(deployment_path.read_text(encoding="utf-8"))
    os.environ["BLACKNODE_APP_DEPLOYMENT"] = str(deployment_path)
    os.environ["BLACKNODE_APP_STATIC_DIR"] = str(ROOT / "editor")
    os.environ["BLACKNODE_PACKAGE_PATH"] = str(ROOT / "packages")
    os.environ.setdefault(
        "BLACKNODE_APP_PUBLIC_ORIGINS",
        f"http://localhost:{args.port},http://127.0.0.1:{args.port}",
    )

    server_dir = ROOT / "server"
    os.chdir(server_dir)
    sys.path.insert(0, str(server_dir))
    url = f"http://127.0.0.1:{args.port}/app/{manifest['start_app']}"
    if not args.no_open:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()

    import uvicorn
    uvicorn.run("server:app", host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _install_powershell() -> str:
    return '''$ErrorActionPreference = "Stop"
$BundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $BundleRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $BundleRoot ".venv")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $BundleRoot ".venv")
    } else {
        throw "Python 3.11 or newer is required. Install Python, then run install.ps1 again."
    }
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install (Join-Path $BundleRoot "core")
& $VenvPython -m pip install -r (Join-Path $BundleRoot "server\\requirements.txt")
& $VenvPython (Join-Path $BundleRoot "bundle_setup.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Installed. Run .\\start.ps1 to open the Blacknode App."
'''


def _start_powershell() -> str:
    return '''$ErrorActionPreference = "Stop"
$BundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $BundleRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Run install.ps1 before starting this Blacknode App."
}
& $VenvPython (Join-Path $BundleRoot "run_app.py") @args
exit $LASTEXITCODE
'''


def _install_shell() -> str:
    return '''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11 or newer is required." >&2; exit 1; }
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install "$ROOT/core"
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/server/requirements.txt"
"$ROOT/.venv/bin/python" "$ROOT/bundle_setup.py"
echo "Installed. Run ./start.sh to open the Blacknode App."
'''


def _start_shell() -> str:
    return '''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run ./install.sh before starting this Blacknode App." >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/run_app.py" "$@"
'''


def _readme(manifest: Mapping[str, Any]) -> str:
    app_names = ", ".join(str(app.get("name") or app.get("id")) for app in manifest.get("apps", []))
    return f'''# Blacknode App package

This package contains the Blacknode customer shell and these Apps: {app_names}.

## Windows

1. Install Python 3.11 or newer.
2. Open PowerShell in this folder and run `./install.ps1` once.
3. Run `./start.ps1`. Blacknode opens the first App automatically.

If PowerShell blocks local scripts, run `Set-ExecutionPolicy -Scope Process Bypass`
in that PowerShell window, then retry the scripts.

## Linux

1. Install Python 3.11 or newer, including the `venv` package for your distribution.
2. Run `bash ./install.sh` once.
3. Run `bash ./start.sh`. Blacknode opens the first App automatically.

Use the top-bar App icons to switch between bundled Apps. Use the gear button to
configure the connection and other inputs exposed by the active App. Hardware
drivers, ROS services, credentials, and network access required by the target
robot must be available on this computer or its connected device.
'''


def package_app_deployment(
    deployment: str | Path,
    output: str | Path | None = None,
    *,
    source_root: str | Path | None = None,
    editor_dist: str | Path | None = None,
    packages_root: str | Path | None = None,
) -> Path:
    deployment_path = Path(deployment).expanduser().resolve()
    manifest = load_app_deployment(deployment_path)
    root = Path(source_root).expanduser().resolve() if source_root else _repo_root()
    dist = Path(editor_dist).expanduser().resolve() if editor_dist else root / "editor" / "dist"
    package_root = Path(packages_root).expanduser().resolve() if packages_root else root / "packages"
    if not (dist / "index.html").is_file():
        raise AppDeploymentError(
            f"Built editor assets were not found in {dist}. Run 'npm run build' in {root / 'editor'} first."
        )

    _require_clean_tracked_files(root)
    tracked_root = _tracked_files(root)
    core_files = _safe_files(
        root,
        (
            path for path in tracked_root
            if path.as_posix() in _CORE_FILES
            or path.as_posix().startswith(_CORE_PREFIXES)
        ),
    )
    server_files = _safe_files(
        root,
        (
            path for path in tracked_root
            if path.as_posix() in _SERVER_FILES
            or (
                path.as_posix().startswith("editor-server/")
                and path.suffix.lower() in _SERVER_SUFFIXES
            )
        ),
    )
    if "pyproject.toml" not in {path.as_posix() for path in core_files} or not server_files:
        raise AppDeploymentError(f"{root} does not contain a complete Blacknode release checkout.")

    package_sources = _package_sources(package_root, manifest.get("required_packages", []))
    _infer_node_component_requirements(manifest, package_sources)
    output_path = Path(output).expanduser() if output else Path(f"{manifest['id']}.blacknode-app.zip")
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path == deployment_path:
        raise AppDeploymentError("App package output cannot overwrite the deployment manifest.")

    revisions: dict[str, str] = {"blacknode": _git_revision(root)}
    for name, package_dir in package_sources.items():
        _require_clean_tracked_files(package_dir)
        revisions[name] = _git_revision(package_dir)
    package_metadata = {
        "kind": APP_PACKAGE_KIND,
        "schema_version": APP_PACKAGE_SCHEMA_VERSION,
        "id": manifest["id"],
        "start_app": manifest["start_app"],
        "python": ">=3.11",
        "revisions": revisions,
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        _write_text(archive, "deployment.blacknode-app.json", json.dumps(manifest, indent=2) + "\n")
        _write_text(archive, "blacknode-app-package.json", json.dumps(package_metadata, indent=2) + "\n")
        _write_text(
            archive,
            "packages/.blacknode-components.json",
            json.dumps(_initial_component_state(package_sources), indent=2) + "\n",
        )
        _write_text(archive, "README.md", _readme(manifest))
        _write_text(archive, "bundle_setup.py", _bundle_setup_script())
        _write_text(archive, "run_app.py", _run_app_script())
        _write_text(archive, "install.ps1", _install_powershell())
        _write_text(archive, "start.ps1", _start_powershell())
        _write_text(archive, "install.sh", _install_shell(), executable=True)
        _write_text(archive, "start.sh", _start_shell(), executable=True)

        for relative in core_files:
            _copy_file(archive, root / relative, f"core/{relative.as_posix()}")
        for relative in server_files:
            destination = relative.relative_to("editor-server").as_posix()
            _copy_file(archive, root / relative, f"server/{destination}")
        for source in sorted(path for path in dist.rglob("*") if path.is_file()):
            resolved = source.resolve()
            if dist not in resolved.parents:
                continue
            _copy_file(archive, source, f"editor/{source.relative_to(dist).as_posix()}")
        for name, package_dir in package_sources.items():
            for relative in _safe_files(package_dir, _tracked_files(package_dir)):
                _copy_file(archive, package_dir / relative, f"packages/{name}/{relative.as_posix()}")

    return output_path
