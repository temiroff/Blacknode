from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mapping_actions_report_progress_and_remain_on_robot_card():
    deployments = (
        ROOT / "editor" / "src" / "components" / "DeploymentsPanel.tsx"
    ).read_text(encoding="utf-8")
    devices = (
        ROOT / "editor" / "src" / "components" / "DevicesPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "Saving occupancy grid and pose graph on the robot" in deployments
    assert "Closing map stream and SLAM process" in deployments
    assert "DeploymentActionProgress" in deployments
    assert "Restart mapping" in devices
    assert "Save map" in devices
    assert "Stop mapping" in devices
    assert "<LiveOccupancyMap" in devices
    assert "bn-device-capability-control" in devices


def test_compute_device_node_stays_focused_on_the_compute_target():
    node = (
        ROOT / "editor" / "src" / "components" / "ComputeDeviceNode.tsx"
    ).read_text(encoding="utf-8")

    assert "Physical robot" not in node
    assert "Capability stream" not in node
