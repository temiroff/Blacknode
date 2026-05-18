import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'

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
  const dotColor  = isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)'
  const dotHex    = isCooking ? '#facc15'     : isError ? '#ef4444'    : '#22c55e'
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
        border: '1.5px solid var(--node)',
        boxShadow: `0 0 6px ${dotHex}88`,
        cursor: 'default',
      }} />
      {visible && (
        <div style={{
          position: 'absolute',
          bottom: 16, right: 0,
          width: 260,
          background: 'var(--panel)',
          border: `1px solid ${isError ? 'var(--err)' : 'var(--ok)'}`,
          borderRadius: 8,
          padding: '8px 10px',
          pointerEvents: 'none',
          zIndex: 100,
          boxShadow: '0 8px 24px rgba(0,0,0,.3)',
        }}>
          <div style={{
            color: isError ? 'var(--err)' : 'var(--ok)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
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
  const cookNode   = useStore(s => s.cookNode)
  const selectNode = useStore(s => s.selectNode)
  const color      = headerColor(data.type)
  const portsRef   = useRef<HTMLDivElement>(null)

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
      <StatusDot data={data} />

      {/* header */}
      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '6px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontWeight: 600, fontSize: 13, fontFamily: 'var(--font-ui)' }}>
          {data.type}
        </span>
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
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {/* ports */}
      <div ref={portsRef} style={{ flex: 1, padding: '6px 0' }}>
        {data.inputs.map(inp => (
          <PortRow key={inp} name={inp} type={data.input_types?.[inp] ?? 'Any'} dir="input" />
        ))}
        {data.outputs.map(out => (
          <PortRow key={out} name={out} type={data.output_types?.[out] ?? 'Any'} dir="output" />
        ))}
      </div>
    </div>
  )
}

export default memo(BlackNode)
