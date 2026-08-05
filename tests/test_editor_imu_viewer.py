from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_imu_viewer_has_quaternion_robot_axes_logo_and_live_telemetry():
    source = (ROOT / "editor" / "src" / "components" / "IMUOrientationViewer.tsx").read_text(encoding="utf-8")

    assert "normalizeQuaternion" in source
    assert "rotate(point" in source
    assert "blacknode-logo-dark.png" in source
    assert "drawArrow(bodyOrigin" in source
    assert "ROLL" in source and "PITCH" in source and "YAW" in source
    assert "ANGULAR" in source and "ACCEL" in source and "FRAME" in source


def test_imu_viewer_uses_the_managed_viewer_node_shell():
    source = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "data.type === 'IMUViewer'" in source
    assert "<IMUOrientationViewer" in source
    assert "LIVE • IMU" in source
    assert "meta.type === 'IMUViewer'" in store
