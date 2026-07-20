"""Blacknode extension packages.

A package is a folder (usually a separate git repo cloned into ``packages/``)
with a ``blacknode-package.toml`` manifest, node modules, and optionally a
``templates/`` directory of workflow JSON files. Flat packages use ``nodes/``;
component packages can declare several selectively enabled node directories.

Discovery order at import time: built-in nodes -> packages -> custom-nodes.
Loaded package node modules get a stable import alias
``blacknode.pkg.<name>.<module>`` (dashes become underscores), e.g.
``blacknode.pkg.blacknode_cuda.cuda``.

Packages installed from PyPI register through the ``blacknode.packages``
entry-point group instead of a folder clone; the entry point names a module
whose import registers its nodes.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import traceback
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ._version import __version__ as _CORE_VERSION
from .node import _NODE_REGISTRY
from .package_index import indexed_package

MANIFEST_NAME = "blacknode-package.toml"
ENTRY_POINT_GROUP = "blacknode.packages"
_PKG_MODULE_ROOT = "blacknode.pkg"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PACKAGE_DIRS = (_REPO_ROOT / "packages",)
_DEFAULT_PACKAGE_GIT_BASE = "https://github.com/temiroff"
_PACKAGE_GIT_BASE_ENV = "BLACKNODE_PACKAGE_GIT_BASE"
_SCP_GIT_URL_RE = re.compile(r"^[^/\s@]+@[^:\s]+:.+")
_COMPONENT_STATE_NAME = ".blacknode-components.json"
_PACKAGE_LOCK_NAME = ".blacknode-package-lock.json"


@dataclass
class PackageInfo:
    name: str
    version: str = ""
    description: str = ""
    layer: str = "extensions"
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    component_mode: bool = False
    enabled_components: list[str] = field(default_factory=list)
    path: str = ""
    source: str = "folder"  # folder | entry-point
    requires_blacknode: str = ""
    categories: dict[str, str] = field(default_factory=dict)  # category -> hex color
    pip_dependencies: list[str] = field(default_factory=list)
    import_dependencies: list[str] = field(default_factory=list)  # modules that must import
    docker_images: list[str] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    expected_node_types: list[str] = field(default_factory=list)
    missing_node_types: list[str] = field(default_factory=list)
    git_status: dict[str, Any] = field(default_factory=dict)
    templates_dir: str = ""
    ok: bool = True
    error: str = ""
    warnings: list[str] = field(default_factory=list)  # non-fatal (e.g. missing runtime dep)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PACKAGE_REGISTRY: dict[str, PackageInfo] = {}


def packages_root() -> Path:
    """The default folder packages are cloned into."""
    return _DEFAULT_PACKAGE_DIRS[0]


def default_package_git_base() -> str:
    """Git namespace used when installing packages by short name."""
    configured = os.environ.get(_PACKAGE_GIT_BASE_ENV, "").strip()
    if configured:
        return configured.rstrip("/")

    remote = _repo_origin_url()
    if remote:
        base = _package_git_base_from_url(remote)
        if base:
            return base

    return _DEFAULT_PACKAGE_GIT_BASE


def resolve_package_git_url(source: str) -> str:
    """Resolve a package name, owner/repo shorthand, URL, or local path."""
    value = source.strip()
    if not value:
        return value

    if _is_explicit_git_source(value):
        return value

    # Common GitHub shorthand. Existing local paths are handled above.
    if re.fullmatch(r"[\w.-]+/[\w.-]+(?:\.git)?", value):
        return _join_git_base("https://github.com", value)

    return _join_git_base(default_package_git_base(), value)


def default_package_dirs() -> list[Path]:
    paths = [path for path in _DEFAULT_PACKAGE_DIRS if path.exists()]
    extra = os.environ.get("BLACKNODE_PACKAGE_PATH", "")
    for raw in extra.split(os.pathsep):
        if raw.strip():
            paths.append(Path(raw).expanduser())
    return paths


def installed_packages() -> list[PackageInfo]:
    return list(_PACKAGE_REGISTRY.values())


def package_category_colors() -> dict[str, str]:
    """Category -> color declared by loaded packages, for the editor palette."""
    colors: dict[str, str] = {}
    for info in _PACKAGE_REGISTRY.values():
        if info.ok:
            colors.update(info.categories)
    return colors


def package_template_dirs() -> list[str]:
    return [info.templates_dir for info in _PACKAGE_REGISTRY.values() if info.ok and info.templates_dir]


def _package_layer(value: Any) -> str:
    """Normalize a manifest/catalog layer into a stable grouping identifier."""
    layer = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return layer or "extensions"


def _package_components(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize component metadata from a manifest or catalog."""
    if not isinstance(value, Mapping):
        return {}
    components: dict[str, dict[str, Any]] = {}
    for raw_name, raw_config in value.items():
        name = re.sub(r"[^a-z0-9]+", "-", str(raw_name).strip().lower()).strip("-")
        if not name:
            continue
        config = raw_config if isinstance(raw_config, Mapping) else {}
        capabilities = config.get("capabilities", [])
        dependencies = config.get("dependencies", {})
        if not isinstance(dependencies, Mapping):
            dependencies = {}
        node_paths = config.get("nodes", config.get("node-paths", []))
        if isinstance(node_paths, str):
            node_paths = [node_paths]
        requirements, requirement_errors = _component_requirements(dependencies.get("requires", []))
        components[name] = {
            "name": name,
            "description": str(config.get("description") or ""),
            "default": bool(config.get("default", False)),
            "capabilities": sorted({
                str(capability).strip()
                for capability in capabilities
                if str(capability).strip()
            }) if isinstance(capabilities, list) else [],
            "node_types": _string_list(config.get("node-types", config.get("node_types", []))),
            "node_paths": _string_list(node_paths),
            "module_root": bool(config.get("module-root", False)),
            "pip_dependencies": _string_list(dependencies.get("pip", config.get("pip", []))),
            "import_dependencies": _string_list(dependencies.get("imports", config.get("imports", []))),
            "docker_images": _string_list(dependencies.get("docker", config.get("docker", []))),
            "requirements": requirements,
            "requirement_errors": requirement_errors,
            "enabled": False,
        }
    return components


def _component_requirements(value: Any) -> tuple[list[dict[str, str]], list[str]]:
    """Normalize versioned package/component dependency descriptors."""
    if value in (None, ""):
        return [], []
    if not isinstance(value, list):
        return [], ["dependencies.requires must be an array of tables"]
    requirements: list[dict[str, str]] = []
    errors: list[str] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, Mapping):
            errors.append(f"dependency {index} must be a table")
            continue
        package = _package_name(raw.get("package"))
        component = _component_name(raw.get("component"))
        version = str(raw.get("version") or "").strip()
        if not package and not component:
            errors.append(f"dependency {index} needs package or component")
            continue
        requirements.append({
            "package": package,
            "component": component,
            "version": version,
        })
    return requirements, errors


def _package_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-")


def _component_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _component_state_path(pkg_path: Path) -> Path:
    """Keep local activation outside the extension repository worktree."""
    return pkg_path.parent / _COMPONENT_STATE_NAME


def _read_component_overrides(pkg_path: Path, package_name: str) -> tuple[dict[str, bool], str]:
    state_path = _component_state_path(pkg_path)
    if not state_path.is_file():
        return {}, ""
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        packages = payload.get("packages", {}) if isinstance(payload, Mapping) else {}
        raw = packages.get(package_name, {}) if isinstance(packages, Mapping) else {}
        if not isinstance(raw, Mapping):
            return {}, ""
        return {
            str(name): enabled
            for name, enabled in raw.items()
            if isinstance(enabled, bool)
        }, ""
    except Exception as exc:
        return {}, f"could not read component state {state_path}: {exc}"


def _write_component_override(
    pkg_path: Path,
    package_name: str,
    component_name: str,
    enabled: bool | None,
) -> None:
    state_path = _component_state_path(pkg_path)
    payload: dict[str, Any] = {"schema_version": 1, "packages": {}}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            pass
    payload["schema_version"] = 1
    packages = payload.setdefault("packages", {})
    if not isinstance(packages, dict):
        packages = {}
        payload["packages"] = packages
    package_state = packages.setdefault(package_name, {})
    if not isinstance(package_state, dict):
        package_state = {}
        packages[package_name] = package_state
    if enabled is None:
        package_state.pop(component_name, None)
    else:
        package_state[component_name] = enabled
    if not package_state:
        packages.pop(package_name, None)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(state_path)


def discover_packages(paths: list[str | Path] | None = None) -> dict[str, Any]:
    infos: list[PackageInfo] = []
    for root in paths or default_package_dirs():
        root_path = Path(root).expanduser()
        if not root_path.exists():
            continue
        for pkg_dir in sorted(root_path.iterdir()):
            if not pkg_dir.is_dir() or not (pkg_dir / MANIFEST_NAME).exists():
                continue
            infos.append(load_package(pkg_dir))
    infos.extend(_load_entry_point_packages())
    _audit_enabled_component_dependencies(infos)
    return {
        "loaded": [info.to_dict() for info in infos if info.ok],
        "failed": [info.to_dict() for info in infos if not info.ok],
    }


def _audit_enabled_component_dependencies(infos: list[PackageInfo]) -> None:
    """Reject persisted/default activation states with unavailable requirements."""
    for info in infos:
        if not info.ok or not info.component_mode:
            continue
        errors: list[str] = []
        for component_name in info.enabled_components:
            try:
                resolution = component_dependency_plan(info.name, component_name)
            except ValueError as exc:
                errors.append(f"{component_name}: {exc}")
                continue
            missing_activation = [
                f"{item['package']}/{item['component']}"
                for item in resolution["changes"]
                if not (item["package"] == info.name and item["component"] == component_name)
            ]
            if missing_activation:
                errors.append(
                    f"{component_name}: required components are disabled: "
                    + ", ".join(missing_activation)
                )
        if not errors:
            continue
        _deregister_package_nodes(info.name)
        _clear_package_modules(_safe_module_name(info.name))
        _record_failure(
            info,
            "Enabled component dependency audit failed:\n- " + "\n- ".join(errors),
        )


def load_package(pkg_dir: str | Path) -> PackageInfo:
    pkg_path = Path(pkg_dir).expanduser().resolve()
    info = PackageInfo(name=pkg_path.name, path=str(pkg_path))
    try:
        manifest = tomllib.loads((pkg_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    except Exception:
        return _record_failure(info, f"Could not parse {MANIFEST_NAME}:\n{traceback.format_exc()}")

    meta = manifest.get("package", {}) or {}
    info.name = str(meta.get("name") or pkg_path.name)
    indexed = indexed_package(info.name) or {}
    info.version = str(meta.get("version", ""))
    info.description = str(meta.get("description", ""))
    info.layer = _package_layer(meta.get("layer") or indexed.get("layer"))
    manifest_components = manifest.get("components")
    info.components = _package_components(manifest_components or indexed.get("components"))
    info.component_mode = bool(meta.get("component-mode", False)) or (
        isinstance(manifest_components, Mapping)
        and any(component["node_paths"] for component in info.components.values())
    )
    info.requires_blacknode = str(meta.get("requires-blacknode", ""))
    info.categories = {str(k): str(v) for k, v in (manifest.get("categories", {}) or {}).items()}
    deps = manifest.get("dependencies", {}) or {}
    info.pip_dependencies = _string_list(deps.get("pip", []))
    info.import_dependencies = _string_list(deps.get("imports", []))
    info.docker_images = _string_list(deps.get("docker", []))

    overrides: dict[str, bool] = {}
    if info.component_mode:
        overrides, state_warning = _read_component_overrides(pkg_path, info.name)
        if state_warning:
            info.warnings.append(state_warning)
    for component_name, component in info.components.items():
        component["enabled"] = (
            overrides.get(component_name, component["default"])
            if info.component_mode else True
        )
        if not component["enabled"]:
            continue
        info.enabled_components.append(component_name)
        info.pip_dependencies = _merge_strings(info.pip_dependencies, component["pip_dependencies"])
        info.import_dependencies = _merge_strings(info.import_dependencies, component["import_dependencies"])
        info.docker_images = _merge_strings(info.docker_images, component["docker_images"])

    invalid_requirements = [
        f"{component_name}: {error}"
        for component_name in info.enabled_components
        for error in info.components[component_name]["requirement_errors"]
    ]
    if invalid_requirements:
        _deregister_package_nodes(info.name)
        _clear_package_modules(_safe_module_name(info.name))
        return _record_failure(
            info,
            "Invalid enabled component dependencies:\n- " + "\n- ".join(invalid_requirements),
        )

    templates_dir = pkg_path / "templates"
    if templates_dir.is_dir():
        info.templates_dir = str(templates_dir)

    if info.requires_blacknode and not _version_satisfied(info.requires_blacknode, _CORE_VERSION):
        _deregister_package_nodes(info.name)
        _clear_package_modules(_safe_module_name(info.name))
        return _record_failure(info, f"Requires blacknode {info.requires_blacknode}, this is {_CORE_VERSION}")

    _deregister_package_nodes(info.name)
    snake_name = _safe_module_name(info.name)
    _clear_package_modules(snake_name)
    try:
        if info.component_mode:
            _prepare_component_package(snake_name, pkg_path)
            for component_name in info.enabled_components:
                component = info.components[component_name]
                for index, nodes_dir in enumerate(_component_node_dirs(pkg_path, component_name, component)):
                    before = dict(_NODE_REGISTRY)
                    module_suffix = _safe_module_name(component_name)
                    if index:
                        module_suffix += f"_{index + 1}"
                    if component.get("module_root"):
                        if index:
                            raise ValueError(
                                f"Component '{component_name}' may mount only one node path at the package module root"
                            )
                        _import_nodes_package(snake_name, nodes_dir, clear=False)
                    else:
                        _import_nodes_module(
                            f"{_PKG_MODULE_ROOT}.{snake_name}.{module_suffix}",
                            nodes_dir,
                        )
                    _tag_new_package_nodes(before, info.name, nodes_dir, component_name)
        else:
            nodes_dir = pkg_path / "nodes"
            if not nodes_dir.is_dir():
                raise FileNotFoundError("Package has no nodes/ directory")
            before = dict(_NODE_REGISTRY)
            _import_nodes_package(snake_name, nodes_dir, clear=False)
            _tag_new_package_nodes(before, info.name, nodes_dir)
    except Exception:
        _deregister_package_nodes(info.name)
        _clear_package_modules(snake_name)
        return _record_failure(info, traceback.format_exc())

    info.node_types = sorted(
        name for name, fn in _NODE_REGISTRY.items()
        if getattr(fn, "_bn_package", "") == info.name
    )
    _check_import_dependencies(info)
    _check_indexed_nodes(info)
    _PACKAGE_REGISTRY[info.name] = info
    return info


def component_dependency_plan(package_name: str, component_name: str) -> dict[str, Any]:
    """Resolve installed dependencies in activation order without mutation."""
    target_package = _package_name(package_name)
    target_component = _component_name(component_name)
    plan: list[dict[str, Any]] = []
    visited: set[tuple[str, str]] = set()
    visiting: list[tuple[str, str]] = []

    def visit(current_package: str, current_component: str, version: str = "") -> None:
        key = (current_package, current_component)
        if key in visiting:
            cycle = visiting[visiting.index(key):] + [key]
            rendered = " -> ".join(
                f"{package}/{component}" if component else package
                for package, component in cycle
            )
            raise ValueError(f"Component dependency cycle: {rendered}")
        info = _PACKAGE_REGISTRY.get(current_package)
        if info is None:
            indexed = indexed_package(current_package) or {}
            git_url = str(indexed.get("git_url") or "")
            fix = f"; install it with: blacknode packages install {git_url}" if git_url else ""
            raise ValueError(f"Required package '{current_package}' is not installed{fix}")
        if version:
            if not info.version:
                raise ValueError(
                    f"Required package '{current_package}' does not declare a version; needs {version}"
                )
            if not _version_constraint_satisfied(version, info.version):
                raise ValueError(
                    f"Package '{current_package}' {info.version} does not satisfy required version {version}"
                )
        if key in visited:
            return
        if not current_component:
            visited.add(key)
            plan.append({
                "package": current_package,
                "component": "",
                "version": info.version,
                "enabled": True,
            })
            return
        if current_component not in info.components:
            raise ValueError(
                f"Required package '{current_package}' has no component '{current_component}'"
            )
        if not info.component_mode:
            raise ValueError(
                f"Package '{current_package}' does not support selective component activation"
            )
        component = info.components[current_component]
        if component.get("requirement_errors"):
            raise ValueError(
                f"Invalid dependencies for {current_package}/{current_component}: "
                + "; ".join(component["requirement_errors"])
            )
        visiting.append(key)
        for requirement in component.get("requirements", []):
            dependency_package = requirement.get("package") or current_package
            visit(
                dependency_package,
                requirement.get("component") or "",
                requirement.get("version") or "",
            )
        visiting.pop()
        visited.add(key)
        plan.append({
            "package": current_package,
            "component": current_component,
            "version": info.version,
            "enabled": bool(component.get("enabled")),
        })

    visit(target_package, target_component)
    return {
        "target": {"package": target_package, "component": target_component},
        "plan": plan,
        "changes": [item for item in plan if item["component"] and not item["enabled"]],
    }


def component_dependency_install_plan(package_name: str, component_name: str) -> dict[str, Any]:
    """Plan official installs, safe fast-forward updates, and activation.

    This preflight never changes package contents. Missing packages must have
    an official catalog URL. Incompatible installed versions are upgradable
    only from a clean, behind-only Git checkout.
    """
    target_package = _package_name(package_name)
    target_component = _component_name(component_name)
    actions: list[dict[str, Any]] = []
    conflicts: list[str] = []
    visited: set[tuple[str, str, str]] = set()
    visiting: list[tuple[str, str]] = []

    def visit(current_package: str, current_component: str, version: str = "") -> None:
        signature = (current_package, current_component, version)
        if signature in visited:
            return
        key = (current_package, current_component)
        if key in visiting:
            cycle = visiting[visiting.index(key):] + [key]
            conflicts.append("Component dependency cycle: " + " -> ".join(
                f"{package}/{component}" if component else package
                for package, component in cycle
            ))
            return
        info = _PACKAGE_REGISTRY.get(current_package)
        if info is None:
            indexed = indexed_package(current_package) or {}
            source = str(indexed.get("git_url") or "")
            if not source:
                conflicts.append(f"Required package '{current_package}' is not installed and has no catalog source")
                return
            actions.append({
                "action": "install",
                "package": current_package,
                "component": current_component,
                "version": version,
                "source": source,
            })
            visited.add(signature)
            return
        if version and (not info.version or not _version_constraint_satisfied(version, info.version)):
            state = package_git_status(info.path, fetch=True) if info.source == "folder" and info.path else {}
            if state.get("can_fast_forward"):
                actions.append({
                    "action": "update",
                    "package": current_package,
                    "component": current_component,
                    "version": version,
                    "source": state.get("remote") or "",
                })
            else:
                reason = "working tree is dirty" if state.get("dirty") else "no clean fast-forward update is available"
                conflicts.append(
                    f"Package '{current_package}' {info.version or '?'} does not satisfy {version}; {reason}"
                )
            visited.add(signature)
            return
        if not current_component:
            visited.add(signature)
            return
        if current_component not in info.components:
            conflicts.append(f"Required package '{current_package}' has no component '{current_component}'")
            return
        if not info.component_mode:
            conflicts.append(f"Package '{current_package}' does not support selective component activation")
            return
        component = info.components[current_component]
        if component.get("requirement_errors"):
            conflicts.extend(
                f"Invalid dependency for {current_package}/{current_component}: {error}"
                for error in component["requirement_errors"]
            )
            return
        visiting.append(key)
        for requirement in component.get("requirements", []):
            visit(
                requirement.get("package") or current_package,
                requirement.get("component") or "",
                requirement.get("version") or "",
            )
        visiting.pop()
        if not component.get("enabled"):
            actions.append({
                "action": "enable",
                "package": current_package,
                "component": current_component,
                "version": info.version,
                "source": "",
            })
        visited.add(signature)

    visit(target_package, target_component)
    return {
        "target": {"package": target_package, "component": target_component},
        "ok": not conflicts,
        "actions": actions,
        "conflicts": conflicts,
    }


def ensure_component_enabled(
    package_name: str,
    component_name: str,
    *,
    progress: Callable[[str], None] = print,
) -> PackageInfo:
    """Install/update official dependencies, then transactionally activate."""
    target = _component_package_info(_package_name(package_name), _component_name(component_name))
    root = Path(target.path).resolve().parent
    newly_installed: list[str] = []
    try:
        for _attempt in range(10):
            preflight = component_dependency_install_plan(package_name, component_name)
            if not preflight["ok"]:
                raise ValueError("; ".join(preflight["conflicts"]))
            mutations = [item for item in preflight["actions"] if item["action"] in {"install", "update"}]
            if not mutations:
                return set_component_enabled(package_name, component_name, True)
            for item in mutations:
                if item["action"] == "install":
                    result = install_from_git(item["source"], root=root, install_deps=True, progress=progress)
                    if not result.get("ok"):
                        raise RuntimeError(result.get("error") or f"Could not install {item['package']}")
                    newly_installed.append(str(result["package"]["name"]))
                else:
                    result = update_packages([item["package"]], install_deps=True, progress=progress)
                    if not result.get("ok") or not result.get("updated"):
                        raise RuntimeError(f"Could not update required package {item['package']}")
        raise RuntimeError("Dependency installation did not converge after 10 passes")
    except Exception:
        for name in reversed(newly_installed):
            remove_package(name, root=root)
        raise


def set_component_enabled(package_name: str, component_name: str, enabled: bool) -> PackageInfo:
    """Activate a component dependency graph or safely disable one component.

    Activation state lives beside package repositories. Enable resolves the
    complete installed graph before writing any override and rolls every change
    back if a package reload fails.
    """
    normalized_package = _package_name(package_name)
    normalized_component = _component_name(component_name)
    info = _component_package_info(normalized_package, normalized_component)
    if enabled:
        plan = component_dependency_plan(normalized_package, normalized_component)
        return _activate_component_plan(plan)

    dependents = _enabled_component_dependents(normalized_package, normalized_component)
    if dependents:
        raise ValueError(
            f"Cannot disable {normalized_package}/{normalized_component}; required by: "
            + ", ".join(dependents)
        )
    return _set_single_component(info, normalized_component, False)


def _component_package_info(package_name: str, component_name: str) -> PackageInfo:
    info = _PACKAGE_REGISTRY.get(package_name)
    if info is None:
        raise ValueError(f"No package named '{package_name}' is installed")
    if info.source != "folder" or not info.path:
        raise ValueError("Selective components currently require a folder package")
    if component_name not in info.components:
        raise ValueError(f"Package '{package_name}' has no component '{component_name}'")
    if not info.component_mode:
        raise ValueError(
            f"Package '{package_name}' only publishes component labels; its manifest has not enabled selective loading"
        )
    return info


def _activate_component_plan(resolution: Mapping[str, Any]) -> PackageInfo:
    changes = list(resolution.get("changes") or [])
    target = resolution["target"]
    if not changes:
        return _component_package_info(target["package"], target["component"])

    snapshots: list[tuple[Path, str, str, bool, bool | None]] = []
    package_order: list[str] = []
    try:
        for item in changes:
            info = _component_package_info(item["package"], item["component"])
            pkg_path = Path(info.path).resolve()
            overrides, state_error = _read_component_overrides(pkg_path, info.name)
            if state_error:
                raise ValueError(state_error)
            component_name = item["component"]
            snapshots.append((
                pkg_path,
                info.name,
                component_name,
                component_name in overrides,
                overrides.get(component_name),
            ))
            _write_component_override(pkg_path, info.name, component_name, True)
            if info.name not in package_order:
                package_order.append(info.name)

        for name in package_order:
            updated = load_package(Path(_PACKAGE_REGISTRY[name].path))
            if not updated.ok:
                detail = updated.error.strip().splitlines()[-1] if updated.error.strip() else "package reload failed"
                raise RuntimeError(f"Could not activate dependency graph: {name}: {detail}")
    except Exception:
        for pkg_path, name, component, had_previous, previous in reversed(snapshots):
            _write_component_override(
                pkg_path,
                name,
                component,
                previous if had_previous else None,
            )
        for name in package_order:
            registered = _PACKAGE_REGISTRY.get(name)
            if registered and registered.path:
                load_package(Path(registered.path))
        raise
    updated = _component_package_info(target["package"], target["component"])
    write_package_lock(Path(updated.path).parent)
    return updated


def _set_single_component(info: PackageInfo, component_name: str, enabled: bool) -> PackageInfo:
    pkg_path = Path(info.path).resolve()
    overrides, state_error = _read_component_overrides(pkg_path, info.name)
    if state_error:
        raise ValueError(state_error)
    had_previous = component_name in overrides
    previous = overrides.get(component_name)
    _write_component_override(pkg_path, info.name, component_name, enabled)
    updated = load_package(pkg_path)
    if updated.ok:
        write_package_lock(pkg_path.parent)
        return updated
    _write_component_override(
        pkg_path,
        info.name,
        component_name,
        previous if had_previous else None,
    )
    load_package(pkg_path)
    action = "enable" if enabled else "disable"
    detail = updated.error.strip().splitlines()[-1] if updated.error.strip() else "package reload failed"
    raise RuntimeError(f"Could not {action} {info.name}/{component_name}: {detail}")


def _enabled_component_dependents(package_name: str, component_name: str) -> list[str]:
    dependents: list[str] = []
    for info in _PACKAGE_REGISTRY.values():
        for candidate_name in info.enabled_components:
            if info.name == package_name and candidate_name == component_name:
                continue
            candidate = info.components.get(candidate_name, {})
            for requirement in candidate.get("requirements", []):
                dependency_package = requirement.get("package") or info.name
                if dependency_package == package_name and requirement.get("component") == component_name:
                    dependents.append(f"{info.name}/{candidate_name}")
    return sorted(set(dependents))


def _enabled_package_dependents(package_name: str) -> list[str]:
    """Return enabled components that require any part of a package."""
    dependents: list[str] = []
    for info in _PACKAGE_REGISTRY.values():
        if info.name == package_name:
            continue
        for candidate_name in info.enabled_components:
            candidate = info.components.get(candidate_name, {})
            for requirement in candidate.get("requirements", []):
                if (requirement.get("package") or info.name) == package_name:
                    dependents.append(f"{info.name}/{candidate_name}")
    return sorted(set(dependents))


def package_lock_path(root: str | Path | None = None) -> Path:
    """Return the workspace-local package lockfile path."""
    base = Path(root).expanduser().resolve() if root else packages_root().resolve()
    return base / _PACKAGE_LOCK_NAME


def write_package_lock(root: str | Path | None = None) -> dict[str, Any]:
    """Atomically snapshot installed package versions and enabled components."""
    path = package_lock_path(root)
    packages: dict[str, Any] = {}
    for info in sorted(_PACKAGE_REGISTRY.values(), key=lambda item: item.name):
        if info.source != "folder" or not info.path:
            continue
        pkg_path = Path(info.path).resolve()
        try:
            if pkg_path.parent != path.parent:
                continue
        except OSError:
            continue
        git = package_git_status(pkg_path, fetch=False)
        revision = _git_stdout(_run_git(pkg_path, ["rev-parse", "HEAD"])) if git.get("is_git_repo") else ""
        packages[info.name] = {
            "version": info.version,
            "source": git.get("remote") or info.source,
            "revision": revision,
            "enabled_components": sorted(info.enabled_components),
        }
    payload = {"schema_version": 1, "packages": packages}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {"path": str(path), **payload}


def _merge_strings(existing: list[str], additions: list[str]) -> list[str]:
    return list(dict.fromkeys([*existing, *additions]))


def _component_node_dirs(
    pkg_path: Path,
    component_name: str,
    component: Mapping[str, Any],
) -> list[Path]:
    directories: list[Path] = []
    for raw_path in component.get("node_paths", []):
        nodes_dir = (pkg_path / str(raw_path)).resolve()
        if nodes_dir != pkg_path and pkg_path not in nodes_dir.parents:
            raise ValueError(
                f"Component '{component_name}' node path escapes the package: {raw_path}"
            )
        if not nodes_dir.is_dir():
            raise FileNotFoundError(
                f"Component '{component_name}' node path does not exist: {raw_path}"
            )
        directories.append(nodes_dir)
    return directories


def _tag_new_package_nodes(
    before: Mapping[str, Any],
    package_name: str,
    nodes_dir: Path,
    component_name: str = "",
) -> None:
    for name, fn in _NODE_REGISTRY.items():
        if before.get(name) is fn:
            continue
        fn._bn_package = package_name
        fn._bn_component = component_name
        if not getattr(fn, "_bn_source_path", ""):
            fn._bn_source_path = str(nodes_dir)


def _deregister_package_nodes(package_name: str) -> None:
    for node_name, fn in list(_NODE_REGISTRY.items()):
        if getattr(fn, "_bn_package", "") == package_name:
            del _NODE_REGISTRY[node_name]


def _check_indexed_nodes(info: PackageInfo) -> None:
    """Warn when an official package checkout lacks indexed node types."""
    indexed = indexed_package(info.name)
    if indexed is None:
        return

    expected_set = {str(node_type) for node_type in indexed.get("node_types", []) if str(node_type)}
    if info.component_mode:
        indexed_components = _package_components(indexed.get("components"))
        for component_name, component in info.components.items():
            if component.get("enabled"):
                continue
            declared = component.get("node_types") or indexed_components.get(component_name, {}).get("node_types", [])
            expected_set.difference_update(str(node_type) for node_type in declared)
    expected = sorted(expected_set)
    info.expected_node_types = expected
    info.missing_node_types = sorted(set(expected) - set(info.node_types))
    if not info.missing_node_types:
        return

    plural = "s" if len(info.missing_node_types) != 1 else ""
    info.warnings.append(
        f"missing official node{plural}: {', '.join(info.missing_node_types)}\n"
        "Fix: startup auto-update can repair this after local package git changes are committed, "
        "stashed, or discarded.\n"
        f"Manual repair: blacknode packages update {info.name}\n"
        "If this package is intentionally older, update the package index or template requirements."
    )

def _check_import_dependencies(info: PackageInfo) -> None:
    """Warn (non-fatally) about declared runtime modules that won't import.

    A package's nodes often guard heavy imports (GPU, ROS, ...) so the package
    still loads on machines without them. That means a missing dependency is
    invisible until a node fails at runtime. Listing the modules under
    ``[dependencies] imports`` lets the loader verify them up front and report
    exactly what to install — into this server's own interpreter — in
    ``blacknode packages list``, the ``/packages`` endpoint, and the editor's
    Packages tab.
    """
    missing = _missing_import_dependencies(info)
    if not missing:
        return
    requirements = Path(info.path) / "requirements.txt"
    if requirements.exists():
        fix = f'"{sys.executable}" -m pip install -r "{requirements}"'
    else:
        fix = f'"{sys.executable}" -m pip install ' + " ".join(missing)
    plural = "ies" if len(missing) > 1 else "y"
    info.warnings.append(
        f"missing Python dependenc{plural}: {', '.join(missing)} — its nodes will "
        f"return errors until installed.\nFix: {fix}\n(or: blacknode packages setup {info.name})"
    )


def _missing_import_dependencies(info: PackageInfo) -> list[str]:
    missing: list[str] = []
    for raw in info.import_dependencies:
        module = raw.strip()
        if not module:
            continue
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(module)
    return missing


def install_missing_python_dependencies(
    infos: list[PackageInfo] | None = None,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Install declared Python dependencies only for packages missing imports.

    This is intentionally narrower than :func:`install_prerequisites`: normal
    startup may repair Python packages, but it must not pull Docker images or
    invoke package setup scripts on every launch.
    """
    selected = infos if infos is not None else installed_packages()
    installed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for info in selected:
        missing = _missing_import_dependencies(info)
        if not missing:
            skipped.append({"name": info.name, "reason": "Python dependencies already available"})
            continue
        if info.source != "folder" or not info.path:
            failed.append({"name": info.name, "missing": missing, "error": "package is not a local folder package"})
            continue
        package_path = Path(info.path).resolve()
        requirements = package_path / "requirements.txt"
        if requirements.is_file() or info.pip_dependencies:
            install_args = []
            sources = []
            if requirements.is_file():
                install_args.extend(["-r", str(requirements)])
                sources.append(str(requirements))
            if info.pip_dependencies:
                install_args.extend(info.pip_dependencies)
                sources.append("enabled manifest dependencies")
            source = " and ".join(sources)
        else:
            install_args = missing
            source = "declared import names"
        progress(f"Installing missing Python dependencies for {info.name} from {source}")
        pip = subprocess.run([
            sys.executable, "-m", "pip", "install", *install_args,
            "--disable-pip-version-check", "--no-warn-script-location",
        ])
        if pip.returncode == 0:
            importlib.invalidate_caches()
            installed.append({"name": info.name, "missing": missing, "source": source})
        else:
            failed.append({"name": info.name, "missing": missing, "error": f"pip exited with code {pip.returncode}"})
    return {"ok": not failed, "installed": installed, "skipped": skipped, "failed": failed}


def _record_failure(info: PackageInfo, error: str) -> PackageInfo:
    info.ok = False
    info.error = error
    _check_indexed_nodes(info)
    _PACKAGE_REGISTRY[info.name] = info
    return info


def _safe_module_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def _pkg_root_module() -> types.ModuleType:
    root = sys.modules.get(_PKG_MODULE_ROOT)
    if root is None:
        root = types.ModuleType(_PKG_MODULE_ROOT)
        root.__path__ = []
        sys.modules[_PKG_MODULE_ROOT] = root
        blacknode = sys.modules.get("blacknode")
        if blacknode is not None:
            blacknode.pkg = root
    return root


def _clear_package_modules(snake_name: str) -> None:
    module_name = f"{_PKG_MODULE_ROOT}.{snake_name}"
    for key in [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]:
        del sys.modules[key]
    root = sys.modules.get(_PKG_MODULE_ROOT)
    if root is not None and hasattr(root, snake_name):
        delattr(root, snake_name)


def _prepare_component_package(snake_name: str, pkg_path: Path) -> types.ModuleType:
    root = _pkg_root_module()
    module_name = f"{_PKG_MODULE_ROOT}.{snake_name}"
    module = types.ModuleType(module_name)
    module.__path__ = [str(pkg_path)]
    sys.modules[module_name] = module
    setattr(root, snake_name, module)
    return module


def _import_nodes_package(
    snake_name: str,
    nodes_dir: Path,
    *,
    clear: bool = True,
) -> types.ModuleType:
    root = _pkg_root_module()
    module_name = f"{_PKG_MODULE_ROOT}.{snake_name}"
    if clear:
        _clear_package_modules(snake_name)
    module = _import_nodes_module(module_name, nodes_dir)
    setattr(root, snake_name, module)
    return module


def _import_nodes_module(module_name: str, nodes_dir: Path) -> types.ModuleType:
    """Import one directory as a package and execute each public top-level module."""

    init_py = nodes_dir / "__init__.py"
    if init_py.exists():
        spec = importlib.util.spec_from_file_location(
            module_name, init_py, submodule_search_locations=[str(nodes_dir)]
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load package nodes from {nodes_dir}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
    else:
        module = types.ModuleType(module_name)
        module.__path__ = [str(nodes_dir)]
        sys.modules[module_name] = module

    # Import every top-level node module __init__ did not already pull in.
    for path in sorted(nodes_dir.glob("*.py")):
        if not path.name.startswith("_"):
            importlib.import_module(f"{module_name}.{path.stem}")
    return module


def _load_entry_point_packages() -> list[PackageInfo]:
    infos: list[PackageInfo] = []
    try:
        entry_points = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        return infos
    for entry_point in entry_points:
        info = PackageInfo(name=entry_point.name, source="entry-point")
        before = dict(_NODE_REGISTRY)
        try:
            module = importlib.import_module(entry_point.value)
        except Exception:
            _record_failure(info, traceback.format_exc())
            infos.append(info)
            continue
        info.version = str(getattr(module, "__version__", ""))
        info.description = (module.__doc__ or "").strip().split("\n")[0]
        info.path = getattr(module, "__file__", "") or ""
        indexed = indexed_package(info.name) or {}
        info.layer = _package_layer(getattr(module, "BLACKNODE_LAYER", "") or indexed.get("layer"))
        info.components = _package_components(
            getattr(module, "BLACKNODE_COMPONENTS", {}) or indexed.get("components")
        )
        for component_name, component in info.components.items():
            component["enabled"] = True
            info.enabled_components.append(component_name)
        info.categories = {
            str(k): str(v)
            for k, v in (getattr(module, "BLACKNODE_CATEGORIES", {}) or {}).items()
        }
        info.node_types = sorted(
            name for name, fn in _NODE_REGISTRY.items() if before.get(name) is not fn
        )
        if not info.node_types:
            # Module was already imported (e.g. on reload): keep the first scan's list.
            previous = _PACKAGE_REGISTRY.get(info.name)
            if previous:
                info.node_types = previous.node_types
        for name in info.node_types:
            _NODE_REGISTRY[name]._bn_package = info.name
        _check_indexed_nodes(info)
        _PACKAGE_REGISTRY[info.name] = info
        infos.append(info)
    return infos


def package_git_status(pkg_dir: str | Path, fetch: bool = False) -> dict[str, Any]:
    """Return local git status for a folder package without mutating files."""
    pkg_path = Path(pkg_dir).expanduser().resolve()
    state: dict[str, Any] = {
        "is_git_repo": False,
        "ok": True,
        "error": "",
        "fetch_error": "",
        "remote": "",
        "branch": "",
        "head": "",
        "upstream": "",
        "dirty": False,
        "ahead": None,
        "behind": None,
        "update_available": False,
        "can_fast_forward": False,
    }
    if not (pkg_path / ".git").exists():
        return state
    state["is_git_repo"] = True
    if not shutil.which("git"):
        state["ok"] = False
        state["error"] = "git is not on PATH"
        return state

    inside = _run_git(pkg_path, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0:
        state["ok"] = False
        state["error"] = _git_error(inside)
        return state

    state["remote"] = _git_stdout(_run_git(pkg_path, ["remote", "get-url", "origin"]))
    state["branch"] = _git_stdout(_run_git(pkg_path, ["rev-parse", "--abbrev-ref", "HEAD"]))
    state["head"] = _git_stdout(_run_git(pkg_path, ["rev-parse", "--short", "HEAD"]))
    state["upstream"] = _git_stdout(_run_git(pkg_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]))
    state["dirty"] = bool(_git_stdout(_run_git(pkg_path, ["status", "--porcelain"])))

    if fetch and state["upstream"]:
        fetched = _run_git(pkg_path, ["fetch", "--prune"], timeout=60)
        if fetched.returncode != 0:
            state["fetch_error"] = _git_error(fetched)

    if state["upstream"]:
        counts = _git_stdout(_run_git(pkg_path, ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]))
        parts = counts.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            ahead = int(parts[0])
            behind = int(parts[1])
            state["ahead"] = ahead
            state["behind"] = behind
            state["update_available"] = behind > 0
            state["can_fast_forward"] = behind > 0 and ahead == 0 and not state["dirty"]
    return state


def package_statuses(fetch: bool = False) -> list[dict[str, Any]]:
    """Return installed package records with git status attached."""
    statuses: list[dict[str, Any]] = []
    for info in installed_packages():
        if info.source == "folder" and info.path:
            info.git_status = package_git_status(info.path, fetch=fetch)
        else:
            info.git_status = {"is_git_repo": False, "ok": True, "error": ""}
        statuses.append(info.to_dict())
    return statuses


def update_packages(
    names: list[str] | None = None,
    *,
    install_deps: bool = False,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch and fast-forward clean folder packages.

    Dirty, ahead, diverged, non-git, and failed packages are skipped rather than
    overwritten. This is safe to run before startup when the user opts in.
    """
    wanted = {name.strip() for name in (names or []) if name.strip()}
    by_name = {info.name: info for info in installed_packages()}
    selected = [info for info in installed_packages() if not wanted or info.name in wanted]
    result: dict[str, Any] = {"ok": True, "updated": [], "skipped": [], "failed": []}

    for name in sorted(wanted - set(by_name)):
        result["ok"] = False
        result["failed"].append({"name": name, "error": "package is not installed"})

    for info in selected:
        if info.source != "folder" or not info.path:
            result["skipped"].append({"name": info.name, "reason": "not a folder package"})
            continue
        pkg_path = Path(info.path).expanduser().resolve()
        state = package_git_status(pkg_path, fetch=True)
        if not state.get("is_git_repo"):
            result["skipped"].append({"name": info.name, "reason": "not a git checkout"})
            continue
        if not state.get("ok", True):
            result["ok"] = False
            result["failed"].append({"name": info.name, "error": state.get("error", "git status failed")})
            continue
        if state.get("fetch_error"):
            result["ok"] = False
            result["failed"].append({"name": info.name, "error": state["fetch_error"]})
            continue
        if not state.get("upstream"):
            result["skipped"].append({"name": info.name, "reason": "no upstream branch configured"})
            continue
        if state.get("dirty"):
            result["skipped"].append({"name": info.name, "reason": "working tree has local changes"})
            continue
        ahead = int(state.get("ahead") or 0)
        behind = int(state.get("behind") or 0)
        if ahead > 0:
            reason = f"local branch is ahead of upstream by {ahead} commit(s)"
            if behind > 0:
                reason += f" and behind by {behind} commit(s)"
            result["skipped"].append({"name": info.name, "reason": reason})
            continue
        if behind <= 0:
            result["skipped"].append({"name": info.name, "reason": "already up to date"})
            continue

        progress(f"Updating {info.name} ({behind} upstream commit(s))")
        pulled = _run_git(pkg_path, ["pull", "--ff-only"], timeout=120)
        if pulled.returncode != 0:
            result["ok"] = False
            result["failed"].append({"name": info.name, "error": _git_error(pulled)})
            continue
        if install_deps:
            install_prerequisites(pkg_path, progress=progress)
        reloaded = load_package(pkg_path)
        result["updated"].append({"name": info.name, "package": reloaded.to_dict()})

    return result


def _run_git(pkg_path: Path, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    safe_dir = pkg_path.resolve().as_posix()
    return subprocess.run(
        ["git", "-c", f"safe.directory={safe_dir}", "-C", str(pkg_path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _git_stdout(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "git command failed").strip()

def install_from_git(
    url: str,
    root: str | Path | None = None,
    install_deps: bool = True,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Clone a package repo into the packages folder, install its
    prerequisites, and load it. Returns {ok, package, error}."""
    target_root = Path(root).expanduser().resolve() if root else packages_root()
    target_root.mkdir(parents=True, exist_ok=True)
    resolved_url = resolve_package_git_url(url)
    # handles https URLs, scp-style git@host:user/repo.git, and local paths
    cleaned = resolved_url.replace("\\", "/").rstrip("/").removesuffix(".git")
    name = cleaned.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if not name:
        return {"ok": False, "package": None, "error": f"Could not derive a folder name from '{url}'"}
    dest = target_root / name
    if dest.exists():
        return {"ok": False, "package": None, "error": f"{dest} already exists"}

    source_label = resolved_url if resolved_url == url else f"{url} ({resolved_url})"
    progress(f"Cloning {source_label} -> {dest}")
    clone = subprocess.run(["git", "clone", "--depth", "1", resolved_url, str(dest)], capture_output=True, text=True)
    if clone.returncode != 0:
        return {"ok": False, "package": None, "error": clone.stderr.strip() or "git clone failed"}
    if not (dest / MANIFEST_NAME).exists():
        _rmtree_force(dest)
        return {"ok": False, "package": None, "error": f"Repository has no {MANIFEST_NAME}; not a Blacknode package"}

    if install_deps:
        install_prerequisites(dest, progress=progress)
    info = load_package(dest)
    if info.ok:
        write_package_lock(target_root)
        progress(f"Installed {info.name} {info.version}: {len(info.node_types)} nodes")
        return {"ok": True, "package": info.to_dict(), "error": ""}
    return {"ok": False, "package": info.to_dict(), "error": info.error}


def install_prerequisites(pkg_dir: str | Path, progress: Callable[[str], None] = print) -> list[str]:
    """Install a package's pip requirements and pull its declared Docker
    images. Returns warning strings; never raises."""
    pkg_path = Path(pkg_dir).expanduser().resolve()
    warnings: list[str] = []
    info = load_package(pkg_path)

    requirements = pkg_path / "requirements.txt"
    install_args: list[str] = []
    sources: list[str] = []
    if requirements.is_file():
        install_args.extend(["-r", str(requirements)])
        sources.append(str(requirements))
    if info.pip_dependencies:
        install_args.extend(info.pip_dependencies)
        sources.append("enabled manifest dependencies")
    if install_args:
        progress(f"Installing pip dependencies from {' and '.join(sources)}")
        pip = subprocess.run([sys.executable, "-m", "pip", "install", *install_args])
        if pip.returncode != 0:
            warnings.append("pip install failed; the package may not load until deps are installed")

    setup_script = pkg_path / "scripts" / "setup.sh"
    if setup_script.exists():
        progress(f"Running package setup script {setup_script}")
        setup = subprocess.run(["bash", str(setup_script)], cwd=str(pkg_path))
        if setup.returncode != 0:
            warnings.append(f"package setup script failed; rerun with: bash {setup_script}")

    info = load_package(pkg_path)
    for image in info.docker_images:
        if not shutil.which("docker"):
            warnings.append(f"package wants Docker image '{image}' but docker is not on PATH")
            break
        progress(f"Pulling Docker image {image}")
        pull = subprocess.run(["docker", "pull", image])
        if pull.returncode != 0:
            warnings.append(f"could not pull {image} (is Docker running?); pull it later with: docker pull {image}")
    for warning in warnings:
        progress(f"warning: {warning}")
    return warnings


def remove_package(name: str, root: str | Path | None = None) -> dict[str, Any]:
    """Delete a folder package and deregister its nodes. Returns {ok, error}."""
    info = _PACKAGE_REGISTRY.get(name)
    if info is None:
        return {"ok": False, "error": f"No package named '{name}' is installed"}
    if info.source != "folder":
        return {"ok": False, "error": f"'{name}' was installed via pip; remove it with: pip uninstall {name}"}

    dependents = _enabled_package_dependents(name)
    if dependents:
        return {
            "ok": False,
            "error": f"Cannot remove {name}; required by enabled components: {', '.join(dependents)}",
        }

    path = Path(info.path).resolve()
    allowed_roots = [Path(root).expanduser().resolve()] if root else [Path(p).resolve() for p in default_package_dirs()]
    if not any(allowed in path.parents for allowed in allowed_roots):
        return {"ok": False, "error": f"{path} is outside the packages folders; delete it manually"}
    if not (path / MANIFEST_NAME).exists():
        return {"ok": False, "error": f"{path} does not look like a package (no {MANIFEST_NAME}); delete it manually"}

    try:
        _rmtree_force(path)
    except Exception as exc:
        return {"ok": False, "error": f"Could not delete {path}: {exc}"}

    _deregister_package_nodes(name)
    _clear_package_modules(_safe_module_name(name))
    _remove_package_component_state(path, name)
    del _PACKAGE_REGISTRY[name]
    write_package_lock(path.parent)
    return {"ok": True, "error": ""}


def _remove_package_component_state(pkg_path: Path, package_name: str) -> None:
    state_path = _component_state_path(pkg_path)
    if not state_path.is_file():
        return
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        packages = payload.get("packages", {})
        if not isinstance(packages, dict) or package_name not in packages:
            return
        packages.pop(package_name, None)
        temporary = state_path.with_suffix(state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(state_path)
    except Exception:
        # Package deletion succeeded; stale preferences must not make deletion fail.
        return


def _rmtree_force(path: Path) -> None:
    """rmtree that clears read-only flags (git objects on Windows)."""
    def _onerror(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda func, target, _exc: _onerror(func, target, None))
    else:
        shutil.rmtree(path, onerror=_onerror)


def _is_explicit_git_source(value: str) -> bool:
    if "://" in value or _SCP_GIT_URL_RE.match(value):
        return True
    if value.startswith(("/", "./", "../", "~")):
        return True
    return Path(value).expanduser().exists()


def _repo_origin_url() -> str:
    if not shutil.which("git"):
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _package_git_base_from_url(url: str) -> str:
    value = url.strip().rstrip("/").removesuffix(".git")
    if not value:
        return ""
    if _SCP_GIT_URL_RE.match(value):
        return value.rsplit("/", 1)[0] if "/" in value else ""
    if "://" in value:
        base, separator, _repo = value.rpartition("/")
        return base if separator else ""
    return ""


def _join_git_base(base: str, package: str) -> str:
    clean_base = base.strip().rstrip("/")
    clean_package = package.strip().strip("/").removesuffix(".git")
    if not clean_base or not clean_package:
        return package
    return f"{clean_base}/{clean_package}.git"


def _version_constraint_satisfied(spec: str, current: str) -> bool:
    """Evaluate a comma-separated numeric version constraint strictly."""
    have = _version_tuple(current)
    if have is None:
        raise ValueError(f"invalid installed version '{current}'")
    clauses = [clause.strip() for clause in str(spec or "").split(",") if clause.strip()]
    for clause in clauses:
        match = re.fullmatch(r"(>=|<=|==|>|<)?\s*(\d+(?:\.\d+)*)", clause)
        if not match:
            raise ValueError(f"unsupported version constraint '{clause}'")
        operator = match.group(1) or "=="
        want = _version_tuple(match.group(2))
        if want is None:
            raise ValueError(f"invalid required version '{match.group(2)}'")
        width = max(len(have), len(want))
        comparable_have = have + (0,) * (width - len(have))
        comparable_want = want + (0,) * (width - len(want))
        satisfied = {
            "==": comparable_have == comparable_want,
            ">=": comparable_have >= comparable_want,
            "<=": comparable_have <= comparable_want,
            ">": comparable_have > comparable_want,
            "<": comparable_have < comparable_want,
        }[operator]
        if not satisfied:
            return False
    return True


def _version_satisfied(spec: str, current: str) -> bool:
    spec = spec.strip()
    op = ">="
    for candidate in (">=", "==", ">"):
        if spec.startswith(candidate):
            op = candidate
            spec = spec[len(candidate):]
            break
    want = _version_tuple(spec)
    have = _version_tuple(current)
    if want is None or have is None:
        return True  # unparseable constraint: report nothing, do not block loading
    if op == "==":
        return have == want
    if op == ">":
        return have > want
    return have >= want


def _version_tuple(raw: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in raw.strip().split("."))
    except ValueError:
        return None


__all__ = [
    "ENTRY_POINT_GROUP",
    "MANIFEST_NAME",
    "PackageInfo",
    "component_dependency_plan",
    "default_package_dirs",
    "default_package_git_base",
    "discover_packages",
    "install_from_git",
    "install_prerequisites",
    "install_missing_python_dependencies",
    "installed_packages",
    "package_git_status",
    "package_statuses",
    "load_package",
    "package_category_colors",
    "package_template_dirs",
    "packages_root",
    "remove_package",
    "set_component_enabled",
    "update_packages",
    "resolve_package_git_url",
]
