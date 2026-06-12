"""Extension package discovery: folder packages register nodes, gate on the
core version, and report failures without breaking startup."""
import textwrap

import pytest

import blacknode  # noqa: F401  triggers built-in + package discovery
from blacknode.node import _NODE_REGISTRY
from blacknode.packages import _PACKAGE_REGISTRY, discover_packages, load_package


def _write_package(tmp_path, name="bn-test-pkg", node_name="_PkgProbe", requires=""):
    pkg = tmp_path / name
    (pkg / "nodes").mkdir(parents=True)
    requires_line = f'requires-blacknode = "{requires}"' if requires else ""
    (pkg / "blacknode-package.toml").write_text(textwrap.dedent(f"""
        [package]
        name = "{name}"
        version = "0.0.1"
        description = "test package"
        {requires_line}

        [categories]
        "Test Pkg" = "#123456"
    """), encoding="utf-8")
    (pkg / "nodes" / "probe.py").write_text(textwrap.dedent(f"""
        from blacknode.node import Text, node


        @node(name="{node_name}", category="Test Pkg", inputs={{"text": Text}}, outputs={{"out": Text}})
        def probe(text: str) -> str:
            return text
    """), encoding="utf-8")
    return pkg


def test_folder_package_registers_nodes(tmp_path):
    _write_package(tmp_path)
    report = discover_packages([tmp_path])
    loaded = {p["name"]: p for p in report["loaded"]}
    assert "bn-test-pkg" in loaded
    assert "_PkgProbe" in loaded["bn-test-pkg"]["node_types"]
    assert "_PkgProbe" in _NODE_REGISTRY
    assert _NODE_REGISTRY["_PkgProbe"]._bn_package == "bn-test-pkg"
    assert _PACKAGE_REGISTRY["bn-test-pkg"].categories["Test Pkg"] == "#123456"
    # node runs through the registry like any built-in
    assert _NODE_REGISTRY["_PkgProbe"]({"text": "hi"}) == {"out": "hi"}


def test_version_gate_blocks_load(tmp_path):
    _write_package(tmp_path, name="bn-too-new", node_name="_PkgTooNew", requires=">=99.0.0")
    report = discover_packages([tmp_path])
    failed = {p["name"]: p for p in report["failed"]}
    assert "bn-too-new" in failed
    assert "Requires blacknode" in failed["bn-too-new"]["error"]
    assert "_PkgTooNew" not in _NODE_REGISTRY


def test_broken_package_reports_error_without_raising(tmp_path):
    pkg = _write_package(tmp_path, name="bn-broken", node_name="_PkgBroken")
    (pkg / "nodes" / "probe.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    info = load_package(pkg)
    assert not info.ok
    assert "boom" in info.error


def test_reload_reregisters_nodes(tmp_path):
    pkg = _write_package(tmp_path, name="bn-reload", node_name="_PkgReload")
    assert "_PkgReload" in load_package(pkg).node_types
    # a reload must re-execute the modules and report the same node types
    assert "_PkgReload" in load_package(pkg).node_types


def test_blacknode_cuda_loads_as_package():
    if "blacknode-cuda" not in _PACKAGE_REGISTRY:
        pytest.skip("blacknode-cuda not installed (it lives in its own repo)")
    assert "CUDAKernelLab" in _NODE_REGISTRY
    assert getattr(_NODE_REGISTRY["CUDAKernelLab"], "_bn_package", "") == "blacknode-cuda"
    info = _PACKAGE_REGISTRY["blacknode-cuda"]
    assert info.ok
    assert info.categories.get("NVIDIA GPU")
    assert info.templates_dir
    # stable import alias for tests and user code
    from blacknode.pkg.blacknode_cuda import cuda  # noqa: F401
