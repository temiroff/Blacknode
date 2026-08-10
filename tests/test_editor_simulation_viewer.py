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
    assert "Open scene…" in viewer
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
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    node = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")

    assert "record.runtime === 'newton'" in store
    assert "viewer_url: String(managedRun.viewer_url ?? '')" in store
    assert "viewer_running: managedRun.viewer_running === true" in store
    assert "data.type === 'PPOTraining'" in store
    assert "node.data.type !== 'NewtonSimulation'" in store
    assert "viewer_url: ''" in store
    assert "status.viewer_running === true" in app
    assert "↻ Replay checkpoint" in node
    assert "Close viewer" in node
    assert "controlNode(id, 'close-viewer')" in node


def test_open_newton_scene_uses_the_in_editor_file_browser():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    picker = (
        ROOT / "editor" / "src" / "components" / "LocalFilePicker.tsx"
    ).read_text(encoding="utf-8")
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "<LocalFilePicker" in app
    assert "handleUsdSelected" in app
    assert "api.controlNewtonWorkspace('open_asset'" in app
    assert "xacro_environment: xacroEnvironment" in app
    assert "Xacro configuration required" in app
    assert "missingXacroEnvironmentVariable" in app
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
    assert '_artifact_store.import_value(saved_artifact)' in server
    runtime_path = ROOT / "packages" / "blacknode-newton" / "nodes" / "runtime.py"
    if not runtime_path.is_file():
        return
    runtime = runtime_path.read_text(encoding="utf-8")
    assert "def control_workspace(" in runtime
    assert "def make_empty_scene_spec(" in runtime
    assert 'WORKSPACE_RUN_ID = "__blacknode_newton_workspace__"' in runtime


def test_robot_monitor_reuses_its_calibrated_stream_for_newton():
    monitor = (
        ROOT / "editor" / "src" / "components" / "RobotMonitorNode.tsx"
    ).read_text(encoding="utf-8")
    stream = (ROOT / "editor" / "src" / "robotTelemetryStream.ts").read_text(
        encoding="utf-8"
    )
    runtime_path = ROOT / "packages" / "blacknode-newton" / "nodes" / "runtime.py"
    runtime = runtime_path.read_text(encoding="utf-8") if runtime_path.is_file() else ""
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "Drive Newton robot" in monitor
    assert "Calibration home" in monitor
    assert "subscribeRobotTelemetry(" in monitor
    assert "start_robot_monitor_follow" in monitor
    assert "robot_monitor_sample" in monitor
    assert "controlNewtonStream" in monitor
    assert "robot_monitor_home" in monitor
    assert "home_positions" in monitor
    assert "newtonHomeBusyRef" in monitor
    assert "home_offset_deg" in api
    assert "NewtonStreamControlStatus" in api
    assert "payload.calibrated !== true" in monitor
    assert "payload.raw_mode === true" in monitor
    assert "stop_robot_monitor_follow" in monitor
    assert "const streams = new Map<string, Stream>()" in stream
    if runtime:
        assert 'if command == "robot_monitor_sample":' in runtime
        assert 'if command == "robot_monitor_home":' in runtime
        assert 'if command == "start_robot_monitor_follow":' in runtime
        assert "_mapped_external_joint_positions(" in runtime
        assert "follow_joint_observation(" in runtime
        assert "_expire_stale_stream_follow(" in runtime


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


def test_newton_workspace_exposes_scene_and_robot_editing_windows():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    viewer = (
        ROOT / "editor" / "src" / "components" / "SimulationViewerPane.tsx"
    ).read_text(encoding="utf-8")
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "Outliner" in viewer
    assert "Robot Controller" in viewer
    assert "Digital Twin" in viewer
    assert "Digital Twin tracking error history" in viewer
    assert "Clear trace" in viewer
    assert "Save trace" in viewer
    assert "Saved tracking runs" in viewer
    assert "load_digital_twin_baseline" in viewer
    assert "Clear baseline" in viewer
    assert "clear_digital_twin_history" in viewer
    assert "clear_digital_twin_history" in app
    assert "clear_digital_twin_history" in api
    assert "Show real-pose ghost" in viewer
    assert "Beside simulation" in viewer
    assert "Overlay simulation" in viewer
    assert "Sync Newton once to real pose" in viewer
    assert "set_digital_twin_ghost" in viewer
    assert "set_digital_twin_ghost" in app
    assert "set_digital_twin_ghost" in api
    assert "sync_digital_twin_pose" in viewer
    assert "sync_digital_twin_pose" in app
    assert "tracking_error" in viewer
    assert "source_latency_seconds" in viewer
    assert "Apply transform" not in viewer
    assert "Apply material" not in viewer
    assert "Apply environment" not in viewer
    assert "Apply drive" not in viewer
    assert "requestSubmit()" in viewer
    assert '<form key={`xform:${selectedItem.path}`} onInput={event => event.currentTarget.requestSubmit()}' in viewer
    assert "onMouseLeave" in viewer
    assert "querySelectorAll('details[open]')" in viewer
    assert "MENU_CLOSE_DELAY_MS = 500" in viewer
    assert "onMouseEnter={cancelMenuClose}" in viewer
    assert "scheduleMenuClose(event.currentTarget)" in viewer
    assert "onClick={closeSiblingMenus}" in viewer
    assert "openMenu !== selectedMenu" in viewer
    assert ".bn-simulation-app-menus details[open]::after" in (
        ROOT / "editor" / "src" / "index.css"
    ).read_text(encoding="utf-8")
    assert "onInput={event => sendTarget" in viewer
    assert "viewerFrameRef" in viewer
    assert "blacknode-newton-selection" in viewer
    assert "blacknode-newton-transform" in viewer
    assert "blacknode-newton-view-state" in viewer
    assert "type: 'blacknode-newton-view', mode" in viewer
    assert "new URL('/api/view', url)" not in viewer
    assert "event.source !== viewerFrameRef.current?.contentWindow" in viewer
    assert "Depth IR" in viewer
    assert "Segments" in viewer
    assert "Composite" in viewer
    assert "changePerceptionMode" in viewer
    assert "beginPanelResize" in viewer
    assert "resizePanelWithKeyboard" in viewer
    assert "bn-simulation-panel-resize is-outliner" in viewer
    assert "bn-simulation-panel-resize is-inspector" in viewer
    assert "Drag to resize Outliner · double-click to reset" in viewer
    assert "Drag to resize Properties · double-click to reset" in viewer
    assert "OUTLINER_WIDTH_STORAGE_KEY" in viewer
    assert "INSPECTOR_WIDTH_STORAGE_KEY" in viewer
    assert "set_visibility" in viewer
    assert "set_render_options" in viewer
    assert "Visual geometry" in viewer
    assert "Collision geometry" in viewer
    assert "All lights" in viewer
    assert "Distant light" in viewer
    assert "Angular size" in viewer
    assert "Enable HDRI light" in viewer
    assert "set_light" in viewer
    assert "set_light" in api
    assert "COL ·" in viewer
    assert "collapsedPaths" in viewer
    assert "bn-simulation-disclosure" in viewer
    assert "aria-expanded" in viewer
    assert viewer.index('className="bn-simulation-disclosure"') < viewer.index('className="bn-simulation-eye"')
    assert "joint_target" in viewer
    assert "set_joint_motion" in viewer
    assert "Drive stiffness" in viewer
    assert "Drive damping" in viewer
    assert "engineeringScale" not in viewer
    assert "committedFormNumber" in viewer
    assert "commitNumberOnEnter" in viewer
    assert 'key={`${joint.name}:drive`}' in viewer
    assert 'name="stiffness" type="text" inputMode="decimal"' in viewer
    assert 'name="max_velocity" type="text" inputMode="decimal"' in viewer
    assert "linearToSrgb" in viewer
    assert "srgbToLinear" in viewer
    assert "Child link" in viewer
    assert "Target speed" in viewer
    assert "requestAnimationFrame" in viewer
    runtime_path = ROOT / "packages" / "blacknode-newton" / "nodes" / "runtime.py"
    if runtime_path.is_file():
        assert "joint_motion_limits" in runtime_path.read_text(encoding="utf-8")
    assert "Arm motion" in viewer
    assert "HDRI_FILE_EXTENSIONS" in app
    assert "NEWTON_SCENE_FILE_EXTENSIONS" in app
    assert "'.urdf'" in app
    assert "'.xacro'" in app
    assert "'.xml'" in app
    assert "'.mjcf'" in app
    assert "Open a USD, URDF, Xacro, or MuJoCo scene in Newton" in app
    assert "controlNewtonWorkspace('open_asset'" in app
    assert "Open scene…" in viewer
    assert "handleHdriSelected" in app
    assert "{ hdri: 'custom', hdri_path: selected }" in app
    assert 'value="custom"' in viewer
    assert "hdri_path: hdri === 'custom' ? environment.hdri_path : ''" in viewer
    assert "HDRI lighting remains active when its background is hidden" in viewer
    assert "Fallback background" in viewer
    assert "does not tint an active HDRI" in viewer
    assert "NewtonSceneItem" in api
    assert "NewtonWorkspaceJoint" in api
    assert "NewtonDigitalTwinStatus" in api
    assert "NewtonDigitalTwinSample" in api
    assert "NewtonDigitalTwinArtifactSummary" in api
