"""Extension package discovery: folder packages register nodes, gate on the
core version, and report failures without breaking startup."""
import json
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

import blacknode  # noqa: F401  triggers built-in + package discovery
from blacknode.node import _NODE_REGISTRY
from blacknode.packages import (
    _PACKAGE_REGISTRY,
    adapter_dependency_plan,
    component_dependency_plan,
    component_dependency_install_plan,
    discover_packages,
    ensure_component_enabled,
    install_from_git,
    install_prerequisites,
    load_package,
    package_template_dirs,
    remove_package,
    reset_component,
    set_component_enabled,
    set_adapter_enabled,
    validate_package_catalog,
    write_package_lock,
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


def _write_adapter_node(pkg, component, adapter, node_name):
    nodes = pkg / "components" / component / "adapters" / adapter / "nodes"
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


def test_component_reset_restores_manifest_default(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-component-reset",
        component_metadata='''
        [components.optional]
        default = false
        nodes = ["components/optional/nodes"]
        ''',
    )
    _write_component_node(pkg, "optional", "_PkgComponentReset")
    load_package(pkg)

    enabled = set_component_enabled("bn-component-reset", "optional", True)
    assert enabled.components["optional"]["enabled"] is True
    reset = reset_component("bn-component-reset", "optional")

    assert reset.components["optional"]["enabled"] is False
    state = json.loads((tmp_path / ".blacknode-components.json").read_text(encoding="utf-8"))
    assert "bn-component-reset" not in state["packages"]


def test_enabled_component_owns_templates_and_setup_hooks(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-component-assets",
        component_metadata='''
        [components.camera]
        default = true
        nodes = ["components/camera/nodes"]
        templates = ["components/camera/templates"]
        setup-hooks = ["components/camera/scripts/setup.py"]
        ''',
    )
    _write_component_node(pkg, "camera", "_PkgComponentAssets")
    templates = pkg / "components" / "camera" / "templates"
    templates.mkdir(parents=True)
    (templates / "camera.json").write_text("{}", encoding="utf-8")
    scripts = pkg / "components" / "camera" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "setup.py").write_text(
        "from pathlib import Path\nPath('component-hook-ran').write_text('yes')\n",
        encoding="utf-8",
    )

    info = load_package(pkg)
    assert str(templates.resolve()) in info.template_dirs
    assert str(templates.resolve()) in package_template_dirs()
    assert info.setup_hooks == ["components/camera/scripts/setup.py"]

    assert install_prerequisites(pkg) == []
    assert (pkg / "component-hook-ran").read_text(encoding="utf-8") == "yes"


def test_catalog_validation_detects_component_node_drift(tmp_path, monkeypatch):
    import blacknode.packages as packages_module

    pkg = _write_package(
        tmp_path,
        name="bn-catalog-check",
        package_metadata='layer = "drivers"',
        component_metadata='''
        [components.bus]
        default = true
        nodes = ["components/bus/nodes"]
        node-types = ["_PkgCatalogActual"]
        ''',
    )
    _write_component_node(pkg, "bus", "_PkgCatalogActual")
    monkeypatch.setattr(packages_module, "indexed_package", lambda _name: {
        "name": "bn-catalog-check",
        "layer": "drivers",
        "components": {"bus": {"default": True, "node_types": ["_PkgCatalogExpected"]}},
        "node_types": ["_PkgCatalogExpected"],
    })

    errors = validate_package_catalog(pkg)
    assert any("component bus node-types differ" in error for error in errors)
    assert any("package node-types differ" in error for error in errors)


def test_component_can_preserve_legacy_package_module_root(tmp_path):
    pkg = _write_package(
        tmp_path,
        name="bn-root-mounted",
        node_name="_PkgRootIgnored",
        component_metadata='''
        [components.core]
        default = true
        nodes = ["components/core/nodes"]
        module-root = true
        ''',
    )
    _write_component_node(pkg, "core", "_PkgRootMounted")

    info = load_package(pkg)

    assert info.ok
    assert info.components["core"]["module_root"] is True
    assert "blacknode.pkg.bn_root_mounted.probe" in sys.modules
    assert _NODE_REGISTRY["_PkgRootMounted"]._bn_component == "core"


def test_component_owns_optional_nested_adapter(tmp_path):
    dependency = _write_package(
        tmp_path,
        name="bn-adapter-dependency",
        component_metadata='''
        [components.core]
        default = true
        nodes = ["components/core/nodes"]
        ''',
    )
    _write_component_node(dependency, "core", "_AdapterDependencyCore")
    owner = _write_package(
        tmp_path,
        name="bn-adapter-owner",
        component_metadata='''
        [components.feetech]
        default = true
        nodes = ["components/feetech/nodes"]

        [components.feetech.adapters.ros2]
        default = false
        nodes = ["components/feetech/adapters/ros2/nodes"]

        [components.feetech.adapters.ros2.dependencies]
        requires = [{ package = "bn-adapter-dependency", component = "core", version = ">=0.0.1" }]
        ''',
    )
    _write_component_node(owner, "feetech", "_AdapterOwnerFeetech")
    _write_adapter_node(owner, "feetech", "ros2", "_AdapterOwnerROS2")
    assert load_package(dependency).ok
    info = load_package(owner)
    assert info.ok
    assert set(info.components) == {"feetech"}
    assert info.components["feetech"]["adapters"]["ros2"]["enabled"] is False
    assert "_AdapterOwnerROS2" not in _NODE_REGISTRY

    plan = adapter_dependency_plan("bn-adapter-owner", "feetech", "ros2")
    assert plan["target"] == {
        "package": "bn-adapter-owner", "component": "feetech", "adapter": "ros2"
    }
    enabled = set_adapter_enabled("bn-adapter-owner", "feetech", "ros2", True)

    assert enabled.enabled_components == ["feetech"]
    assert enabled.enabled_adapters == ["feetech/ros2"]
    assert _NODE_REGISTRY["_AdapterOwnerROS2"]._bn_component == "feetech"
    assert _NODE_REGISTRY["_AdapterOwnerROS2"]._bn_adapter == "ros2"
    assert "blacknode.pkg.bn_adapter_owner.feetech.adapters.ros2.probe" in sys.modules
    lock = json.loads((tmp_path / ".blacknode-package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["bn-adapter-owner"]["enabled_components"] == ["feetech"]
    assert lock["packages"]["bn-adapter-owner"]["enabled_adapters"] == ["feetech/ros2"]
    with pytest.raises(ValueError, match="adapter ros2"):
        set_component_enabled("bn-adapter-owner", "feetech", False)

    disabled = set_adapter_enabled("bn-adapter-owner", "feetech", "ros2", False)
    assert disabled.enabled_adapters == []
    assert "_AdapterOwnerROS2" not in _NODE_REGISTRY


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


def test_ensure_component_installs_official_missing_dependency(tmp_path, monkeypatch):
    source = _write_package(
        tmp_path / "sources",
        name="bn-auto-dependency",
        node_name="_AutoDependencyRoot",
        component_metadata='''
        [components.base]
        default = false
        nodes = ["components/base/nodes"]
        ''',
    )
    _write_component_node(source, "base", "_AutoDependencyBase")
    git = ["git", "-C", str(source), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git[:3], "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)

    target = _write_package(
        tmp_path / "installed",
        name="bn-auto-target",
        node_name="_AutoTargetRoot",
        component_metadata='''
        [components.adapter]
        default = false
        nodes = ["components/adapter/nodes"]
        [components.adapter.dependencies]
        requires = [{ package = "bn-auto-dependency", component = "base", version = ">=0.0.1" }]
        ''',
    )
    _write_component_node(target, "adapter", "_AutoTargetAdapter")
    assert load_package(target).ok
    monkeypatch.setattr(
        "blacknode.packages.indexed_package",
        lambda name: {"git_url": str(source)} if name == "bn-auto-dependency" else None,
    )

    preflight = component_dependency_install_plan("bn-auto-target", "adapter")
    assert preflight["actions"][0]["action"] == "install"

    enabled = ensure_component_enabled(
        "bn-auto-target", "adapter", progress=lambda _line: None
    )

    assert enabled.enabled_components == ["adapter"]
    assert _PACKAGE_REGISTRY["bn-auto-dependency"].enabled_components == ["base"]
    assert "_AutoDependencyBase" in _NODE_REGISTRY
    assert "_AutoTargetAdapter" in _NODE_REGISTRY


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
    lock = root / ".blacknode-package-lock.json"
    assert lock.is_file()
    assert '"bn-git-pkg"' in lock.read_text(encoding="utf-8")

    # cloning the same package twice is rejected
    again = install_from_git(str(src), root=root, install_deps=False, progress=lambda _line: None)
    assert not again["ok"]
    assert "already exists" in again["error"]

    removed = remove_package("bn-git-pkg", root=root)
    assert removed["ok"], removed["error"]
    assert "_PkgGit" not in _NODE_REGISTRY
    assert "bn-git-pkg" not in _PACKAGE_REGISTRY
    assert not (root / "src").exists()
    assert '"bn-git-pkg"' not in lock.read_text(encoding="utf-8")


def test_remove_blocks_enabled_cross_package_dependents(tmp_path):
    dependency = _write_package(tmp_path, name="bn-remove-dependency", node_name="_RemoveDependency")
    target = _write_package(
        tmp_path,
        name="bn-remove-target",
        node_name="_RemoveTargetRoot",
        component_metadata='''
        [components.adapter]
        default = true
        nodes = ["components/adapter/nodes"]
        [components.adapter.dependencies]
        requires = [{ package = "bn-remove-dependency", version = ">=0.0.1" }]
        ''',
    )
    _write_component_node(target, "adapter", "_RemoveTargetAdapter")
    assert load_package(dependency).ok
    assert load_package(target).ok

    result = remove_package("bn-remove-dependency", root=tmp_path)

    assert not result["ok"]
    assert "required by enabled components: bn-remove-target/adapter" in result["error"]
    assert dependency.exists()


def test_write_package_lock_records_enabled_components(tmp_path):
    package = _write_package(
        tmp_path,
        name="bn-lock-layer",
        component_metadata='''
        [components.core]
        default = true
        nodes = ["components/core/nodes"]
        ''',
    )
    _write_component_node(package, "core", "_LockCore")
    assert load_package(package).ok

    result = write_package_lock(tmp_path)

    assert result["packages"]["bn-lock-layer"]["enabled_components"] == ["core"]
    assert (tmp_path / ".blacknode-package-lock.json").is_file()


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
