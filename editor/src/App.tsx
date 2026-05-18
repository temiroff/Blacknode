import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore } from './store'
import { api } from './api'
import BlackNode from './components/BlackNode'
import ValueNode from './components/ValueNode'
import ModelNode from './components/ModelNode'
import OutputNode from './components/OutputNode'
import NodePalette from './components/NodePalette'
import Inspector from './components/Inspector'
import NodeSearch from './components/NodeSearch'

const NODE_TYPES = { blacknode: BlackNode, valuenode: ValueNode, modelnode: ModelNode, outputnode: OutputNode }

export default function App() {
  const {
    nodes, edges, serverOk,
    onNodesChange, onEdgesChange, onConnect, disconnectEdge,
    addNode, selectNode, loadNodeTypes, loadGraph, loadApiKeys, checkServer, reset,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const [search, setSearch] = useState<{ screenPos: { x: number; y: number }; flowPos: { x: number; y: number } } | null>(null)
  const [isDark, setIsDark] = useState(true)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  useEffect(() => {
    checkServer().then(() => {
      loadApiKeys()
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

  const onEdgeDoubleClick = useCallback((_: React.MouseEvent, edge: any) => {
    disconnectEdge(edge.id)
  }, [disconnectEdge])

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)' }}>
      <NodePalette />

      <div style={{ flex: 1, position: 'relative' }} onDrop={onDrop} onDragOver={onDragOver}>
        {/* top bar */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
          background: 'var(--panel)',
          borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px',
          height: 44,
        }}>
          <span style={{
            color: 'var(--accent)',
            fontWeight: 700,
            fontSize: 15,
            letterSpacing: '0.12em',
            fontFamily: 'var(--font-ui)',
          }}>
            BLACKNODE
          </span>

          <div style={{ flex: 1 }} />

          <span style={{ color: 'var(--tx2)', fontSize: 12 }}>right-click canvas to add</span>

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
              transition: 'color 0.15s',
            }}
          >
            {isDark ? '☀' : '☾'}
          </button>

          <button
            onClick={reset}
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
            Reset
          </button>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeDoubleClick={onEdgeDoubleClick}
          onInit={i => { rfInstance.current = i }}
          onNodeClick={(_, node) => selectNode(node.id)}
          onPaneClick={() => { selectNode(null); setSearch(null) }}
          onPaneContextMenu={onPaneContextMenu}
          fitView
          deleteKeyCode={['Delete', 'Backspace']}
          style={{ paddingTop: 44 }}
          defaultEdgeOptions={{
            style: { stroke: isDark ? '#2c2e40' : '#bbbcce', strokeWidth: 1.5 },
            animated: false,
          }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            color={isDark ? '#1a1b2a' : '#d0d1e0'}
            gap={24}
            size={1.2}
          />
          <Controls />
          <MiniMap nodeColor={() => isDark ? '#1e2030' : '#e0e0ec'} />
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
