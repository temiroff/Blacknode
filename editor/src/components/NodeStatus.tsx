import { useState } from 'react'

interface NodeStatusData {
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
  cookPort?: string
}

function previewValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
  return s.length > 1200 ? s.slice(0, 1200) + '\n...' : s
}

export default function NodeStatus({ data }: { data: NodeStatusData }) {
  const [visible, setVisible] = useState(false)

  if (!data.cookError && data.cookResult === undefined && !data.cooking) return null

  const isError = !!data.cookError
  const isCooking = !!data.cooking
  const dotColor = isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)'
  const dotHex = isCooking ? '#facc15' : isError ? '#ef4444' : '#22c55e'
  const title = isCooking
    ? `Cooking${data.cookPort ? ` ${data.cookPort}` : ''}...`
    : isError
      ? 'Error'
      : data.cookPort
        ? `Result: ${data.cookPort}`
        : 'Result'
  const label = isCooking ? title : isError ? data.cookError! : previewValue(data.cookResult)

  return (
    <div
      style={{ position: 'absolute', top: -5, right: -5, zIndex: 20 }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      <div style={{
        width: 10,
        height: 10,
        borderRadius: '50%',
        background: dotColor,
        border: '1.5px solid var(--node)',
        boxShadow: `0 0 6px ${dotHex}88`,
        cursor: 'default',
      }} />
      {visible && (
        <div style={{
          position: 'absolute',
          bottom: 16,
          right: 0,
          width: 280,
          background: 'var(--panel)',
          border: `1px solid ${isCooking ? 'var(--warn)' : isError ? 'var(--err)' : 'var(--ok)'}`,
          borderRadius: 8,
          padding: '8px 10px',
          pointerEvents: 'none',
          zIndex: 100,
          boxShadow: '0 8px 24px rgba(0,0,0,.3)',
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
            {title}
          </div>
          {!isCooking && (
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
          )}
        </div>
      )}
    </div>
  )
}
