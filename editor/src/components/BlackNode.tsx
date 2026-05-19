import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

const TOOLBOX_NEW_HANDLE_COLOR = '#ef444488'

interface NodeData extends NodeCookState {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
}

function PortRow({
  name,
  type,
  dir,
  onRemove,
}: {
  name: string
  type: string
  dir: 'input' | 'output'
  onRemove?: () => void
}) {
  const [hovering, setHovering] = useState(false)
  const color   = portColor(type)
  const isInput = dir === 'input'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: isInput ? 'flex-start' : 'flex-end',
        padding: isInput ? `4px 10px 4px ${onRemove ? 28 : 12}px` : '4px 12px 4px 10px',
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
      {onRemove && (
        <button
          onClick={e => { e.stopPropagation(); onRemove() }}
          onMouseDown={e => e.stopPropagation()}
          title="Remove slot"
          style={{
            position: 'absolute',
            left: 7,
            background: 'transparent',
            border: 'none',
            color: 'var(--tx3)',
            cursor: 'pointer',
            fontSize: 12,
            lineHeight: 1,
            padding: '0 2px',
            opacity: hovering ? 1 : 0.55,
          }}
        >
          x
        </button>
      )}
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
  const updateParam = useStore(s => s.updateParam)
  const disconnectEdge = useStore(s => s.disconnectEdge)
  const edges       = useStore(s => s.edges)
  const nodes       = useStore(s => s.nodes)
  const updateNodeInternals = useUpdateNodeInternals()
  const color       = headerColor(data.type)
  const isToolBox   = data.type === 'ToolBox'
  const visibleInputs = data.inputs ?? []
  const inputsKey = visibleInputs.join('|')
  const outputsKey = (data.outputs ?? []).join('|')

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

  const removeToolSlot = async (port: string) => {
    const edge = edges.find(e => e.target === id && e.targetHandle === port)
    if (edge) await disconnectEdge(edge.id)
  }

  useEffect(() => {
    const el = portsRef.current
    if (!el) return
    const stop = (e: WheelEvent) => e.stopPropagation()
    el.addEventListener('wheel', stop)
    return () => el.removeEventListener('wheel', stop)
  }, [])

  useEffect(() => {
    updateNodeInternals(id)
  }, [id, inputsKey, outputsKey, updateNodeInternals])

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={color}
      style={{
        width: '100%',
        height: '100%',
        minWidth: 160,
        minHeight: 60,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={160}
        minHeight={60}
        isVisible={selected}
        lineStyle={{ borderColor: color }}
        handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
      />

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
        {isToolBox && (
          <div style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            padding: '6px 10px 2px 16px',
          }}>
            <Handle
              type="target"
              position={Position.Left}
              id="__new__"
              style={{
                left: -5,
                background: 'var(--node)',
                width: 11,
                height: 11,
                border: `2px dashed ${TOOLBOX_NEW_HANDLE_COLOR}`,
                borderRadius: '50%',
              }}
            />
            <span style={{ fontSize: 9, color: TOOLBOX_NEW_HANDLE_COLOR, fontFamily: 'var(--font-ui)', userSelect: 'none' }}>
              ← drag to create
            </span>
          </div>
        )}
        {visibleInputs.map(inp => (
          <PortRow
            key={inp}
            name={inp}
            type={effectivePortType(inp, 'input')}
            dir="input"
            onRemove={isToolBox ? () => removeToolSlot(inp) : undefined}
          />
        ))}
        {data.outputs.map(out => (
          <PortRow key={out} name={out} type={effectivePortType(out, 'output')} dir="output" />
        ))}
      </div>
    </NodeFrame>
  )
}

export default memo(BlackNode)
