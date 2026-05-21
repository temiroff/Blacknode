import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance, Edge, Connection, SelectionMode,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore, type CookLogEntry, type GraphClipboard } from './store'
import BlackNode from './components/BlackNode'
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
import { api } from './api'

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

export default function App() {
  const {
    nodes, edges, nodeTypes, nodeDefs, serverOk, cookLog, cookActive,
    tabs, activeTabId,
    onNodesChange, onEdgesChange, onConnect: storeOnConnect, disconnectEdge, reconnectEdge,
    addNode, selectNode, loadNodeTypes, loadGraph, loadApiKeys, loadCustomModels,
    addNodeFromConnection, copySelection, pasteClipboard,
    beginAltDragCopy, finishAltDragCopy, undoGraph,
    checkServer, reset, newTab, insertTab, switchTab, closeTab, duplicateTab,
    openGraphAsTab, openWorkflowAsTab, renameTab, saveActiveWorkflow,
    diveIntoSubnet, exitSubnet, collapseToSubnet, organizeNodes, cookNode,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const [search, setSearch] = useState<SearchState | null>(null)
  const [isDark, setIsDark] = useState(true)
  const [editingTabId, setEditingTabId] = useState<string | null>(null)
  const [tabDraft, setTabDraft] = useState('')
  const [savingWorkflow, setSavingWorkflow] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const [tabMenu, setTabMenu] = useState<{ x: number; y: number; tabId: string } | null>(null)
  const [notice, setNotice] = useState<NoticeState | null>(null)
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
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const needsSave = Boolean(activeTab && (activeTab.dirty || !activeTab.slug))
  const menuTab = tabMenu ? tabs.find(tab => tab.id === tabMenu.tabId) : null

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
    checkServer().then(() => {
      loadApiKeys()
      loadCustomModels()
      loadNodeTypes()
      loadGraph()
    })
    const id = setInterval(checkServer, 5000)
    return () => clearInterval(id)
  }, [])

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

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const type = e.dataTransfer.getData('application/blacknode-type')
    if (!type || !rfInstance.current) return
    const paramsRaw = e.dataTransfer.getData('application/blacknode-params')
    const params = paramsRaw ? JSON.parse(paramsRaw) : {}
    const pos = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNode(type, pos, params)
  }, [addNode])

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
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

  const handleOrganize = useCallback(async () => {
    await organizeNodes()
    fitCurrentCanvas(320)
  }, [fitCurrentCanvas, organizeNodes])

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
          <span style={{
            color: 'var(--tx2)',
            fontWeight: 700,
            fontSize: 15,
            letterSpacing: 0,
            fontFamily: 'var(--font-ui)',
          }}>
            BLACKNODE
          </span>

          <div style={{ flex: 1 }} />

          <span style={{ color: 'var(--tx3)', fontSize: 12 }}>right-click to add</span>

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
          }}>
            {serverOk ? '● server' : '○ offline'}
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
                {(tab.dirty || !tab.slug) && !editing && (
                  <span style={{ color: 'var(--tx3)', fontSize: 14, lineHeight: 1 }}>•</span>
                )}
                {tabs.length > 1 && (
                  <button
                    onClick={e => { e.stopPropagation(); void closeTab(tab.id) }}
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
                )}
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
              style={menuItemStyle(tabs.length <= 1, 'var(--err)')}
              disabled={tabs.length <= 1}
              onClick={() => runTabMenuAction(() => closeTab(menuTab.id))}
            >
              Delete
            </button>
          </div>
        )}

        <SubnetBreadcrumb />

        <CookStatusPanel entries={cookLog} active={cookActive} raised={Boolean(notice)} />

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
          }}
          onPaneContextMenu={onPaneContextMenu}
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
  raised,
}: {
  entries: CookLogEntry[]
  active: boolean
  raised: boolean
}) {
  if (entries.length === 0) return null
  const latest = entries[entries.length - 1]
  const recent = entries.slice(-8).reverse()
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
        </div>

        <div style={{ maxHeight: 168, overflowY: 'auto', padding: '4px 0' }}>
          {recent.map(entry => {
            const color = entry.kind === 'error'
              ? 'var(--err)'
              : entry.kind === 'start'
                ? 'var(--warn)'
                : entry.kind === 'done'
                  ? 'var(--accent)'
                  : 'var(--ok)'
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
      </div>
    </div>
  )
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
