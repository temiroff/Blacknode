from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_family_colors_are_stable():
    source = (ROOT / "editor" / "src" / "categories.ts").read_text(encoding="utf-8")

    expected = {
        "Core": "#06b6d4",
        "Agent": "#a855f7",
        "Robot": "#14b8a6",
        "Perception": "#22c55e",
        "ROS2": "#3b82f6",
        "CUDA": "#84cc16",
        "Motion": "#f97316",
        "Drivers": "#64748b",
        "Output": "#ec4899",
        "Values": "#f59e0b",
    }
    for family, color in expected.items():
        assert f"{family}: '{color}'" in source or f"'{family}': '{color}'" in source


def test_search_templates_and_packages_share_family_color_helpers():
    search = (ROOT / "editor" / "src" / "components" / "NodeSearch.tsx").read_text(encoding="utf-8")
    templates = (ROOT / "editor" / "src" / "components" / "TemplateGallery.tsx").read_text(encoding="utf-8")
    packages = (ROOT / "editor" / "src" / "components" / "PackagesPanel.tsx").read_text(encoding="utf-8")

    assert "familyColor(category, color)" in search
    assert "bn-node-search-filters" in search
    assert "packageFamilyName" in templates
    assert "familyColor(tag, visualColor)" in templates
    assert "packageIdentity" in packages
    assert "familyColor(`${label} ${pkg.name} ${pkg.layer || ''}`" in packages


def test_refined_preview_uses_layered_nodes_and_category_only_templates():
    node = (ROOT / "editor" / "src" / "components" / "BlackNode.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert 'className="bn-node-parameter-area"' in node
    assert "--bn-node-parameter-surface" in styles
    assert "--bn-node-port-surface" in styles
    assert ".bn-template-card::before" in styles
    assert "Simple solid handles" in styles
    assert "consistent node icon/title rhythm" in styles
    assert "--bn-node-icon-title-gap: 12px" in styles
    assert "compact template category rhythm" in styles
    assert "margin-top: 1px" in styles
    assert "var(--bn-template-accent) 38%" in styles
    assert "var(--bn-node-accent) 80%, transparent" in styles
    assert "stroke-width: 2.7px !important" in styles
    assert "border-radius: 0 0 15px 15px" in styles
    assert "var(--bn-node-accent) 42%, var(--line2)" in styles
    assert "0 0 0 1px color-mix(in srgb, var(--bn-node-accent) 22%, transparent)" in styles
    assert "0 0 24px color-mix(in srgb, var(--bn-node-accent) 16%, transparent)" in styles
    assert 'html[data-ui-test="refined"] .react-flow__node:hover .bn-node-frame' not in styles
    assert 'html[data-ui-test="refined"] .react-flow__node:hover .bn-node-header' not in styles
    assert ".react-flow__node.bn-wire-endpoint .bn-node-frame" not in styles
    assert "--tx1: #374d57;" in styles


def test_refined_preview_is_the_temporary_default_and_toggle_is_hidden():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    index = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "function loadUiTestPreference() {\n  return true\n}" in app
    assert 'data-ui-test="refined"' in index
    assert ".bn-ui-test-button {\n  display: none !important;" in styles
    assert "UI Test" in app
