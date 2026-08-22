from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_robot_workflow_shortcuts_occupy_the_panel_header_row():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "const WORKFLOW_SHORTCUT_H = 52" in app
    assert "const workflowTabsTop = topbarH + WORKFLOW_SHORTCUT_H" in app
    assert "const canvasPad = workflowTabsTop + TAB_H" in app
    assert "top: workflowTabsTop" in app
    assert "<WorkflowShortcuts />" in app


def test_collect_episodes_is_the_first_persistent_default_shortcut():
    shortcuts = (
        ROOT / "editor" / "src" / "components" / "WorkflowShortcuts.tsx"
    ).read_text(encoding="utf-8")

    first_default = shortcuts.index("id: 'collect-episodes'")
    assert shortcuts.index("label: 'Collect episodes'") > first_default
    assert shortcuts.index("templateSlug: 'teleoperation-episode-recording'") > first_default
    assert "blacknode-workflow-shortcuts" in shortcuts
    assert "window.localStorage.setItem" in shortcuts


def test_shortcuts_open_templates_safely_and_support_full_customization():
    shortcuts = (
        ROOT / "editor" / "src" / "components" / "WorkflowShortcuts.tsx"
    ).read_text(encoding="utf-8")

    assert "await api.loadTemplate(shortcut.templateSlug)" in shortcuts
    assert "await openGraphAsTab(tabName, templateGraph)" in shortcuts
    assert "await api.setGraph(" in shortcuts
    assert "+ Add shortcut" in shortcuts
    assert "Edit workflow shortcut" in shortcuts
    assert "Delete ${shortcut.label}" in shortcuts
    assert "setShortcuts(current => current.filter" in shortcuts
    assert "Reset" in shortcuts


def test_workflow_shortcut_styles_include_the_editor_and_dialog():
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert ".bn-workflow-shortcuts {" in styles
    assert ".bn-workflow-shortcut-dialog {" in styles
    assert ".bn-workflow-shortcut-actions button:last-child:hover" in styles
