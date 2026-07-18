from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_template_gallery_groups_are_collapsed_by_default():
    source = (
        ROOT / "editor" / "src" / "components" / "TemplateGallery.tsx"
    ).read_text(encoding="utf-8")

    assert "useState<Set<string>>(() => new Set())" in source
    assert "template.group || 'Core'" in source
    assert "aria-expanded={isExpanded}" in source
    assert "isExpanded && group.templates.map" in source


def test_template_gallery_searches_and_uses_group_colors():
    source = (
        ROOT / "editor" / "src" / "components" / "TemplateGallery.tsx"
    ).read_text(encoding="utf-8")

    assert 'placeholder="Search templates or categories..."' in source
    assert "const filteredTemplateGroups = useMemo" in source
    assert "Boolean(query.trim()) || expandedGroups.has(group.name)" in source
    assert "border: `1px solid ${dependencyError ? 'var(--warn)' : group.color}`" in source
    assert "color: group.color" in source
