import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import { useStore } from '../store'
import { portColor } from '../portColors'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

interface NodeData extends NodeCookState {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  params: Record<string, unknown>
}

const COLOR = '#8b5cf6'

function OutputNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode   = useStore(s => s.cookNode)
  const edges      = useStore(s => s.edges)
  const nodes      = useStore(s => s.nodes)

  const valueHandleColor = (() => {
    const edge = edges.find(e => e.target === id && e.targetHandle === 'value')
    if (edge) {
      const src = nodes.find(n => n.id === edge.source)
      const t = src?.data?.output_types?.[edge.sourceHandle!] ?? 'Any'
      if (t !== 'Any') return portColor(t)
    }
    return portColor('Any')
  })()

  const { cooking, cookResult, cookError, replayResult, replayError, replayStatus } = data
  const replayHasResult = replayResult !== undefined || !!replayError
  const hasResult = cookResult !== undefined || !!cookError || replayHasResult

  const displayText = cooking
    ? null
    : cookError
    ? cookError
    : cookResult !== undefined
    ? (typeof cookResult === 'object' ? JSON.stringify(cookResult, null, 2) : String(cookResult))
    : replayError
    ? replayError
    : replayResult !== undefined
    ? (typeof replayResult === 'object' ? JSON.stringify(replayResult, null, 2) : String(replayResult))
    : null
  const isReplayValue = !cooking && cookResult === undefined && !cookError && replayHasResult

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={COLOR}
      selectedRingAlpha="44"
      style={{
        width: '100%',
        height: '100%',
        minWidth: 240,
        minHeight: 120,
        display: 'flex',
        flexDirection: 'column',
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
            background: valueHandleColor,
            width: 9, height: 9,
            border: `1.5px solid ${valueHandleColor}`,
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
        cursor: 'text',
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
          <>
            {isReplayValue && (
              <div style={{
                marginBottom: 7,
                color: replayError ? 'var(--err)' : replayStatus === 'done' ? 'var(--ok)' : 'var(--tx3)',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 700,
                textTransform: 'uppercase',
              }}>
                replay preview
              </div>
            )}
            <pre style={{
              margin: 0,
              color: cookError || replayError ? 'var(--err)' : 'var(--tx1)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              lineHeight: 1.65,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {displayText}
            </pre>
          </>
        )}
      </div>
    </NodeFrame>
  )
}

export default memo(OutputNode)
