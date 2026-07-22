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
  const [now, setNow] = useState(Date.now())
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [recall, setRecall] = useState<number | null>(null)
  const [collapse, setCollapse] = useState(true)
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

  // Housekeeping repeats the same handful of commands constantly - reading each
  // package's git status alone spawns one process per package per request - so
  // hundreds of rows say very little. Fold repeats into one row carrying a
  // count and the latest timing; nothing is dropped from the server's log.
  const shown = (() => {
    if (!collapse) return entries
    const byCommand = new Map<string, ConsoleEntry & { repeats: number }>()
    for (const entry of entries) {
      const seen = byCommand.get(entry.command)
      if (seen) {
        byCommand.set(entry.command, { ...entry, repeats: seen.repeats + 1 })
      } else {
        byCommand.set(entry.command, { ...entry, repeats: 1 })
      }
    }
    return Array.from(byCommand.values()).sort((a, b) => a.id - b.id)
  })()

  const submit = async () => {
    const command = input.trim()
    if (!command || busy) return
    setHistory(h => (h[h.length - 1] === command ? h : [...h, command]).slice(-50))
    setRecall(null)
    setInput('')
    setBusy('exec')
    try {
      await api.consoleExec(command)
      setError('')
    } catch (e) {
      // Rejections (unknown tool, shell operators) are the useful feedback here.
      setError(e instanceof Error ? e.message : 'command failed')
    } finally {
      setBusy('')
    }
  }

  // Up/down walks history the way a shell does.
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); void submit(); return }
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    if (!history.length) return
    e.preventDefault()
    const next = e.key === 'ArrowUp'
      ? (recall === null ? history.length - 1 : Math.max(0, recall - 1))
      : (recall === null ? null : Math.min(history.length - 1, recall + 1))
    setRecall(next)
    setInput(next === null ? '' : history[next])
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, fontFamily: 'var(--font-ui)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px 7px' }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: active ? 'var(--warn)' : 'var(--tx3)',
          boxShadow: active ? '0 0 8px var(--warn)' : 'none',
        }} />
        <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: 'var(--tx1)' }}>
          {active ? `${active} running` : `${shown.length} of ${entries.length} commands`}
        </span>
        <button
          onClick={() => setCollapse(c => !c)}
          title={collapse ? 'Showing one row per command' : 'Showing every run'}
          style={{
            padding: '3px 8px', borderRadius: 5,
            border: `1px solid ${collapse ? 'var(--accent)' : 'var(--line2)'}`,
            background: 'transparent', color: collapse ? 'var(--accent)' : 'var(--tx3)',
            cursor: 'pointer', fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700,
          }}
        >
          Collapse
        </button>
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
        {/* A transcript, not a list of expanders: every command and everything it
            printed stays on screen, the way a terminal reads. */}
        {shown.map(entry => {
          const output = [entry.stdout, entry.stderr, entry.error].filter(Boolean).join('\n')
          return (
            <div key={entry.id} style={{ marginBottom: 4 }}>
              <div style={{
                display: 'flex', alignItems: 'baseline', gap: 6,
                fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.5,
              }}>
                <span style={{ color: TONE[entry.status] ?? 'var(--tx3)', flexShrink: 0 }}>
                  {entry.status === 'running' ? '›' : entry.status === 'failed' ? '✗' : '$'}
                </span>
                <span style={{ flex: 1, minWidth: 0, color: 'var(--tx1)', wordBreak: 'break-all' }}>
                  {entry.command}
                </span>
                {(entry as ConsoleEntry & { repeats?: number }).repeats! > 1 && (
                  <span style={{ flexShrink: 0, fontSize: 10, color: 'var(--tx3)' }}>
                    ×{(entry as ConsoleEntry & { repeats?: number }).repeats}
                  </span>
                )}
                <span style={{
                  flexShrink: 0, fontSize: 10,
                  color: entry.status === 'running' ? 'var(--warn)' : 'var(--tx3)',
                }}>
                  {clock(entry, now)}
                </span>
              </div>
              {output && (
                <pre style={{
                  margin: '1px 0 0 14px', padding: 0, background: 'transparent', border: 'none',
                  color: entry.status === 'failed' ? 'var(--err)' : 'var(--tx2)',
                  fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.5,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>
                  {output}
                </pre>
              )}
            </div>
          )
        })}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '7px 10px', borderTop: '1px solid var(--line)', flexShrink: 0,
      }}>
        <span style={{ color: 'var(--ok)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>$</span>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="ros2 topic list"
          spellCheck={false}
          title="Runs one command at a time. Arguments are passed directly, so pipes and redirects are not available."
          style={{
            flex: 1, minWidth: 0, background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--tx1)', fontFamily: 'var(--font-mono)', fontSize: 12,
          }}
        />
        <button
          onClick={() => void submit()}
          disabled={!input.trim() || busy === 'exec'}
          style={{
            padding: '3px 9px', borderRadius: 5,
            border: `1px solid ${input.trim() ? 'var(--ok)' : 'var(--line2)'}`,
            background: 'transparent',
            color: input.trim() && busy !== 'exec' ? 'var(--ok)' : 'var(--tx3)',
            cursor: input.trim() && busy !== 'exec' ? 'pointer' : 'default',
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700,
          }}
        >
          {busy === 'exec' ? 'Running…' : 'Run'}
        </button>
      </div>
    </div>
  )
}
