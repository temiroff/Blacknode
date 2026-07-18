from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_first_editor_visit_opens_packages_with_one_time_welcome():
    source = (ROOT / "editor" / "src" / "components" / "NodePalette.tsx").read_text(encoding="utf-8")

    assert "api.getOnboarding()" in source
    assert "!state.package_welcome_seen" in source
    assert "setActiveTab('packages')" in source
    assert "await api.setOnboarding(true)" in source
    assert "localStorage" not in source
    assert "Prepare your robotics workspace" in source
    assert "Explore essential packages" in source
    assert "Explore core templates" in source
    assert "useState<Tab | null>('templates')" in source
    assert "finishPackageWelcome('templates')" in source
