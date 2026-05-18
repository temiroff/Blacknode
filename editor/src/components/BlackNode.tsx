import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'

interface NodeData {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  params: Record<string, unknown>
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
}

// colour per node category
const CATEGORY_COLORS: Record<string, string> = {
  LLMAgent:   '#6366f1',
  AgentLoop:  '#8b5cf6',
  EmbedText:  '#7c3aed',
  ToolCall:   '#a855f7',
  FileRead:   '#0891b2',
  FileWrite:  '#0891b2',
  HTTPGet:    '#0891b2',
  JSONParse:  '#0891b2',
  JSONDump:   '#0891b2',
  Branch:     '#d97706',
  Gate:       '#d97706',
  Map:        '#d97706',
  Filter:     '#d97706',
  Reduce:     '#d97706',
  Literal:    '#374151',
  Print:      '#374151',
  Concat:     '#374151',
  Switch:     '#374151',
}

function nodeColor(type: string) {
  return CATEGORY_COLORS[type] ?? '#1f2937'
}

function previewValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}

function BlackNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode = useStore(s => s.cookNode)
  const selectNode = useStore(s => s.selectNode)
  const color = nodeColor(data.type)

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
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

      {/* ports row */}
      <div style={{ position: 'relative', padding: '8px 0' }}>
        {/* input handles — left side */}
        {data.inputs.map((inp, i) => (
          <div key={inp} style={{ display: 'flex', alignItems: 'center', padding: '2px 10px 2px 20px', position: 'relative' }}>
            <Handle
              type="target"
              position={Position.Left}
              id={inp}
              style={{ left: 6, background: '#6b7280', width: 8, height: 8, border: '1px solid #9ca3af' }}
            />
            <span style={{ color: '#9ca3af', fontSize: 10 }}>{inp}</span>
          </div>
        ))}

        {/* output handles — right side */}
        {data.outputs.map((out, i) => (
          <div key={out} style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '2px 20px 2px 10px', position: 'relative' }}>
            <span style={{ color: '#9ca3af', fontSize: 10 }}>{out}</span>
            <Handle
              type="source"
              position={Position.Right}
              id={out}
              style={{ right: 6, background: '#22d3ee', width: 8, height: 8, border: '1px solid #67e8f9' }}
            />
          </div>
        ))}
      </div>

      {/* cook result / error */}
      {(data.cookResult !== undefined || data.cookError) && (
        <div style={{
          borderTop: '1px solid #374151',
          padding: '4px 10px 6px',
          color: data.cookError ? '#f87171' : '#4ade80',
          fontSize: 10,
          wordBreak: 'break-all',
        }}>
          {data.cookError ? `⚠ ${data.cookError}` : previewValue(data.cookResult)}
        </div>
      )}
    </div>
  )
}

export default memo(BlackNode)
