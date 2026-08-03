from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "editor" / "src" / "components" / "PointCloudViewer.tsx"


def test_point_cloud_viewer_exposes_spatial_orientation_and_scale():
    source = VIEWER.read_text(encoding="utf-8")

    assert "LiDAR forward" in source
    assert "filtered laser returns" in source
    assert "2D XY plane" in source
    assert "meterLabel" in source
    assert "angle_min_rad" in source
    assert "angle_max_rad" in source
    assert "CURRENT SCAN" in source


def test_point_cloud_viewer_has_direct_camera_navigation():
    source = VIEWER.read_text(encoding="utf-8")

    assert "onWheel" in source
    assert "onPointerMove" in source
    assert "right-drag rotate" in source
    assert "double-click fit" in source
    assert "Rotate left" in source
    assert "Rotate right" in source
