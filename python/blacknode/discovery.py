from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from .node import _NODE_REGISTRY

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_NODE_DIRS = (
    _REPO_ROOT / "custom-nodes",
    _REPO_ROOT / "community-nodes",
    _REPO_ROOT / "nodes",
)


def default_node_dirs() -> list[Path]:
    paths = [path for path in _DEFAULT_NODE_DIRS if path.exists()]
    extra = os.environ.get("BLACKNODE_NODE_PATH", "")
    for raw in extra.split(os.pathsep):
        if raw.strip():
            paths.append(Path(raw).expanduser())
    return paths


def discover_node_modules(paths: list[str | Path] | None = None) -> dict[str, Any]:
    loaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for root in paths or default_node_dirs():
        root_path = Path(root).expanduser()
        if not root_path.exists():
            continue
        for path in sorted(root_path.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            result = load_node_file(path)
            if result["ok"]:
                loaded.append(result)
            else:
                failed.append(result)
    return {"loaded": loaded, "failed": failed}


def load_node_file(path: str | Path) -> dict[str, Any]:
    node_path = Path(path).expanduser().resolve()
    before = dict(_NODE_REGISTRY)
    module_name = _module_name(node_path)
    try:
        spec = importlib.util.spec_from_file_location(module_name, node_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load Python module from {node_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception:
        return {"ok": False, "path": str(node_path), "error": traceback.format_exc(), "new_types": []}

    new_types = [
        name
        for name, fn in sorted(_NODE_REGISTRY.items())
        if before.get(name) is not fn
    ]
    for name in new_types:
        fn = _NODE_REGISTRY[name]
        fn._bn_source_path = str(node_path)
        if not getattr(fn, "_bn_category", None):
            fn._bn_category = _category_for_path(node_path)
    return {"ok": True, "path": str(node_path), "new_types": new_types}


def _module_name(path: Path) -> str:
    stem = "_".join(part for part in path.with_suffix("").parts[-4:] if part)
    token = abs(hash((str(path), path.stat().st_mtime_ns)))
    return f"blacknode_discovered_{stem}_{token}"


def _category_for_path(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "community-nodes" in parts:
        return "Community"
    if "custom-nodes" in parts:
        return "Custom"
    return "Custom"
