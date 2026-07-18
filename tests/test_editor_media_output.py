from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generic_output_renders_typed_images_and_video_instead_of_urls() -> None:
    source = (ROOT / "editor" / "src" / "components" / "OutputNode.tsx").read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "sourceType === 'Image'" in source
    assert "sourceType === 'Video'" in source
    assert "<img" in source
    assert "<video" in source
    assert "data:image/" in source
    assert "data:video/" in source
    assert "sourceType === 'Image' || sourceType === 'Video'" in source
    assert "hasVisualMediaInput ? 860 : 240" in source
    assert "hasVisualMediaInput ? 720 : 120" in source
    assert "MEDIA_OUTPUT_NODE_SIZE = { width: 860, height: 720 }" in store
    assert "MEDIA_OUTPUT_TYPES = new Set(['Image', 'Video'])" in store
    assert "ensureMediaOutputNodeSizes(nodes, edges)" in store


def test_generic_output_converts_legacy_raw_svg_images_to_data_urls() -> None:
    source = (ROOT / "editor" / "src" / "components" / "OutputNode.tsx").read_text(encoding="utf-8")

    assert "svg.startsWith('<svg')" in source
    assert "svg.endsWith('</svg>')" in source
    assert "data:image/svg+xml;charset=utf-8," in source
    assert "encodeURIComponent(svg)" in source


def test_inline_node_dashboard_converts_legacy_raw_svg_images() -> None:
    source = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")

    assert "const normalizedImageSrc" in source
    assert "normalizedImageSrc(data.portResults?.[port]) !== null" in source
    assert "data:image/svg+xml;charset=utf-8," in source


def test_public_camera_is_treated_as_a_live_stream_node() -> None:
    black_node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "'Camera'," in black_node
    assert "data.type === 'Camera'" in store
    assert "n.data.type === 'Camera'" in store


def test_episode_recorder_has_direct_lifecycle_controls_and_live_status() -> None:
    black_node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "data.type === 'EpisodeRecorder'" in black_node
    for label in ("● Record", "Ⅱ Pause", "▶ Resume", "✓ Save episode", "■ Stop", "Discard"):
        assert label in black_node
    assert "await updateParam(id, 'action', 'status')" in black_node
    assert "Object.values(status.modules ?? {})" in store


def test_live_nodes_distinguish_blocked_waiting_and_snapshot_states() -> None:
    black_node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "const liveBlocked =" in black_node
    assert "const liveWaiting =" in black_node
    assert "BLOCKED" in black_node
    assert "LIVE • WAITING" in black_node
    assert "&& !liveBlocked" in black_node
    assert "&& !liveWaiting" in black_node
    assert "blockedControllerCount" in app
    assert "waitingControllerCount" in app


def test_dataset_replay_switches_units_and_keeps_canvas_wheel_zoom() -> None:
    browser = (ROOT / "editor" / "src" / "components" / "DatasetBrowserPanel.tsx").read_text(encoding="utf-8")
    output = (ROOT / "editor" / "src" / "components" / "OutputNode.tsx").read_text(encoding="utf-8")
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "setAngleUnit('radians')" in browser
    assert "setAngleUnit('degrees')" in browser
    assert "numeric * 180 / Math.PI" in browser
    assert "numeric * Math.PI / 180" in browser
    assert 'className="nodrag"' in browser
    assert 'className="nodrag nowheel"' not in browser
    assert 'className="nodrag nowheel bn-output-scroll"' not in output
    assert "✂ Cut before" in browser
    assert "✂ Cut after" in browser
    assert "The selected frame is kept" in browser
    assert "trimDatasetEpisode" in api
