"""Extension package discovery: folder packages register nodes, gate on the
core version, and report failures without breaking startup."""
import subprocess
import textwrap
from types import SimpleNamespace

import pytest

import blacknode  # noqa: F401  triggers built-in + package discovery
from blacknode.node import _NODE_REGISTRY
from blacknode.packages import (
    _PACKAGE_REGISTRY,
    component_dependency_plan,
    discover_packages,
    install_from_git,
    install_prerequisites,
    load_package,
    remove_package,
    set_component_enabled,
)


def _write_package(
    tmp_path,
    name="bn-test-pkg",
    node_name="_PkgProbe",
    requires="",
    package_metadata="",
    component_metadata="",
):
    pkg = tmp_path / name
    (pkg / "nodes").mkdir(parents=True)
    requires_line = f'requires-blacknode = "{requires}"' if requires else ""
    (pkg / "blacknode-package.toml").write_text(textwrap.dedent(f"""
        [package]
        name = "{name}"
        version = "0.0.1"
        description = "test package"
        {requires_line}
        {package_metadata}

        [categories]
        "Test Pkg" = "#123456"

        {component_metadata}
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


def test_folder_package_exposes_layer_and_component_catalog(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-driver-layer",
        node_name="_PkgDriverLayer",
        package_metadata='layer = "Drivers"',
        component_metadata='''
        [components.feetech]
        description = "Feetech serial-bus adapter"
        default = true
        capabilities = ["robot.joint-driver", "driver.feetech"]
        ''',
    )

    info = load_package(pkg)

    assert info.layer == "drivers"
    component = info.components["feetech"]
    assert component["name"] == "feetech"
    assert component["description"] == "Feetech serial-bus adapter"
    assert component["default"] is True
    assert component["enabled"] is True
    assert component["capabilities"] == ["driver.feetech", "robot.joint-driver"]
    assert component["node_paths"] == []
    assert info.component_mode is False
    assert "_PkgDriverLayer" in info.node_types


def _write_component_node(pkg, component, node_name):
    nodes = pkg / "components" / component / "nodes"
    nodes.mkdir(parents=True)
    (nodes / "probe.py").write_text(textwrap.dedent(f"""
        from blacknode.node import Text, node


        @node(name="{node_name}", category="Test Pkg", inputs={{"text": Text}}, outputs={{"out": Text}})
        def probe(text: str) -> str:
            return text
    """), encoding="utf-8")


def test_component_package_loads_only_enabled_nodes_and_dependencies(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-component-layer",
        node_name="_PkgComponentRootIgnored",
        package_metadata='layer = "Drivers"',
        component_metadata='''
        [components.core]
        description = "Default driver contract"
        default = true
        nodes = ["components/core/nodes"]
        pip = ["core-driver>=1"]
        imports = ["json"]

        [components.optional]
        description = "Optional vendor adapter"
        default = false
        nodes = ["components/optional/nodes"]
        pip = ["optional-driver>=2"]
        docker = ["vendor/driver:latest"]
        ''',
    )
    _write_component_node(pkg, "core", "_PkgComponentCore")
    _write_component_node(pkg, "optional", "_PkgComponentOptional")

    info = load_package(pkg)
    assert info.ok
    assert info.component_mode is True
    assert info.enabled_components == ["core"]
    assert "_PkgComponentCore" in _NODE_REGISTRY
    assert "_PkgComponentOptional" not in _NODE_REGISTRY
    assert "_PkgComponentRootIgnored" not in _NODE_REGISTRY
    assert info.pip_dependencies == ["core-driver>=1"]
    assert info.docker_images == []
    assert _NODE_REGISTRY["_PkgComponentCore"]._bn_component == "core"

    enabled = set_component_enabled("bn-component-layer", "optional", True)
    assert enabled.enabled_components == ["core", "optional"]
    assert "_PkgComponentCore" in _NODE_REGISTRY
    assert "_PkgComponentOptional" in _NODE_REGISTRY
    assert enabled.pip_dependencies == ["core-driver>=1", "optional-driver>=2"]
    assert enabled.docker_images == ["vendor/driver:latest"]
    state = tmp_path / ".blacknode-components.json"
    assert state.is_file()
    assert '"optional": true' in state.read_text(encoding="utf-8")

    disabled = set_component_enabled("bn-component-layer", "optional", False)
    assert disabled.enabled_components == ["core"]
    assert "_PkgComponentOptional" not in _NODE_REGISTRY
    assert "_PkgComponentCore" in _NODE_REGISTRY


def test_component_activation_rejects_paths_outside_package_and_rolls_back(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-component-invalid",
        node_name="_PkgComponentInvalidRoot",
        component_metadata='''
        [components.core]
        default = true
        nodes = ["components/core/nodes"]

        [components.unsafe]
        default = false
        nodes = ["../outside"]
        ''',
    )
    _write_component_node(pkg, "core", "_PkgComponentSafe")
    assert load_package(pkg).ok

    with pytest.raises(RuntimeError, match="escapes the package"):
        set_component_enabled("bn-component-invalid", "unsafe", True)

    restored = _PACKAGE_REGISTRY["bn-component-invalid"]
    assert restored.ok
    assert restored.enabled_components == ["core"]
    assert "_PkgComponentSafe" in _NODE_REGISTRY


def test_component_setup_installs_only_enabled_manifest_dependencies(tmp_path, monkeypatch):
    pkg = _write_package(
        tmp_path,
        name="bn-component-setup",
        node_name="_PkgComponentSetupRoot",
        component_metadata='''
        [components.core]
        default = true
        nodes = ["components/core/nodes"]
        pip = ["core-driver>=1"]

        [components.optional]
        default = false
        nodes = ["components/optional/nodes"]
        pip = ["optional-driver>=2"]
        ''',
    )
    _write_component_node(pkg, "core", "_PkgComponentSetupCore")
    _write_component_node(pkg, "optional", "_PkgComponentSetupOptional")
    (pkg / "requirements.txt").write_text("shared-runtime>=1\n", encoding="utf-8")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    warnings = install_prerequisites(pkg, progress=lambda _line: None)

    assert warnings == []
    assert len(commands) == 1
    command = commands[0]
    assert "-r" in command
    assert "core-driver>=1" in command
    assert "optional-driver>=2" not in command


def test_component_dependency_plan_enables_installed_dependencies_in_order(tmp_path):
    dependency = _write_package(
        tmp_path,
        name="bn-dependency-layer",
        node_name="_PkgDependencyRoot",
        component_metadata='''
        [components.base]
        default = false
        nodes = ["components/base/nodes"]
        ''',
    )
    _write_component_node(dependency, "base", "_PkgDependencyBase")
    target = _write_package(
        tmp_path,
        name="bn-dependent-layer",
        node_name="_PkgDependentRoot",
        component_metadata='''
        [components.adapter]
        default = false
        nodes = ["components/adapter/nodes"]

        [components.adapter.dependencies]
        requires = [
          { package = "bn-dependency-layer", component = "base", version = ">=0.0.1,<1.0.0" }
        ]
        ''',
    )
    _write_component_node(target, "adapter", "_PkgDependentAdapter")
    assert load_package(dependency).ok
    assert load_package(target).ok

    resolution = component_dependency_plan("bn-dependent-layer", "adapter")

    assert [
        (item["package"], item["component"])
        for item in resolution["plan"]
    ] == [
        ("bn-dependency-layer", "base"),
        ("bn-dependent-layer", "adapter"),
    ]
    assert len(resolution["changes"]) == 2

    enabled = set_component_enabled("bn-dependent-layer", "adapter", True)
    assert enabled.enabled_components == ["adapter"]
    assert _PACKAGE_REGISTRY["bn-dependency-layer"].enabled_components == ["base"]
    assert "_PkgDependencyBase" in _NODE_REGISTRY
    assert "_PkgDependentAdapter" in _NODE_REGISTRY

    with pytest.raises(ValueError, match="required by: bn-dependent-layer/adapter"):
        set_component_enabled("bn-dependency-layer", "base", False)

    set_component_enabled("bn-dependent-layer", "adapter", False)
    dependency_info = set_component_enabled("bn-dependency-layer", "base", False)
    assert dependency_info.enabled_components == []


def test_component_dependency_cycle_and_version_conflict_do_not_change_state(tmp_path):
    cycle = _write_package(
        tmp_path,
        name="bn-cycle-layer",
        node_name="_PkgCycleRoot",
        component_metadata='''
        [components.a]
        default = false
        nodes = ["components/a/nodes"]
        [components.a.dependencies]
        requires = [{ component = "b", version = ">=0.0.1" }]

        [components.b]
        default = false
        nodes = ["components/b/nodes"]
        [components.b.dependencies]
        requires = [{ component = "a", version = ">=0.0.1" }]
        ''',
    )
    _write_component_node(cycle, "a", "_PkgCycleA")
    _write_component_node(cycle, "b", "_PkgCycleB")
    assert load_package(cycle).ok

    with pytest.raises(ValueError, match="dependency cycle"):
        set_component_enabled("bn-cycle-layer", "a", True)
    assert _PACKAGE_REGISTRY["bn-cycle-layer"].enabled_components == []
    assert not (tmp_path / ".blacknode-components.json").exists()

    versioned = _write_package(
        tmp_path,
        name="bn-version-layer",
        node_name="_PkgVersionRoot",
        component_metadata='''
        [components.adapter]
        default = false
        nodes = ["components/adapter/nodes"]
        [components.adapter.dependencies]
        requires = [{ package = "bn-cycle-layer", version = ">=2.0.0" }]
        ''',
    )
    _write_component_node(versioned, "adapter", "_PkgVersionAdapter")
    assert load_package(versioned).ok

    with pytest.raises(ValueError, match="does not satisfy required version"):
        set_component_enabled("bn-version-layer", "adapter", True)
    assert _PACKAGE_REGISTRY["bn-version-layer"].enabled_components == []


def test_component_dependency_activation_rolls_back_every_changed_package(tmp_path):
    dependency = _write_package(
        tmp_path,
        name="bn-rollback-dependency",
        node_name="_PkgRollbackDependencyRoot",
        component_metadata='''
        [components.base]
        default = false
        nodes = ["components/base/nodes"]
        ''',
    )
    _write_component_node(dependency, "base", "_PkgRollbackDependency")
    target = _write_package(
        tmp_path,
        name="bn-rollback-target",
        node_name="_PkgRollbackTargetRoot",
        component_metadata='''
        [components.broken]
        default = false
        nodes = ["components/missing/nodes"]
        [components.broken.dependencies]
        requires = [{ package = "bn-rollback-dependency", component = "base" }]
        ''',
    )
    assert load_package(dependency).ok
    assert load_package(target).ok

    with pytest.raises(RuntimeError, match="Could not activate dependency graph"):
        set_component_enabled("bn-rollback-target", "broken", True)

    assert _PACKAGE_REGISTRY["bn-rollback-dependency"].enabled_components == []
    assert _PACKAGE_REGISTRY["bn-rollback-target"].enabled_components == []
    assert "_PkgRollbackDependency" not in _NODE_REGISTRY


def test_discovery_rejects_inconsistent_persisted_dependency_state(tmp_path):
    dependency = _write_package(
        tmp_path,
        name="bn-audit-dependency",
        node_name="_PkgAuditDependencyRoot",
        component_metadata='''
        [components.base]
        default = false
        nodes = ["components/base/nodes"]
        ''',
    )
    _write_component_node(dependency, "base", "_PkgAuditDependency")
    target = _write_package(
        tmp_path,
        name="bn-audit-target",
        node_name="_PkgAuditTargetRoot",
        component_metadata='''
        [components.adapter]
        default = true
        nodes = ["components/adapter/nodes"]
        [components.adapter.dependencies]
        requires = [{ package = "bn-audit-dependency", component = "base" }]
        ''',
    )
    _write_component_node(target, "adapter", "_PkgAuditTarget")

    report = discover_packages([tmp_path])

    failures = {item["name"]: item for item in report["failed"]}
    assert "bn-audit-target" in failures
    assert "required components are disabled: bn-audit-dependency/base" in failures["bn-audit-target"]["error"]
    assert "_PkgAuditTarget" not in _NODE_REGISTRY
    assert _PACKAGE_REGISTRY["bn-audit-dependency"].ok


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


def test_install_from_git_and_remove(tmp_path):
    # a local git repo stands in for the remote package repository
    src = _write_package(tmp_path / "src", name="bn-git-pkg", node_name="_PkgGit")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git[:3], "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)

    root = tmp_path / "root"
    result = install_from_git(str(src), root=root, install_deps=False, progress=lambda _line: None)
    assert result["ok"], result["error"]
    assert result["package"]["name"] == "bn-git-pkg"
    assert "_PkgGit" in _NODE_REGISTRY

    # cloning the same package twice is rejected
    again = install_from_git(str(src), root=root, install_deps=False, progress=lambda _line: None)
    assert not again["ok"]
    assert "already exists" in again["error"]

    removed = remove_package("bn-git-pkg", root=root)
    assert removed["ok"], removed["error"]
    assert "_PkgGit" not in _NODE_REGISTRY
    assert "bn-git-pkg" not in _PACKAGE_REGISTRY
    assert not (root / "src").exists()


def test_remove_unknown_package_is_structured_error():
    result = remove_package("bn-does-not-exist")
    assert not result["ok"]
    assert "No package named" in result["error"]


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
