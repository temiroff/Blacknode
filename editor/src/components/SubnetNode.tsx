import { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { useQualifiedTypeLabel } from '../nodeTypeLabel'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

interface NodeData extends NodeCookState {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
}

const SUBNET_HEADER = '#6366f1'
const TOOL_HEADER = '#14b8a6'

function SubnetNode({ id, data, selected }: NodeProps<NodeData>) {
  const { diveIntoSubnet, cookNode, updateParam } = useStore()
  const edges = useStore(s => s.edges)
  const nodes = useStore(s => s.nodes)
  const qualifiedType = useQualifiedTypeLabel(data.type)
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
  const isToolSubnet = data.type === 'SubnetAsTool'
  const isVisualLoop = data.type === 'VisualAgentLoop'
  const headerColor = isToolSubnet ? TOOL_HEADER : SUBNET_HEADER
  const labelKey = isToolSubnet ? 'name' : 'label'
  const label = String(data.params?.[labelKey] ?? (isVisualLoop ? 'VisualAgentLoop' : isToolSubnet ? 'tool' : 'Subnet'))

  const startRename = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLabelDraft(label)
    setEditingLabel(true)
  }
  const commitRename = () => {
    setEditingLabel(false)
    const v = labelDraft.trim()
    if (v && v !== label) updateParam(id, labelKey, v).catch(() => {})
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={headerColor}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        minWidth: 160,
      }}
    >
      {/* header */}
      <div style={{
        background: headerColor,
        borderRadius: '8px 8px 0 0',
        padding: '5px 8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 6,
      }}>
        <span style={{ fontSize: 10, opacity: 0.7, flexShrink: 0 }}>{isToolSubnet ? 'fn' : isVisualLoop ? 'loop' : '⬡'}</span>
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
                width: '100%', background: 'rgba(0,0,0,.25)', border: 'none', outline: 'none',
                color: '#fff', fontWeight: 600, fontSize: 12,
                fontFamily: 'var(--font-ui)', borderRadius: 3, padding: '1px 4px',
              }}
            />
          ) : (
            <span
              title={isToolSubnet ? 'Double-click to rename tool' : isVisualLoop ? 'Double-click to rename loop' : 'Double-click to rename'}
              onDoubleClick={startRename}
              style={{ display: 'block', fontWeight: 600, fontSize: 12, fontFamily: 'var(--font-ui)', cursor: 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {label}
            </span>
          )}
          {!editingLabel && (
            <span
              title={`Node type ${data.type}`}
              style={{ fontSize: 8, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {qualifiedType}
            </span>
          )}
        </div>
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
          title={isToolSubnet ? 'Build tool inside' : isVisualLoop ? 'Inspect loop inside' : 'Dive inside'}
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
          {isToolSubnet ? 'double-click to build tool' : isVisualLoop ? 'double-click to inspect loop' : 'double-click to dive in'}
        </div>
      )}
    </NodeFrame>
  )
}

export default memo(SubnetNode)
