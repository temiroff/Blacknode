import type { CSSProperties, ReactNode } from 'react'
import { useStore } from '../store'
import NodeStatus from './NodeStatus'
import type { NodeCookState } from '../types'
import {
  HUGGING_FACE_API_KEY_PROVIDER,
  NVIDIA_API_KEY_PROVIDER,
  usesHuggingFaceCredential,
  usesNvidiaCredential,
} from '../credentials'

// Trigger ("hook") node types → the driver that listens for them. The badge
// reflects that driver's real heartbeat (live/processing/offline).
const TRIGGER_DRIVER: Record<string, string> = {
  SlackMessage: 'slack',
  TelegramMessage: 'telegram',
}

interface NodeFrameProps {
  id: string
  data: NodeCookState
  selected: boolean
  color: string
  children: ReactNode
  style?: CSSProperties
  selectedRingAlpha?: string
  nodeType?: string
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
  nodeType,
  onMouseEnter,
  onMouseLeave,
}: NodeFrameProps) {
  const selectNode = useStore(s => s.selectNode)
  const driverStatus = useStore(s => s.driverStatus)
  const drivers = useStore(s => s.drivers)
  const apiKeyStatus = useStore(s => s.apiKeyStatus)
  const replayActive = Boolean(data.replayRunId)
  const replayColor = replayStatusColor(data.replayStatus)
  const replayBadge = replayActive ? replayBadgeText(data) : ''
  const driverName = nodeType ? TRIGGER_DRIVER[nodeType] : undefined
  const driver = driverName ? driverStatus[driverName] : undefined
  const driverInfo = driverName ? drivers[driverName] : undefined
  const driverLive = Boolean(driver?.live)
  const notInstalled = driverInfo ? !driverInfo.packages_installed : false
  const usesNvidiaKey = usesNvidiaCredential(nodeType)
  const usesHuggingFaceKey = usesHuggingFaceCredential(nodeType)
  const credentialProvider = usesNvidiaKey
    ? NVIDIA_API_KEY_PROVIDER
    : usesHuggingFaceKey
      ? HUGGING_FACE_API_KEY_PROVIDER
      : ''
  const credentialLabel = usesNvidiaKey ? 'NIM' : 'HF'
  const credentialConfigured = Boolean(credentialProvider && apiKeyStatus[credentialProvider]?.configured)

  return (
    <div
      data-bn-node-frame={id}
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
      {driverName && (() => {
        const label = notInstalled
          ? 'needs install'
          : driverLive
            ? (driver?.state === 'processing' ? 'processing' : (driver?.label || 'listening'))
            : 'offline'
        const color = notInstalled ? 'var(--warn)' : driverLive ? 'var(--ok)' : 'var(--tx3)'
        const title = notInstalled
          ? `Hook node — the ${driverName} package isn't installed. Select this node to install it.`
          : driverLive
            ? `Hook node — live as ${driver?.label || '(unknown bot)'} (${driver?.processed ?? 0} processed). Runs this graph once per message.`
            : `Hook node — no ${driverName} driver running. Start it with the Start button.`
        return (
          <div
            title={title}
            style={{
              position: 'absolute', right: 8, top: -24, zIndex: 19,
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 7px', background: 'var(--panel)',
              border: `1px solid ${color}`, borderRadius: 5, color,
              boxShadow: '0 4px 12px rgba(0,0,0,.24)',
              fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
              lineHeight: 1.2, whiteSpace: 'nowrap',
            }}
          >
            <span
              className={driverLive ? 'bn-hook-dot' : undefined}
              style={driverLive ? undefined : { width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }}
            />
            <span>{label}</span>
          </div>
        )
      })()}
      {(usesNvidiaKey || usesHuggingFaceKey) && (
        <div
          title={credentialConfigured
            ? `This node automatically reuses the shared ${credentialProvider} credential.`
            : `No shared ${credentialProvider} credential was found. Select the node to configure it once.`}
          style={{
            position: 'absolute', right: 8, top: -24, zIndex: 19,
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '3px 7px', background: 'var(--panel)',
            border: `1px solid ${credentialConfigured ? 'var(--ok)' : 'var(--warn)'}`,
            borderRadius: 5, color: credentialConfigured ? 'var(--ok)' : 'var(--warn)',
            boxShadow: '0 4px 12px rgba(0,0,0,.24)',
            fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
            lineHeight: 1.2, whiteSpace: 'nowrap',
          }}
        >
          <span>{credentialConfigured ? '✓' : '!'}</span>
          <span>{credentialConfigured ? `${credentialLabel} credential ready` : `${credentialLabel} credential missing`}</span>
        </div>
      )}
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
