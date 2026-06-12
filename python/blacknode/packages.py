"""Blacknode extension packages.

A package is a folder (usually a separate git repo cloned into ``packages/``)
with a ``blacknode-package.toml`` manifest, a ``nodes/`` directory of ``@node``
modules, and optionally a ``templates/`` directory of workflow JSON files.

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
import os
import sys
import tomllib
import traceback
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ._version import __version__ as _CORE_VERSION
from .node import _NODE_REGISTRY

MANIFEST_NAME = "blacknode-package.toml"
ENTRY_POINT_GROUP = "blacknode.packages"
_PKG_MODULE_ROOT = "blacknode.pkg"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PACKAGE_DIRS = (_REPO_ROOT / "packages",)


@dataclass
class PackageInfo:
    name: str
    version: str = ""
    description: str = ""
    path: str = ""
    source: str = "folder"  # folder | entry-point
    requires_blacknode: str = ""
    categories: dict[str, str] = field(default_factory=dict)  # category -> hex color
    pip_dependencies: list[str] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    templates_dir: str = ""
    ok: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PACKAGE_REGISTRY: dict[str, PackageInfo] = {}


def packages_root() -> Path:
    """The default folder packages are cloned into."""
    return _DEFAULT_PACKAGE_DIRS[0]


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


def discover_packages(paths: list[str | Path] | None = None) -> dict[str, Any]:
    loaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for root in paths or default_package_dirs():
        root_path = Path(root).expanduser()
        if not root_path.exists():
            continue
        for pkg_dir in sorted(root_path.iterdir()):
            if not pkg_dir.is_dir() or not (pkg_dir / MANIFEST_NAME).exists():
                continue
            info = load_package(pkg_dir)
            (loaded if info.ok else failed).append(info.to_dict())
    for info in _load_entry_point_packages():
        (loaded if info.ok else failed).append(info.to_dict())
    return {"loaded": loaded, "failed": failed}


def load_package(pkg_dir: str | Path) -> PackageInfo:
    pkg_path = Path(pkg_dir).expanduser().resolve()
    info = PackageInfo(name=pkg_path.name, path=str(pkg_path))
    try:
        manifest = tomllib.loads((pkg_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    except Exception:
        return _record_failure(info, f"Could not parse {MANIFEST_NAME}:\n{traceback.format_exc()}")

    meta = manifest.get("package", {}) or {}
    info.name = str(meta.get("name") or pkg_path.name)
    info.version = str(meta.get("version", ""))
    info.description = str(meta.get("description", ""))
    info.requires_blacknode = str(meta.get("requires-blacknode", ""))
    info.categories = {str(k): str(v) for k, v in (manifest.get("categories", {}) or {}).items()}
    deps = manifest.get("dependencies", {}) or {}
    info.pip_dependencies = [str(d) for d in (deps.get("pip", []) or [])]

    templates_dir = pkg_path / "templates"
    if templates_dir.is_dir():
        info.templates_dir = str(templates_dir)

    if info.requires_blacknode and not _version_satisfied(info.requires_blacknode, _CORE_VERSION):
        return _record_failure(info, f"Requires blacknode {info.requires_blacknode}, this is {_CORE_VERSION}")

    nodes_dir = pkg_path / "nodes"
    if not nodes_dir.is_dir():
        return _record_failure(info, "Package has no nodes/ directory")

    before = dict(_NODE_REGISTRY)
    try:
        _import_nodes_package(_safe_module_name(info.name), nodes_dir)
    except Exception:
        return _record_failure(info, traceback.format_exc())

    info.node_types = sorted(
        name for name, fn in _NODE_REGISTRY.items() if before.get(name) is not fn
    )
    for name in info.node_types:
        fn = _NODE_REGISTRY[name]
        fn._bn_package = info.name
        if not getattr(fn, "_bn_source_path", ""):
            fn._bn_source_path = str(nodes_dir)
    _PACKAGE_REGISTRY[info.name] = info
    return info


def _record_failure(info: PackageInfo, error: str) -> PackageInfo:
    info.ok = False
    info.error = error
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


def _import_nodes_package(snake_name: str, nodes_dir: Path) -> types.ModuleType:
    root = _pkg_root_module()
    module_name = f"{_PKG_MODULE_ROOT}.{snake_name}"
    # Drop any previous load so a reload re-executes the node modules.
    for key in [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]:
        del sys.modules[key]

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
    setattr(root, snake_name, module)

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
        _PACKAGE_REGISTRY[info.name] = info
        infos.append(info)
    return infos


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
    "default_package_dirs",
    "discover_packages",
    "installed_packages",
    "load_package",
    "package_category_colors",
    "package_template_dirs",
    "packages_root",
]
