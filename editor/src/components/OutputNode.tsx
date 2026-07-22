import { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
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
  params: Record<string, unknown>
}

const COLOR = '#8b5cf6'

const isMediaSource = (value: unknown, dataPrefix: string): value is string =>
  typeof value === 'string'
  && (value.startsWith(dataPrefix) || value.startsWith('/') || /^https?:\/\//i.test(value))

const imageSourceFrom = (value: unknown): string | null => {
  if (isMediaSource(value, 'data:image/')) return value
  if (typeof value !== 'string') return null
  const svg = value.trim()
  return svg.startsWith('<svg') && svg.endsWith('</svg>')
    ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
    : null
}

function OutputNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode    = useStore(s => s.cookNode)
  const updateParam = useStore(s => s.updateParam)
  const edges      = useStore(s => s.edges)
  const nodes      = useStore(s => s.nodes)
  const qualifiedType = useQualifiedTypeLabel(data.type)
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const startRename = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLabelDraft(typeof data.params.label === 'string' ? data.params.label : data.type)
    setEditingLabel(true)
  }
  const commitRename = () => {
    setEditingLabel(false)
    const v = labelDraft.trim()
    updateParam(id, 'label', v || null).catch(() => {})
  }

  const valueEdge = edges.find(e => e.target === id && e.targetHandle === 'value')
  const sourceNode = valueEdge ? nodes.find(n => n.id === valueEdge.source) : undefined
  const sourceType = valueEdge
    ? sourceNode?.data?.output_types?.[valueEdge.sourceHandle!] ?? 'Any'
    : 'Any'
  const valueHandleColor = portColor(sourceType)

  const { cooking, cookResult, cookError, replayResult, replayError, replayStatus } = data
  const liveInput = data.portResults?.live === true
  const replayHasResult = replayResult !== undefined || !!replayError
  const hasResult = cookResult !== undefined || !!cookError || replayHasResult
  const customLabel = typeof data.params.label === 'string' && data.params.label.trim()
    ? data.params.label.trim()
    : null
  const label = customLabel ?? data.type

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
  const displayValue = cookResult !== undefined ? cookResult : replayResult
  const imageSource = !cookError && !replayError && sourceType === 'Image'
    ? imageSourceFrom(displayValue) : null
  const videoSource = !cookError && !replayError && sourceType === 'Video'
    && isMediaSource(displayValue, 'data:video/') ? displayValue : null
  const hasMedia = imageSource !== null || videoSource !== null
  const hasVisualMediaInput = sourceType === 'Image' || sourceType === 'Video'
  const mediaMinWidth = hasVisualMediaInput ? 860 : 240
  const mediaMinHeight = hasVisualMediaInput ? 720 : 120

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
        minWidth: mediaMinWidth,
        minHeight: mediaMinHeight,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={mediaMinWidth}
        minHeight={mediaMinHeight}
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
                color: '#fff', fontWeight: 700, fontSize: 12,
                fontFamily: 'var(--font-ui)', width: '100%', borderRadius: 3,
                padding: '1px 4px', letterSpacing: '0.08em',
              }}
            />
          ) : (
            <span
              title="Double-click to rename"
              onDoubleClick={startRename}
              style={{ fontWeight: 700, fontSize: 12, fontFamily: 'var(--font-ui)', letterSpacing: '0.08em', display: 'block', cursor: 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {label}
            </span>
          )}
          {!editingLabel && (
            <span
              title={`Node type ${data.type}`}
              style={{ fontSize: 9, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {qualifiedType}
            </span>
          )}
        </div>
        {liveInput && (
          <span
            title="This output is receiving values from a live upstream node"
            style={{ marginLeft: 'auto', marginRight: 8, color: '#dcfce7', fontSize: 10, fontWeight: 800, fontFamily: 'var(--font-ui)' }}
          >
            ● LIVE
          </span>
        )}
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
        <span style={{ color: 'var(--tx2)', fontSize: 12, fontFamily: 'var(--font-ui)' }}>
          value{sourceType !== 'Any' ? ` · ${sourceType}` : ''}
        </span>
      </div>

      {/* result area */}
      <div
        className="nodrag bn-output-scroll"
        tabIndex={0}
        aria-label="Scrollable output value"
        style={{
        flex: '1 1 0',
        minWidth: 0,
        minHeight: 0,
        overflowX: hasMedia ? 'hidden' : 'auto',
        overflowY: hasMedia ? 'hidden' : 'scroll',
        overscrollBehavior: 'contain',
        scrollbarGutter: 'stable',
        padding: hasMedia ? 6 : '10px 12px',
        cursor: hasMedia ? 'default' : 'text',
        position: 'relative',
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

        {!cooking && hasResult && hasMedia && (
          <>
            {isReplayValue && (
              <div style={{
                position: 'absolute',
                margin: 7,
                padding: '2px 6px',
                borderRadius: 4,
                background: 'rgba(0,0,0,.65)',
                color: 'var(--tx2)',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 700,
                textTransform: 'uppercase',
                zIndex: 1,
              }}>
                replay preview
              </div>
            )}
            {imageSource && (
              <img
                src={imageSource}
                alt={label}
                draggable={false}
                style={{ width: '100%', height: '100%', display: 'block', objectFit: 'contain', borderRadius: 5 }}
              />
            )}
            {videoSource && (
              <video
                src={videoSource}
                controls
                autoPlay
                muted
                playsInline
                style={{ width: '100%', height: '100%', display: 'block', objectFit: 'contain', borderRadius: 5 }}
              />
            )}
          </>
        )}

        {!cooking && hasResult && !hasMedia && (
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
              minWidth: '100%',
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
