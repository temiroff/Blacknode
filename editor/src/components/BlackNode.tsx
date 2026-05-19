import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import NodeStatus from './NodeStatus'

interface NodeData {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
  cookPort?: string
}

function PortRow({ name, type, dir }: { name: string; type: string; dir: 'input' | 'output' }) {
  const [hovering, setHovering] = useState(false)
  const color   = portColor(type)
  const isInput = dir === 'input'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: isInput ? 'flex-start' : 'flex-end',
        padding: isInput ? '4px 10px 4px 12px' : '4px 12px 4px 10px',
        position: 'relative',
        gap: 5,
      }}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <Handle
        type={isInput ? 'target' : 'source'}
        position={isInput ? Position.Left : Position.Right}
        id={name}
        style={{
          [isInput ? 'left' : 'right']: -5,
          background: color,
          width: 9, height: 9,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
          boxShadow: hovering ? `0 0 6px ${color}` : undefined,
          transition: 'box-shadow 0.15s',
        }}
      />
      <span style={{
        color: 'var(--tx2)',
        fontSize: 12,
        fontFamily: 'var(--font-ui)',
      }}>
        {name}
      </span>
      {hovering && (
        <span style={{
          fontSize: 11,
          padding: '1px 6px',
          borderRadius: 4,
          background: color + '28',
          color: color,
          fontFamily: 'var(--font-mono)',
          whiteSpace: 'nowrap',
        }}>
          {type}
        </span>
      )}
    </div>
  )
}

function BlackNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode    = useStore(s => s.cookNode)
  const selectNode  = useStore(s => s.selectNode)
  const updateParam = useStore(s => s.updateParam)
  const edges       = useStore(s => s.edges)
  const nodes       = useStore(s => s.nodes)
  const color       = headerColor(data.type)

  const effectivePortType = (portName: string, side: 'input' | 'output'): string => {
    const declared = side === 'input'
      ? (data.input_types?.[portName] ?? 'Any')
      : (data.output_types?.[portName] ?? 'Any')
    if (declared !== 'Any') return declared
    if (side === 'input') {
      const edge = edges.find(e => e.target === id && e.targetHandle === portName)
      if (edge) {
        const src = nodes.find(n => n.id === edge.source)
        const t = src?.data?.output_types?.[edge.sourceHandle!] ?? 'Any'
        if (t !== 'Any') return t
      }
    } else {
      const edge = edges.find(e => e.source === id && e.sourceHandle === portName)
      if (edge) {
        const tgt = nodes.find(n => n.id === edge.target)
        const t = tgt?.data?.input_types?.[edge.targetHandle!] ?? 'Any'
        if (t !== 'Any') return t
      }
    }
    return 'Any'
  }
  const portsRef    = useRef<HTMLDivElement>(null)
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const label = data.params?.label ? String(data.params.label) : null

  const startRename = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLabelDraft(label ?? data.type)
    setEditingLabel(true)
  }
  const commitRename = () => {
    setEditingLabel(false)
    const v = labelDraft.trim()
    updateParam(id, 'label', v || null).catch(() => {})
  }

  useEffect(() => {
    const el = portsRef.current
    if (!el) return
    const stop = (e: WheelEvent) => e.stopPropagation()
    el.addEventListener('wheel', stop)
    return () => el.removeEventListener('wheel', stop)
  }, [])

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minWidth: 160,
        minHeight: 60,
        background: 'var(--node)',
        border: `1px solid ${selected ? color : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${color}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        overflow: 'visible',
      }}
    >
      <NodeResizer
        minWidth={160}
        minHeight={60}
        isVisible={selected}
        lineStyle={{ borderColor: color }}
        handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
      />
      <NodeStatus data={data} />

      {/* header */}
      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '6px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 6,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {editingLabel ? (
            <input
              autoFocus
              value={labelDraft}
              onChange={e => setLabelDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); commitRename() }
                if (e.key === 'Escape') setEditingLabel(false)
              }}
              onClick={e => e.stopPropagation()}
              onMouseDown={e => e.stopPropagation()}
              style={{
                background: 'rgba(0,0,0,.25)', border: 'none', outline: 'none',
                color: '#fff', fontWeight: 600, fontSize: 13,
                fontFamily: 'var(--font-ui)', width: '100%', borderRadius: 3,
                padding: '1px 4px',
              }}
            />
          ) : (
            <span
              title="Double-click to rename"
              onDoubleClick={startRename}
              style={{ fontWeight: 600, fontSize: 13, fontFamily: 'var(--font-ui)', display: 'block', cursor: 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {label ?? data.type}
            </span>
          )}
          {label && !editingLabel && (
            <span style={{ fontSize: 9, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1 }}>
              {data.type}
            </span>
          )}
        </div>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, data.outputs[0] ?? 'output') }}
          style={{
            background: 'rgba(0,0,0,.2)',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            cursor: 'pointer',
            fontSize: 10,
            padding: '2px 7px',
            fontFamily: 'var(--font-ui)',
            flexShrink: 0,
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {/* ports */}
      <div ref={portsRef} style={{ flex: 1, padding: '6px 0' }}>
        {data.inputs.map(inp => (
          <PortRow key={inp} name={inp} type={effectivePortType(inp, 'input')} dir="input" />
        ))}
        {data.outputs.map(out => (
          <PortRow key={out} name={out} type={effectivePortType(out, 'output')} dir="output" />
        ))}
      </div>
    </div>
  )
}

export default memo(BlackNode)
