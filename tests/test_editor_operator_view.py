from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operator_view_contract_is_declarative_and_versioned():
    contract = (ROOT / "editor" / "src" / "operatorView.ts").read_text(encoding="utf-8")

    assert "export interface WorkflowOperatorView" in contract
    assert "schema_version: 1" in contract
    assert "id?: string" in contract
    assert "export type OperatorWidget" in contract
    assert "type: 'image'" in contract
    assert "type: 'fields'" in contract
    assert "type: 'actions'" in contract
    assert "isWorkflowOperatorView" in contract


def test_workflow_tabs_preserve_app_or_graph_surface():
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "surface?: 'graph' | 'app'" in store
    assert "surface?: 'graph' | 'app') => Promise<void>" in store
    assert "openGraphAsTab: async (name, graph, surface = 'graph')" in store
    assert "setActiveTabSurface: (surface)" in store
    assert "surface: tab.surface ?? 'graph'" in store


def test_shortcuts_launch_declared_operator_apps():
    shortcuts = (
        ROOT / "editor" / "src" / "components" / "WorkflowShortcuts.tsx"
    ).read_text(encoding="utf-8")

    assert "isWorkflowOperatorView(templateGraph.metadata?.operator_view)" in shortcuts
    assert "openGraphAsTab(tabName, templateGraph, launchAsApp ? 'app' : 'graph')" in shortcuts
    assert "The operator app is ready" in shortcuts


def test_editor_hides_builder_chrome_but_keeps_edit_workflow_escape_hatch():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "activeTab?.surface === 'app'" in app
    assert "!activeOperatorView && <NodePalette />" in app
    assert "!activeOperatorView && <Inspector />" in app
    assert "<WorkflowOperatorView" in app
    assert "onEditWorkflow={() => setActiveTabSurface('graph')}" in app
    assert "Edit workflow" in view
    assert "Support the robot" in view
    assert ".bn-operator-view {" in styles
    assert ".bn-operator-image-frame" in styles


def test_operator_actions_reuse_graph_params_cooks_and_direct_controls():
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")

    assert "await updateParam(update.node_id, update.param, update.value)" in view
    assert "await controlNode(item.control.node_id, item.control.action" in view
    assert "await cookNode(" in view
    assert "window.confirm(item.confirm)" in view


def test_operator_actions_support_persistent_keyboard_and_pedal_bindings():
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "blacknode-operator-action-bindings:" in view
    assert "Shortcuts & pedals" in view
    assert "Assign key" in view
    assert "Assign pedal" in view
    assert "navigator.getGamepads()" in view
    assert "window.addEventListener('keydown', onKeyDown, true)" in view
    assert "isEditableBindingTarget(event.target)" in view
    assert "void runAction(action)" in view
    assert ".bn-operator-bindings-dialog" in styles
