import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance, Edge, Connection, SelectionMode,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore, type CookLogEntry, type GraphClipboard } from './store'
import BlackNode from './components/BlackNode'
import { LIVE_STREAM_NODE_TYPES } from './liveNodeTypes'
import { VIEWER_NODE_TYPES } from './viewerTypes'
import ValueNode from './components/ValueNode'
import ModelNode from './components/ModelNode'
import OutputNode from './components/OutputNode'
import ComputeDeviceNode from './components/ComputeDeviceNode'
import ROS2GraphExplorerNode from './components/ROS2GraphExplorerNode'
import SimulationViewerPane from './components/SimulationViewerPane'
import CloudRunPanel from './components/CloudRunPanel'
import EmailVerificationPage from './components/EmailVerificationPage'
import LocalFilePicker from './components/LocalFilePicker'
import RobotMonitorNode from './components/RobotMonitorNode'
import RobotServoNode from './components/RobotServoNode'
import SubnetNode from './components/SubnetNode'
import SubnetBreadcrumb from './components/SubnetBreadcrumb'
import SubgraphInputNode from './components/SubgraphInputNode'
import SubgraphOutputNode from './components/SubgraphOutputNode'
import NodePalette from './components/NodePalette'
import Inspector from './components/Inspector'
import WorkflowShortcuts from './components/WorkflowShortcuts'
import WorkflowOperatorView from './components/WorkflowOperatorView'
import NodeSearch from './components/NodeSearch'
import { portColor, portVisualColor, portsCompatible } from './portColors'
import { PYTHON_TOOL_TYPES, resolvePythonToolPreset } from './pythonToolPresets'
import type { BnNodeDef, ConnectionDraft } from './types'
import { api, type CloudJob, type CloudStatus, type FrameworkExportTarget, type NewtonWorkspaceStatus, type WorkflowMetadata } from './api'
import { inferGraphRunTargets } from './graphRun'
import { copyTextToClipboard } from './clipboard'
import { isWorkflowOperatorView } from './operatorView'

const NODE_TYPES = {
  blacknode: BlackNode,
  valuenode: ValueNode,
  modelnode: ModelNode,
  outputnode: OutputNode,
  computedevice: ComputeDeviceNode,
  ros2graphexplorer: ROS2GraphExplorerNode,
  robotmonitor: RobotMonitorNode,
  robotservo: RobotServoNode,
  subnetnode: SubnetNode,
  subnetinput: SubgraphInputNode,
  subnetoutput: SubgraphOutputNode,
}

const TAB_H = 52  // workflow tab bar height
const WORKFLOW_SHORTCUT_H = 52
const THEME_STORAGE_KEY = 'blacknode-theme'
const UI_TEST_STORAGE_KEY = 'blacknode-ui-test'
const SIMULATION_VIEWER_HEIGHT_STORAGE_KEY = 'blacknode-simulation-viewer-height'
const NEWTON_SCENE_FILE_EXTENSIONS = [
  '.usd', '.usda', '.usdc', '.urdf', '.xacro', '.xml', '.mjcf',
]
const HDRI_FILE_EXTENSIONS = ['.hdr', '.exr']

function loadDarkThemePreference() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) !== 'light'
  } catch {
    return true
  }
}

function loadCloudAccountEntryRequest(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('cloud') === 'account'
  } catch {
    return false
  }
}

function loadUiTestPreference() {
  return true
}

function loadSimulationViewerHeight(): number {
  try {
    const value = Number(window.localStorage.getItem(SIMULATION_VIEWER_HEIGHT_STORAGE_KEY))
    return Number.isFinite(value) && value >= 180 ? value : 420
  } catch {
    return 420
  }
}

const DEFAULT_FRAMEWORK_EXPORT_TARGETS: FrameworkExportTarget[] = [
  { id: 'python', label: 'Plain Python', description: 'Readable Blacknode Graph script.', extension: '.py' },
  { id: 'python-class', label: 'Python Class', description: 'Class-based Blacknode workflow script.', extension: '.py' },
  { id: 'langgraph', label: 'LangGraph', description: 'LangGraph StateGraph export.', extension: '.py' },
  { id: 'crewai', label: 'CrewAI', description: 'CrewAI task map export.', extension: '.py' },
  { id: 'autogen', label: 'AutoGen', description: 'AutoGen agent map export.', extension: '.py' },
  { id: 'swarm', label: 'OpenAI Swarm', description: 'Swarm handoff map export.', extension: '.py' },
]

interface SearchState {
  screenPos: { x: number; y: number }
  flowPos: { x: number; y: number }
  connect?: ConnectionDraft
}

interface NoticeState {
  kind: 'error' | 'warning' | 'info'
  title: string
  message: string
}

interface PendingCloseState {
  tabId: string
  draftName: string
}

interface PendingXacroEnvironmentState {
  assetPath: string
  variableName: string
  values: Record<string, string>
}

function ToolbarIcon({
  name,
  className,
}: {
  name: 'organize' | 'refresh' | 'light' | 'dark' | 'clear'
  className?: string
}) {
  return (
    <svg
      className={['bn-top-icon', className].filter(Boolean).join(' ')}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {name === 'organize' && (
        <>
          <rect x="2.5" y="2.5" width="5" height="5" rx="1" />
          <rect x="12.5" y="2.5" width="5" height="5" rx="1" />
          <rect x="2.5" y="12.5" width="5" height="5" rx="1" />
          <rect x="12.5" y="12.5" width="5" height="5" rx="1" />
        </>
      )}
      {name === 'refresh' && (
        <>
          <path d="M16.4 7.2A7 7 0 0 0 4.6 4.6L3 6.2" />
          <path d="M3 2.8v3.4h3.4" />
          <path d="M3.6 12.8a7 7 0 0 0 11.8 2.6l1.6-1.6" />
          <path d="M17 17.2v-3.4h-3.4" />
        </>
      )}
      {name === 'light' && (
        <>
          <circle cx="10" cy="10" r="3.2" />
          <path d="M10 2v1.6M10 16.4V18M2 10h1.6M16.4 10H18M4.3 4.3l1.1 1.1M14.6 14.6l1.1 1.1M15.7 4.3l-1.1 1.1M5.4 14.6l-1.1 1.1" />
        </>
      )}
      {name === 'dark' && (
        <path d="M16.7 12.3A6.8 6.8 0 0 1 7.7 3.3 6.8 6.8 0 1 0 16.7 12.3Z" />
      )}
      {name === 'clear' && (
        <>
          <path d="M3.5 5.5h13" />
          <path d="M7.5 3.5h5" />
          <path d="M5.5 5.5l.7 11h7.6l.7-11" />
          <path d="M8.2 8.2v5.5M11.8 8.2v5.5" />
        </>
      )}
    </svg>
  )
}

function missingXacroEnvironmentVariable(message: string): string | null {
  const match = message.match(/Xacro requires environment variable ['"]([^'"]+)['"]/i)
  return match?.[1] ?? null
}

function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function fileBaseName(filename: string): string {
  return filename
    .replace(/\.(workflow\.)?json$/i, '')
    .replace(/\.(langgraph|python-class|python|crewai|autogen|swarm|nvidia-agent-stack)?\.?py$/i, '')
    .trim()
}

function isImageFile(file: File): boolean {
  return file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|tiff?|avif)$/i.test(file.name)
}

function isImageDataUrl(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith('data:image/')
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error ?? new Error(`Could not read ${file.name}`))
    reader.readAsDataURL(file)
  })
}

function nodeIdAtScreenPoint(point: { x: number; y: number }): string | null {
  for (const element of document.elementsFromPoint(point.x, point.y)) {
    if (!(element instanceof HTMLElement)) continue
    const nodeEl = element.closest('.react-flow__node[data-id]')
    if (!(nodeEl instanceof HTMLElement)) continue
    return nodeEl.dataset.id ?? null
  }
  return null
}

export default function App() {
  if (window.location.pathname.replace(/\/+$/, '') === '/verify-email') {
    return <EmailVerificationPage />
  }
  return <WorkspaceApp />
}

function WorkspaceApp() {
  const {
    nodes, edges, nodeTypes, nodeDefs, selectedId, serverOk, serverError, cookLog, cookActive, cookStatusHidden,
    tabs, activeTabId, activeProject, workflowMetadata, workflowEntrypoint,
    onNodesChange, onEdgesChange, onConnect: storeOnConnect, disconnectEdge, reconnectEdge,
    addNode, selectNode, loadNodeTypes, loadGraph, loadApiKeys, loadApiKeyStatus, loadCustomModels, loadLearnedNodes, loadDriverStatus, loadRuntimeNodeOutputs, loadSpatialViewerNodeOutputs, loadDrivers,
    addNodeFromConnection, copySelection, pasteClipboard,
    beginAltDragCopy, finishAltDragCopy, undoGraph,
    checkServer, reset, newTab, insertTab, switchTab, closeTab, duplicateTab,
    openGraphAsTab, openWorkflowAsTab, setActiveTabSurface, renameTab, saveActiveWorkflow,
    diveIntoSubnet, exitSubnet, collapseToSubnet, organizeNodes, cookNode, stopCook, stopRuntimeServices, dismissCookStatus, applyRunReplay,
    handleLearnedNodeEvent, updateParam,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const pythonImportInput = useRef<HTMLInputElement | null>(null)
  const [search, setSearch] = useState<SearchState | null>(null)
  const [isDark, setIsDark] = useState(loadDarkThemePreference)
  const [isUiTest, setIsUiTest] = useState(loadUiTestPreference)
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)
  const [hoveredPort, setHoveredPort] = useState<{
    nodeId: string
    port: string
    dir: 'input' | 'output'
  } | null>(null)
  const [editingTabId, setEditingTabId] = useState<string | null>(null)
  const [tabDraft, setTabDraft] = useState('')
  const [savingWorkflow, setSavingWorkflow] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const [tabMenu, setTabMenu] = useState<{ x: number; y: number; tabId: string } | null>(null)
  const [nodeMenu, setNodeMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null)
  const [notice, setNotice] = useState<NoticeState | null>(null)
  const [pendingClose, setPendingClose] = useState<PendingCloseState | null>(null)
  const [closeSaving, setCloseSaving] = useState(false)
  const [frameworkExportTargets, setFrameworkExportTargets] = useState(DEFAULT_FRAMEWORK_EXPORT_TARGETS)
  const [exportingTarget, setExportingTarget] = useState('')
  const [importingFile, setImportingFile] = useState(false)
  const [runtimeStopPending, setRuntimeStopPending] = useState(false)
  const [activeRunMode, setActiveRunMode] = useState<'once' | 'live' | null>(null)
  const [executionTarget, setExecutionTarget] = useState<'local' | 'cloud'>('local')
  const [hostedPreview, setHostedPreview] = useState(false)
  const [cloudPanelOpen, setCloudPanelOpen] = useState(loadCloudAccountEntryRequest)
  const [cloudJobPending, setCloudJobPending] = useState(false)
  const [cloudJob, setCloudJob] = useState<CloudJob | null>(null)
  const [cloudJobError, setCloudJobError] = useState('')
  const [cloudAccountStatus, setCloudAccountStatus] = useState<CloudStatus | null>(null)
  const [cloudPanelView, setCloudPanelView] = useState<'account' | 'job'>('account')
  const [refreshingCanvas, setRefreshingCanvas] = useState(false)
  const [openingUsd, setOpeningUsd] = useState(false)
  const [usdPickerInitialPath, setUsdPickerInitialPath] = useState<string | null>(null)
  const [pendingXacroEnvironment, setPendingXacroEnvironment] = useState<PendingXacroEnvironmentState | null>(null)
  const [xacroEnvironmentDraft, setXacroEnvironmentDraft] = useState('')
  const [hdriPickerInitialPath, setHdriPickerInitialPath] = useState<string | null>(null)
  const [simulationViewerVisible, setSimulationViewerVisible] = useState(true)
  const [simulationViewerDetached, setSimulationViewerDetached] = useState(false)
  const [simulationViewerHeight, setSimulationViewerHeight] = useState(loadSimulationViewerHeight)
  const [fileMenuOpen, setFileMenuOpen] = useState(false)
  const [fileMenuPosition, setFileMenuPosition] = useState({ top: 0, left: 0 })
  const [simulationViewerMenuOpen, setSimulationViewerMenuOpen] = useState(false)
  const [simulationViewerMenuPosition, setSimulationViewerMenuPosition] = useState({ top: 0, left: 0 })
  const [newtonWorkspace, setNewtonWorkspace] = useState<NewtonWorkspaceStatus | null>(null)
  const [newtonWorkspaceAvailable, setNewtonWorkspaceAvailable] = useState(false)
  const [newtonWorkspaceBusy, setNewtonWorkspaceBusy] = useState(false)

  useEffect(() => {
    void api.hostedStatus()
      .then(status => {
        setHostedPreview(status.hosted)
        if (status.hosted) setExecutionTarget('cloud')
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!loadCloudAccountEntryRequest()) return
    const url = new URL(window.location.href)
    url.searchParams.delete('cloud')
    window.history.replaceState(
      window.history.state,
      '',
      `${url.pathname}${url.search}${url.hash}`,
    )
  }, [])
  const lastSimulationViewerUrl = useRef('')
  const fileMenuTriggerRef = useRef<HTMLButtonElement | null>(null)
  const fileMenuRef = useRef<HTMLDivElement | null>(null)
  const simulationViewerMenuTriggerRef = useRef<HTMLButtonElement | null>(null)
  const simulationViewerMenuRef = useRef<HTMLDivElement | null>(null)
  const updatePendingCloseName = useCallback((draftName: string) => {
    setPendingClose(current => current ? { ...current, draftName } : current)
  }, [])
  const saveOkTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const graphClipboard = useRef<GraphClipboard | null>(null)
  const lastMouseFlowPos = useRef<{ x: number; y: number } | null>(null)
  const connectionMade = useRef(false)
  const connectionDraft = useRef<ConnectionDraft | null>(null)
  const edgeUpdateActive = useRef(false)
  const suppressConnectMenuUntil = useRef(0)
  const altDragCopy = useRef<{
    nodeIds: string[]
    originalPositions: Record<string, { x: number; y: number }>
    copyPromise: Promise<Record<string, string> | null>
  } | null>(null)
  const suppressPaneClick = useRef(false)
  const lastBackendNotice = useRef<string | null>(null)
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const operatorView = isWorkflowOperatorView(workflowMetadata.operator_view)
    ? workflowMetadata.operator_view
    : null
  const activeOperatorView = activeTab?.surface === 'app' ? operatorView : null
  const menuTab = tabMenu ? tabs.find(tab => tab.id === tabMenu.tabId) : null
  const pendingCloseTab = pendingClose ? tabs.find(tab => tab.id === pendingClose.tabId) : null
  const simulationViewer = useMemo(() => {
    for (const node of nodes) {
      if (node.data.type === 'PPOTraining') {
        const results = node.data.portResults ?? {}
        const status = results.status && typeof results.status === 'object'
          ? results.status as Record<string, unknown>
          : {}
        const viewer = results.viewer && typeof results.viewer === 'object'
          ? results.viewer as Record<string, unknown>
          : {}
        const url = String(results.viewer_url ?? status.viewer_url ?? viewer.viewer_url ?? '').trim()
        const viewerRunning = results.viewer_running === true
          || status.viewer_running === true
          || viewer.running === true
        if (!url || (results.running !== true && !viewerRunning)) continue
        return {
          url,
          label: String(node.data.params?.run_id ?? 'SO-ARM101 PPO training'),
          phase: String(results.phase ?? status.phase ?? 'running'),
          armed: false,
        }
      }
      if (node.data.type !== 'NewtonSimulation') continue
      const results = node.data.portResults ?? {}
      const session = results.session && typeof results.session === 'object'
        ? results.session as Record<string, unknown>
        : {}
      const url = String(results.viewer_url ?? session.viewer_url ?? '').trim()
      if (!url || (results.running !== true && session.running !== true)) continue
      return {
        url,
        label: String(node.data.params?.run_id ?? node.data.input_defaults?.run_id ?? 'Newton simulation'),
        phase: String(results.phase ?? session.phase ?? 'running'),
        armed: results.armed === true || session.armed === true,
      }
    }
    return null
  }, [nodes])

  const activeSimulationViewer = useMemo(() => {
    if (newtonWorkspace?.open && newtonWorkspace.viewer_url) {
      return {
        url: newtonWorkspace.viewer_url,
        label: 'Newton',
        phase: newtonWorkspace.phase,
        armed: newtonWorkspace.armed,
        workspace: true,
      }
    }
    return simulationViewer ? { ...simulationViewer, workspace: false } : null
  }, [newtonWorkspace, simulationViewer])

  const attachSimulationViewer = useCallback(() => {
    setSimulationViewerDetached(false)
    setSimulationViewerVisible(true)
  }, [])

  const detachSimulationViewer = useCallback(() => {
    if (!activeSimulationViewer) return
    setSimulationViewerDetached(true)
    setSimulationViewerVisible(true)
  }, [activeSimulationViewer])

  const controlNewtonWorkspace = useCallback(async (
    action: string,
    payload: Record<string, unknown> = {},
  ) => {
    const liveAction = new Set([
      'select', 'set_grid', 'set_visibility', 'set_transform', 'set_material',
      'set_environment', 'set_render_options', 'joint_target', 'set_joint_properties',
      'set_joint_motion', 'set_digital_twin_ghost', 'sync_digital_twin_pose',
      'clear_digital_twin_history',
      'save_digital_twin_artifact', 'load_digital_twin_baseline',
      'clear_digital_twin_baseline',
    ]).has(action)
    if (newtonWorkspaceBusy && !liveAction) return null
    if (!liveAction) setNewtonWorkspaceBusy(true)
    try {
      const status = await api.controlNewtonWorkspace(action, payload)
      setNewtonWorkspaceAvailable(true)
      setNewtonWorkspace(status)
      if (status.open) setSimulationViewerVisible(true)
      return status
    } catch (error) {
      setNotice({
        kind: 'error',
        title: 'Newton workspace action failed',
        message: error instanceof Error ? error.message : String(error),
      })
      return null
    } finally {
      if (!liveAction) setNewtonWorkspaceBusy(false)
    }
  }, [newtonWorkspaceBusy])

  const openNewtonWorkspace = useCallback(() => {
    void controlNewtonWorkspace('open')
  }, [controlNewtonWorkspace])

  const handleOpenUsd = useCallback(() => {
    if (openingUsd || usdPickerInitialPath !== null) return
    if (!newtonWorkspaceAvailable) {
      setNotice({
        kind: 'warning',
        title: 'Newton workspace is unavailable',
        message: 'Install and enable the blacknode-newton runtime and a viewer component first.',
      })
      return
    }
    setUsdPickerInitialPath(String(newtonWorkspace?.asset_path ?? ''))
  }, [newtonWorkspace?.asset_path, newtonWorkspaceAvailable, openingUsd, usdPickerInitialPath])

  const loadNewtonAsset = useCallback(async (
    selected: string,
    xacroEnvironment: Record<string, string> = {},
  ) => {
    if (!selected || openingUsd) return
    setOpeningUsd(true)
    try {
      const status = await api.controlNewtonWorkspace('open_asset', {
        asset_path: selected,
        xacro_environment: xacroEnvironment,
      })
      setNewtonWorkspaceAvailable(true)
      setNewtonWorkspace(status)
      setSimulationViewerVisible(true)
      setPendingXacroEnvironment(null)
      setXacroEnvironmentDraft('')
      setNotice({
        kind: 'info',
        title: 'Scene opened in Newton',
        message: status.warning || `${selected} is loaded and simulation is stopped at its initial state.`,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const variableName = missingXacroEnvironmentVariable(message)
      if (variableName && /\.xacro$/i.test(selected)) {
        setPendingXacroEnvironment({ assetPath: selected, variableName, values: xacroEnvironment })
        setXacroEnvironmentDraft(xacroEnvironment[variableName] ?? '')
        return
      }
      setNotice({
        kind: 'error',
        title: 'Could not open scene',
        message,
      })
    } finally {
      setOpeningUsd(false)
    }
  }, [openingUsd])

  const handleUsdSelected = useCallback((selected: string) => {
    if (!selected || openingUsd) return
    setUsdPickerInitialPath(null)
    void loadNewtonAsset(selected)
  }, [loadNewtonAsset, openingUsd])

  const submitXacroEnvironment = useCallback(() => {
    if (!pendingXacroEnvironment || openingUsd) return
    const values = {
      ...pendingXacroEnvironment.values,
      [pendingXacroEnvironment.variableName]: xacroEnvironmentDraft,
    }
    const assetPath = pendingXacroEnvironment.assetPath
    setPendingXacroEnvironment(null)
    void loadNewtonAsset(assetPath, values)
  }, [loadNewtonAsset, openingUsd, pendingXacroEnvironment, xacroEnvironmentDraft])

  const handleChooseHdri = useCallback(() => {
    if (hdriPickerInitialPath !== null) return
    setHdriPickerInitialPath(String(newtonWorkspace?.environment?.hdri_path ?? ''))
  }, [hdriPickerInitialPath, newtonWorkspace?.environment?.hdri_path])

  const handleHdriSelected = useCallback((selected: string) => {
    setHdriPickerInitialPath(null)
    if (selected) void controlNewtonWorkspace('set_environment', { hdri: 'custom', hdri_path: selected })
  }, [controlNewtonWorkspace])

  useEffect(() => {
    if (!serverOk) {
      setCloudAccountStatus(null)
      return
    }
    let cancelled = false
    void api.cloudStatus()
      .then(status => {
        if (!cancelled) setCloudAccountStatus(status)
      })
      .catch(() => {
        if (!cancelled) setCloudAccountStatus(null)
      })
    return () => {
      cancelled = true
    }
  }, [serverOk])

  useEffect(() => {
    if (!nodeTypes.includes('NewtonSimulation')) {
      setNewtonWorkspaceAvailable(false)
      setNewtonWorkspace(null)
      return
    }
    let cancelled = false
    const refresh = async () => {
      try {
        const status = await api.newtonWorkspaceStatus()
        if (cancelled) return
        setNewtonWorkspaceAvailable(true)
        setNewtonWorkspace(status)
      } catch {
        if (!cancelled) setNewtonWorkspaceAvailable(false)
      }
    }
    void refresh()
    const timer = window.setInterval(() => {
      if (newtonWorkspace?.open) void refresh()
    }, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [newtonWorkspace?.open, nodeTypes])

  useLayoutEffect(() => {
    if (!fileMenuOpen) return
    const positionMenu = () => {
      const trigger = fileMenuTriggerRef.current
      if (!trigger) return
      const bounds = trigger.getBoundingClientRect()
      const width = 250
      setFileMenuPosition({
        top: bounds.bottom + 7,
        left: Math.max(8, Math.min(window.innerWidth - width - 8, bounds.left)),
      })
    }
    const closeMenu = () => setFileMenuOpen(false)
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (fileMenuTriggerRef.current?.contains(target)) return
      if (fileMenuRef.current?.contains(target)) return
      closeMenu()
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu()
    }
    positionMenu()
    document.addEventListener('pointerdown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    window.addEventListener('resize', positionMenu)
    window.addEventListener('scroll', positionMenu, true)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('resize', positionMenu)
      window.removeEventListener('scroll', positionMenu, true)
    }
  }, [fileMenuOpen])

  useLayoutEffect(() => {
    if (!simulationViewerMenuOpen) return
    const positionMenu = () => {
      const trigger = simulationViewerMenuTriggerRef.current
      if (!trigger) return
      const bounds = trigger.getBoundingClientRect()
      const width = 210
      setSimulationViewerMenuPosition({
        top: bounds.bottom + 7,
        left: Math.max(8, Math.min(window.innerWidth - width - 8, bounds.right - width)),
      })
    }
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (simulationViewerMenuTriggerRef.current?.contains(target)) return
      if (simulationViewerMenuRef.current?.contains(target)) return
      setSimulationViewerMenuOpen(false)
    }
    positionMenu()
    document.addEventListener('pointerdown', closeOnOutsidePointer)
    window.addEventListener('resize', positionMenu)
    window.addEventListener('scroll', positionMenu, true)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer)
      window.removeEventListener('resize', positionMenu)
      window.removeEventListener('scroll', positionMenu, true)
    }
  }, [simulationViewerMenuOpen])

  useEffect(() => {
    if (!activeSimulationViewer) {
      setSimulationViewerDetached(false)
    }
  }, [activeSimulationViewer])

  useEffect(() => {
    const url = activeSimulationViewer?.url ?? ''
    if (url && url !== lastSimulationViewerUrl.current) {
      lastSimulationViewerUrl.current = url
      if (!simulationViewerDetached) setSimulationViewerVisible(true)
    }
  }, [activeSimulationViewer?.url, simulationViewerDetached])

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SIMULATION_VIEWER_HEIGHT_STORAGE_KEY,
        String(Math.round(simulationViewerHeight)),
      )
    } catch {
      // The resized split remains active for this editor session.
    }
  }, [simulationViewerHeight])

  useLayoutEffect(() => {
    const theme = isDark ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', theme)
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
      // The selected theme still applies for this session when storage is unavailable.
    }
  }, [isDark])

  useLayoutEffect(() => {
    if (isUiTest) {
      document.documentElement.setAttribute('data-ui-test', 'refined')
    } else {
      document.documentElement.removeAttribute('data-ui-test')
    }
    try {
      window.localStorage.setItem(UI_TEST_STORAGE_KEY, isUiTest ? 'refined' : 'standard')
    } catch {
      // The comparison mode still applies for this session when storage is unavailable.
    }
  }, [isUiTest])

  useEffect(() => {
    const onPortHover = (event: Event) => {
      const detail = (event as CustomEvent<{
        nodeId?: string
        port?: string
        dir?: 'input' | 'output'
      } | null>).detail
      setHoveredPort(detail?.nodeId && detail.port && detail.dir
        ? { nodeId: detail.nodeId, port: detail.port, dir: detail.dir }
        : null)
    }
    window.addEventListener('blacknode:port-hover', onPortHover)
    return () => window.removeEventListener('blacknode:port-hover', onPortHover)
  }, [])

  useEffect(() => {
    return () => {
      if (saveOkTimer.current) clearTimeout(saveOkTimer.current)
      if (noticeTimer.current) clearTimeout(noticeTimer.current)
    }
  }, [])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<Partial<NoticeState>>).detail ?? {}
      const next: NoticeState = {
        kind: detail.kind ?? 'info',
        title: detail.title ?? 'Notice',
        message: detail.message ?? '',
      }
      setNotice(next)
      if (noticeTimer.current) clearTimeout(noticeTimer.current)
      noticeTimer.current = setTimeout(() => setNotice(null), next.kind === 'error' ? 7000 : 4500)
    }
    window.addEventListener('blacknode:notice', handler)
    return () => window.removeEventListener('blacknode:notice', handler)
  }, [])

  useEffect(() => {
    if (serverOk) {
      lastBackendNotice.current = null
      return
    }
    if (!serverError || lastBackendNotice.current === serverError) return
    lastBackendNotice.current = serverError
    setNotice({
      kind: 'error',
      title: 'Backend disconnected',
      message: serverError,
    })
    if (noticeTimer.current) clearTimeout(noticeTimer.current)
    noticeTimer.current = setTimeout(() => setNotice(null), 9000)
  }, [serverError, serverOk])

  useEffect(() => {
    if (!tabMenu) return
    const close = () => setTabMenu(null)
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [tabMenu])

  useEffect(() => {
    if (!nodeMenu) return
    const close = () => setNodeMenu(null)
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [nodeMenu])

  useEffect(() => {
    if (!pendingClose || closeSaving) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPendingClose(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [closeSaving, pendingClose])

  useEffect(() => {
    checkServer().then(() => {
      loadApiKeys()
      loadApiKeyStatus()
      loadCustomModels()
      loadLearnedNodes()
      loadNodeTypes()
      loadGraph()
      loadDriverStatus()
      loadRuntimeNodeOutputs()
      loadSpatialViewerNodeOutputs()
      loadDrivers()
    })
    const id = setInterval(checkServer, 5000)
    // Poll running-driver heartbeats so trigger nodes show live/offline truthfully.
    const driverId = setInterval(loadDriverStatus, 4000)
    const runtimeOutputsId = setInterval(loadRuntimeNodeOutputs, 1000)
    // Spatial scenes are cached by their managed workers, so this lightweight
    // poll can deliver responsive point-cloud motion independently of slower
    // ROS/device health checks.
    const spatialViewerOutputsId = setInterval(loadSpatialViewerNodeOutputs, 100)
    return () => {
      clearInterval(id)
      clearInterval(driverId)
      clearInterval(runtimeOutputsId)
      clearInterval(spatialViewerOutputsId)
    }
  }, [])

  useEffect(() => {
    if (!serverOk) return
    const source = new EventSource(api.learnedNodeEventsUrl())
    const handleEvent = (event: MessageEvent) => {
      try {
        void handleLearnedNodeEvent(JSON.parse(event.data))
      } catch {
      }
    }
    source.addEventListener('learned_node_added', handleEvent)
    source.addEventListener('learned_node_deleted', handleEvent)
    source.onmessage = handleEvent
    return () => source.close()
  }, [handleLearnedNodeEvent, serverOk])

  useEffect(() => {
    if (!serverOk) return
    let cancelled = false
    api.listFrameworkExportTargets()
      .then(({ targets }) => {
        if (!cancelled && targets.length) setFrameworkExportTargets(targets)
      })
      .catch(() => {
        if (!cancelled) setFrameworkExportTargets(DEFAULT_FRAMEWORK_EXPORT_TARGETS)
      })
    return () => {
      cancelled = true
    }
  }, [serverOk])

  useEffect(() => {
    if (!serverOk) return
    let cancelled = false
    let running = false

    const consumeActions = async () => {
      if (running) return
      running = true
      try {
        const { actions } = await api.consumeEditorActions()
        for (const action of actions) {
          if (cancelled) break
          if (action.type === 'new_workflow_tab') {
            const name = typeof action.payload?.name === 'string'
              ? action.payload.name
              : undefined
            await newTab(name)
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: `Created workflow tab "${name?.trim() || 'Untitled'}".`,
              },
            }))
          } else if (action.type === 'open_workflow_tab') {
            const workflow = action.payload?.workflow
            if (!workflow || typeof workflow !== 'object') continue
            const record = workflow as Record<string, any>
            const nodeMeta = record.node_meta && typeof record.node_meta === 'object'
              ? record.node_meta as Record<string, any>
              : {}
            const edges = Array.isArray(record.edges) ? record.edges : []
            const name = typeof action.payload?.name === 'string'
              ? action.payload.name
              : typeof record.name === 'string'
                ? record.name
                : 'Untitled'
            await openGraphAsTab(name, {
              nodes: Object.values(nodeMeta),
              edges,
              metadata: (
                record.metadata && typeof record.metadata === 'object'
                  ? record.metadata
                  : {}
              ) as WorkflowMetadata,
            })
            if (action.payload?.organize !== false) {
              await organizeNodes()
              window.requestAnimationFrame(() => {
                window.requestAnimationFrame(() => {
                  rfInstance.current?.fitView({
                    padding: 0.24,
                    maxZoom: 1,
                    duration: 320,
                  })
                })
              })
            }
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: `Opened workflow tab "${name.trim() || 'Untitled'}"${action.payload?.organize === false ? '' : ' and organized it'}.`,
              },
            }))
          } else if (action.type === 'cook_node') {
            const nodeId = typeof action.payload?.node_id === 'string'
              ? action.payload.node_id
              : ''
            const port = typeof action.payload?.port === 'string'
              ? action.payload.port
              : 'value'
            if (!nodeId) continue
            await cookNode(nodeId, port)
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: `Cooked ${nodeId}.${port}.`,
              },
            }))
          } else if (action.type === 'load_saved_workflow_tab') {
            const slug = typeof action.payload?.slug === 'string'
              ? action.payload.slug
              : ''
            if (!slug) continue
            const name = typeof action.payload?.name === 'string'
              ? action.payload.name
              : slug
            await openWorkflowAsTab(slug, name)
            if (action.payload?.organize !== false) {
              await organizeNodes()
              window.requestAnimationFrame(() => {
                window.requestAnimationFrame(() => {
                  rfInstance.current?.fitView({
                    padding: 0.24,
                    maxZoom: 1,
                    duration: 320,
                  })
                })
              })
            }
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: `Loaded saved workflow "${name.trim() || slug}".`,
              },
            }))
          } else if (action.type === 'organize_graph') {
            await organizeNodes()
            window.requestAnimationFrame(() => {
              window.requestAnimationFrame(() => {
                rfInstance.current?.fitView({
                  padding: 0.24,
                  maxZoom: 1,
                  duration: 320,
                })
              })
            })
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: 'Organized current graph.',
              },
            }))
          } else if (action.type === 'rename_tab') {
            const name = typeof action.payload?.name === 'string'
              ? action.payload.name
              : 'Untitled'
            renameTab(activeTabId, name)
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: `Renamed active tab to "${name.trim() || 'Untitled'}".`,
              },
            }))
          } else if (action.type === 'close_tab') {
            await closeTab(activeTabId)
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'MCP',
                message: 'Closed active workflow tab.',
              },
            }))
          } else if (action.type === 'sync_run_event') {
            const record = action.payload?.record
            if (!record || typeof record !== 'object') continue
            const events = (record as { events?: unknown }).events
            if (!Array.isArray(events)) continue
            const cursor = typeof action.payload?.cursor === 'number'
              ? action.payload.cursor
              : events.length - 1
            const playing = action.payload?.playing !== false
            applyRunReplay(record as any, cursor, playing)
          }
        }
      } catch {
      } finally {
        running = false
      }
    }

    void consumeActions()
    const id = setInterval(consumeActions, 1000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [
    activeTabId,
    applyRunReplay,
    closeTab,
    cookNode,
    newTab,
    openGraphAsTab,
    openWorkflowAsTab,
    organizeNodes,
    renameTab,
    serverOk,
  ])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') void exitSubnet()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [exitSubnet])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.shiftKey) return
      if (isEditableTarget(e.target)) return
      const key = e.key.toLowerCase()
      if (key === 'z') {
        e.preventDefault()
        void undoGraph()
      } else if (key === 'c') {
        const clipboard = copySelection()
        if (!clipboard) return
        e.preventDefault()
        graphClipboard.current = clipboard
      } else if (key === 'v') {
        const clipboard = graphClipboard.current
        if (!clipboard || !rfInstance.current) return
        e.preventDefault()
        const target = lastMouseFlowPos.current
          ?? rfInstance.current.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 })
        void pasteClipboard(clipboard, target)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [copySelection, pasteClipboard, undoGraph])

  const fitCurrentCanvas = useCallback((duration = 280) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        rfInstance.current?.fitView({
          padding: 0.24,
          maxZoom: 1,
          duration,
        })
      })
    })
  }, [])

  useEffect(() => {
    const handler = () => fitCurrentCanvas(320)
    window.addEventListener('blacknode:fit-view', handler)
    return () => window.removeEventListener('blacknode:fit-view', handler)
  }, [fitCurrentCanvas])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{
        robotId?: string
        robotName?: string
      }>).detail
      const robotId = String(detail?.robotId || '').trim()
      const robotName = String(detail?.robotName || '').trim()
      if (!robotId) return

      void (async () => {
        try {
          if (!useStore.getState().nodeTypes.includes('RobotMonitor')) {
            window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
              detail: { tab: 'packages' },
            }))
            window.dispatchEvent(new CustomEvent('blacknode:notice', {
              detail: {
                kind: 'info',
                title: 'Robot package required',
                message: 'Install or reload blacknode-robot to add the Robot Monitor node.',
              },
            }))
            return
          }
          window.dispatchEvent(new CustomEvent('blacknode:close-panel'))
          let target = useStore.getState().nodes.find(node => (
            node.data.type === 'RobotMonitor'
            && String(node.data.params?.robot_id || '') === robotId
          ))
          if (!target) {
            const before = new Set(useStore.getState().nodes.map(node => node.id))
            const position = rfInstance.current?.screenToFlowPosition({
              x: window.innerWidth / 2,
              y: window.innerHeight / 2,
            }) ?? { x: 120, y: 100 }
            await addNode('RobotMonitor', position, {
              robot_id: robotId,
              robot_name: robotName,
            })
            target = useStore.getState().nodes.find(node => (
              !before.has(node.id) && node.data.type === 'RobotMonitor'
            ))
          } else if (robotName && target.data.params?.robot_name !== robotName) {
            await updateParam(target.id, 'robot_name', robotName)
            target = useStore.getState().nodes.find(node => node.id === target?.id) ?? target
          }
          if (!target) throw new Error('The Robot Monitor node was not created.')

          const live = useStore.getState()
          live.onNodesChange(live.nodes.map(node => ({
            id: node.id,
            type: 'select' as const,
            selected: node.id === target?.id,
          })))
          selectNode(target.id)
          window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
              rfInstance.current?.setCenter(
                target!.position.x + 380,
                target!.position.y + 240,
                { zoom: 0.9, duration: 320 },
              )
            })
          })
        } catch (error) {
          window.dispatchEvent(new CustomEvent('blacknode:notice', {
            detail: {
              kind: 'error',
              title: 'Monitor could not open',
              message: error instanceof Error ? error.message : String(error),
            },
          }))
        }
      })()
    }
    window.addEventListener('blacknode:monitor-robot', handler)
    return () => window.removeEventListener('blacknode:monitor-robot', handler)
  }, [addNode, selectNode, updateParam])

  const importWorkflowFile = useCallback(async (file: File) => {
    if (importingFile) return
    setImportingFile(true)
    try {
      const text = await file.text()
      const name = fileBaseName(file.name) || 'Imported Workflow'
      const lowerName = file.name.toLowerCase()
      let tabName = name
      let nodeMeta: Record<string, any> = {}
      let edges: any[] = []
      let metadata: WorkflowMetadata = {}
      let sourceLabel = 'workflow'

      if (lowerName.endsWith('.py')) {
        const result = await api.importPython(text, name)
        if (!result.validation.ok) {
          const firstError = result.validation.errors[0]
          throw new Error(String(firstError?.message ?? 'Imported Python did not validate.'))
        }
        const workflow = result.workflow
        tabName = workflow.name?.trim() || name
        nodeMeta = workflow.node_meta && typeof workflow.node_meta === 'object'
          ? workflow.node_meta
          : {}
        edges = Array.isArray(workflow.edges) ? workflow.edges : []
        metadata = (
          workflow.metadata && typeof workflow.metadata === 'object'
            ? workflow.metadata
            : {}
        ) as WorkflowMetadata
        sourceLabel = 'Python'
      } else {
        const parsed = JSON.parse(text)
        const workflow = parsed?.workflow && typeof parsed.workflow === 'object'
          ? parsed.workflow
          : parsed
        if (workflow?.node_meta && typeof workflow.node_meta === 'object') {
          tabName = typeof workflow.name === 'string' && workflow.name.trim() ? workflow.name : name
          nodeMeta = workflow.node_meta as Record<string, any>
          edges = Array.isArray(workflow.edges) ? workflow.edges : []
          metadata = (
            workflow.metadata && typeof workflow.metadata === 'object'
              ? workflow.metadata
              : {}
          ) as WorkflowMetadata
        } else if (Array.isArray(workflow?.nodes)) {
          tabName = typeof workflow.name === 'string' && workflow.name.trim() ? workflow.name : name
          nodeMeta = Object.fromEntries(
            workflow.nodes
              .filter((node: any) => node && typeof node === 'object' && typeof node.id === 'string')
              .map((node: any) => [node.id, node])
          )
          edges = Array.isArray(workflow.edges) ? workflow.edges : []
          metadata = (
            workflow.metadata && typeof workflow.metadata === 'object'
              ? workflow.metadata
              : {}
          ) as WorkflowMetadata
        } else {
          throw new Error('Drop a Blacknode workflow JSON file or a Blacknode-generated Python/LangGraph export.')
        }
        sourceLabel = 'workflow JSON'
      }

      if (Object.keys(nodeMeta).length === 0) {
        throw new Error('Imported file has no workflow nodes.')
      }

      await openGraphAsTab(tabName, {
        nodes: Object.values(nodeMeta),
        edges,
        metadata,
      })
      await organizeNodes()
      fitCurrentCanvas(320)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'Import',
          message: `Imported ${Object.keys(nodeMeta).length} nodes from ${file.name} (${sourceLabel}).`,
        },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Import failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setImportingFile(false)
    }
  }, [fitCurrentCanvas, importingFile, openGraphAsTab, organizeNodes])

  const handleImageDrop = useCallback(async (file: File, screenPoint: { x: number; y: number }) => {
    if (!rfInstance.current) return
    try {
      const source = await readFileAsDataUrl(file)
      const nodeId = nodeIdAtScreenPoint(screenPoint)
      const targetNode = nodeId ? nodes.find(node => node.id === nodeId) : null
      if (targetNode?.data?.type === 'LoadImage') {
        await updateParam(targetNode.id, 'source', source)
        selectNode(targetNode.id)
        window.dispatchEvent(new CustomEvent('blacknode:notice', {
          detail: {
            kind: 'info',
            title: 'Image loaded',
            message: `Loaded ${file.name} into LoadImage.`,
          },
        }))
        return
      }

      const pos = rfInstance.current.screenToFlowPosition(screenPoint)
      await addNode('LoadImage', pos, { source })
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'Image node created',
          message: `Created LoadImage from ${file.name}.`,
        },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Image drop failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    }
  }, [addNode, nodes, selectNode, updateParam])

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files ?? [])
    if (files.length > 0) {
      e.stopPropagation()
      if (isImageFile(files[0])) {
        void handleImageDrop(files[0], { x: e.clientX, y: e.clientY })
        return
      }
      void importWorkflowFile(files[0])
      return
    }
    const type = e.dataTransfer.getData('application/blacknode-type')
    if (!type || !rfInstance.current) return
    const paramsRaw = e.dataTransfer.getData('application/blacknode-params')
    const params = paramsRaw ? JSON.parse(paramsRaw) : {}
    const pos = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNode(type, pos, params)
  }, [addNode, handleImageDrop, importWorkflowFile])

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = Array.from(e.dataTransfer.types).includes('Files') ? 'copy' : 'move'
  }

  const trackMouseFlowPos = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!rfInstance.current) return
    lastMouseFlowPos.current = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
  }, [])

  const onPaneContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    if (!rfInstance.current) return
    const flowPos = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    setSearch({ screenPos: { x: e.clientX, y: e.clientY }, flowPos })
  }, [])

  const handleSearchSelect = useCallback((type: string) => {
    if (!search) return
    const preset = resolvePythonToolPreset(type)
    const typeName = preset?.type ?? type
    const params = preset ? { ...preset.params } : {}
    if (search.connect) {
      addNodeFromConnection(typeName, search.flowPos, search.connect, params)
    } else {
      addNode(typeName, search.flowPos, params)
    }
    setSearch(null)
  }, [search, addNode, addNodeFromConnection])

  const edgeReconnected = useRef(false)
  const onEdgeUpdateStart = useCallback(() => {
    edgeReconnected.current = false
    edgeUpdateActive.current = true
    suppressConnectMenuUntil.current = Date.now() + 500
    connectionDraft.current = null
  }, [])
  const onEdgeUpdate = useCallback((oldEdge: Edge, newConn: Connection) => {
    edgeReconnected.current = true
    reconnectEdge(oldEdge, newConn)
  }, [reconnectEdge])
  const onEdgeUpdateEnd = useCallback((_: MouseEvent | TouchEvent, edge: Edge) => {
    if (!edgeReconnected.current) disconnectEdge(edge.id)
    suppressConnectMenuUntil.current = Date.now() + 200
    window.setTimeout(() => { edgeUpdateActive.current = false }, 0)
  }, [disconnectEdge])
  const onEdgeDoubleClick = useCallback((_: React.MouseEvent, edge: any) => {
    disconnectEdge(edge.id)
  }, [disconnectEdge])
  const handleConnect = useCallback((conn: Connection) => {
    connectionMade.current = true
    connectionDraft.current = null
    return storeOnConnect(conn)
  }, [storeOnConnect])
  const onConnectStart = useCallback((_: React.MouseEvent | React.TouchEvent, params: any) => {
    connectionMade.current = false
    if (edgeUpdateActive.current || Date.now() < suppressConnectMenuUntil.current) {
      connectionDraft.current = null
      return
    }
    const nodeId = params?.nodeId
    const handleId = params?.handleId
    const handleType = params?.handleType
    if (!nodeId || !handleId || (handleType !== 'source' && handleType !== 'target')) {
      connectionDraft.current = null
      return
    }
    const node = nodes.find(n => n.id === nodeId)
    const portType = handleType === 'source'
      ? node?.data.output_types?.[handleId]
      : node?.data.input_types?.[handleId]
    connectionDraft.current = { nodeId, handleId, handleType, portType: portType ?? 'Any' }
  }, [nodes])
  const onConnectEnd = useCallback((event: MouseEvent | TouchEvent) => {
    const draft = connectionDraft.current
    connectionDraft.current = null
    if (edgeUpdateActive.current || Date.now() < suppressConnectMenuUntil.current) return
    if (connectionMade.current || !draft || !rfInstance.current) return
    const point = clientPointFromEvent(event)
    if (!point) return
    const flowPos = rfInstance.current.screenToFlowPosition(point)
    if (draft.handleType === 'source' && portsCompatible(draft.portType, 'Fn')) {
      const toolBoxId = findToolBoxAtScreenPoint(nodes, point) ?? findToolBoxAtPoint(nodes, flowPos)
      if (toolBoxId) {
        connectionMade.current = true
        void storeOnConnect({
          source: draft.nodeId,
          sourceHandle: draft.handleId,
          target: toolBoxId,
          targetHandle: '__new__',
        })
        return
      }
    }
    const hasNodeDefs = Object.keys(nodeDefs).length > 0
    const compatibleTypes = hasNodeDefs ? getCompatibleNodeTypes(draft, nodeDefs) : []
    if (hasNodeDefs && compatibleTypes.length === 0) return
    suppressPaneClick.current = true
    window.setTimeout(() => { suppressPaneClick.current = false }, 200)
    setSearch({ screenPos: point, flowPos, connect: draft })
  }, [nodeDefs, nodes, storeOnConnect])

  const onNodeDragStart = useCallback((event: React.MouseEvent, node: any) => {
    if (!event.altKey) {
      altDragCopy.current = null
      return
    }
    const selectedNodes = nodes.filter(n => n.selected)
    const copyNodes = node.selected && selectedNodes.length > 1
      ? selectedNodes
      : nodes.filter(n => n.id === node.id)
    const nodeIds = copyNodes.map(n => n.id)
    const originalPositions = Object.fromEntries(copyNodes.map(n => [
      n.id,
      { x: n.position.x, y: n.position.y },
    ]))
    altDragCopy.current = {
      nodeIds,
      originalPositions,
      copyPromise: beginAltDragCopy(nodeIds, originalPositions),
    }
  }, [beginAltDragCopy, nodes])

  const onNodeDragStop = useCallback(() => {
    const copy = altDragCopy.current
    altDragCopy.current = null
    if (!copy) return
    void copy.copyPromise.then(copyIdMap =>
      finishAltDragCopy(copy.nodeIds, copy.originalPositions, copyIdMap)
    ).catch(console.error)
  }, [finishAltDragCopy])

  const startTabRename = useCallback((tab: { id: string; name: string }) => {
    setTabMenu(null)
    setEditingTabId(tab.id)
    setTabDraft(tab.name)
  }, [])

  const commitTabRename = useCallback(() => {
    if (editingTabId) renameTab(editingTabId, tabDraft)
    setEditingTabId(null)
    setTabDraft('')
  }, [editingTabId, renameTab, tabDraft])

  const handleSaveWorkflow = useCallback(async () => {
    if (!activeTab) return
    const name = (editingTabId === activeTabId ? tabDraft : activeTab.name).trim() || 'Untitled'
    if (editingTabId === activeTabId) {
      renameTab(activeTabId, name)
      setEditingTabId(null)
      setTabDraft('')
    }
    setSavingWorkflow(true)
    setSaveOk(false)
    try {
      await saveActiveWorkflow(name)
      setSaveOk(true)
      if (saveOkTimer.current) clearTimeout(saveOkTimer.current)
      saveOkTimer.current = setTimeout(() => setSaveOk(false), 1800)
    } finally {
      setSavingWorkflow(false)
    }
  }, [activeTab, activeTabId, editingTabId, renameTab, saveActiveWorkflow, tabDraft])

  const closeTabNow = useCallback(async (tabId: string) => {
    if (editingTabId === tabId) {
      setEditingTabId(null)
      setTabDraft('')
    }
    await closeTab(tabId)
  }, [closeTab, editingTabId])

  const requestCloseTab = useCallback((tabId: string) => {
    setTabMenu(null)
    const tab = tabs.find(item => item.id === tabId)
    if (!tab) return
    if (tab.dirty) {
      const draftName = (editingTabId === tabId ? tabDraft : tab.name).trim() || 'Untitled'
      setPendingClose({ tabId, draftName })
      return
    }
    void closeTabNow(tabId)
  }, [closeTabNow, editingTabId, tabDraft, tabs])

  const cancelPendingClose = useCallback(() => {
    if (closeSaving) return
    setPendingClose(null)
  }, [closeSaving])

  const discardPendingClose = useCallback(async () => {
    if (!pendingClose || closeSaving) return
    const tabId = pendingClose.tabId
    setPendingClose(null)
    await closeTabNow(tabId)
  }, [closeSaving, closeTabNow, pendingClose])

  const savePendingClose = useCallback(async () => {
    if (!pendingClose || closeSaving) return
    if (!pendingClose.draftName.trim()) return
    const tab = tabs.find(item => item.id === pendingClose.tabId)
    if (!tab) {
      setPendingClose(null)
      return
    }
    setCloseSaving(true)
    try {
      const name = pendingClose.draftName.trim() || 'Untitled'
      if (editingTabId === tab.id) {
        renameTab(tab.id, name)
        setEditingTabId(null)
        setTabDraft('')
      }
      if (tab.id !== activeTabId) {
        await switchTab(tab.id)
      }
      await saveActiveWorkflow(name)
      setPendingClose(null)
      await closeTab(tab.id)
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Save failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setCloseSaving(false)
    }
  }, [activeTabId, closeSaving, closeTab, editingTabId, pendingClose, renameTab, saveActiveWorkflow, switchTab, tabs])

  const handleOrganize = useCallback(async () => {
    await organizeNodes()
    fitCurrentCanvas(320)
  }, [fitCurrentCanvas, organizeNodes])

  const handleRefreshCanvas = useCallback(async () => {
    if (refreshingCanvas) return
    setRefreshingCanvas(true)
    try {
      const result = await api.refreshCanvasSchemas()
      if (!result.ok) {
        const failedFile = result.failed[0]?.path?.split(/[\\/]/).pop()
        throw new Error(failedFile
          ? `Could not reload ${failedFile}. Open it in Script to fix the Python error.`
          : 'A custom-node file could not be reloaded. Open Script to check its Python code.')
      }
      await Promise.all([loadNodeTypes(), loadGraph()])
      const fileCount = result.loaded.length
      const nodeCount = result.updated_nodes.length
      const edgeCount = result.removed_edges.length
      const parts = [
        `Reloaded ${fileCount} custom-node file${fileCount === 1 ? '' : 's'}`,
        `updated ${nodeCount} canvas node${nodeCount === 1 ? '' : 's'}`,
      ]
      if (edgeCount) {
        parts.push(`removed ${edgeCount} connection${edgeCount === 1 ? '' : 's'} to deleted ports`)
      }
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'Canvas refreshed',
          message: `${parts.join(', ')}.`,
        },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Refresh failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setRefreshingCanvas(false)
    }
  }, [loadGraph, loadNodeTypes, refreshingCanvas])

  const handleRunGraph = useCallback(async (runMode: 'once' | 'live' = 'once') => {
    const entrypointTarget = workflowEntrypoint && nodes.some(node => (
      node.id === workflowEntrypoint.node_id
      && (node.data.outputs.includes(workflowEntrypoint.port) || node.data.inputs.includes(workflowEntrypoint.port))
    ))
      ? { id: workflowEntrypoint.node_id, port: workflowEntrypoint.port }
      : null
    const targets = entrypointTarget ? [entrypointTarget] : inferGraphRunTargets(nodes, edges)
    if (targets.length === 0) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'warning',
          title: 'Run',
          message: 'No runnable terminal node found in the current graph.',
        },
      }))
      return
    }
    fitCurrentCanvas(220)
    const liveCapable = nodes.filter(node => node.data.live_capable).length
    const effectiveMode = runMode === 'live' && liveCapable > 0 ? 'live' : 'once'
    if (runMode === 'live' && liveCapable === 0) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'No live nodes in this graph',
          message: 'This graph has no streaming-capable nodes, so Blacknode is running it once.',
        },
      }))
    }
    setActiveRunMode(effectiveMode)
    try {
      await cookNode(targets[0].id, targets[0].port, targets, effectiveMode)
    } finally {
      setActiveRunMode(current => current === effectiveMode ? null : current)
    }
  }, [cookNode, edges, fitCurrentCanvas, nodes, workflowEntrypoint])

  const handleCloudRun = useCallback(async () => {
    if (cloudJobPending) return
    const explicit = workflowEntrypoint && nodes.some(node => (
      node.id === workflowEntrypoint.node_id
      && (node.data.outputs.includes(workflowEntrypoint.port) || node.data.inputs.includes(workflowEntrypoint.port))
    ))
      ? { id: workflowEntrypoint.node_id, port: workflowEntrypoint.port }
      : null
    const target = explicit ?? inferGraphRunTargets(nodes, edges)[0]
    if (!target) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'warning',
          title: 'Run on Cloud',
          message: 'No runnable workflow output was found. Add an Output node or select an entrypoint.',
        },
      }))
      return
    }
    setCloudPanelView('account')
    setCloudPanelOpen(true)
    setCloudJobPending(true)
    setCloudJobError('')
    try {
      const accountStatus = await api.cloudStatus()
      setCloudAccountStatus(accountStatus)
      if (!accountStatus.configured) {
        setCloudJobError('Configure the Blacknode Cloud URL on the editor server.')
        return
      }
      if (!accountStatus.authenticated) return
      if (!accountStatus.account?.email_verified_at) {
        setCloudJobError('Verify your email address before running workflows on Blacknode Cloud.')
        return
      }
      setCloudJob(null)
      const created = await api.createCloudJob(
        { node_id: target.id, port: target.port },
        activeTab?.name || 'Current Graph',
        activeProject?.id ?? activeTab?.slug ?? null,
      )
      setCloudJob(created)
      setCloudPanelView('job')
      void api.cloudStatus().then(setCloudAccountStatus).catch(() => undefined)
    } catch (cause) {
      setCloudJobError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setCloudJobPending(false)
    }
  }, [activeProject?.id, activeTab?.name, activeTab?.slug, cloudJobPending, edges, nodes, workflowEntrypoint])

  const handleCloudAccountOpen = useCallback(async () => {
    if (cloudJobPending || !serverOk) return
    setCloudPanelView('account')
    setCloudPanelOpen(true)
    setCloudJobError('')
    setCloudJobPending(true)
    try {
      setCloudAccountStatus(await api.cloudStatus())
    } catch (cause) {
      setCloudJobError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setCloudJobPending(false)
    }
  }, [cloudJobPending, serverOk])

  const handleCloudVlaRun = useCallback(async (request: {
    dataset_uri: string
    dataset_revision: string
    steps: number
    batch_size: number
    action_horizon: number
    max_runtime_seconds: number
  }) => {
    if (cloudJobPending) return
    setCloudJobPending(true)
    setCloudJobError('')
    try {
      setCloudJob(null)
      const created = await api.createCloudVlaJob({
        ...request,
        project_ref: activeProject?.id ?? activeTab?.slug ?? null,
      })
      setCloudJob(created)
      setCloudPanelView('job')
      void api.cloudStatus().then(setCloudAccountStatus).catch(() => undefined)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setCloudJobError(message)
      throw cause
    } finally {
      setCloudJobPending(false)
    }
  }, [activeProject?.id, activeTab?.slug, cloudJobPending])

  const handleCloudJobCompleted = useCallback((job: CloudJob) => {
    if (!activeProject || job.result === null || job.result === undefined) return
    void api.importProjectArtifacts(activeProject.id, {
      node_type: job.workload_kind === 'vla_train' ? 'OpenPIFineTune' : '',
      value: job.result,
    }).then(() => {
      useStore.setState(state => ({ projectRevision: state.projectRevision + 1 }))
    }).catch(() => undefined)
  }, [activeProject])

  const handleResetRun = useCallback(() => {
    stopCook()
    setActiveRunMode(null)
    window.dispatchEvent(new CustomEvent('blacknode:notice', {
      detail: {
        kind: 'info',
        title: 'Run reset',
        message: 'Cleared running state and asked the backend to stop active work.',
      },
    }))
  }, [stopCook])

  const handleStopRuntime = useCallback(async () => {
    if (runtimeStopPending) return
    // Stop is authoritative from the moment it is requested. Do not let an
    // unreachable device keep the top-level live state latched on.
    setActiveRunMode(null)
    setRuntimeStopPending(true)
    try {
      const result = await stopRuntimeServices()
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: result.ok ? 'info' : 'error',
          title: result.ok ? 'Runtime stopped' : 'Runtime stop failed',
          message: result.report || result.error || 'Stopped workflow runtime services.',
        },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Runtime stop failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setRuntimeStopPending(false)
      setActiveRunMode(null)
    }
  }, [runtimeStopPending, stopRuntimeServices])

  const handleFrameworkExport = useCallback(async (target: string) => {
    if (!target || exportingTarget) return
    setExportingTarget(target)
    try {
      const result = await api.exportFramework(target)
      downloadTextFile(result.filename, result.code)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'Framework export',
          message: `${result.label} exported as ${result.filename}.`,
        },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Export failed',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setExportingTarget('')
    }
  }, [exportingTarget])

  const handlePythonImport = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file) return
    await importWorkflowFile(file)
  }, [importWorkflowFile])

  const runTabMenuAction = useCallback((action: () => void | Promise<void>) => {
    setTabMenu(null)
    void action()
  }, [])

  const openTabMenu = useCallback((e: React.MouseEvent, tabId: string) => {
    e.preventDefault()
    e.stopPropagation()
    setTabMenu({ x: e.clientX, y: e.clientY, tabId })
  }, [])

  const topbarH = 52
  const leftRailW = 78
  const workflowTabsTop = topbarH + WORKFLOW_SHORTCUT_H
  const canvasPad = workflowTabsTop + TAB_H
  const liveStreamCount = nodes.filter(n => (
    LIVE_STREAM_NODE_TYPES.has(n.data.type) &&
    n.data.portResults?.streaming === true
  )).length
  const cameraStreamCount = nodes.filter(n => (
    n.data.type.startsWith('Camera')
    && n.data.portResults?.streaming === true
  )).length
  const managedRunCount = nodes.filter(n => n.data.type === 'ROS2Run' && n.data.portResults?.running === true).length
  const simulationRunCount = nodes.filter(n => n.data.type === 'NewtonSimulation' && n.data.portResults?.running === true).length
  const controllerNodes = nodes.filter(n => (
    n.data.type === 'RobotFollow'
    || n.data.type === 'ROS2LeaderFollower'
    || n.data.type === 'ROS2JointController'
  ))
  const controllerRunningCount = controllerNodes.filter(n => n.data.portResults?.running === true).length
  const controllerCount = controllerNodes.filter(n => n.data.portResults?.live === true).length
  const blockedControllerCount = controllerNodes.filter(n => (
    n.data.portResults?.running === true
    && n.data.portResults?.live !== true
    && /^(blocked|failed|error)\b/i.test(String(n.data.portResults?.report ?? '').trim())
  )).length
  const waitingControllerCount = Math.max(0, controllerRunningCount - controllerCount - blockedControllerCount)
  const manualMoveCount = nodes.filter(n => n.data.type === 'ROS2ManualMove' && n.data.portResults?.live === true).length
  const liveDashboardCount = nodes.filter(n => n.data.type === 'ROS2MotionDashboard' && n.data.portResults?.live === true).length
  const visualizerRunCount = nodes.filter(n => (
    VIEWER_NODE_TYPES.has(n.data.type)
    && n.data.portResults?.running === true
  )).length
  const liveCapableCount = nodes.filter(n => n.data.live_capable).length
  // The node card treats any live-capable node with an active runtime flag as
  // live. Keep the global control aligned with that generic contract so new
  // ROS 2 and package nodes do not need to be added to a hard-coded list here.
  const liveCapableRuntimeCount = nodes.filter(n => (
    n.data.live_capable === true
    && (
      n.data.portResults?.live === true
      || n.data.portResults?.running === true
      || n.data.portResults?.streaming === true
      || n.data.portResults?.launched === true
    )
  )).length
  const runOnceNodeCount = Math.max(0, nodes.length - liveCapableCount)
  const runtimeActive = liveCapableRuntimeCount > 0 || liveStreamCount > 0 || managedRunCount > 0 || simulationRunCount > 0 || controllerRunningCount > 0 || manualMoveCount > 0 || liveDashboardCount > 0 || visualizerRunCount > 0
  const liveRunActive = (cookActive && activeRunMode === 'live') || runtimeActive
  const onceRunActive = cookActive && activeRunMode !== 'live'
  const visibleEdges = useMemo(() => {
    const nodesById = new Map(nodes.map(node => [node.id, node]))
    return edges.map(edge => {
      const connected = !selectedId || edge.source === selectedId || edge.target === selectedId
      const source = nodesById.get(edge.source)
      const sourceActive = Boolean(
        source?.data?.cooking
        || source?.data?.replayStatus === 'running'
        || source?.data?.replayStatus === 'model'
        || source?.data?.replayStatus === 'tool'
        || source?.data?.portResults?.streaming === true
        || source?.data?.portResults?.running === true
        || source?.data?.portResults?.live === true,
      )
      const portHovered = Boolean(hoveredPort && (
        (
          hoveredPort.dir === 'output'
          && edge.source === hoveredPort.nodeId
          && edge.sourceHandle === hoveredPort.port
        )
        || (
          hoveredPort.dir === 'input'
          && edge.target === hoveredPort.nodeId
          && edge.targetHandle === hoveredPort.port
        )
      ))
      const sourceType = String(source?.data?.output_types?.[edge.sourceHandle || ''] ?? 'Any')
      const target = nodesById.get(edge.target)
      const targetType = String(target?.data?.input_types?.[edge.targetHandle || ''] ?? 'Any')
      const wireType = sourceType === 'Any' ? targetType : sourceType
      return {
        ...edge,
        style: {
          ...edge.style,
          stroke: edge.style?.stroke ?? portColor(wireType),
          '--bn-edge-color': portVisualColor(wireType),
        } as React.CSSProperties,
        className: [
          edge.className,
          selectedId ? (connected ? 'bn-edge-connected' : 'bn-edge-dimmed') : '',
          sourceActive ? 'bn-edge-executing' : '',
          edge.id === hoveredEdgeId ? 'bn-edge-hovered' : '',
          portHovered ? 'bn-edge-port-hover' : '',
        ]
          .filter(Boolean)
          .join(' '),
      }
    })
  }, [edges, hoveredEdgeId, hoveredPort, nodes, selectedId])
  const visibleNodes = useMemo(() => {
    const endpoints = new Set<string>()
    if (hoveredEdgeId) {
      const edge = edges.find(candidate => candidate.id === hoveredEdgeId)
      if (edge) {
        endpoints.add(edge.source)
        endpoints.add(edge.target)
      }
    }
    if (hoveredPort) {
      endpoints.add(hoveredPort.nodeId)
      for (const edge of edges) {
        const matches = hoveredPort.dir === 'output'
          ? edge.source === hoveredPort.nodeId && edge.sourceHandle === hoveredPort.port
          : edge.target === hoveredPort.nodeId && edge.targetHandle === hoveredPort.port
        if (matches) {
          endpoints.add(edge.source)
          endpoints.add(edge.target)
        }
      }
    }
    if (endpoints.size === 0) return nodes
    return nodes.map(node => ({
      ...node,
      className: [node.className, endpoints.has(node.id) ? 'bn-wire-endpoint' : '']
        .filter(Boolean)
        .join(' '),
    }))
  }, [edges, hoveredEdgeId, hoveredPort, nodes])
  const cloudProviderLabel = cloudAccountStatus?.compute_providers?.options.find(
    option => option.id === (
      cloudAccountStatus.account?.compute_provider_preference
        ?? cloudAccountStatus.compute_providers?.preference
    ),
  )?.label ?? 'Auto'
  return (
    <div className={`bn-editor-shell${activeOperatorView ? ' is-operator-view' : ''}`} style={{ display: 'flex', height: '100vh', background: 'var(--bg)' }}>
      {!activeOperatorView && <NodePalette />}

      <div className="bn-editor-main" style={{ flex: 1, position: 'relative' }} onDrop={onDrop} onDragOver={onDragOver} onMouseMove={trackMouseFlowPos}>

        {/* ── top bar ── */}
        <div className={`bn-topbar${hostedPreview ? ' is-hosted-preview' : ''}`} style={{
          position: 'fixed', top: 0, left: activeOperatorView ? 0 : leftRailW, right: 0, zIndex: 50,
          background: 'var(--panel)',
          borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center',
          height: topbarH,
        }}>
          <div
            className="bn-brand"
            aria-label="Blacknode"
            style={{ width: 'var(--bn-palette-panel-width, 240px)', padding: '0 18px' }}
          >
            <img
              className="bn-brand-logo"
              src="/blacknode-logo.png"
              alt=""
            />
            <span>BLACKNODE</span>
          </div>

          <div className="bn-topbar-controls">
            <div className="bn-topbar-group bn-topbar-file-group" aria-label="File controls">
              <input
                ref={pythonImportInput}
                type="file"
                accept=".py,.json,application/json,text/x-python"
                style={{ display: 'none' }}
                onChange={handlePythonImport}
              />

              <button
                ref={fileMenuTriggerRef}
                type="button"
                className="bn-top-button bn-file-menu-trigger"
                onClick={() => {
                  setSimulationViewerMenuOpen(false)
                  setFileMenuOpen(open => !open)
                }}
                disabled={!serverOk || importingFile || Boolean(exportingTarget)}
                title="Import or export a workflow"
                aria-haspopup="menu"
                aria-expanded={fileMenuOpen}
              >
                {importingFile ? 'Importing…' : exportingTarget ? 'Exporting…' : 'File'}
                <span aria-hidden="true">▾</span>
              </button>

              {fileMenuOpen && createPortal(
                <div
                  ref={fileMenuRef}
                  className="bn-simulation-viewer-menu-items bn-file-menu-items is-portal"
                  role="menu"
                  style={fileMenuPosition}
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setFileMenuOpen(false)
                      pythonImportInput.current?.click()
                    }}
                  >
                    <span>Import workflow…</span>
                    <small>JSON or Python</small>
                  </button>
                  <div className="bn-file-menu-divider" role="separator" />
                  <span className="bn-file-menu-label">Export as</span>
                  {frameworkExportTargets.map(target => (
                    <button
                      key={target.id}
                      type="button"
                      role="menuitem"
                      disabled={nodes.length === 0}
                      onClick={() => {
                        setFileMenuOpen(false)
                        void handleFrameworkExport(target.id)
                      }}
                    >
                      <span>{target.label}</span>
                      <small>{target.extension}</small>
                    </button>
                  ))}
                </div>,
                document.body,
              )}
            </div>

            <div className="bn-topbar-group bn-topbar-run-group" aria-label="Run controls">
              {hostedPreview && <span className="bn-hosted-preview-badge">WEB PREVIEW</span>}
              {hostedPreview ? (
                <span className="bn-hosted-target-badge" title={`Runs on Blacknode Cloud via ${cloudProviderLabel} using one NVIDIA L40S`}>
                  Cloud · {cloudProviderLabel} · L40S
                </span>
              ) : (
                <select
                  className="bn-top-select"
                  value={executionTarget}
                  disabled={onceRunActive || liveRunActive || cloudJobPending}
                  onChange={event => setExecutionTarget(event.target.value === 'cloud' ? 'cloud' : 'local')}
                  title="Choose where this graph executes"
                >
                  <option value="local">Local</option>
                  <option value="cloud">Blacknode Cloud · {cloudProviderLabel} · L40S</option>
                </select>
              )}
              {executionTarget === 'cloud' && cloudAccountStatus?.credits && (
                <span className="bn-cloud-credit-badge" title="Available Blacknode Cloud GPU-second credits">
                  {cloudAccountStatus.credits.available.toLocaleString()} credits
                </span>
              )}
              <button
                className="bn-top-button bn-top-run-button"
                onClick={() => {
                  if (executionTarget === 'cloud') void handleCloudRun()
                  else if (onceRunActive) stopCook()
                  else void handleRunGraph('once')
                }}
                disabled={!serverOk || liveRunActive || (!onceRunActive && nodes.length === 0)}
                title={executionTarget === 'cloud'
                  ? `Submit this graph to Blacknode Cloud via ${cloudProviderLabel} on one NVIDIA L40S.`
                  : onceRunActive
                    ? 'Stop the current one-time evaluation'
                    : 'Evaluate the graph once. Live-capable nodes return one snapshot and do not keep streaming.'}
              >
                {executionTarget === 'cloud'
                  ? cloudJobPending ? 'Submitting…' : '☁ Run on Cloud'
                  : onceRunActive ? '■ Stop once' : '▶ Run once'}
              </button>

              {!hostedPreview && (
                <button
                  className={`bn-top-button bn-top-run-button bn-top-live-button${liveRunActive ? ' is-stop-live' : ' is-start-live'}`}
                  onClick={() => (liveRunActive ? void handleStopRuntime() : void handleRunGraph('live'))}
                  disabled={executionTarget === 'cloud' || !serverOk || runtimeStopPending || onceRunActive || (!liveRunActive && nodes.length === 0)}
                  title={liveRunActive
                    ? 'Stop the live graph and its managed runtime services.'
                    : liveCapableCount > 0
                    ? `Start ${liveCapableCount} live-capable node${liveCapableCount === 1 ? '' : 's'}; evaluate the other ${runOnceNodeCount} node${runOnceNodeCount === 1 ? '' : 's'} once.`
                    : 'No live-capable nodes are present; this will run the graph once.'}
                >
                  {runtimeStopPending ? 'Stopping live…' : liveRunActive ? '■ Stop live' : '● Go live'}
                </button>
              )}

              <button
                className="bn-top-button bn-top-reset-button"
                onClick={handleResetRun}
                title="Stop active work and clear any stuck running state"
              >
                Reset Run
              </button>
            </div>

            <div className="bn-topbar-group bn-topbar-view-group" aria-label="View controls">
              {!hostedPreview && (
                <>
              <button
                className={`bn-top-button bn-simulation-viewer-toggle${activeSimulationViewer && (simulationViewerVisible || simulationViewerDetached) ? ' is-visible' : ''}`}
                type="button"
                disabled={!newtonWorkspaceAvailable || newtonWorkspaceBusy}
                onClick={() => {
                  if (newtonWorkspace?.open) setSimulationViewerVisible(true)
                  else openNewtonWorkspace()
                }}
                title={simulationViewerDetached
                  ? 'Show the floating Newton workspace inside Blacknode'
                  : newtonWorkspace?.open
                    ? 'Show the Newton workspace above the node canvas'
                    : 'Open Newton with an empty stage'}
              >
                {newtonWorkspaceBusy ? 'Opening Newton…' : newtonWorkspace?.open ? `Newton${simulationViewerDetached ? ' ◫' : ''}` : 'Open Newton'}
              </button>
              <div className="bn-simulation-viewer-menu">
                <button
                  ref={simulationViewerMenuTriggerRef}
                  type="button"
                  className="bn-top-button bn-simulation-viewer-menu-trigger"
                  title="Viewer options"
                  aria-label="Viewer options"
                  aria-haspopup="menu"
                  aria-expanded={simulationViewerMenuOpen}
                  onClick={() => {
                    setFileMenuOpen(false)
                    setSimulationViewerMenuOpen(open => !open)
                  }}
                >
                  ▾
                </button>
                {simulationViewerMenuOpen && createPortal(
                <div
                  ref={simulationViewerMenuRef}
                  className="bn-simulation-viewer-menu-items is-portal"
                  role="menu"
                  style={simulationViewerMenuPosition}
                >
                  {!activeSimulationViewer && (
                    <>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          void controlNewtonWorkspace('open', { provider: 'viser' })
                          setSimulationViewerMenuOpen(false)
                        }}
                      >
                        Open with Viser
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        disabled={!newtonWorkspace?.available_viewers?.includes('ovrtx')}
                        title={newtonWorkspace?.available_viewers?.includes('ovrtx')
                          ? 'Open the RTX renderer inside Blacknode'
                          : 'Enable the optional viewer-ovrtx package component first'}
                        onClick={() => {
                          void controlNewtonWorkspace('open', { provider: 'ovrtx' })
                          setSimulationViewerMenuOpen(false)
                        }}
                      >
                        Open with OVRT (RTX)
                      </button>
                    </>
                  )}
                  {activeSimulationViewer && (
                    <>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setSimulationViewerVisible(visible => !visible)
                          setSimulationViewerMenuOpen(false)
                        }}
                      >
                        {simulationViewerVisible ? 'Hide Newton' : 'Show Newton'}
                      </button>
                      {simulationViewerDetached ? (
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            attachSimulationViewer()
                            setSimulationViewerMenuOpen(false)
                          }}
                        >
                          Attach Newton above canvas
                        </button>
                      ) : (
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            detachSimulationViewer()
                            setSimulationViewerMenuOpen(false)
                          }}
                        >
                          Float Newton in editor
                        </button>
                      )}
                      <button
                        type="button"
                        role="menuitem"
                        disabled={newtonWorkspace?.viewer_provider === 'viser'}
                        onClick={() => {
                          void controlNewtonWorkspace('set_viewer', { provider: 'viser' })
                          setSimulationViewerMenuOpen(false)
                        }}
                      >
                        Use Viser renderer
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        disabled={newtonWorkspace?.viewer_provider === 'ovrtx'
                          || !newtonWorkspace?.available_viewers?.includes('ovrtx')}
                        title={newtonWorkspace?.available_viewers?.includes('ovrtx')
                          ? 'Restart this scene with the RTX renderer'
                          : 'Enable the optional viewer-ovrtx package component first'}
                        onClick={() => {
                          void controlNewtonWorkspace('set_viewer', { provider: 'ovrtx' })
                          setSimulationViewerMenuOpen(false)
                        }}
                      >
                        Use OVRT (RTX) renderer
                      </button>
                    </>
                  )}
                </div>,
                document.body,
                )}
              </div>
                </>
              )}
              <button
                type="button"
                className="bn-top-button bn-top-icon-button"
                onClick={() => void handleOrganize()}
                title="Organize current graph"
                aria-label="Organize current graph"
              >
                <ToolbarIcon name="organize" />
              </button>

              <button
                type="button"
                className="bn-top-button bn-top-icon-button"
                onClick={() => void handleRefreshCanvas()}
                disabled={!serverOk || cookActive || refreshingCanvas}
                title="Reload custom-node files and update sockets on existing canvas nodes"
                aria-label={refreshingCanvas ? 'Refreshing canvas' : 'Refresh canvas'}
              >
                <ToolbarIcon name="refresh" className={refreshingCanvas ? 'is-spinning' : undefined} />
              </button>

              <button
                type="button"
                className="bn-top-button bn-top-icon-button"
                onClick={() => setIsDark(d => !d)}
                title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                <ToolbarIcon name={isDark ? 'light' : 'dark'} />
              </button>

              <button
                className={`bn-top-button bn-ui-test-button${isUiTest ? ' is-active' : ''}`}
                onClick={() => setIsUiTest(active => !active)}
                title={isUiTest ? 'Return to the standard Blacknode interface' : 'Compare the refined UI experiment'}
                aria-pressed={isUiTest}
              >
                UI Test
              </button>

              <button
                type="button"
                className="bn-top-button bn-top-icon-button bn-top-clear-button"
                onClick={() => void reset()}
                title="Clear workflow"
                aria-label="Clear workflow"
              >
                <ToolbarIcon name="clear" />
              </button>
            </div>

            <button
              className="bn-top-button bn-top-save-button"
              onClick={() => void handleSaveWorkflow()}
              disabled={!activeTab || savingWorkflow}
              title="Save active workflow"
            >
              {savingWorkflow ? 'Saving…' : saveOk ? 'Saved' : 'Save'}
            </button>

          <span className="bn-backend-status" style={{
            padding: '3px 10px',
            borderRadius: 20,
            background: serverOk ? 'var(--ok-soft)' : 'var(--err-soft)',
            color: serverOk ? 'var(--ok)' : 'var(--err)',
            fontSize: 14,
            fontWeight: 500,
            marginLeft: 2,
            maxWidth: 260,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
            title={serverOk
              ? 'Backend connected'
              : `Backend disconnected${serverError ? `: ${serverError}` : ''}`}
          >
            <span>{serverOk ? '●' : '○'}</span>
            <span className="bn-backend-label">
              {serverOk ? 'backend' : `backend offline${serverError ? ': ' + serverError : ''}`}
            </span>
          </span>
          </div>

          <button
            type="button"
            className={`bn-cloud-account-trigger${cloudAccountStatus?.authenticated ? ' is-authenticated' : ''}`}
            onClick={() => void handleCloudAccountOpen()}
            disabled={!serverOk || cloudJobPending}
            aria-haspopup="dialog"
            aria-expanded={cloudPanelOpen && cloudPanelView === 'account'}
            title={cloudAccountStatus?.authenticated
              ? `Open Blacknode Cloud account for ${cloudAccountStatus.account?.email ?? 'signed-in user'}`
              : serverOk ? 'Sign in to Blacknode Cloud' : 'Backend connection required'}
          >
            <span className="bn-cloud-account-avatar" aria-hidden="true">
              {cloudAccountStatus?.authenticated
                ? String(cloudAccountStatus.account?.display_name || cloudAccountStatus.account?.email || '?').trim().charAt(0).toUpperCase()
                : '☁'}
            </span>
            <span className="bn-cloud-account-trigger-copy">
              <strong>
                {cloudAccountStatus?.authenticated && cloudAccountStatus.credits
                  ? `${cloudAccountStatus.credits.available.toLocaleString()} GPU-s`
                  : cloudAccountStatus?.configured === false ? 'Cloud unavailable' : 'Sign in'}
              </strong>
              <small>
                {cloudAccountStatus?.authenticated
                  ? cloudAccountStatus.account?.display_name || cloudAccountStatus.account?.email
                  : 'Blacknode Cloud'}
              </small>
            </span>
          </button>
        </div>

        <div style={{
          position: 'absolute', top: topbarH, left: 0, right: 0, zIndex: 11,
          height: WORKFLOW_SHORTCUT_H,
        }}>
          <WorkflowShortcuts />
        </div>

        {/* ── workflow tab bar ── */}
        <div className="bn-workflow-tabs" style={{
          position: 'absolute', top: workflowTabsTop, left: 0, right: 0, zIndex: 10,
          height: TAB_H,
          background: 'var(--tabbar)',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 6px',
          gap: 2,
          overflowX: 'auto',
        }}>
          {activeProject && activeTab?.slug && activeProject.workflowSlugs.includes(activeTab.slug) && (
            <div
              title={`Active project: ${activeProject.name}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                height: 26,
                padding: '0 9px',
                marginRight: 4,
                borderRadius: 6,
                border: '1px solid color-mix(in srgb, var(--accent) 45%, var(--line))',
                background: 'color-mix(in srgb, var(--accent) 10%, transparent)',
                color: 'var(--tx2)',
                fontFamily: 'var(--font-ui)',
                fontSize: 13,
                fontWeight: 650,
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              <span>{activeProject.name}</span>
              <span style={{ color: 'var(--tx3)', fontWeight: 500 }}>/</span>
            </div>
          )}
          {tabs.map(tab => {
            const active = tab.id === activeTabId
            const editing = editingTabId === tab.id
            return (
              <div
                className={`bn-workflow-tab${active ? ' is-active' : ''}`}
                key={tab.id}
                onClick={() => { setTabMenu(null); if (!editing) void switchTab(tab.id) }}
                onMouseDown={e => { if (e.button === 2) openTabMenu(e, tab.id) }}
                onContextMenu={e => openTabMenu(e, tab.id)}
                onDoubleClick={e => { e.stopPropagation(); startTabRename(tab) }}
                title="Double-click to rename"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '0 8px 0 12px',
                  height: 26,
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: active ? 'var(--tab-active)' : 'var(--tab)',
                  color: active ? 'var(--tx1)' : 'var(--tx3)',
                  border: `1px solid ${active ? 'var(--accent)' : 'transparent'}`,
                  fontSize: 14,
                  fontFamily: 'var(--font-ui)',
                  whiteSpace: 'nowrap',
                  userSelect: 'none',
                  flexShrink: 0,
                  transition: 'background 0.12s, color 0.12s',
                }}
                onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.color = 'var(--tx2)' }}
                onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.color = 'var(--tx3)' }}
              >
                {editing ? (
                  <input
                    autoFocus
                    value={tabDraft}
                    onChange={e => setTabDraft(e.target.value)}
                    onClick={e => e.stopPropagation()}
                    onFocus={e => e.currentTarget.select()}
                    onBlur={commitTabRename}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        commitTabRename()
                      }
                      if (e.key === 'Escape') {
                        e.preventDefault()
                        setEditingTabId(null)
                        setTabDraft('')
                      }
                    }}
                    style={{
                      width: Math.max(76, Math.min(190, tabDraft.length * 8 + 24)),
                      background: 'var(--lift)',
                      border: '1px solid var(--accent)',
                      borderRadius: 4,
                      color: 'var(--tx1)',
                      fontFamily: 'var(--font-ui)',
                      fontSize: 14,
                      outline: 'none',
                      padding: '2px 5px',
                    }}
                  />
                ) : (
                  <span>{tab.name}</span>
                )}
                {!editing && (
                  <span
                    title={tab.dirty || !tab.slug ? 'Unsaved changes' : 'Saved'}
                    style={{
                      color: tab.dirty || !tab.slug ? 'var(--err)' : 'var(--ok)',
                      fontSize: 16,
                      lineHeight: 1,
                    }}
                  >
                    •
                  </span>
                )}
                <button
                  onClick={e => { e.stopPropagation(); requestCloseTab(tab.id) }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'inherit',
                    cursor: 'pointer',
                    fontSize: 15,
                    lineHeight: 1,
                    padding: '0 2px',
                    opacity: 0.5,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                  onMouseLeave={e => (e.currentTarget.style.opacity = '0.5')}
                >
                  ×
                </button>
              </div>
            )
          })}

          <button
            onClick={() => void newTab()}
            title="New workflow tab"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--tx3)',
              cursor: 'pointer',
              fontSize: 22,
              lineHeight: 1,
              padding: '0 6px',
              flexShrink: 0,
            }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--tx1)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--tx3)')}
          >
            +
          </button>

          {operatorView && (
            <button
              type="button"
              className={`bn-workflow-surface-toggle${activeOperatorView ? ' is-app' : ''}`}
              onClick={() => setActiveTabSurface(activeOperatorView ? 'graph' : 'app')}
              title={activeOperatorView ? 'Show workflow nodes' : 'Show workflow app'}
            >
              <span aria-hidden="true">{activeOperatorView ? '⌘' : '▦'}</span>
              {activeOperatorView ? 'Nodes' : 'App'}
            </button>
          )}

          <button
            className="bn-tab-save-button"
            onClick={() => void handleSaveWorkflow()}
            disabled={!activeTab || savingWorkflow}
            title="Save active workflow"
            style={{
              marginLeft: operatorView ? 0 : 'auto',
              position: 'sticky',
              right: 6,
              background: 'var(--action)',
              border: 'none',
              borderRadius: 6,
              color: 'var(--action-ink)',
              cursor: activeTab && !savingWorkflow ? 'pointer' : 'default',
              fontFamily: 'var(--font-ui)',
              fontSize: 14,
              fontWeight: 600,
              padding: '5px 12px',
              opacity: activeTab && !savingWorkflow ? 1 : 0.5,
              flexShrink: 0,
            }}
          >
            {savingWorkflow ? 'Saving…' : saveOk ? 'Saved' : 'Save'}
          </button>
        </div>

        {tabMenu && menuTab && (
          <div
            onMouseDown={e => e.stopPropagation()}
            onClick={e => e.stopPropagation()}
            onContextMenu={e => e.preventDefault()}
            style={{
              position: 'fixed',
              top: tabMenu.y,
              left: tabMenu.x,
              zIndex: 40,
              minWidth: 148,
              background: 'var(--panel)',
              border: '1px solid var(--line2)',
              borderRadius: 7,
              padding: 4,
              boxShadow: '0 8px 24px rgba(0,0,0,.28)',
            }}
          >
            <button className="bn-menu-item" style={menuItemStyle()} onClick={() => startTabRename(menuTab)}>Rename</button>
            <button className="bn-menu-item" style={menuItemStyle()} onClick={() => runTabMenuAction(() => insertTab(menuTab.id))}>Insert</button>
            <button className="bn-menu-item" style={menuItemStyle()} onClick={() => runTabMenuAction(() => duplicateTab(menuTab.id))}>Duplicate</button>
            <button
              className="bn-menu-item"
              style={menuItemStyle(false, 'var(--err)')}
              onClick={() => runTabMenuAction(() => requestCloseTab(menuTab.id))}
            >
              Close
            </button>
          </div>
        )}

        {!activeOperatorView && nodeMenu && (() => {
          const menuNode = nodes.find(n => n.id === nodeMenu.nodeId)
          if (!menuNode) return null
          const data = menuNode.data
          const hasValue = data.cookResult !== undefined
          const hasError = Boolean(data.cookError)
          return (
            <div
              onMouseDown={e => e.stopPropagation()}
              onClick={e => e.stopPropagation()}
              onContextMenu={e => e.preventDefault()}
              style={{
                position: 'fixed',
                top: nodeMenu.y,
                left: nodeMenu.x,
                zIndex: 40,
                minWidth: 168,
                background: 'var(--panel)',
                border: '1px solid var(--line2)',
                borderRadius: 7,
                padding: 4,
                boxShadow: '0 8px 24px rgba(0,0,0,.28)',
              }}
            >
              <button
                className="bn-menu-item"
                style={menuItemStyle(!hasValue)}
                disabled={!hasValue}
                onClick={() => {
                  void copyValueToClipboard(data.cookResult).catch(err => {
                    window.dispatchEvent(new CustomEvent('blacknode:notice', {
                      detail: {
                        kind: 'error',
                        title: 'Copy failed',
                        message: err instanceof Error ? err.message : String(err),
                      },
                    }))
                  })
                  setNodeMenu(null)
                }}
              >
                Copy value
              </button>
              {hasError && (
                <button
                  className="bn-menu-item"
                  style={menuItemStyle(false, 'var(--err)')}
                  onClick={() => { void copyTextToClipboard(String(data.cookError)); setNodeMenu(null) }}
                >
                  Copy error
                </button>
              )}
              <button
                className="bn-menu-item"
                style={menuItemStyle()}
                onClick={() => { void copyTextToClipboard(menuNode.id); setNodeMenu(null) }}
              >
                Copy node ID
              </button>
            </div>
          )
        })()}

        {usdPickerInitialPath !== null && (
          <LocalFilePicker
            title="Open a USD, URDF, Xacro, or MuJoCo scene in Newton"
            initialPath={usdPickerInitialPath}
            extensions={NEWTON_SCENE_FILE_EXTENSIONS}
            onSelect={path => void handleUsdSelected(path)}
            onCancel={() => setUsdPickerInitialPath(null)}
          />
        )}

        {pendingXacroEnvironment && (
          <div
            className="bn-xacro-environment-backdrop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="bn-xacro-environment-title"
            onMouseDown={event => {
              if (event.target === event.currentTarget && !openingUsd) {
                setPendingXacroEnvironment(null)
              }
              event.stopPropagation()
            }}
          >
            <form
              className="bn-xacro-environment-dialog"
              onSubmit={event => {
                event.preventDefault()
                submitXacroEnvironment()
              }}
            >
              <header>
                <div>
                  <strong id="bn-xacro-environment-title">Xacro configuration required</strong>
                  <span>{pendingXacroEnvironment.assetPath}</span>
                </div>
                <button
                  type="button"
                  disabled={openingUsd}
                  onClick={() => setPendingXacroEnvironment(null)}
                  aria-label="Cancel Xacro configuration"
                >×</button>
              </header>
              <p>
                This robot description reads an environment variable. Its value is used only while
                expanding this Xacro file and does not change the editor server environment.
              </p>
              <label htmlFor="bn-xacro-environment-value">
                {pendingXacroEnvironment.variableName}
              </label>
              <input
                id="bn-xacro-environment-value"
                autoFocus
                value={xacroEnvironmentDraft}
                onChange={event => setXacroEnvironmentDraft(event.target.value)}
                placeholder="Enter the robot configuration value"
                spellCheck={false}
              />
              {Object.keys(pendingXacroEnvironment.values).length > 0 && (
                <small>
                  Already supplied: {Object.keys(pendingXacroEnvironment.values).join(', ')}
                </small>
              )}
              <footer>
                <button
                  type="button"
                  disabled={openingUsd}
                  onClick={() => setPendingXacroEnvironment(null)}
                >Cancel</button>
                <button className="is-primary" type="submit" disabled={openingUsd}>
                  {openingUsd ? 'Expanding…' : 'Open Xacro'}
                </button>
              </footer>
            </form>
          </div>
        )}

        {hdriPickerInitialPath !== null && (
          <LocalFilePicker
            title="Choose an HDRI environment"
            initialPath={hdriPickerInitialPath}
            extensions={HDRI_FILE_EXTENSIONS}
            onSelect={handleHdriSelected}
            onCancel={() => setHdriPickerInitialPath(null)}
          />
        )}

        {pendingClose && pendingCloseTab && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="close-workflow-title"
            onMouseDown={e => e.stopPropagation()}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 80,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(0,0,0,.42)',
            }}
          >
            <div
              style={{
                width: 'min(420px, calc(100vw - 32px))',
                background: 'var(--panel)',
                border: '1px solid var(--line2)',
                borderRadius: 8,
                boxShadow: '0 18px 48px rgba(0,0,0,.35)',
                padding: 18,
                color: 'var(--tx1)',
              }}
            >
              <div id="close-workflow-title" style={{ fontSize: 17, fontWeight: 700, marginBottom: 8 }}>
                Save changes to "{pendingClose.draftName}"?
              </div>
              <div style={{ color: 'var(--tx2)', fontSize: 15, lineHeight: 1.45, marginBottom: 10 }}>
                Name it before saving, or close without saving.
              </div>
              <label
                htmlFor="close-workflow-name"
                style={{ display: 'block', color: 'var(--tx3)', fontSize: 13, marginBottom: 6 }}
              >
                Workflow name
              </label>
              <input
                id="close-workflow-name"
                autoFocus
                aria-label="Workflow name"
                value={pendingClose.draftName}
                onChange={e => updatePendingCloseName(e.target.value)}
                onFocus={e => e.currentTarget.select()}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void savePendingClose()
                  }
                }}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  background: 'var(--lift)',
                  border: '1px solid var(--line2)',
                  borderRadius: 6,
                  color: 'var(--tx1)',
                  fontFamily: 'var(--font-ui)',
                  fontSize: 15,
                  padding: '8px 10px',
                  marginBottom: 18,
                  outline: 'none',
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button
                  className="bn-top-button"
                  disabled={closeSaving}
                  onClick={cancelPendingClose}
                >
                  Cancel
                </button>
                <button
                  className="bn-top-button"
                  disabled={closeSaving}
                  onClick={() => void discardPendingClose()}
                  style={{ borderColor: 'var(--err)', color: 'var(--err)' }}
                >
                  Don't Save
                </button>
                <button
                  className="bn-top-button"
                  disabled={closeSaving || !pendingClose.draftName.trim()}
                  onClick={() => void savePendingClose()}
                  style={{
                    background: 'var(--action)',
                    borderColor: 'var(--action)',
                    color: 'var(--action-ink)',
                    opacity: closeSaving || !pendingClose.draftName.trim() ? 0.65 : 1,
                  }}
                >
                  {closeSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        {!activeOperatorView && <SubnetBreadcrumb />}

        <CookStatusPanel
          entries={cookLog}
          active={cookActive}
          hidden={cookStatusHidden}
          raised={Boolean(notice)}
          onDismiss={dismissCookStatus}
        />

        <CloudRunPanel
          open={cloudPanelOpen}
          view={cloudPanelView}
          pending={cloudJobPending}
          initialJob={cloudJob}
          error={cloudJobError}
          accountStatus={cloudAccountStatus}
          onAccountStatus={setCloudAccountStatus}
          onRun={() => void handleCloudRun()}
          onRunVla={handleCloudVlaRun}
          onJobCompleted={handleCloudJobCompleted}
          onClose={() => setCloudPanelOpen(false)}
        />

        {notice && (
          <div
            role="alert"
            style={{
              position: 'absolute',
              left: '50%',
              bottom: 24,
              transform: 'translateX(-50%)',
              zIndex: 60,
              width: 'min(520px, calc(100% - 48px))',
              background: 'var(--panel)',
              border: `1px solid ${notice.kind === 'error' ? 'var(--err)' : notice.kind === 'warning' ? 'var(--warn)' : 'var(--accent)'}`,
              borderRadius: 8,
              boxShadow: '0 12px 32px rgba(0,0,0,.35)',
              padding: '10px 12px',
              color: 'var(--tx1)',
              pointerEvents: 'auto',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <div style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                marginTop: 5,
                flexShrink: 0,
                background: notice.kind === 'error' ? 'var(--err)' : notice.kind === 'warning' ? 'var(--warn)' : 'var(--accent)',
              }} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 3 }}>{notice.title}</div>
                {notice.message && (
                  <div style={{ fontSize: 14, color: 'var(--tx2)', lineHeight: 1.45, overflowWrap: 'anywhere' }}>
                    {notice.message}
                  </div>
                )}
              </div>
              <button
                onClick={() => setNotice(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--tx3)',
                  cursor: 'pointer',
                  fontSize: 18,
                  lineHeight: 1,
                  padding: 0,
                }}
              >
                ×
              </button>
            </div>
          </div>
        )}

        {/* ── Collapse-to-subnet floating button ── */}
        {!activeOperatorView && (() => {
          const selected = nodes.filter(n => n.selected)
          if (selected.length < 2) return null
          return (
            <div style={{
              position: 'absolute',
              bottom: 48,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 20,
              pointerEvents: 'none',
              display: 'flex',
              justifyContent: 'center',
            }}>
              <button
                onClick={() => void collapseToSubnet(selected.map(n => n.id), 'Subnet')}
                style={{
                  pointerEvents: 'all',
                  background: 'var(--action)',
                  border: 'none',
                  borderRadius: 8,
                  color: 'var(--action-ink)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-ui)',
                  fontSize: 15,
                  fontWeight: 600,
                  padding: '8px 18px',
                  boxShadow: '0 4px 16px color-mix(in srgb, var(--accent) 35%, transparent)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                }}
              >
                <span style={{ fontSize: 17 }}>⬡</span>
                Group {selected.length} nodes into Subnet
              </button>
            </div>
          )
        })()}

        <div className="bn-workspace-split" style={{ top: canvasPad }}>
          {activeOperatorView ? (
            <WorkflowOperatorView
              config={activeOperatorView}
              onEditWorkflow={() => setActiveTabSurface('graph')}
            />
          ) : <>
          {activeSimulationViewer && (
            <SimulationViewerPane
              url={activeSimulationViewer.url}
              label={activeSimulationViewer.label}
              phase={activeSimulationViewer.phase}
              armed={activeSimulationViewer.armed}
              visible={simulationViewerVisible}
              floating={simulationViewerDetached}
              height={simulationViewerHeight}
              onHeightChange={setSimulationViewerHeight}
              onDetach={detachSimulationViewer}
              onAttach={attachSimulationViewer}
              onClose={() => setSimulationViewerVisible(false)}
              workspace={activeSimulationViewer.workspace}
              sceneLabel={newtonWorkspace?.scene_label}
              simulationRunning={newtonWorkspace?.simulation_running}
              busy={newtonWorkspaceBusy || openingUsd}
              warning={newtonWorkspace?.warning}
              onNewStage={() => void controlNewtonWorkspace('new')}
              onOpenUsd={handleOpenUsd}
              onPlay={() => void controlNewtonWorkspace('play')}
              onStop={() => void controlNewtonWorkspace('stop')}
              onReset={() => void controlNewtonWorkspace('reset')}
              onCloseWorkspace={() => {
                void controlNewtonWorkspace('close').then(() => {
                  setSimulationViewerVisible(false)
                  setSimulationViewerDetached(false)
                })
              }}
              workspaceStatus={newtonWorkspace}
              onWorkspaceAction={(action, payload) => { void controlNewtonWorkspace(action, payload) }}
              onChooseHdri={handleChooseHdri}
            />
          )}
          <div className="bn-canvas-region">
          <ReactFlow
          nodes={visibleNodes}
          edges={visibleEdges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onNodeDragStart={onNodeDragStart}
          onNodeDragStop={onNodeDragStop}
          onEdgeDoubleClick={onEdgeDoubleClick}
          onEdgeMouseEnter={(_, edge) => setHoveredEdgeId(edge.id)}
          onEdgeMouseLeave={() => setHoveredEdgeId(null)}
          onEdgeUpdateStart={onEdgeUpdateStart}
          onEdgeUpdate={onEdgeUpdate}
          onEdgeUpdateEnd={onEdgeUpdateEnd}
          onInit={i => { rfInstance.current = i }}
          onNodeClick={(_, node) => selectNode(node.id)}
          onNodeDoubleClick={(_, node) => {
            if (['Subnet', 'SubnetAsTool', 'VisualAgentLoop'].includes(node.data?.type)) void diveIntoSubnet(node.id)
          }}
          onPaneClick={() => {
            if (suppressPaneClick.current) {
              suppressPaneClick.current = false
              return
            }
            selectNode(null)
            setSearch(null)
            setTabMenu(null)
            setNodeMenu(null)
          }}
          onPaneContextMenu={onPaneContextMenu}
          onNodeContextMenu={(e, node) => {
            e.preventDefault()
            selectNode(node.id)
            setNodeMenu({ x: e.clientX, y: e.clientY, nodeId: node.id })
          }}
          // Only dedicated embedded viewers capture the wheel for their own
          // camera. Everywhere else—including other nodes—the wheel continues
          // to zoom the React Flow graph.
          zoomOnScroll={true}
          noWheelClassName="bn-viewer-wheel-capture"
          minZoom={0.05}
          fitView
          fitViewOptions={{ padding: 0.24, maxZoom: 1 }}
          deleteKeyCode={['Delete', 'Backspace']}
          selectionKeyCode="Control"
          multiSelectionKeyCode="Control"
          selectionMode={SelectionMode.Partial}
          style={{ paddingTop: 0 }}
          defaultEdgeOptions={{ animated: false }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            color="var(--rf-dot)"
            gap={72}
            size={2}
          />
          <Controls />
          <MiniMap nodeColor={() => 'var(--lift)'} />
          {nodes.length === 0 && (
            <div className="bn-canvas-empty-state">
              <div className="bn-canvas-empty-content">
                <span className="bn-canvas-empty-mark" aria-hidden="true">+</span>
                <h1>Create your first workflow</h1>
                <p>Drag nodes from the sidebar or start with a reusable template.</p>
                <div>
                  <button
                    type="button"
                    className="bn-canvas-empty-primary"
                    onClick={() => window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
                      detail: { tab: 'nodes' },
                    }))}
                  >
                    Add node
                  </button>
                  <button
                    type="button"
                    onClick={() => window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
                      detail: { tab: 'templates' },
                    }))}
                  >
                    Browse templates
                  </button>
                </div>
              </div>
            </div>
          )}
          </ReactFlow>
          </div>
          </>}
        </div>

        <div className="bn-execution-status-strip" role="status" aria-label="Blacknode execution status">
          <span className={`bn-status-item ${serverOk ? 'is-active' : 'is-error'}`}>
            <i />
            Backend {serverOk ? 'connected' : 'offline'}
          </span>
          <span className={`bn-status-item ${cookActive || runtimeActive ? 'is-active' : 'is-muted'}`}>
            <i />
            {cookActive ? 'Evaluating graph' : runtimeActive ? 'Runtime live' : 'Runtime idle'}
          </span>
          <span className={`bn-status-item ${managedRunCount > 0 ? 'is-active' : 'is-muted'}`}>
            <i />
            ROS 2 {managedRunCount > 0 ? `${managedRunCount} active` : 'idle'}
          </span>
          <span className={`bn-status-item ${simulationRunCount > 0 ? 'is-active' : 'is-muted'}`}>
            <i />
            Simulation {simulationRunCount > 0 ? `${simulationRunCount} active` : 'idle'}
          </span>
          <span className={`bn-status-item ${
            blockedControllerCount > 0
              ? 'is-error'
              : controllerCount > 0
                ? 'is-active'
                : waitingControllerCount > 0
                  ? 'is-warning'
                  : 'is-muted'
          }`}>
            <i />
            Robot {
              blockedControllerCount > 0
                ? `${blockedControllerCount} blocked`
                : controllerCount > 0
                  ? `${controllerCount} live`
                  : waitingControllerCount > 0
                    ? `${waitingControllerCount} waiting`
                    : 'idle'
            }
          </span>
          <span className={`bn-status-item ${cameraStreamCount > 0 ? 'is-active' : 'is-muted'}`}>
            <i />
            Camera {cameraStreamCount > 0 ? `${cameraStreamCount} streaming` : 'idle'}
          </span>
          <span className="bn-status-spacer" />
          <span className="bn-status-metric">{nodes.length} nodes</span>
          <span className="bn-status-metric">{edges.length} wires</span>
          {liveStreamCount > cameraStreamCount && (
            <span className="bn-status-metric">{liveStreamCount} streams</span>
          )}
        </div>
      </div>

      {!activeOperatorView && <Inspector />}

      {!activeOperatorView && search && (
        <NodeSearch
          screenPos={search.screenPos}
          nodeTypes={nodeTypes}
          nodeDefs={nodeDefs}
          allowedTypes={search.connect && Object.keys(nodeDefs).length > 0 ? getCompatibleNodeTypes(search.connect, nodeDefs) : undefined}
          title={search.connect ? `${search.connect.portType} port` : undefined}
          emptyMessage={search.connect ? 'No nodes can connect to this port' : undefined}
          actionLabel={search.connect ? 'add + connect' : 'add node'}
          onSelect={handleSearchSelect}
          onClose={() => setSearch(null)}
        />
      )}
    </div>
  )
}

function clientPointFromEvent(event: MouseEvent | TouchEvent): { x: number; y: number } | null {
  if ('changedTouches' in event) {
    const touch = event.changedTouches[0]
    return touch ? { x: touch.clientX, y: touch.clientY } : null
  }
  return { x: event.clientX, y: event.clientY }
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select'
}

function findToolBoxAtPoint(nodes: any[], point: { x: number; y: number }): string | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i]
    if (node.data?.type !== 'ToolBox') continue
    const pos = node.positionAbsolute ?? node.position
    const width = node.width ?? 180
    const height = node.height ?? 96
    const pad = 24
    if (
      point.x >= pos.x - pad &&
      point.x <= pos.x + width + pad &&
      point.y >= pos.y - pad &&
      point.y <= pos.y + height + pad
    ) {
      return node.id
    }
  }
  return null
}

function findToolBoxAtScreenPoint(nodes: any[], point: { x: number; y: number }): string | null {
  const elements = document.elementsFromPoint(point.x, point.y)
  for (const element of elements) {
    if (!(element instanceof HTMLElement)) continue
    const nodeEl = element.closest('.react-flow__node[data-id]')
    if (!(nodeEl instanceof HTMLElement)) continue
    const nodeId = nodeEl.dataset.id
    if (nodeId && nodes.some(node => node.id === nodeId && node.data?.type === 'ToolBox')) {
      return nodeId
    }
  }
  return null
}

function CookStatusPanel({
  entries,
  active,
  hidden,
  raised,
  onDismiss,
}: {
  entries: CookLogEntry[]
  active: boolean
  hidden: boolean
  raised: boolean
  onDismiss: () => void
}) {
  const [debug, setDebug] = useState(false)
  if (hidden || entries.length === 0) return null
  const latest = entries[entries.length - 1]
  const recent = entries.slice(-8).reverse()
  const debugRows = entries.slice(-300)
  const statusColor = active ? 'var(--warn)' : latest.kind === 'error' ? 'var(--err)' : 'var(--ok)'

  return (
    <div style={{
      position: 'absolute',
      left: '50%',
      bottom: raised ? 108 : 20,
      transform: 'translateX(-50%)',
      zIndex: 35,
      width: 'min(680px, calc(100% - 48px))',
      pointerEvents: 'none',
    }}>
      <div style={{
        background: 'var(--panel)',
        border: `1px solid ${statusColor}`,
        borderRadius: 8,
        boxShadow: '0 12px 32px rgba(0,0,0,.35)',
        color: 'var(--tx1)',
        overflow: 'hidden',
        pointerEvents: 'auto',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          minHeight: 34,
          padding: '7px 10px',
          borderBottom: '1px solid var(--line)',
        }}>
          <div style={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: statusColor,
            boxShadow: active ? `0 0 8px ${statusColor}` : 'none',
            flexShrink: 0,
          }} />
          <div style={{
            flex: 1,
            minWidth: 0,
            fontFamily: 'var(--font-ui)',
            fontSize: 14,
            fontWeight: 700,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {latest.message}
          </div>
          <div style={{
            color: active ? 'var(--warn)' : 'var(--tx3)',
            fontSize: 13,
            fontFamily: 'var(--font-ui)',
            flexShrink: 0,
          }}>
            {active ? 'running' : 'idle'} · {entries.length}
          </div>
          <button
            type="button"
            aria-label="Toggle debug output"
            title="Show full system output (stdout/stderr, node results, tracebacks)"
            onClick={() => setDebug(d => !d)}
            style={{
              minHeight: 26,
              padding: '0 8px',
              border: `1px solid ${debug ? 'var(--accent)' : 'var(--line2)'}`,
              borderRadius: 6,
              background: debug ? 'var(--accent)' : 'transparent',
              color: debug ? '#fff' : 'var(--tx3)',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 700,
              fontFamily: 'var(--font-ui)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              flexShrink: 0,
            }}
          >
            Debug
          </button>
          <button
            type="button"
            aria-label="Hide run status"
            title="Hide run status"
            onClick={onDismiss}
            style={{
              width: 26,
              height: 26,
              border: '1px solid var(--line2)',
              borderRadius: 6,
              background: 'transparent',
              color: 'var(--tx3)',
              cursor: 'pointer',
              display: 'grid',
              placeItems: 'center',
              fontSize: 16,
              lineHeight: 1,
              padding: 0,
              flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>

        {debug ? (
          <div style={{ maxHeight: 360, overflowY: 'auto', padding: '4px 0' }}>
            {debugRows.map(entry => {
              const color = cookEntryColor(entry.kind)
              return (
                <div
                  key={entry.id}
                  style={{ padding: '4px 10px', borderBottom: '1px solid var(--line)' }}
                >
                  <div style={{
                    display: 'flex', gap: 8, alignItems: 'baseline',
                    fontSize: 13, fontFamily: 'var(--font-ui)',
                  }}>
                    <span style={{ color, fontWeight: 700, textTransform: 'uppercase', flexShrink: 0 }}>
                      {entry.stream ?? entry.kind}
                    </span>
                    <span style={{ color: 'var(--tx2)', fontFamily: 'var(--font-mono)', wordBreak: 'break-word' }}>
                      {entry.message}
                    </span>
                  </div>
                  {entry.detail && (
                    <pre style={{
                      margin: '4px 0 0',
                      padding: '6px 8px',
                      background: 'var(--lift)',
                      border: `1px solid ${entry.kind === 'error' ? 'var(--err)' : 'var(--line2)'}`,
                      borderRadius: 5,
                      color: entry.kind === 'error' ? 'var(--err)' : entry.stream === 'stderr' ? 'var(--warn)' : 'var(--tx2)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 13,
                      lineHeight: 1.4,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 180,
                      overflowY: 'auto',
                    }}>
                      {entry.detail}
                    </pre>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ maxHeight: 168, overflowY: 'auto', padding: '4px 0' }}>
            {recent.map(entry => {
              const color = cookEntryColor(entry.kind)
              return (
                <div
                  key={entry.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '70px 1fr',
                    gap: 8,
                    padding: '4px 10px',
                    fontSize: 13,
                    lineHeight: 1.35,
                    fontFamily: 'var(--font-ui)',
                  }}
                >
                  <span style={{ color, fontWeight: 700, textTransform: 'uppercase' }}>
                    {entry.kind}
                  </span>
                  <span style={{
                    color: entry.kind === 'error' ? 'var(--err)' : 'var(--tx2)',
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {entry.message}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function stringifyValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

async function copyValueToClipboard(value: unknown): Promise<void> {
  if (isImageDataUrl(value)) {
    await copyImageToClipboard(value)
    return
  }
  await copyTextToClipboard(stringifyValue(value))
}

async function copyImageToClipboard(dataUrl: string): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
    throw new Error('This browser does not support copying images to the clipboard.')
  }
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  const type = blob.type || 'image/png'
  await navigator.clipboard.write([new ClipboardItem({ [type]: blob })])
}

function cookEntryColor(kind: CookLogEntry['kind']): string {
  switch (kind) {
    case 'error': return 'var(--err)'
    case 'start': return 'var(--warn)'
    case 'done':  return 'var(--accent)'
    case 'log':   return 'var(--tx3)'
    case 'info':  return 'var(--tx3)'
    default:      return 'var(--ok)'
  }
}

function getCompatibleNodeTypes(draft: ConnectionDraft, nodeDefs: Record<string, BnNodeDef>): string[] {
  const types = Object.values(nodeDefs)
    .filter(def => draft.handleType === 'source'
      ? def.inputs.some(port => portsCompatible(draft.portType, def.input_types?.[port] ?? 'Any'))
      : def.outputs.some(port => portsCompatible(def.output_types?.[port] ?? 'Any', draft.portType))
    )
    .map(def => def.type)
  if (draft.handleType === 'target' && portsCompatible('Fn', draft.portType)) {
    types.push(...PYTHON_TOOL_TYPES)
  }
  return [...new Set(types)].sort()
}

function menuItemStyle(disabled = false, color = 'var(--tx2)'): React.CSSProperties {
  return {
    width: '100%',
    background: 'transparent',
    border: 'none',
    borderRadius: 5,
    color: disabled ? 'var(--tx3)' : color,
    cursor: disabled ? 'default' : 'pointer',
    display: 'block',
    fontFamily: 'var(--font-ui)',
    fontSize: 14,
    padding: '6px 9px',
    textAlign: 'left',
  }
}
