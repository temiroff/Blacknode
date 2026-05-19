import { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'

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

const HEADER = '#6366f1'

function SubnetNode({ id, data, selected }: NodeProps<NodeData>) {
  const { selectNode, diveIntoSubnet, cookNode, updateParam } = useStore()
  const edges = useStore(s => s.edges)
  const nodes = useStore(s => s.nodes)
  const [hovered, setHovered] = useState(false)

  const effectiveColor = (portName: string, side: 'input' | 'output'): string => {
    const declared = side === 'input'
      ? (data.input_types?.[portName] ?? 'Any')
      : (data.output_types?.[portName] ?? 'Any')
    if (declared !== 'Any') return portColor(declared)
    if (side === 'input') {
      const edge = edges.find(e => e.target === id && e.targetHandle === portName)
      if (edge) {
        const src = nodes.find(n => n.id === edge.source)
        const t = src?.data?.output_types?.[edge.sourceHandle!] ?? 'Any'
        if (t !== 'Any') return portColor(t)
      }
    } else {
      const edge = edges.find(e => e.source === id && e.sourceHandle === portName)
      if (edge) {
        const tgt = nodes.find(n => n.id === edge.target)
        const t = tgt?.data?.input_types?.[edge.targetHandle!] ?? 'Any'
        if (t !== 'Any') return portColor(t)
      }
    }
    return portColor('Any')
  }
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const label = String(data.params?.label ?? 'Subnet')

  const startRename = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLabelDraft(label)
    setEditingLabel(true)
  }
  const commitRename = () => {
    setEditingLabel(false)
    const v = labelDraft.trim()
    if (v && v !== label) updateParam(id, 'label', v).catch(() => {})
  }

  return (
    <div
      onClick={() => selectNode(id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        minWidth: 160,
        background: 'var(--node)',
        border: `1px solid ${selected ? HEADER : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${HEADER}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
      }}
    >
      {/* header */}
      <div style={{
        background: HEADER,
        borderRadius: '8px 8px 0 0',
        padding: '5px 8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 6,
      }}>
        <span style={{ fontSize: 10, opacity: 0.7, flexShrink: 0 }}>⬡</span>
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
              flex: 1, background: 'rgba(0,0,0,.25)', border: 'none', outline: 'none',
              color: '#fff', fontWeight: 600, fontSize: 12,
              fontFamily: 'var(--font-ui)', borderRadius: 3, padding: '1px 4px',
            }}
          />
        ) : (
          <span
            title="Double-click to rename"
            onDoubleClick={startRename}
            style={{ flex: 1, fontWeight: 600, fontSize: 12, fontFamily: 'var(--font-ui)', cursor: 'text' }}
          >
            {label}
          </span>
        )}
        <button
          title="Cook"
          onClick={e => { e.stopPropagation(); cookNode(id, data.outputs[0] ?? 'output') }}
          style={{
            background: 'rgba(0,0,0,.2)', border: 'none', borderRadius: 3,
            color: '#fff', cursor: 'pointer', fontSize: 9, padding: '1px 5px',
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
        <button
          title="Dive inside"
          onClick={e => { e.stopPropagation(); diveIntoSubnet(id) }}
          style={{
            background: 'rgba(255,255,255,.15)', border: 'none', borderRadius: 3,
            color: '#fff', cursor: 'pointer', fontSize: 10, padding: '1px 5px',
          }}
        >
          ↓
        </button>
      </div>

      {/* ports */}
      <div style={{ padding: '6px 0', minHeight: 28 }}>
        {data.inputs.map((inp, i) => (
          <div key={inp} style={{ position: 'relative', padding: '2px 28px 2px 14px', fontSize: 11, color: 'var(--tx2)' }}>
            {inp}
            <Handle
              type="target"
              position={Position.Left}
              id={inp}
              style={{
                left: -5, top: '50%',
                background: effectiveColor(inp, 'input'),
                width: 9, height: 9,
                border: `1.5px solid ${effectiveColor(inp, 'input')}`,
                borderRadius: 3,
              }}
            />
          </div>
        ))}
        {data.outputs.map((out) => (
          <div key={out} style={{ position: 'relative', padding: '2px 14px 2px 28px', fontSize: 11, color: 'var(--tx2)', textAlign: 'right' }}>
            {out}
            <Handle
              type="source"
              position={Position.Right}
              id={out}
              style={{
                right: -5, top: '50%',
                background: effectiveColor(out, 'output'),
                width: 9, height: 9,
                border: `1.5px solid ${effectiveColor(out, 'output')}`,
                borderRadius: 3,
              }}
            />
          </div>
        ))}
      </div>

      {hovered && (
        <div style={{
          position: 'absolute', bottom: -20, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 4,
          padding: '2px 6px', fontSize: 10, color: 'var(--tx2)', whiteSpace: 'nowrap', pointerEvents: 'none',
        }}>
          double-click to dive in
        </div>
      )}
    </div>
  )
}

export default memo(SubnetNode)
