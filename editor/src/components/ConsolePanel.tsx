import { useEffect, useRef, useState } from 'react'
import { api, ConsoleEntry } from '../api'

// Nodes shell out to real tools, and a command that blocks used to look exactly
// like a graph doing nothing. This shows each command as it starts, so a slow
// `docker exec ... ros2 topic list` reads as "still running, 33s" rather than
// silence.

const TONE: Record<string, string> = {
  running: 'var(--warn)',
  ok: 'var(--ok)',
  failed: 'var(--err)',
}

const clock = (entry: ConsoleEntry, now: number) =>
  entry.status === 'running'
    ? `${Math.max(0, Math.round(now / 1000 - entry.started_at))}s`
    : `${((entry.duration_ms ?? 0) / 1000).toFixed(1)}s`

export default function ConsolePanel() {
  const [entries, setEntries] = useState<ConsoleEntry[]>([])
  const [diagnostics, setDiagnostics] = useState<Array<{ id: string; label: string }>>([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [now, setNow] = useState(Date.now())
  const feed = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const next = await api.consoleLog(200)
        if (!alive) return
        setEntries(next.entries)
        setDiagnostics(next.diagnostics)
        setError('')
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'console unavailable')
      }
    }
    void poll()
    const poller = setInterval(poll, 1000)
    // Separate ticker so a running command's elapsed time keeps moving.
    const ticker = setInterval(() => setNow(Date.now()), 1000)
    return () => { alive = false; clearInterval(poller); clearInterval(ticker) }
  }, [])

  useEffect(() => {
    const el = feed.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries.length])

  const runDiagnostic = async (id: string) => {
    setBusy(id)
    try { await api.consoleRun(id) } catch (e) {
      setError(e instanceof Error ? e.message : 'diagnostic failed')
    } finally { setBusy('') }
  }

  const active = entries.filter(e => e.status === 'running').length

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, fontFamily: 'var(--font-ui)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px 7px' }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: active ? 'var(--warn)' : 'var(--tx3)',
          boxShadow: active ? '0 0 8px var(--warn)' : 'none',
        }} />
        <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: 'var(--tx1)' }}>
          {active ? `${active} command${active === 1 ? '' : 's'} running` : `${entries.length} commands`}
        </span>
        <button
          onClick={() => { void api.consoleClear().then(() => setEntries([])) }}
          style={{
            padding: '3px 8px', borderRadius: 5, border: '1px solid var(--line2)',
            background: 'transparent', color: 'var(--tx3)', cursor: 'pointer',
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700,
          }}
        >
          Clear
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, padding: '0 12px 8px' }}>
        {diagnostics.map(d => (
          <button
            key={d.id}
            disabled={busy === d.id}
            onClick={() => void runDiagnostic(d.id)}
            title="Run this diagnostic and show it in the log below"
            style={{
              padding: '3px 8px', borderRadius: 5,
              border: '1px solid var(--line2)', background: 'var(--lift)',
              color: busy === d.id ? 'var(--tx3)' : 'var(--tx2)',
              cursor: busy === d.id ? 'default' : 'pointer',
              fontFamily: 'var(--font-ui)', fontSize: 10,
            }}
          >
            {busy === d.id ? 'Running…' : d.label}
          </button>
        ))}
      </div>

      {error && <div style={{ color: 'var(--err)', fontSize: 11, padding: '0 12px 6px' }}>{error}</div>}

      <div ref={feed} style={{ flex: 1, overflowY: 'auto', padding: '0 8px 10px', minHeight: 0 }}>
        {entries.length === 0 && !error && (
          <div style={{ color: 'var(--tx3)', fontSize: 11, lineHeight: 1.6, padding: '0 4px' }}>
            Commands appear here as nodes run them. Press a diagnostic above to check
            the ROS 2 graph without building a workflow.
          </div>
        )}
        {entries.map(entry => {
          const output = [entry.stdout, entry.stderr, entry.error].filter(Boolean).join('\n')
          const expanded = open === entry.id
          return (
            <div key={entry.id} style={{ marginBottom: 2 }}>
              <div
                onClick={() => setOpen(expanded ? null : entry.id)}
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 7, padding: '3px 6px',
                  borderRadius: 4, cursor: output ? 'pointer' : 'default',
                  borderLeft: `2px solid ${TONE[entry.status] ?? 'var(--tx3)'}`,
                  background: expanded ? 'var(--lift)' : 'transparent',
                }}
              >
                <span style={{
                  flex: 1, minWidth: 0, fontFamily: 'var(--font-mono)', fontSize: 11,
                  color: 'var(--tx1)', overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {entry.command}
                </span>
                {entry.backend && (
                  <span style={{ fontSize: 9, color: 'var(--tx3)', flexShrink: 0 }}>{entry.backend}</span>
                )}
                <span style={{
                  fontSize: 10, flexShrink: 0, fontFamily: 'var(--font-mono)',
                  color: TONE[entry.status] ?? 'var(--tx3)',
                }}>
                  {clock(entry, now)}
                </span>
              </div>
              {expanded && output && (
                <pre style={{
                  margin: '2px 0 6px 8px', padding: '6px 8px', borderRadius: 4,
                  background: 'var(--lift)', border: '1px solid var(--line)',
                  color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 10,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 260, overflow: 'auto',
                }}>
                  {output}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
