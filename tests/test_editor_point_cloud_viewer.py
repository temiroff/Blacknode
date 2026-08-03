from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "editor" / "src" / "components" / "PointCloudViewer.tsx"


def test_point_cloud_viewer_exposes_spatial_orientation_and_scale():
    source = VIEWER.read_text(encoding="utf-8")

    assert "LiDAR forward" in source
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
