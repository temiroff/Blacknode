from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generic_output_renders_typed_images_and_video_instead_of_urls() -> None:
    source = (ROOT / "editor" / "src" / "components" / "OutputNode.tsx").read_text(encoding="utf-8")

    assert "sourceType === 'Image'" in source
    assert "sourceType === 'Video'" in source
    assert "<img" in source
    assert "<video" in source
    assert "data:image/" in source
    assert "data:video/" in source


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
