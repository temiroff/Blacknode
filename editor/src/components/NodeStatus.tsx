import { useState } from 'react'
import type { NodeCookState } from '../types'
import { copyTextToClipboard } from '../clipboard'

const isImageSrc = (v: unknown): v is string =>
  typeof v === 'string' && (v.startsWith('data:image/') || /^https?:\/\//i.test(v))

function previewValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
  return s.length > 1200 ? s.slice(0, 1200) + '\n...' : s
}

export default function NodeStatus({ data }: { data: NodeCookState }) {
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)

  // Reflect either an editor cook (cook*) or a live driver run (replay*), so the
  // circle + result show whether you cooked it here or a bot just ran it.
  const replayRunning = data.replayStatus === 'running' || data.replayStatus === 'model' || data.replayStatus === 'tool'
  const isCooking = !!data.cooking || replayRunning
  const runtimeError = data.cookError ?? (data.replayStatus === 'error' ? data.replayError : undefined)
  const result = data.cookResult !== undefined ? data.cookResult : data.replayResult
  const port = data.cookPort ?? data.replayPort
  const outputStatus = typeof data.portResults?.status === 'string' ? data.portResults.status : ''
  const outputReport = typeof data.portResults?.report === 'string' ? data.portResults.report : ''
  const semanticError = !runtimeError && data.portResults?.ok === false
    ? outputReport || 'The operation reported ok=false.'
    : undefined
  const errorText = runtimeError ?? semanticError
  const isError = !!errorText
  const incompleteLabel = outputStatus === 'checked_not_exported'
    ? 'NOT EXPORTED'
    : outputStatus === 'checked_not_uploaded'
      ? 'NOT UPLOADED'
      : ''
  const completedLabel = outputStatus === 'exists' ? 'EXISTS' : ''
  const isWarning = !isError && (Boolean(incompleteLabel) || result === false)
  const toneColor = isCooking ? 'var(--warn)' : isError ? 'var(--err)' : isWarning ? 'var(--warn)' : 'var(--ok)'
  const toneHex = isCooking ? '#facc15' : isError ? '#ef4444' : isWarning ? '#facc15' : '#22c55e'

  if (!isError && result === undefined && !isCooking) return null

  const title = isCooking
    ? `Cooking${port ? ` ${port}` : ''}...`
    : isError
      ? 'Error'
      : incompleteLabel
        ? incompleteLabel.replace('_', ' ').toLowerCase()
        : completedLabel
          ? completedLabel.toLowerCase()
        : isWarning
          ? 'False result'
      : port
        ? `Result: ${port}`
        : 'Result'
  const label = isCooking
    ? title
    : isError
      ? errorText!
      : incompleteLabel
        ? outputReport || `${incompleteLabel.replace('_', ' ').toLowerCase()}.`
        : completedLabel
          ? outputReport || 'A valid export already exists and was left unchanged.'
        : previewValue(result)
  const copyLabel = copied ? 'Copied' : title
  const copyValue = isCooking ? title : label
  const persistentLabel = !isCooking && (isError ? 'FAILED' : incompleteLabel || completedLabel)

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!copyValue.trim()) return
    try {
      await copyTextToClipboard(copyValue)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1100)
    } catch (err) {
      console.error('Failed to copy node status', err)
    }
  }

  return (
    <div
      title={`${title} - click to copy`}
      style={{
        position: 'absolute',
        top: -9,
        right: -9,
        zIndex: 20,
        minWidth: 22,
        height: 22,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: persistentLabel ? 4 : 0,
        padding: persistentLabel ? '0 6px' : 0,
        borderRadius: persistentLabel ? 11 : 0,
        background: persistentLabel ? 'var(--panel)' : 'transparent',
        border: persistentLabel ? `1px solid ${toneColor}` : 'none',
        color: toneColor,
        fontFamily: 'var(--font-ui)',
        fontSize: 8,
        fontWeight: 800,
        whiteSpace: 'nowrap',
      }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onMouseDown={e => e.stopPropagation()}
      onClick={handleCopy}
    >
      <div style={{
        width: 10,
        height: 10,
        borderRadius: '50%',
        background: toneColor,
        border: '1.5px solid var(--node)',
        boxShadow: `0 0 6px ${toneHex}88`,
        cursor: 'copy',
        flexShrink: 0,
      }} />
      {persistentLabel && <span>{persistentLabel}</span>}
      {visible && (
        <div style={{
          position: 'absolute',
          bottom: 22,
          right: 0,
          width: 280,
          background: 'var(--panel)',
          border: `1px solid ${toneColor}`,
          borderRadius: 8,
          padding: '8px 10px',
          pointerEvents: 'auto',
          cursor: 'copy',
          zIndex: 100,
          boxShadow: '0 8px 24px rgba(0,0,0,.3)',
          userSelect: 'text',
        }}>
          <div style={{
            color: toneColor,
            fontFamily: 'var(--font-ui)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: isCooking ? 0 : 6,
          }}>
            {copyLabel}
          </div>
          {!isCooking && (
            !isError && isImageSrc(result) ? (
              <img
                src={result as string}
                alt="result"
                style={{ maxWidth: '100%', borderRadius: 4, display: 'block' }}
              />
            ) : (
              <div style={{
                color: isError ? 'var(--err)' : 'var(--tx1)',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 240,
                overflowY: 'auto',
              }}>
                {label}
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}
