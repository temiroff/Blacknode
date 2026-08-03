from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_robot_profile_controls_show_name_id_and_calibration_count():
    node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(
        encoding="utf-8"
    )
    inspector = (
        ROOT / "editor" / "src" / "components" / "Inspector.tsx"
    ).read_text(encoding="utf-8")

    assert "`${profile.name} · ${profile.id}`" in node
    assert "profile.calibration_count" in node
    assert "choiceLabels?.[opt] ?? opt" in inspector
    assert "`${profile.name} · ${profile.id}`" in inspector


def test_robot_node_adopts_the_exact_calibration_applied_from_usb_identity():
    node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(
        encoding="utf-8"
    )

    assert "data.portResults?.calibration" in node
    assert "appliedRobotCalibrationCandidate" in node
    assert "profile_id: appliedRobotCalibrationCandidate.profile_id" in node
    assert "hardware_id: appliedRobotCalibrationCandidate.hardware_id" in node


def test_calibration_picker_does_not_disable_itself_when_opened():
    node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(
        encoding="utf-8"
    )
    picker = node.split('aria-label="Calibration used for deployment"', 1)[1]
    picker = picker.split("</select>", 1)[0]

    assert "onFocus" not in picker
    assert "onChange={e => { void selectRobotCalibration(e.target.value) }}" in picker
