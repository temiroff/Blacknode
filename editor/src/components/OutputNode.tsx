import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import { useStore } from '../store'
import { portColor } from '../portColors'

interface NodeData {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  params: Record<string, unknown>
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
}

const COLOR = '#8b5cf6'

function OutputNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode   = useStore(s => s.cookNode)
  const selectNode = useStore(s => s.selectNode)

  const { cooking, cookResult, cookError } = data
  const hasResult = cookResult !== undefined || !!cookError

  const displayText = cooking
    ? null
    : cookError
    ? cookError
    : cookResult !== undefined
    ? (typeof cookResult === 'object' ? JSON.stringify(cookResult, null, 2) : String(cookResult))
    : null

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minWidth: 240,
        minHeight: 120,
        background: 'var(--node)',
        border: `1px solid ${selected ? COLOR : 'var(--line2)'}`,
        borderRadius: 9,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${COLOR}44, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
      }}
    >
      <NodeResizer
        minWidth={240}
        minHeight={120}
        isVisible={selected}
        lineStyle={{ borderColor: COLOR }}
        handleStyle={{ background: COLOR, borderColor: COLOR, width: 8, height: 8, borderRadius: 2 }}
      />

      {/* header */}
      <div style={{
        background: COLOR,
        borderRadius: '8px 8px 0 0',
        padding: '6px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: 12, fontFamily: 'var(--font-ui)', letterSpacing: '0.08em' }}>
          OUTPUT
        </span>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, 'value') }}
          style={{
            background: cooking ? 'rgba(0,0,0,.3)' : 'rgba(0,0,0,.2)',
            border: 'none',
            borderRadius: 5,
            color: '#fff',
            cursor: cooking ? 'default' : 'pointer',
            fontSize: 11,
            fontFamily: 'var(--font-ui)',
            fontWeight: 600,
            padding: '3px 10px',
          }}
        >
          {cooking ? '● running…' : '▶  Cook'}
        </button>
      </div>

      {/* input port */}
      <div style={{
        padding: '6px 10px 6px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        borderBottom: '1px solid var(--line)',
        flexShrink: 0,
        position: 'relative',
      }}>
        <Handle
          type="target"
          position={Position.Left}
          id="value"
          style={{
            left: -5,
            background: portColor('Any'),
            width: 9, height: 9,
            border: `1.5px solid ${portColor('Any')}`,
            borderRadius: 3,
          }}
        />
        <span style={{ color: 'var(--tx2)', fontSize: 12, fontFamily: 'var(--font-ui)' }}>value</span>
      </div>

      {/* result area */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: '10px 12px',
      }}>
        {cooking && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            color: 'var(--warn)',
            fontSize: 13,
          }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>◌</span>
            Running…
          </div>
        )}

        {!cooking && !hasResult && (
          <div style={{ color: 'var(--tx3)', fontSize: 12, fontStyle: 'italic' }}>
            Wire a node in, then click Cook
          </div>
        )}

        {!cooking && hasResult && (
          <pre style={{
            margin: 0,
            color: cookError ? 'var(--err)' : 'var(--tx1)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            lineHeight: 1.65,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {displayText}
          </pre>
        )}
      </div>
    </div>
  )
}

export default memo(OutputNode)
