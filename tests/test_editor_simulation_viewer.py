from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_newton_viewer_is_embedded_above_the_node_canvas():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    viewer = (
        ROOT / "editor" / "src" / "components" / "SimulationViewerPane.tsx"
    ).read_text(encoding="utf-8")

    viewer_position = app.index("<SimulationViewerPane")
    canvas_position = app.index("<ReactFlow\n")
    assert viewer_position < canvas_position
    assert 'className="bn-workspace-split"' in app
    assert 'className="bn-simulation-viewer-frame"' in viewer
    assert "role=\"separator\"" in viewer
    assert "floating ? onAttach : onDetach" in viewer
    assert "Open Newton" in app
    assert "Open USD…" in viewer
    assert "Float Newton in editor" in app
    assert "Attach Newton above canvas" in app
    assert "New stage" in viewer
    assert "Simulation" in viewer
    assert "Close Newton" in viewer


def test_newton_viewer_floats_inside_editor_without_recreating_its_iframe():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    viewer = (
        ROOT / "editor" / "src" / "components" / "SimulationViewerPane.tsx"
    ).read_text(encoding="utf-8")

    assert "window.open(" not in app
    assert "renderDetachedSimulationViewer" not in app
    assert "activeSimulationViewer && (" in app
    assert "visible={simulationViewerVisible}" in app
    assert "floating={simulationViewerDetached}" in app
    assert "floating ? ' is-floating'" in viewer
    assert "visible ? '' : ' is-hidden'" in viewer
    assert 'key={`${url}:${reloadKey}`}' in viewer
    assert "Resize floating simulation viewer" in viewer


def test_newton_managed_runtime_state_supplies_and_clears_the_viewer_url():
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "record.runtime === 'newton'" in store
    assert "viewer_url: String(managedRun.viewer_url ?? '')" in store
    assert "node.data.type !== 'NewtonSimulation'" in store
    assert "viewer_url: ''" in store


def test_open_usd_uses_the_in_editor_file_browser():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    picker = (
        ROOT / "editor" / "src" / "components" / "LocalFilePicker.tsx"
    ).read_text(encoding="utf-8")
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "<LocalFilePicker" in app
    assert "handleUsdSelected" in app
    assert "api.controlNewtonWorkspace('open_usd'" in app
    assert "updateParam(sceneNode.id, 'asset_path'" not in app
    assert "api.pickFile(" not in app
    assert "api.browseFiles" in picker
    assert "Open file" in picker
    assert "'/filesystem/browse'" in api


def test_newton_workspace_has_node_independent_editor_server_routes():
    server = (ROOT / "editor-server" / "server.py").read_text(encoding="utf-8")

    assert '@app.get("/newton/workspace")' in server
    assert '@app.post("/newton/workspace/{action}")' in server
    assert '"control_workspace"' in server
    runtime_path = ROOT / "packages" / "blacknode-newton" / "nodes" / "runtime.py"
    if not runtime_path.is_file():
        return
    runtime = runtime_path.read_text(encoding="utf-8")
    assert "def control_workspace(" in runtime
    assert "def make_empty_scene_spec(" in runtime
    assert 'WORKSPACE_RUN_ID = "__blacknode_newton_workspace__"' in runtime


def test_newton_workspace_can_switch_to_the_optional_ovrtx_provider():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    css = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")
    assert "Open with OVRT (RTX)" in app
    assert "Use OVRT (RTX) renderer" in app
    assert "available_viewers?.includes('ovrtx')" in app
    assert "controlNewtonWorkspace('set_viewer', { provider: 'ovrtx' })" in app
    assert "simulationViewerMenuOpen && createPortal(" in app
    assert 'className="bn-simulation-viewer-menu-items is-portal"' in app
    assert ".bn-simulation-viewer-menu-items.is-portal" in css
    assert "position: fixed" in css[css.index(".bn-simulation-viewer-menu-items.is-portal"):]
    package_root = ROOT / "packages" / "blacknode-newton"
    runtime_path = package_root / "nodes" / "runtime.py"
    manifest_path = package_root / "blacknode-package.toml"
    if not runtime_path.is_file() or not manifest_path.is_file():
        return
    runtime = runtime_path.read_text(encoding="utf-8")
    manifest = manifest_path.read_text(encoding="utf-8")
    assert 'if command == "set_viewer":' in runtime
    assert '"available_viewers": available_viewers()' in runtime
    assert "[components.viewer-ovrtx]" in manifest
    assert "default = false" in manifest
