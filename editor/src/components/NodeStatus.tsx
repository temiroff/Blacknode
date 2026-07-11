import { useState } from 'react'
import type { NodeCookState } from '../types'

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

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
  const errorText = data.cookError ?? (data.replayStatus === 'error' ? data.replayError : undefined)
  const isError = !!errorText
  const result = data.cookResult !== undefined ? data.cookResult : data.replayResult
  const port = data.cookPort ?? data.replayPort

  if (!isError && result === undefined && !isCooking) return null

  const dotColor = isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)'
  const dotHex = isCooking ? '#facc15' : isError ? '#ef4444' : '#22c55e'
  const title = isCooking
    ? `Cooking${port ? ` ${port}` : ''}...`
    : isError
      ? 'Error'
      : port
        ? `Result: ${port}`
        : 'Result'
  const label = isCooking ? title : isError ? errorText! : previewValue(result)
  const copyLabel = copied ? 'Copied' : title
  const copyValue = isCooking ? title : label

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!copyValue.trim()) return
    try {
      await copyText(copyValue)
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
        width: 22,
        height: 22,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
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
        background: dotColor,
        border: '1.5px solid var(--node)',
        boxShadow: `0 0 6px ${dotHex}88`,
        cursor: 'copy',
      }} />
      {visible && (
        <div style={{
          position: 'absolute',
          bottom: 22,
          right: 0,
          width: 280,
          background: 'var(--panel)',
          border: `1px solid ${isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)'}`,
          borderRadius: 8,
          padding: '8px 10px',
          pointerEvents: 'auto',
          cursor: 'copy',
          zIndex: 100,
          boxShadow: '0 8px 24px rgba(0,0,0,.3)',
          userSelect: 'text',
        }}>
          <div style={{
            color: isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)',
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
