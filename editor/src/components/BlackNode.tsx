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
}

const HEADER_COLORS: Record<string, string> = {
  LLMAgent:  '#6366f1',
  AgentLoop: '#8b5cf6',
  EmbedText: '#7c3aed',
  ToolCall:  '#a855f7',
  FileRead:  '#0891b2',
  FileWrite: '#0891b2',
  HTTPGet:   '#0891b2',
  JSONParse: '#0891b2',
  JSONDump:  '#0891b2',
  Branch:    '#d97706',
  Gate:      '#d97706',
  Map:       '#d97706',
  Filter:    '#d97706',
  Reduce:    '#d97706',
  Literal:   '#374151',
  Print:     '#374151',
  Concat:    '#374151',
  Switch:    '#374151',
}

function headerColor(type: string) {
  return HEADER_COLORS[type] ?? '#1f2937'
}

function previewValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
  return s.length > 400 ? s.slice(0, 400) + '\n…' : s
}

function StatusDot({ data }: { data: NodeData }) {
  const [visible, setVisible] = useState(false)

  if (!data.cookError && data.cookResult === undefined && !data.cooking) return null

  const isError   = !!data.cookError
  const isCooking = !!data.cooking
  const dotColor  = isCooking ? '#facc15' : isError ? '#ef4444' : '#22c55e'
  const label     = isCooking ? 'cooking…' : isError ? data.cookError! : previewValue(data.cookResult)

  return (
    <div
      style={{ position: 'absolute', top: -5, right: -5, zIndex: 20 }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      <div style={{
        width: 10, height: 10,
        borderRadius: '50%',
        background: dotColor,
        border: '1.5px solid #111827',
        boxShadow: `0 0 6px ${dotColor}`,
        cursor: 'default',
      }} />
      {visible && (
        <div style={{
          position: 'absolute',
          bottom: 16,
          right: 0,
          width: 260,
          background: '#0f172a',
          border: `1px solid ${isError ? '#ef4444' : '#22c55e'}`,
          borderRadius: 6,
          padding: '8px 10px',
          pointerEvents: 'none',
          zIndex: 100,
        }}>
          <div style={{
            color: isError ? '#f87171' : '#86efac',
            fontFamily: 'monospace',
            fontSize: 10,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxHeight: 200,
            overflowY: 'auto',
          }}>
            {label}
          </div>
        </div>
      )}
    </div>
  )
}

function PortRow({
  name, type, dir,
}: {
  name: string
  type: string
  dir: 'input' | 'output'
}) {
  const [hovering, setHovering] = useState(false)
  const color = portColor(type)
  const isInput = dir === 'input'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: isInput ? 'flex-start' : 'flex-end',
        padding: isInput ? '3px 10px 3px 18px' : '3px 18px 3px 10px',
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
          [isInput ? 'left' : 'right']: 4,
          background: color,
          width: 9,
          height: 9,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
          boxShadow: hovering ? `0 0 6px ${color}` : undefined,
          transition: 'box-shadow 0.15s',
        }}
      />

      {/* port name */}
      <span style={{ color: '#9ca3af', fontSize: 10 }}>{name}</span>

      {/* type badge — visible on hover */}
      {hovering && (
        <span style={{
          fontSize: 9,
          padding: '1px 4px',
          borderRadius: 3,
          background: color + '33',
          color: color,
          fontFamily: 'monospace',
          whiteSpace: 'nowrap',
        }}>
          {type}
        </span>
      )}
    </div>
  )
}

function BlackNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode   = useStore(s => s.cookNode)
  const selectNode = useStore(s => s.selectNode)
  const color      = headerColor(data.type)

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        minWidth: 160,
        background: '#111827',
        border: `1px solid ${selected ? '#f9fafb' : '#374151'}`,
        borderRadius: 8,
        fontFamily: 'monospace',
        fontSize: 12,
        color: '#f9fafb',
        boxShadow: selected ? `0 0 0 2px ${color}` : '0 2px 8px rgba(0,0,0,.5)',
        cursor: 'default',
      }}
    >
      <StatusDot data={data} />

      {/* header */}
      <div style={{
        background: color,
        borderRadius: '7px 7px 0 0',
        padding: '5px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontWeight: 600 }}>{data.type}</span>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, data.outputs[0] ?? 'output') }}
          style={{
            background: 'rgba(255,255,255,.15)',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            cursor: 'pointer',
            fontSize: 10,
            padding: '2px 6px',
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {/* ports */}
      <div style={{ padding: '6px 0' }}>
        {data.inputs.map(inp => (
          <PortRow
            key={inp}
            name={inp}
            type={data.input_types?.[inp] ?? 'Any'}
            dir="input"
          />
        ))}
        {data.outputs.map(out => (
          <PortRow
            key={out}
            name={out}
            type={data.output_types?.[out] ?? 'Any'}
            dir="output"
          />
        ))}
      </div>
    </div>
  )
}

export default memo(BlackNode)
