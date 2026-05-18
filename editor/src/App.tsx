import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance, Edge, Connection, SelectionMode,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore } from './store'
import BlackNode from './components/BlackNode'
import ValueNode from './components/ValueNode'
import ModelNode from './components/ModelNode'
import OutputNode from './components/OutputNode'
import NodePalette from './components/NodePalette'
import Inspector from './components/Inspector'
import NodeSearch from './components/NodeSearch'

const NODE_TYPES = { blacknode: BlackNode, valuenode: ValueNode, modelnode: ModelNode, outputnode: OutputNode }

const TAB_H = 36  // workflow tab bar height

export default function App() {
  const {
    nodes, edges, serverOk,
    tabs, activeTabId,
    onNodesChange, onEdgesChange, onConnect, disconnectEdge, reconnectEdge,
    addNode, selectNode, loadNodeTypes, loadGraph, loadApiKeys, loadCustomModels,
    checkServer, reset, newTab, insertTab, switchTab, closeTab, duplicateTab,
    renameTab, saveActiveWorkflow,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const [search, setSearch] = useState<{ screenPos: { x: number; y: number }; flowPos: { x: number; y: number } } | null>(null)
  const [isDark, setIsDark] = useState(true)
  const [editingTabId, setEditingTabId] = useState<string | null>(null)
  const [tabDraft, setTabDraft] = useState('')
  const [savingWorkflow, setSavingWorkflow] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const [tabMenu, setTabMenu] = useState<{ x: number; y: number; tabId: string } | null>(null)
  const saveOkTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const needsSave = Boolean(activeTab && (activeTab.dirty || !activeTab.slug))
  const menuTab = tabMenu ? tabs.find(tab => tab.id === tabMenu.tabId) : null

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  useEffect(() => {
    return () => {
      if (saveOkTimer.current) clearTimeout(saveOkTimer.current)
    }
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

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const type = e.dataTransfer.getData('application/blacknode-type')
    if (!type || !rfInstance.current) return
    const pos = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNode(type, pos)
  }, [addNode])

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const onPaneContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    if (!rfInstance.current) return
    const flowPos = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    setSearch({ screenPos: { x: e.clientX, y: e.clientY }, flowPos })
  }, [])

  const handleSearchSelect = useCallback((type: string) => {
    if (!search) return
    addNode(type, search.flowPos)
    setSearch(null)
  }, [search, addNode])

  const edgeReconnected = useRef(false)
  const onEdgeUpdateStart = useCallback(() => { edgeReconnected.current = false }, [])
  const onEdgeUpdate = useCallback((oldEdge: Edge, newConn: Connection) => {
    edgeReconnected.current = true
    reconnectEdge(oldEdge, newConn)
  }, [reconnectEdge])
  const onEdgeUpdateEnd = useCallback((_: MouseEvent | TouchEvent, edge: Edge) => {
    if (!edgeReconnected.current) disconnectEdge(edge.id)
  }, [disconnectEdge])
  const onEdgeDoubleClick = useCallback((_: React.MouseEvent, edge: any) => {
    disconnectEdge(edge.id)
  }, [disconnectEdge])

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

      <div style={{ flex: 1, position: 'relative' }} onDrop={onDrop} onDragOver={onDragOver}>

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
            letterSpacing: '0.12em',
            fontFamily: 'var(--font-ui)',
          }}>
            BLACKNODE
          </span>

          <div style={{ flex: 1 }} />

          <span style={{ color: 'var(--tx3)', fontSize: 12 }}>right-click to add</span>

          <span style={{
            padding: '3px 10px',
            borderRadius: 20,
            background: serverOk ? (isDark ? '#0d2a1a' : '#dcfce7') : (isDark ? '#2a0d0d' : '#fee2e2'),
            color: serverOk ? 'var(--ok)' : 'var(--err)',
            fontSize: 12,
            fontWeight: 500,
          }}>
            {serverOk ? '● server' : '○ offline'}
          </span>

          <button
            onClick={() => setIsDark(d => !d)}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              background: 'var(--hover)',
              border: '1px solid var(--line2)',
              borderRadius: 6,
              color: 'var(--tx2)',
              cursor: 'pointer',
              fontSize: 15,
              width: 32, height: 32,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            {isDark ? '☀' : '☾'}
          </button>

          <button
            onClick={() => void reset()}
            style={{
              background: 'transparent',
              border: '1px solid var(--line2)',
              borderRadius: 6,
              color: 'var(--err)',
              cursor: 'pointer',
              fontFamily: 'var(--font-ui)',
              fontSize: 12,
              fontWeight: 500,
              padding: '5px 12px',
            }}
          >
            Clear
          </button>
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
                  background: active ? 'var(--panel)' : 'transparent',
                  color: active ? 'var(--tx1)' : 'var(--tx3)',
                  border: `1px solid ${active ? 'var(--line2)' : 'transparent'}`,
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

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeDoubleClick={onEdgeDoubleClick}
          onEdgeUpdateStart={onEdgeUpdateStart}
          onEdgeUpdate={onEdgeUpdate}
          onEdgeUpdateEnd={onEdgeUpdateEnd}
          onInit={i => { rfInstance.current = i }}
          onNodeClick={(_, node) => selectNode(node.id)}
          onPaneClick={() => { selectNode(null); setSearch(null); setTabMenu(null) }}
          onPaneContextMenu={onPaneContextMenu}
          fitView
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
          onSelect={handleSearchSelect}
          onClose={() => setSearch(null)}
        />
      )}
    </div>
  )
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
