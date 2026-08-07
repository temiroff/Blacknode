from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def test_depth_cloud_viewer_exposes_depth_rgb_and_ir_controls():
    viewer = (
        ROOT / "editor" / "src" / "components" / "PointCloudViewer.tsx"
    ).read_text(encoding="utf-8")
    node = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")

    assert "Point color" in viewer
    assert '<option value="depth">Depth</option>' in viewer
    assert '<option value="rgb">RGB</option>' in viewer
    assert '<option value="ir">IR</option>' in viewer
    assert "color_error" in viewer
    assert "using depth color" in viewer
    assert "onDepthColorModeChange" in viewer
    assert "data.type === 'DepthCloudViewer'" in node
    assert "updateParam(id, 'color_mode', mode)" in node


def test_depth_cloud_color_mode_is_pushed_to_the_live_viewer():
    import sys

    editor_server = ROOT / "editor-server"
    if str(editor_server) not in sys.path:
        sys.path.insert(0, str(editor_server))
    import server

    calls = []
    with patch.object(
        server,
        "_runtime_callable",
        return_value=lambda viewer_id, mode: calls.append((viewer_id, mode)) or {"ok": True},
    ):
        server._push_live_node_param_update(
            {"type": "DepthCloudViewer", "params": {"viewer_id": "camera-cloud"}},
            "color_mode",
            "ir",
            {"viewer_id": "camera-cloud", "color_mode": "rgb"},
        )

    assert calls == [("camera-cloud", "ir")]
