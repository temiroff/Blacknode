from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operator_view_contract_is_declarative_and_versioned():
    contract = (ROOT / "editor" / "src" / "operatorView.ts").read_text(encoding="utf-8")

    assert "export interface WorkflowOperatorView" in contract
    assert "schema_version: 1" in contract
    assert "id?: string" in contract
    assert "icon?: 'record' | 'camera' | 'robot' | 'workflow' | 'play'" in contract
    assert "settings?: OperatorSettings" in contract
    assert "apply_to?: Array<{ node_id: string; param: string }>" in contract
    assert "region?: 'main' | 'parameters'" in contract
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
    assert '<aside className="bn-operator-sidebar">' in view
    assert '<aside className="bn-operator-parameters">' in view
    assert "section.region === 'parameters'" in view
    assert "grid-template-columns: 196px minmax(0, 1fr) 300px" in styles
    assert "Support the robot" in view
    assert ".bn-operator-view {" in styles
    assert ".bn-operator-image-frame" in styles


def test_operator_panels_use_consistent_compact_spacing_and_cyan_highlights():
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "--bn-operator-panel-gap: 6px" in styles
    assert "--bn-operator-panel-highlight: var(--accent)" in styles
    assert "padding: var(--bn-operator-panel-gap)" in styles
    assert "margin-top: var(--bn-operator-panel-gap)" in styles
    assert "gap: var(--bn-operator-panel-gap)" in styles
    assert "var(--bn-operator-panel-highlight) 28%" in styles
    assert ".bn-operator-card::before" not in styles
    assert "max-height: min(42vh, 340px)" in styles
    assert "overflow-y: auto" in styles
    assert ".bn-operator-image-card.is-dashboard .bn-operator-image-frame img" in styles
    assert "height: auto" in styles


def test_operator_actions_reuse_graph_params_cooks_and_direct_controls():
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")

    assert "await updateParam(update.node_id, update.param, update.value)" in view
    assert "await controlNode(item.control.node_id, item.control.action" in view
    assert "await cookNode(" in view
    assert "window.confirm(item.confirm)" in view


def test_operator_settings_import_calibration_json_in_the_browser():
    contract = (ROOT / "editor" / "src" / "operatorView.ts").read_text(encoding="utf-8")
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")

    assert "'calibration_file'" in contract
    assert 'accept=".json,application/json"' in view
    assert "await file.text()" in view
    assert "kind: 'blacknode.calibration-import'" in view
    assert "bound to the connected arm" in view


def test_operator_view_surfaces_live_activity_and_structured_failures():
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "cookActive, cookLog" in view
    assert 'className="bn-operator-activity"' in view
    assert "Needs attention" in view
    assert "entry.kind === 'error'" in view
    assert "BLOCKED|FAILED|MISSING" in store
    assert "kind: reportedProblem ? 'error' : 'success'" in store
    assert ".bn-operator-latest-issue" in styles


def test_runtime_poll_preserves_managed_camera_stream_preview():
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "...(Array.isArray(status.cv2_streams) ? status.cv2_streams : [])" in store
    assert "const managedStream = managedStreams.find" in store
    assert "owner === node.id" in store
    assert "streaming: true" in store
    assert "...liveOutputs, ...streamOutputs, ...managedOutputs" in store


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


def test_customer_app_shell_direct_launches_and_keeps_editor_controls_outside_operator_mode():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    shell = (
        ROOT / "editor" / "src" / "components" / "CustomerAppShell.tsx"
    ).read_text(encoding="utf-8")
    view = (
        ROOT / "editor" / "src" / "components" / "WorkflowOperatorView.tsx"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "editor" / "src" / "index.css").read_text(encoding="utf-8")

    assert "function AppDeploymentGate()" in app
    assert "api.appDeployment()" in app
    assert "import BlacknodeLogo from './components/BlacknodeLogo'" in app
    assert '<BlacknodeLogo className="bn-app-mode-loading-logo"' in app
    assert "<CustomerAppShell deployment={deployment}" in app
    assert "appsById.has(deployment.start_app)" in shell
    assert "api.activateDeploymentApp(appId)" in shell
    assert 'className="bn-customer-app-bar"' in shell
    assert "import BlacknodeLogo from './BlacknodeLogo'" in shell
    assert '<BlacknodeLogo className="bn-rail-logo"' in shell
    assert '<BlacknodeLogo className="bn-customer-app-loading-logo"' in shell
    assert 'aria-label="Deployed Apps"' in shell
    assert "<AppGlyph icon={app.icon || 'workflow'}" in shell
    assert 'aria-label="App settings"' in shell
    assert "settingsOpen={settingsOpen}" in shell
    assert "onEditWorkflow?: () => void" in view
    assert "{onEditWorkflow && <button" in view
    assert "item.apply_to ?? []" in view
    assert ".bn-customer-app-bar" in styles
    assert ".bn-operator-settings-dialog" in styles
