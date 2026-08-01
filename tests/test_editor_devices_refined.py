from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_refined_devices_use_health_summary_tabs_and_robot_chips():
    devices = (
        ROOT / "editor" / "src" / "components" / "DevicesPanel.tsx"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "bn-device-primary-health" not in devices
    assert "bn-device-hero-badges" not in devices
    assert "bn-device-detail-tabs" in devices
    assert "openDeviceDetailTab('diagnostics')" in devices
    assert "deviceDetailTab === 'overview'" in devices
    assert "deviceDetailTab === 'diagnostics'" in devices
    assert "bn-device-card-firmware" in devices
    assert "Firmware {" in devices
    assert "isUiTest ? robot.remote_device_id" not in devices

    assert "Devices as a health-focused control center" in styles
    assert ".bn-device-card-state::before" in styles
    assert ".bn-device-card-chevron" in styles
    assert "grid-column: 3" in styles
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in styles
    assert "min-height: 60px" in styles
    assert "min-height: 56px" in styles
    assert "compact, aligned Software cards" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert ".bn-device-card.is-expanded" in styles
    assert "bn-local-package-check-compact" in devices
    assert ".bn-local-package-version-action:has(.bn-local-package-check-latest)" in styles
    assert "@container devices-panel (max-width: 420px)" in styles


def test_refined_devices_only_show_reported_health_signals():
    devices = (
        ROOT / "editor" / "src" / "components" / "DevicesPanel.tsx"
    ).read_text(encoding="utf-8")

    for invented_metric in ("CPU 18%", "RAM 5.2 GB", "Temp 51°", "RTX4090"):
        assert invented_metric not in devices


def test_remote_device_setup_defaults_to_reviewed_runtime_only_install():
    devices = (
        ROOT / "editor" / "src" / "components" / "DevicesPanel.tsx"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "useState<RuntimeInstallAction>('runtime_only')" in devices
    assert "Install Runtime only" in devices
    assert "verified Linux bundle" in devices
    assert "Changes on this device" in devices
    assert "installChangesConfirmed" in devices
    assert "authorize this installation" in devices
    assert "openInspectedRuntimeSetup" in devices
    assert "Install Runtime" in devices
    assert "workflow execution" in devices
    assert "This Windows editor downloads" in devices
    assert "does not need internet" in devices
    assert "bn-runtime-change-plan" in styles
