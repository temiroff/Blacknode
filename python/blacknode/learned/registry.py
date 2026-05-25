from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..node import _NODE_REGISTRY, node
from ..sandbox import docker_runner
from .manifest import LearnedNodeManifest, ManifestValidationError, load_manifest


LOGGER = logging.getLogger(__name__)

LEARNED_NODE_MANIFESTS: dict[str, LearnedNodeManifest] = {}
LEARNED_NODE_DIRS: dict[str, Path] = {}


@dataclass
class LearnedLoadReport:
    loaded: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.loaded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loaded": list(self.loaded),
            "skipped": dict(self.skipped),
            "count": self.count,
        }


def learned_dir() -> Path:
    configured = os.environ.get("BLACKNODE_LEARNED_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _repo_root() / "nodes" / "learned"


def load_all(root: str | Path | None = None) -> LearnedLoadReport:
    base = Path(root).resolve() if root is not None else learned_dir()
    report = LearnedLoadReport()
    if not base.exists():
        return report

    for manifest_path in sorted(base.glob("*/manifest.json")):
        name = manifest_path.parent.name
        try:
            register_one(name, learned_dir=base)
        except Exception as exc:
            report.skipped[name] = str(exc)
            LOGGER.warning("Skipping learned node %s: %s", name, exc)
        else:
            report.loaded.append(name)
    return report


def sync_with_disk(root: str | Path | None = None) -> LearnedLoadReport:
    """Reconcile in-memory learned nodes with the learned-node directory.

    The editor backend and MCP server often run as separate processes. A learned
    node may be deleted from disk by one process while another still has the
    wrapper registered in memory. Disk is the source of truth, so stale learned
    wrappers are removed before valid manifests are loaded again.
    """
    base = Path(root).resolve() if root is not None else learned_dir()
    for name, fn in list(_NODE_REGISTRY.items()):
        if getattr(fn, "_bn_source", None) != "learned":
            continue
        source_raw = getattr(fn, "_bn_source_path", "")
        manifest_raw = getattr(fn, "_bn_manifest_path", "")
        source_path = Path(source_raw).resolve() if source_raw else None
        manifest_path = Path(manifest_raw).resolve() if manifest_raw else None
        if (
            source_path is None
            or manifest_path is None
            or not _is_relative_to(source_path, base)
            or not _is_relative_to(manifest_path, base)
            or not source_path.is_file()
            or not manifest_path.is_file()
        ):
            unregister_one(name)
    return load_all(base)


def register_one(name: str, *, learned_dir: str | Path | None = None) -> LearnedNodeManifest:
    base = Path(learned_dir).resolve() if learned_dir is not None else globals()["learned_dir"]()
    node_dir = base / name
    manifest_path = node_dir / "manifest.json"
    source_path = node_dir / "node.py"

    manifest = load_manifest(manifest_path)
    if manifest.name != name:
        raise ManifestValidationError(
            f"{manifest_path}: manifest name '{manifest.name}' must match directory '{name}'"
        )
    if not source_path.is_file():
        raise ManifestValidationError(f"{source_path}: learned node source file is required")

    existing = _NODE_REGISTRY.get(manifest.name)
    if existing is not None and getattr(existing, "_bn_source", None) != "learned":
        raise ManifestValidationError(
            f"{manifest.name}: learned node cannot replace built-in node type"
        )

    wrapper = _make_learned_wrapper(manifest, source_path)
    node(
        inputs=list(manifest.inputs),
        outputs=list(manifest.outputs),
        name=manifest.name,
        category=manifest.category,
        description=manifest.description,
    )(wrapper)

    registered = _NODE_REGISTRY[manifest.name]
    registered._bn_source = "learned"
    registered._bn_source_path = str(source_path.resolve())
    registered._bn_manifest_path = str(manifest_path.resolve())
    registered._bn_permissions = dict(manifest.permissions)

    LEARNED_NODE_MANIFESTS[manifest.name] = manifest
    LEARNED_NODE_DIRS[manifest.name] = node_dir.resolve()
    return manifest


def unregister_one(name: str) -> bool:
    existing = _NODE_REGISTRY.get(name)
    if existing is None or getattr(existing, "_bn_source", None) != "learned":
        return False
    _NODE_REGISTRY.pop(name, None)
    LEARNED_NODE_MANIFESTS.pop(name, None)
    LEARNED_NODE_DIRS.pop(name, None)
    return True


def _make_learned_wrapper(manifest: LearnedNodeManifest, source_path: Path):
    def _wrapper(ctx: dict) -> dict[str, Any]:
        return _learned_node_impl(ctx, manifest=manifest, source_path=source_path)

    _wrapper.__name__ = manifest.name
    return _wrapper


def _learned_node_impl(
    ctx: dict,
    *,
    manifest: LearnedNodeManifest,
    source_path: Path,
) -> dict[str, Any]:
    inputs = {
        name: ctx[name]
        for name in manifest.input_names
        if name in ctx
    }
    code = source_path.read_text(encoding="utf-8")
    return docker_runner.run_in_container(
        code=code,
        inputs=inputs,
        permissions=manifest.permissions,
        node_name=manifest.name,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
