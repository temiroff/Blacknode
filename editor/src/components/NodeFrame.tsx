import type { CSSProperties, ReactNode } from 'react'
import { useStore } from '../store'
import NodeStatus from './NodeStatus'
import type { NodeCookState } from '../types'

interface NodeFrameProps {
  id: string
  data: NodeCookState
  selected: boolean
  color: string
  children: ReactNode
  style?: CSSProperties
  selectedRingAlpha?: string
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export default function NodeFrame({
  id,
  data,
  selected,
  color,
  children,
  style,
  selectedRingAlpha = '55',
  onMouseEnter,
  onMouseLeave,
}: NodeFrameProps) {
  const selectNode = useStore(s => s.selectNode)
  const replayActive = Boolean(data.replayRunId)
  const replayColor = replayStatusColor(data.replayStatus)
  const replayBadge = replayActive ? replayBadgeText(data) : ''

  return (
    <div
      onClick={() => selectNode(id)}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        position: 'relative',
        background: 'var(--node)',
        border: `1px solid ${data.replayFocused ? replayColor : selected ? color : replayActive ? `${replayColor}88` : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: data.replayFocused
          ? `0 0 0 3px ${replayColor}55, 0 0 22px ${replayColor}44, 0 5px 18px rgba(0,0,0,.4)`
          : selected
            ? `0 0 0 2px ${color}${selectedRingAlpha}, 0 4px 16px rgba(0,0,0,.4)`
            : replayActive
              ? `0 0 0 1px ${replayColor}33, 0 3px 12px rgba(0,0,0,.28)`
              : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
        boxSizing: 'border-box',
        overflow: 'visible',
        ...style,
      }}
    >
      <NodeStatus data={data} />
      {replayActive && replayBadge && (
        <div
          title={replayBadge}
          style={{
            position: 'absolute',
            left: 8,
            top: -24,
            zIndex: 19,
            maxWidth: 'calc(100% + 40px)',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            padding: '3px 7px',
            background: 'var(--panel)',
            border: `1px solid ${replayColor}`,
            borderRadius: 5,
            color: replayColor,
            boxShadow: data.replayFocused ? `0 0 12px ${replayColor}55` : '0 4px 12px rgba(0,0,0,.24)',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            fontWeight: 700,
            lineHeight: 1.2,
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          <span style={{
            width: 7,
            height: 7,
            borderRadius: 2,
            background: replayColor,
            flexShrink: 0,
          }} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{replayBadge}</span>
        </div>
      )}
      {children}
    </div>
  )
}

function replayStatusColor(status: NodeCookState['replayStatus']): string {
  if (status === 'running') return 'var(--warn)'
  if (status === 'error') return 'var(--err)'
  if (status === 'model') return '#a855f7'
  if (status === 'tool') return '#14b8a6'
  if (status === 'cached') return 'var(--tx3)'
  return 'var(--ok)'
}

function replayBadgeText(data: NodeCookState): string {
  const status = data.replayStatus === 'cached'
    ? 'cached'
    : data.replayStatus === 'model'
      ? 'model'
      : data.replayStatus === 'tool'
        ? 'tool'
        : data.replayStatus === 'done'
          ? 'done'
          : data.replayStatus ?? 'replay'
  const port = data.replayPort ? `.${data.replayPort}` : ''
  const duration = typeof data.replayDurationMs === 'number' ? ` ${formatDuration(data.replayDurationMs)}` : ''
  const modelCalls = data.replayModelCalls ? ` m${data.replayModelCalls}` : ''
  const toolCalls = data.replayToolCalls ? ` t${data.replayToolCalls}` : ''
  const label = data.replayLabel && !['finished', 'running', 'error'].includes(data.replayLabel)
    ? ` ${shortText(data.replayLabel, 42)}`
    : ''
  return `${status}${port}${duration}${modelCalls}${toolCalls}${label}`
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

function shortText(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}...` : text
}
