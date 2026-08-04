from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "editor" / "src" / "components" / "PointCloudViewer.tsx"
BLACK_NODE = ROOT / "editor" / "src" / "components" / "BlackNode.tsx"


def test_point_cloud_viewer_exposes_spatial_orientation_and_scale():
    source = VIEWER.read_text(encoding="utf-8")

    assert "Robot forward" in source
    assert "robotHeadingYaw" in source
    assert "robotCorners" in source
    assert "filtered laser returns" in source
    assert "3D orbit · LaserScan lies on XY plane" in source
    assert "meterLabel" in source
    assert "angle_min_rad" in source
    assert "angle_max_rad" in source
    assert "CURRENT SCAN" in source
    assert "accumulated returns" in source
    assert "history is sensor-local" in source
    assert "pose-registered history" in source
    assert "scanCoverageDeg" in source
    assert "360° scan" in source
    assert "sequenceRef" not in source
    assert "counterclockwisePoints" in source
    assert "real_scan_pulse" not in source
    assert "Accumulate:" in source


def test_point_cloud_viewer_has_direct_camera_navigation():
    source = VIEWER.read_text(encoding="utf-8")

    assert "onWheel" in source
    assert "onPointerMove" in source
    assert "drag orbit" in source
    assert "Shift/right-drag pan" in source
    assert "double-click fit" in source
    assert "Orbit left" in source
    assert "Orbit right" in source
    assert "Tilt camera up" in source
    assert "pitch:" in source
    assert "onClear" in source


def test_point_cloud_viewer_exposes_accumulation_control():
    source = BLACK_NODE.read_text(encoding="utf-8")

    assert "onToggleViewerAccumulation" in source
    assert "viewerHistoryPaused ? 'resume' : 'pause'" in source
    assert "await updateParam(id, 'action', 'status')" in source
    assert "data.type === 'Viewer' || data.type === 'SLAM'" in source
    assert "optimized trajectory" in VIEWER.read_text(encoding="utf-8")
    assert "loop closure" in VIEWER.read_text(encoding="utf-8")


def test_point_cloud_viewer_draws_current_scan_when_map_is_empty():
    source = VIEWER.read_text(encoding="utf-8")

    assert "() => [...points, ...currentPoints]" in source
    assert "currentColors[currentIndex]" in source
    assert "if (renderedPoints.length === 0) return" in source
    assert "Live scan; map is empty" in source
