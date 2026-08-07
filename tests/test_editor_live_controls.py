from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "editor" / "src" / "App.tsx"
API = ROOT / "editor" / "src" / "api.ts"
STORE = ROOT / "editor" / "src" / "store.ts"


def test_top_live_control_tracks_generic_live_capable_runtime_nodes():
    source = APP.read_text(encoding="utf-8")

    assert "const liveCapableRuntimeCount" in source
    assert "n.data.live_capable === true" in source
    assert "n.data.portResults?.live === true" in source
    assert "n.data.portResults?.running === true" in source
    assert "n.data.portResults?.streaming === true" in source
    assert "n.data.portResults?.launched === true" in source
    assert "const runtimeActive = liveCapableRuntimeCount > 0" in source


def test_stop_live_request_has_a_bounded_browser_wait():
    source = API.read_text(encoding="utf-8")

    assert "stopRuntime: () => req<RuntimeStopResult>('POST', '/runtime/stop', undefined, 15000)" in source


def test_stop_live_clears_browser_state_before_waiting_for_remote_shutdown():
    app_source = APP.read_text(encoding="utf-8")
    store_source = STORE.read_text(encoding="utf-8")

    handler = app_source.index("const handleStopRuntime = useCallback")
    clear_mode = app_source.index("setActiveRunMode(null)", handler)
    pending = app_source.index("setRuntimeStopPending(true)", handler)
    clear_state = store_source.index("Stop requested; clearing live state")
    stop_request = store_source.index("result = await api.stopRuntime()", clear_state)

    assert clear_mode < pending
    assert clear_state < stop_request


def test_stop_live_cannot_be_reactivated_by_a_stale_runtime_status_poll():
    source = STORE.read_text(encoding="utf-8")

    assert "let runtimeOutputsPollInFlight = false" in source
    assert "let runtimeOutputsEpoch = 0" in source
    assert "if (runtimeOutputsPollInFlight || runtimeStopInFlight) return" in source
    assert "const requestEpoch = runtimeOutputsEpoch" in source
    assert "if (requestEpoch !== runtimeOutputsEpoch) return" in source
    assert "runtimeOutputsEpoch += 1" in source
    assert "runtimeOutputsPollInFlight = false" in source


def test_spatial_viewer_frames_use_the_fast_cached_runtime_path():
    app_source = APP.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")
    store_source = STORE.read_text(encoding="utf-8")

    assert "'/runtime/spatial-viewers'" in api_source
    assert "setInterval(loadSpatialViewerNodeOutputs, 100)" in app_source
    assert "if (FAST_SPATIAL_VIEWER_TYPES.has(node.data.type)) return node" in store_source
    assert "if (spatialViewerOutputsPollInFlight || runtimeStopInFlight) return" in store_source
    assert "'IMUViewer'," in store_source


def test_stop_live_clears_all_ros2_and_viewer_live_fields_and_stale_frames():
    source = STORE.read_text(encoding="utf-8")

    assert "const stoppedResults = {" in source
    assert "running: false," in source
    assert "live: false," in source
    assert "streaming: false," in source
    assert "launched: false," in source
    assert "scene: undefined," in source
    assert "preview: undefined," in source
    assert "data: clearRuntimeNodeData(node.data)," in source
    assert "node.data.type.startsWith('ROS2')" in source
