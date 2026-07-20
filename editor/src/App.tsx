import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance, Edge, Connection, SelectionMode,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore, type CookLogEntry, type GraphClipboard } from './store'
import BlackNode from './components/BlackNode'
import { LIVE_STREAM_NODE_TYPES } from './liveNodeTypes'
import ValueNode from './components/ValueNode'
import ModelNode from './components/ModelNode'
import OutputNode from './components/OutputNode'
import SubnetNode from './components/SubnetNode'
import SubnetBreadcrumb from './components/SubnetBreadcrumb'
import SubgraphInputNode from './components/SubgraphInputNode'
import SubgraphOutputNode from './components/SubgraphOutputNode'
import NodePalette from './components/NodePalette'
import Inspector from './components/Inspector'
import NodeSearch from './components/NodeSearch'
import { portsCompatible } from './portColors'
import { PYTHON_TOOL_TYPES, resolvePythonToolPreset } from './pythonToolPresets'
import type { BnNodeDef, ConnectionDraft } from './types'
import { api, type FrameworkExportTarget } from './api'
import { inferGraphRunTargets } from './graphRun'
import { copyTextToClipboard } from './clipboard'

const NODE_TYPES = {
  blacknode: BlackNode,
  valuenode: ValueNode,
  modelnode: ModelNode,
  outputnode: OutputNode,
  subnetnode: SubnetNode,
  subnetinput: SubgraphInputNode,
  subnetoutput: SubgraphOutputNode,
}

const TAB_H = 36  // workflow tab bar height

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
  const {
    nodes, edges, nodeTypes, nodeDefs, serverOk, serverError, cookLog, cookActive, cookStatusHidden,
    tabs, activeTabId,
    onNodesChange, onEdgesChange, onConnect: storeOnConnect, disconnectEdge, reconnectEdge,
    addNode, selectNode, loadNodeTypes, loadGraph, loadApiKeys, loadApiKeyStatus, loadCustomModels, loadLearnedNodes, loadDriverStatus, loadRuntimeNodeOutputs, loadDrivers,
    addNodeFromConnection, copySelection, pasteClipboard,
    beginAltDragCopy, finishAltDragCopy, undoGraph,
    checkServer, reset, newTab, insertTab, switchTab, closeTab, duplicateTab,
    openGraphAsTab, openWorkflowAsTab, renameTab, saveActiveWorkflow,
    diveIntoSubnet, exitSubnet, collapseToSubnet, organizeNodes, cookNode, stopCook, stopRuntimeServices, dismissCookStatus, applyRunReplay,
    handleLearnedNodeEvent, updateParam,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const pythonImportInput = useRef<HTMLInputElement | null>(null)
  const [search, setSearch] = useState<SearchState | null>(null)
  const [isDark, setIsDark] = useState(true)
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
  const needsSave = Boolean(activeTab && (activeTab.dirty || !activeTab.slug))
  const menuTab = tabMenu ? tabs.find(tab => tab.id === tabMenu.tabId) : null
  const pendingCloseTab = pendingClose ? tabs.find(tab => tab.id === pendingClose.tabId) : null

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
  }, [isDark])

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
      loadDrivers()
    })
    const id = setInterval(checkServer, 5000)
    // Poll running-driver heartbeats so trigger nodes show live/offline truthfully.
    const driverId = setInterval(loadDriverStatus, 4000)
    const runtimeOutputsId = setInterval(loadRuntimeNodeOutputs, 250)
    return () => { clearInterval(id); clearInterval(driverId); clearInterval(runtimeOutputsId) }
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
        } else if (Array.isArray(workflow?.nodes)) {
          tabName = typeof workflow.name === 'string' && workflow.name.trim() ? workflow.name : name
          nodeMeta = Object.fromEntries(
            workflow.nodes
              .filter((node: any) => node && typeof node === 'object' && typeof node.id === 'string')
              .map((node: any) => [node.id, node])
          )
          edges = Array.isArray(workflow.edges) ? workflow.edges : []
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

  const handleRunGraph = useCallback(async (runMode: 'once' | 'live' = 'once') => {
    const targets = inferGraphRunTargets(nodes, edges)
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
    await cookNode(targets[0].id, targets[0].port, targets, effectiveMode)
  }, [cookNode, edges, fitCurrentCanvas, nodes])

  const handleResetRun = useCallback(() => {
    stopCook()
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

  const topbarH = 44
  const canvasPad = topbarH + TAB_H
  const liveStreamCount = nodes.filter(n => (
    LIVE_STREAM_NODE_TYPES.has(n.data.type) &&
    n.data.portResults?.streaming === true
  )).length
  const managedRunCount = nodes.filter(n => n.data.type === 'ROS2Run' && n.data.portResults?.running === true).length
  const controllerNodes = nodes.filter(n => (
    n.data.type === 'ROS2ContinuousFollowDetectionJoint' || n.data.type === 'ROS2LeaderFollower'
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
  const liveOutputCount = nodes.filter(n => (
    (n.data.type === 'Output' || n.data.type === 'OutputImage') && n.data.portResults?.live === true
  )).length
  const liveCapableCount = nodes.filter(n => n.data.live_capable).length
  const runOnceNodeCount = Math.max(0, nodes.length - liveCapableCount)
  const activelyUpdatingCount = liveStreamCount + managedRunCount + controllerCount + manualMoveCount + liveDashboardCount + liveOutputCount
  const lastRunNodeCount = Math.max(0, nodes.length - activelyUpdatingCount - blockedControllerCount - waitingControllerCount)
  const runtimeActive = liveStreamCount > 0 || managedRunCount > 0 || controllerRunningCount > 0 || manualMoveCount > 0
  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)' }}>
      <NodePalette />

      <div style={{ flex: 1, position: 'relative' }} onDrop={onDrop} onDragOver={onDragOver} onMouseMove={trackMouseFlowPos}>

        {/* ── top bar ── */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
          background: 'var(--panel)',
          borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px',
          height: topbarH,
        }}>
          <div className="bn-brand" aria-label="Blacknode">
            <img
              className="bn-brand-logo"
              src={isDark ? '/blacknode-logo-white.png' : '/blacknode-logo.png'}
              alt=""
            />
            <span>BLACKNODE</span>
          </div>

          <div style={{ flex: 1 }} />

          <span style={{ color: 'var(--tx3)', fontSize: 12 }}>right-click to add</span>

          <select
            className="bn-top-select"
            value={exportingTarget}
            onChange={e => void handleFrameworkExport(e.target.value)}
            disabled={!serverOk || nodes.length === 0 || Boolean(exportingTarget)}
            title="Export current graph"
          >
            <option value="">{exportingTarget ? 'Exporting...' : 'Export'}</option>
            {frameworkExportTargets.map(target => (
              <option key={target.id} value={target.id}>{target.label}</option>
            ))}
          </select>

          <input
            ref={pythonImportInput}
            type="file"
            accept=".py,.json,application/json,text/x-python"
            style={{ display: 'none' }}
            onChange={handlePythonImport}
          />

          <button
            className="bn-top-button"
            onClick={() => pythonImportInput.current?.click()}
            disabled={!serverOk || importingFile}
            title="Import a workflow JSON, Python export, or LangGraph export"
          >
            {importingFile ? 'Importing...' : 'Import'}
          </button>

          <button
            className="bn-top-button bn-top-run-button"
            onClick={() => (cookActive ? stopCook() : void handleRunGraph('once'))}
            disabled={!serverOk || (!cookActive && nodes.length === 0)}
            title={cookActive ? 'Stop the current evaluation' : 'Evaluate the graph once. Live-capable nodes return one snapshot and do not keep streaming.'}
          >
            {cookActive ? '■ Stop run' : '▶ Run once'}
          </button>

          <button
            className="bn-top-button bn-top-run-button"
            onClick={() => void handleRunGraph('live')}
            disabled={!serverOk || cookActive || nodes.length === 0}
            title={liveCapableCount > 0
              ? `Start ${liveCapableCount} live-capable node${liveCapableCount === 1 ? '' : 's'}; evaluate the other ${runOnceNodeCount} node${runOnceNodeCount === 1 ? '' : 's'} once.`
              : 'No live-capable nodes are present; this will run the graph once.'}
          >
            ● Go live
          </button>

          {runtimeActive && (
            <button
              className="bn-top-button bn-top-streaming-button"
              onClick={() => void handleStopRuntime()}
              disabled={!serverOk || runtimeStopPending}
              title={`Graph is mixed: ${liveCapableCount} live-capable node${liveCapableCount === 1 ? '' : 's'} and ${runOnceNodeCount} run-once node${runOnceNodeCount === 1 ? '' : 's'}. Stop active streams and ROS 2 processes.`}
            >
              <span className="bn-top-live-dot" />
              <span>{runtimeStopPending
                ? 'Stopping...'
                : `LIVE · ${activelyUpdatingCount} updating${blockedControllerCount ? ` · ${blockedControllerCount} blocked` : ''}${waitingControllerCount ? ` · ${waitingControllerCount} waiting` : ''} · ${lastRunNodeCount} last-run`}</span>
              <span className="bn-top-streaming-stop">Stop</span>
            </button>
          )}

          <button
            className="bn-top-button"
            onClick={handleResetRun}
            title="Stop active work and clear any stuck running state"
          >
            Reset Run
          </button>

          <button
            className="bn-top-button"
            onClick={() => void handleOrganize()}
            title="Organize current graph"
          >
            Organize
          </button>

          <button
            className="bn-top-button"
            onClick={() => setIsDark(d => !d)}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            Theme
          </button>

          <button
            className="bn-top-button"
            onClick={() => void reset()}
          >
            Clear
          </button>

          <span style={{
            padding: '3px 10px',
            borderRadius: 20,
            background: serverOk ? (isDark ? '#0d2a1a' : '#dcfce7') : (isDark ? '#2a0d0d' : '#fee2e2'),
            color: serverOk ? 'var(--ok)' : 'var(--err)',
            fontSize: 12,
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
            {serverOk ? '● backend' : `○ backend offline${serverError ? ': ' + serverError : ''}`}
          </span>
        </div>

        {/* ── workflow tab bar ── */}
        <div style={{
          position: 'absolute', top: topbarH, left: 0, right: 0, zIndex: 10,
          height: TAB_H,
          background: 'var(--bg)',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 6px',
          gap: 2,
          overflowX: 'auto',
        }}>
          {tabs.map(tab => {
            const active = tab.id === activeTabId
            const editing = editingTabId === tab.id
            return (
              <div
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
                  background: active ? 'var(--menu-active)' : 'transparent',
                  color: active ? 'var(--tx1)' : 'var(--tx3)',
                  border: `1px solid ${active ? 'var(--accent)' : 'transparent'}`,
                  fontSize: 12,
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
                      fontSize: 12,
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
                      color: tab.dirty || !tab.slug ? '#b86b68' : '#6f9b78',
                      fontSize: 14,
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
                    fontSize: 13,
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
              fontSize: 20,
              lineHeight: 1,
              padding: '0 6px',
              flexShrink: 0,
            }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--tx1)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--tx3)')}
          >
            +
          </button>

          <button
            onClick={() => void handleSaveWorkflow()}
            disabled={!activeTab || savingWorkflow}
            title="Save active workflow"
            style={{
              marginLeft: 'auto',
              position: 'sticky',
              right: 6,
              background: saveOk ? 'var(--ok)' : needsSave ? 'var(--save-pending)' : 'var(--accent)',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              cursor: activeTab && !savingWorkflow ? 'pointer' : 'default',
              fontFamily: 'var(--font-ui)',
              fontSize: 12,
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

        {nodeMenu && (() => {
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
              <div id="close-workflow-title" style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>
                Save changes to "{pendingClose.draftName}"?
              </div>
              <div style={{ color: 'var(--tx2)', fontSize: 13, lineHeight: 1.45, marginBottom: 10 }}>
                Name it before saving, or close without saving.
              </div>
              <label
                htmlFor="close-workflow-name"
                style={{ display: 'block', color: 'var(--tx3)', fontSize: 11, marginBottom: 6 }}
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
                  fontSize: 13,
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
                    background: 'var(--accent)',
                    borderColor: 'var(--accent)',
                    color: '#fff',
                    opacity: closeSaving || !pendingClose.draftName.trim() ? 0.65 : 1,
                  }}
                >
                  {closeSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        <SubnetBreadcrumb />

        <CookStatusPanel
          entries={cookLog}
          active={cookActive}
          hidden={cookStatusHidden}
          raised={Boolean(notice)}
          onDismiss={dismissCookStatus}
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
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 3 }}>{notice.title}</div>
                {notice.message && (
                  <div style={{ fontSize: 12, color: 'var(--tx2)', lineHeight: 1.45, overflowWrap: 'anywhere' }}>
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
                  fontSize: 16,
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
        {(() => {
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
                  background: '#6366f1',
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-ui)',
                  fontSize: 13,
                  fontWeight: 600,
                  padding: '8px 18px',
                  boxShadow: '0 4px 16px rgba(99,102,241,0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                }}
              >
                <span style={{ fontSize: 15 }}>⬡</span>
                Group {selected.length} nodes into Subnet
              </button>
            </div>
          )
        })()}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onNodeDragStart={onNodeDragStart}
          onNodeDragStop={onNodeDragStop}
          onEdgeDoubleClick={onEdgeDoubleClick}
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
          minZoom={0.05}
          fitView
          fitViewOptions={{ padding: 0.24, maxZoom: 1 }}
          deleteKeyCode={['Delete', 'Backspace']}
          selectionKeyCode="Control"
          multiSelectionKeyCode="Control"
          selectionMode={SelectionMode.Partial}
          style={{ paddingTop: canvasPad }}
          defaultEdgeOptions={{ animated: false }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            color={isDark ? '#3a3a3a' : '#d0d1e0'}
            gap={24}
            size={1.5}
          />
          <Controls />
          <MiniMap nodeColor={() => isDark ? '#2e2e2e' : '#e0e0ec'} />
        </ReactFlow>
      </div>

      <Inspector />

      {search && (
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
            fontSize: 12,
            fontWeight: 700,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {latest.message}
          </div>
          <div style={{
            color: active ? 'var(--warn)' : 'var(--tx3)',
            fontSize: 11,
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
              height: 20,
              padding: '0 8px',
              border: `1px solid ${debug ? 'var(--accent)' : 'var(--line2)'}`,
              borderRadius: 6,
              background: debug ? 'var(--accent)' : 'transparent',
              color: debug ? '#fff' : 'var(--tx3)',
              cursor: 'pointer',
              fontSize: 10,
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
              width: 20,
              height: 20,
              border: '1px solid var(--line2)',
              borderRadius: 6,
              background: 'transparent',
              color: 'var(--tx3)',
              cursor: 'pointer',
              display: 'grid',
              placeItems: 'center',
              fontSize: 14,
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
                    fontSize: 11, fontFamily: 'var(--font-ui)',
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
                      fontSize: 11,
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
                    fontSize: 11,
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
    fontSize: 12,
    padding: '6px 9px',
    textAlign: 'left',
  }
}
