from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPATIAL_CAMERA = ROOT / "editor" / "src" / "spatialCamera.ts"


def test_imu_viewer_has_quaternion_robot_axes_logo_and_live_telemetry():
    source = (ROOT / "editor" / "src" / "components" / "IMUOrientationViewer.tsx").read_text(encoding="utf-8")

    assert "normalizeQuaternion" in source
    assert "rotate(point" in source
    assert "blacknode-logo-dark.png" in source
    assert "drawArrow(bodyOrigin" in source
    assert "ROLL" in source and "PITCH" in source and "YAW" in source
    assert "ANGULAR" in source and "ACCEL" in source and "FRAME" in source
    assert "multiplyQuaternion(rawQuaternion, inverseQuaternion(sensorMountQuaternion))" in source
    assert "multiplyQuaternion(rawBodyQuaternion, inverseQuaternion(referenceQuaternion))" in source
    assert "Zero pose" in source
    assert "Absolute" in source
    assert "startup-relative robot pose" in source
    assert "IMU axes" in source
    assert "IMU X" in source and "IMU Y" in source and "IMU Z" in source
    assert "body_from_sensor_quaternion" in source
    assert "spatialCameraCoordinates" in source
    assert "const IMU_DEFAULT_CAMERA:" in source
    assert "yaw: -0.68" in source
    assert "pitch: -0.62" in source
    assert "IMU_CAMERA_MIN_PITCH" in source and "IMU_CAMERA_MAX_PITCH" in source
    assert "return depth(right) - depth(left)" in source

    camera_source = SPATIAL_CAMERA.read_text(encoding="utf-8")
    assert "World coordinates are +X forward, +Y left, +Z up" in camera_source
    assert "const cameraDepth = -pitchSine * yawY - pitchCosine * z" in camera_source


def test_imu_viewer_uses_the_managed_viewer_node_shell():
    source = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "data.type === 'IMUViewer'" in source
    assert "<IMUOrientationViewer" in source
    assert "LIVE • IMU" in source
    assert "VIEWER_NODE_TYPES.has(meta.type)" in store
