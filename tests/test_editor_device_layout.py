from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manage_device_actions_use_a_dedicated_responsive_row() -> None:
    panel = (ROOT / "editor" / "src" / "components" / "DevicesPanel.tsx").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "showDeviceManagement ? ' is-managing' : ''" in panel
    assert '.bn-device-header-actions.is-managing {' in styles
    managing_rule = styles.split('.bn-device-header-actions.is-managing {', 1)[1].split(
        '}', 1
    )[0]
    assert "grid-column: 1 / -1;" in managing_rule
    assert "grid-row: auto;" in managing_rule
    assert "justify-self: stretch;" in managing_rule


def test_refined_danger_actions_keep_a_visible_outline() -> None:
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    danger_rule = styles.split(
        'html[data-ui-test="refined"] .bn-device-action-button.is-danger {', 1
    )[1].split('}', 1)[0]
    assert "border-color: color-mix" in danger_rule
    assert "border-color: transparent;" not in danger_rule
