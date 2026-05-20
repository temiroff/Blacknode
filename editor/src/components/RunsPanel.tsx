import { useEffect, useMemo, useState } from 'react'
import { api, type RunRecord, type RunStatus, type RunSummary } from '../api'

const REFRESH_INTERVAL_MS = 4000

const STATUS_COLOR: Record<RunStatus, string> = {
  success: '#22c55e',
  error: '#ef4444',
  running: '#f59e0b',
}

const STATUS_LABEL: Record<RunStatus, string> = {
  success: 'OK',
  error: 'FAIL',
  running: 'RUN',
}

export default function RunsPanel() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const result = await api.listRuns(50)
      setRuns(result.runs)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [])

  const handleDelete = async (runId: string) => {
    try {
      await api.deleteRun(runId)
      setRuns(prev => prev.filter(r => r.run_id !== runId))
      if (activeRunId === runId) setActiveRunId(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleClearAll = async () => {
    if (!runs.length) return
    if (!window.confirm(`Delete all ${runs.length} runs?`)) return
    try {
      await api.clearRuns()
      setRuns([])
      setActiveRunId(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{
        padding: '8px 12px',
        borderBottom: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
      }}>
        <span style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-mono)' }}>
          {runs.length} {runs.length === 1 ? 'run' : 'runs'}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={refresh} style={miniButton}>Refresh</button>
          <button onClick={handleClearAll} disabled={!runs.length} style={miniButton}>Clear</button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: '8px 12px',
          fontSize: 11,
          color: '#ef4444',
          fontFamily: 'var(--font-mono)',
          borderBottom: '1px solid var(--line)',
        }}>
          {error}
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {runs.length === 0 && !error && (
          <div style={{ padding: 16, color: 'var(--tx3)', fontSize: 12, lineHeight: 1.5 }}>
            No runs yet. Click the Cook button on any node to record one.
          </div>
        )}
        {runs.map(run => (
          <RunRow
            key={run.run_id}
            run={run}
            expanded={activeRunId === run.run_id}
            onToggle={() => setActiveRunId(prev => prev === run.run_id ? null : run.run_id)}
            onDelete={() => handleDelete(run.run_id)}
          />
        ))}
      </div>
    </div>
  )
}

function RunRow({ run, expanded, onToggle, onDelete }: {
  run: RunSummary
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
}) {
  const color = STATUS_COLOR[run.status]
  return (
    <div style={{ borderBottom: '1px solid var(--line)' }}>
      <button
        onClick={onToggle}
        style={{
          width: '100%',
          background: expanded ? 'var(--menu-active)' : 'transparent',
          border: 'none',
          color: 'var(--tx2)',
          cursor: 'pointer',
          textAlign: 'left',
          padding: '8px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontFamily: 'var(--font-ui)',
        }}
        onMouseEnter={e => { if (!expanded) e.currentTarget.style.background = 'var(--hover)' }}
        onMouseLeave={e => { if (!expanded) e.currentTarget.style.background = 'transparent' }}
      >
        <span style={{
          padding: '1px 6px',
          fontSize: 9,
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          color,
          border: `1px solid ${color}`,
          borderRadius: 3,
          minWidth: 36,
          textAlign: 'center',
          flexShrink: 0,
        }}>
          {STATUS_LABEL[run.status]}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12,
            color: 'var(--tx1)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {run.node_type} <span style={{ color: 'var(--tx3)' }}>· {run.node_id}</span>
          </div>
          <div style={{
            fontSize: 10,
            color: 'var(--tx3)',
            fontFamily: 'var(--font-mono)',
            marginTop: 1,
          }}>
            {formatDuration(run.duration_ms)} · {run.node_count} nodes
            {run.model_calls > 0 && ` · ${run.model_calls} model`}
            {run.tool_calls > 0 && ` · ${run.tool_calls} tool`}
            {run.cached_nodes > 0 && ` · ${run.cached_nodes} cached`}
          </div>
        </div>
        <span style={{ color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
          {formatRelativeTime(run.started_at)}
        </span>
      </button>

      {expanded && (
        <RunDetail runId={run.run_id} onDelete={onDelete} />
      )}
    </div>
  )
}

function RunDetail({ runId, onDelete }: { runId: string; onDelete: () => void }) {
  const [record, setRecord] = useState<RunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getRun(runId)
      .then(rec => { if (!cancelled) setRecord(rec) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)) })
    return () => { cancelled = true }
  }, [runId])

  if (error) {
    return <div style={detailBox}><div style={{ color: '#ef4444', fontSize: 11 }}>{error}</div></div>
  }
  if (!record) {
    return <div style={detailBox}><div style={{ color: 'var(--tx3)', fontSize: 11 }}>Loading…</div></div>
  }

  return (
    <div style={detailBox}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 10, color: 'var(--tx3)', fontFamily: 'var(--font-mono)' }}>
          {record.run_id}
        </span>
        <button onClick={onDelete} style={miniButton}>Delete</button>
      </div>

      {record.error && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: '#ef4444',
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 4,
          padding: '6px 8px',
          marginBottom: 8,
          whiteSpace: 'pre-wrap',
          maxHeight: 160,
          overflowY: 'auto',
        }}>
          {record.error}
        </div>
      )}

      {record.status === 'success' && record.value !== undefined && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--tx2)',
          background: 'var(--bg)',
          border: '1px solid var(--line)',
          borderRadius: 4,
          padding: '6px 8px',
          marginBottom: 8,
          whiteSpace: 'pre-wrap',
          maxHeight: 160,
          overflowY: 'auto',
        }}>
          {formatValue(record.value)}
        </div>
      )}

      <EventTimeline events={record.events} />
    </div>
  )
}

function EventTimeline({ events }: { events: RunRecord['events'] }) {
  const filtered = useMemo(
    () => events.filter(e => ['start', 'success', 'error', 'model_call', 'tool_call'].includes(e.type as string)),
    [events],
  )
  if (!filtered.length) {
    return <div style={{ color: 'var(--tx3)', fontSize: 11 }}>No events.</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {filtered.map((event, i) => (
        <EventRow key={i} event={event} />
      ))}
    </div>
  )
}

function EventRow({ event }: { event: RunRecord['events'][number] }) {
  const type = event.type as string
  const nodeId = event.node_id as string | undefined
  const nodeType = event.node_type as string | undefined
  let color = 'var(--tx3)'
  let label = type
  let detail = ''
  if (type === 'start') { color = '#06b6d4'; label = 'start' }
  else if (type === 'success') { color = event.cached ? 'var(--tx3)' : '#22c55e'; label = event.cached ? 'cached' : 'ok' }
  else if (type === 'error') { color = '#ef4444'; label = 'error'; detail = lastErrorLine(event.error) }
  else if (type === 'model_call') { color = '#a855f7'; label = 'model'; detail = String(event.model ?? '') }
  else if (type === 'tool_call') { color = '#14b8a6'; label = 'tool'; detail = String(event.name ?? '') }

  const nodeLabel = nodeType
    ? `${nodeType}${nodeId ? ` · ${shortId(nodeId)}` : ''}`
    : (nodeId ? shortId(nodeId) : '')

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      lineHeight: 1.5,
    }}>
      <span style={{ color, minWidth: 48, fontWeight: 700 }}>{label}</span>
      {nodeLabel && <span style={{ color: 'var(--tx2)' }}>{nodeLabel}</span>}
      {detail && <span style={{ color: 'var(--tx3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{detail}</span>}
    </div>
  )
}

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id
}

function lastErrorLine(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean)
  return lines.length ? lines[lines.length - 1] : ''
}

const miniButton: React.CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '2px 8px',
  fontSize: 10,
  fontFamily: 'var(--font-ui)',
  borderRadius: 4,
  cursor: 'pointer',
}

const detailBox: React.CSSProperties = {
  padding: '10px 12px 12px',
  background: 'var(--bg)',
  borderTop: '1px solid var(--line)',
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = (Date.now() - then) / 1000
  if (diff < 60) return `${Math.floor(diff)}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

function formatValue(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
