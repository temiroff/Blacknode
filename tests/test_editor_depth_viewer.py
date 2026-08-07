from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


def _metric_frame() -> bytes:
    header = json.dumps({
        "width": 1,
        "height": 1,
        "step": 2,
        "encoding": "16UC1",
        "is_bigendian": False,
    }).encode("utf-8")
    return b"BNDEPTH1" + struct.pack("<I", len(header)) + header + struct.pack("<H", 500)


class _UpstreamFrame:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_depth_frame_relay_uses_the_cooked_viewer_source():
    node_id = "depth-viewer-relay-test"
    payload = _metric_frame()
    server._session.node_meta[node_id] = {
        "id": node_id,
        "type": "DepthViewer",
        "params": {},
    }
    server._session.graph._cache[(node_id, "status")] = {
        "frame_url": "http://robot.local:41000/frame.bin",
    }
    try:
        with patch.object(
            server.urllib.request,
            "urlopen",
            return_value=_UpstreamFrame(payload),
        ) as open_frame:
            response = TestClient(server.app).get(f"/nodes/{node_id}/depth-frame")
    finally:
        server._session.node_meta.pop(node_id, None)
        server._session.graph._cache.pop((node_id, "status"), None)

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"].startswith(
        "application/vnd.blacknode.metric-depth-frame"
    )
    assert open_frame.call_args.args[0].full_url == "http://robot.local:41000/frame.bin"


def test_depth_viewer_renders_raw_metric_frames_locally_without_recooking():
    viewer = (
        ROOT / "editor" / "src" / "components" / "ImageSensorViewer.tsx"
    ).read_text(encoding="utf-8")
    black_node = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")

    assert "parseMetricDepthFrame" in viewer
    assert "renderMetricDepth" in viewer
    assert "api.depthFrame(nodeId" in viewer
    assert "<canvas" in viewer
    assert "depthPreviewUrl" not in viewer
    assert "onDepthDisplayChange" in black_node
    assert "updateParam(id, key, value)" in black_node


def test_depth_viewer_click_inspects_metric_distance_at_the_source_pixel():
    viewer = (
        ROOT / "editor" / "src" / "components" / "ImageSensorViewer.tsx"
    ).read_text(encoding="utf-8")

    assert "function depthPixelFromPointer" in viewer
    assert "const scale = Math.min(rect.width / frame.width, rect.height / frame.height)" in viewer
    assert "function sampleDepth" in viewer
    assert "frame.values[pixel.y * frame.width + pixel.x] * depthScale" in viewer
    assert "onClick={inspectDepth}" in viewer
    assert 'title="Click to inspect metric distance"' in viewer
    assert "Click image to measure" in viewer
    assert "No depth · pixel" in viewer
    assert "depthSample.distanceM.toFixed(3)" in viewer
