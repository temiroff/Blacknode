import { useCallback, useEffect, useRef } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  BackgroundVariant, ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useStore } from './store'
import BlackNode from './components/BlackNode'
import NodePalette from './components/NodePalette'
import Inspector from './components/Inspector'

const NODE_TYPES = { blacknode: BlackNode }

export default function App() {
  const {
    nodes, edges, serverOk,
    onNodesChange, onEdgesChange, onConnect,
    addNode, selectNode, loadNodeTypes, loadGraph, checkServer, reset,
  } = useStore()

  const rfInstance = useRef<ReactFlowInstance | null>(null)

  useEffect(() => {
    checkServer().then(() => {
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

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#030712' }}>
      {/* palette */}
      <NodePalette />

      {/* canvas */}
      <div style={{ flex: 1, position: 'relative' }} onDrop={onDrop} onDragOver={onDragOver}>
        {/* top bar */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
          background: '#0f172a', borderBottom: '1px solid #1e293b',
          display: 'flex', alignItems: 'center', gap: 12, padding: '6px 14px',
          fontFamily: 'monospace', fontSize: 12,
        }}>
          <span style={{ color: '#6366f1', fontWeight: 700, letterSpacing: 2 }}>BLACKNODE</span>
          <div style={{ flex: 1 }} />
          <span style={{
            padding: '2px 8px',
            borderRadius: 12,
            background: serverOk ? '#14532d' : '#450a0a',
            color: serverOk ? '#4ade80' : '#f87171',
            fontSize: 10,
          }}>
            {serverOk ? '● server' : '✕ offline'}
          </span>
          <button onClick={reset} style={topBtn('#7f1d1d')}>Reset</button>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={i => { rfInstance.current = i }}
          onNodeClick={(_, node) => selectNode(node.id)}
          onPaneClick={() => selectNode(null)}
          fitView
          style={{ paddingTop: 40 }}
          defaultEdgeOptions={{ style: { stroke: '#4b5563', strokeWidth: 1.5 }, animated: false }}
        >
          <Background variant={BackgroundVariant.Dots} color="#1e293b" gap={20} size={1} />
          <Controls style={{ background: '#0f172a', border: '1px solid #1e293b' }} />
          <MiniMap
            style={{ background: '#0f172a', border: '1px solid #1e293b' }}
            nodeColor={() => '#1e293b'}
          />
        </ReactFlow>
      </div>

      {/* inspector */}
      <Inspector />
    </div>
  )
}

function topBtn(bg: string): React.CSSProperties {
  return {
    background: bg,
    border: 'none',
    borderRadius: 4,
    color: '#fff',
    cursor: 'pointer',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: '4px 10px',
  }
}
