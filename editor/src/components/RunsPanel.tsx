import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, type RunRecord, type RunStatus, type RunSummary } from '../api'

const REFRESH_INTERVAL_MS = 4000
const PREVIEW_LIMIT = 9000
const EVENT_PREVIEW_LIMIT = 2200

type RunFilter = 'all' | 'errors' | 'running' | 'models' | 'tools'
type RunEvent = RunRecord['events'][number]

const STATUS_COLOR: Record<RunStatus, string> = {
  success: 'var(--ok)',
  error: 'var(--err)',
  running: 'var(--warn)',
}

const STATUS_LABEL: Record<RunStatus, string> = {
  success: 'OK',
  error: 'FAIL',
  running: 'RUN',
}

const STATUS_TEXT: Record<RunStatus, string> = {
  success: 'Success',
  error: 'Error',
  running: 'Running',
}

export default function RunsPanel() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [filter, setFilter] = useState<RunFilter>('all')

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

  const analytics = useMemo(() => buildRunAnalytics(runs), [runs])
  const visibleRuns = useMemo(() => filterRuns(runs, filter), [runs, filter])

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
    <div className="bn-runs-panel">
      <div className="bn-runs-toolbar">
        <div>
          <div className="bn-runs-title">Run History</div>
          <div className="bn-runs-subtitle">{runs.length} {runs.length === 1 ? 'run' : 'runs'} tracked</div>
        </div>
        <div className="bn-runs-actions">
          <button onClick={refresh} style={miniButton}>Refresh</button>
          <button onClick={handleClearAll} disabled={!runs.length} style={miniButton}>Clear</button>
        </div>
      </div>

      <AnalyticsStrip analytics={analytics} />

      <div className="bn-runs-filters" role="tablist" aria-label="Run filters">
        {([
          ['all', 'All', runs.length],
          ['errors', 'Errors', analytics.errors],
          ['running', 'Running', analytics.running],
          ['models', 'Models', analytics.modelRuns],
          ['tools', 'Tools', analytics.toolRuns],
        ] as const).map(([id, label, count]) => (
          <button
            key={id}
            className={`bn-runs-filter${filter === id ? ' is-active' : ''}`}
            onClick={() => setFilter(id)}
            disabled={count === 0 && id !== 'all'}
            type="button"
          >
            <span>{label}</span>
            <span>{count}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="bn-runs-error">
          {error}
        </div>
      )}

      <div className="bn-runs-list">
        {runs.length === 0 && !error && (
          <div className="bn-runs-empty">
            No runs yet. Cook any node to start recording execution history.
          </div>
        )}
        {runs.length > 0 && visibleRuns.length === 0 && (
          <div className="bn-runs-empty">
            No runs match this filter.
          </div>
        )}
        {visibleRuns.map((run, index) => (
          <RunRow
            key={run.run_id}
            run={run}
            index={index}
            expanded={activeRunId === run.run_id}
            onToggle={() => setActiveRunId(prev => prev === run.run_id ? null : run.run_id)}
            onDelete={() => handleDelete(run.run_id)}
          />
        ))}
      </div>
    </div>
  )
}

function AnalyticsStrip({ analytics }: { analytics: RunAnalytics }) {
  return (
    <div className="bn-runs-analytics" aria-label="Run analytics">
      <Metric label="Success" value={analytics.successRate} muted={analytics.total === 0} />
      <Metric label="Avg" value={formatDuration(analytics.avgDurationMs)} muted={analytics.completed === 0} />
      <Metric label="Models" value={String(analytics.modelCalls)} muted={analytics.modelCalls === 0} />
      <Metric label="Tools" value={String(analytics.toolCalls)} muted={analytics.toolCalls === 0} />
    </div>
  )
}

function Metric({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className={`bn-runs-metric${muted ? ' is-muted' : ''}`}>
      <span>{value}</span>
      <small>{label}</small>
    </div>
  )
}

function RunRow({ run, index, expanded, onToggle, onDelete }: {
  run: RunSummary
  index: number
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
}) {
  const color = STATUS_COLOR[run.status]
  const title = `${run.node_type}.${run.port}`
  const errorLine = run.error ? lastErrorLine(run.error) : ''

  return (
    <div className={`bn-run-row${expanded ? ' is-expanded' : ''}`} style={{ '--run-status': color } as CSSProperties}>
      <button
        onClick={onToggle}
        className="bn-run-summary"
        type="button"
        aria-expanded={expanded}
      >
        <div className="bn-run-timeline-mark">
          <span />
        </div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-index">#{index + 1}</span>
            <span className="bn-run-title" title={title}>{title}</span>
            <span className="bn-run-age">{formatRelativeTime(run.started_at)}</span>
          </div>
          <div className="bn-run-node" title={run.node_id}>
            {shortId(run.node_id)} <span>{formatTimestamp(run.started_at)}</span>
          </div>
          <RunBadges run={run} />
          {errorLine && <div className="bn-run-error-line">{errorLine}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{STATUS_LABEL[run.status]}</span>
          <span>{formatDuration(run.duration_ms)}</span>
        </div>
      </button>

      {expanded && (
        <RunDetail runId={run.run_id} runStatus={run.status} onDelete={onDelete} />
      )}
    </div>
  )
}

function RunBadges({ run }: { run: RunSummary }) {
  const badges = [
    `${run.node_count} ${plural(run.node_count, 'node')}`,
    run.model_calls > 0 ? `${run.model_calls} model` : null,
    run.tool_calls > 0 ? `${run.tool_calls} tool` : null,
    run.cached_nodes > 0 ? `${run.cached_nodes} cached` : null,
  ].filter(Boolean)

  return (
    <div className="bn-run-badges">
      {badges.map(badge => (
        <span key={badge}>{badge}</span>
      ))}
    </div>
  )
}

function RunDetail({ runId, runStatus, onDelete }: { runId: string; runStatus: RunStatus; onDelete: () => void }) {
  const [record, setRecord] = useState<RunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      api.getRun(runId)
        .then(rec => {
          if (!cancelled) {
            setRecord(rec)
            setError(null)
          }
        })
        .catch(err => {
          if (!cancelled) setError(err instanceof Error ? err.message : String(err))
        })
    }

    load()
    if (runStatus !== 'running') {
      return () => { cancelled = true }
    }

    const id = window.setInterval(load, REFRESH_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [runId, runStatus])

  if (error) {
    return <div className="bn-run-detail"><div className="bn-runs-error is-inline">{error}</div></div>
  }
  if (!record) {
    return <div className="bn-run-detail"><div className="bn-run-loading">Loading...</div></div>
  }

  const eventStats = buildEventStats(record.events)

  return (
    <div className="bn-run-detail">
      <div className="bn-run-detail-head">
        <div>
          <div className="bn-run-detail-title">{STATUS_TEXT[record.status]} run</div>
          <div className="bn-run-id" title={record.run_id}>{record.run_id}</div>
        </div>
        <button onClick={onDelete} style={miniButton}>Delete</button>
      </div>

      <div className="bn-run-facts">
        <Fact label="Started" value={formatTimestamp(record.started_at)} />
        <Fact label="Finished" value={record.finished_at ? formatTimestamp(record.finished_at) : 'In progress'} />
        <Fact label="Duration" value={formatDuration(record.duration_ms)} />
        <Fact label="Target" value={`${record.node_type}.${record.port}`} />
        <Fact label="Events" value={String(record.events.length)} />
        <Fact label="Touched" value={`${eventStats.nodeCount} ${plural(eventStats.nodeCount, 'node')}`} />
      </div>

      {record.error && (
        <PayloadBlock
          title="Error"
          value={record.error}
          tone="error"
          limit={PREVIEW_LIMIT}
          defaultOpen
        />
      )}

      {record.status === 'success' && record.value !== undefined && (
        <PayloadBlock
          title="Result"
          value={record.value}
          tone="value"
          limit={PREVIEW_LIMIT}
          defaultOpen
        />
      )}

      <div className="bn-run-event-stats">
        <span>{eventStats.modelCalls} model</span>
        <span>{eventStats.toolCalls} tool</span>
        <span>{eventStats.cached} cached</span>
        <span>{eventStats.errors} errors</span>
      </div>

      <EventTimeline events={record.events} />
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="bn-run-fact">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </div>
  )
}

function EventTimeline({ events }: { events: RunRecord['events'] }) {
  const timeline = useMemo(() => buildTimeline(events), [events])

  if (!timeline.length) {
    return <div className="bn-run-loading">No events.</div>
  }

  return (
    <div className="bn-event-timeline" aria-label="Run event timeline">
      {timeline.map(item => (
        <EventRow key={item.index} item={item} />
      ))}
    </div>
  )
}

function EventRow({ item }: { item: TimelineItem }) {
  const event = item.event
  const type = event.type as string
  const style = eventStyle(type, event)
  const nodeId = stringValue(event.node_id)
  const nodeType = stringValue(event.node_type)
  const nodeLabel = nodeType
    ? `${nodeType}${nodeId ? ` / ${shortId(nodeId)}` : ''}`
    : (nodeId ? shortId(nodeId) : '')
  const details = eventDetails(event)
  const payload = eventPayload(event)

  return (
    <div className="bn-event-row" style={{ '--event-color': style.color } as CSSProperties}>
      <div className="bn-event-time">
        <span>{item.offset}</span>
        {item.gap && <small>{item.gap}</small>}
      </div>
      <div className="bn-event-dot" />
      <div className="bn-event-body">
        <div className="bn-event-head">
          <span className="bn-event-label">{style.label}</span>
          {nodeLabel && <span className="bn-event-node" title={nodeId}>{nodeLabel}</span>}
        </div>
        {details && <div className="bn-event-detail">{details}</div>}
        {payload !== undefined && (
          <PayloadBlock
            title="Payload"
            value={payload}
            tone="event"
            limit={EVENT_PREVIEW_LIMIT}
          />
        )}
      </div>
    </div>
  )
}

function PayloadBlock({ title, value, tone, limit, defaultOpen = false }: {
  title: string
  value: unknown
  tone: 'error' | 'value' | 'event'
  limit: number
  defaultOpen?: boolean
}) {
  const preview = useMemo(() => formatPayload(value, limit), [value, limit])

  return (
    <details className={`bn-payload bn-payload-${tone}`} open={defaultOpen}>
      <summary>
        <span>{title}</span>
        <small>{preview.truncated ? `${preview.lengthLabel}, truncated` : preview.lengthLabel}</small>
      </summary>
      <pre>{preview.text}</pre>
    </details>
  )
}

interface RunAnalytics {
  total: number
  completed: number
  errors: number
  running: number
  modelRuns: number
  toolRuns: number
  modelCalls: number
  toolCalls: number
  avgDurationMs: number | null
  successRate: string
}

function buildRunAnalytics(runs: RunSummary[]): RunAnalytics {
  const completedRuns = runs.filter(run => run.duration_ms != null)
  const success = runs.filter(run => run.status === 'success').length
  const errors = runs.filter(run => run.status === 'error').length
  const running = runs.filter(run => run.status === 'running').length
  const modelCalls = runs.reduce((sum, run) => sum + run.model_calls, 0)
  const toolCalls = runs.reduce((sum, run) => sum + run.tool_calls, 0)
  const avgDurationMs = completedRuns.length
    ? completedRuns.reduce((sum, run) => sum + (run.duration_ms ?? 0), 0) / completedRuns.length
    : null
  const successRate = runs.length ? `${Math.round((success / runs.length) * 100)}%` : '--'

  return {
    total: runs.length,
    completed: completedRuns.length,
    errors,
    running,
    modelRuns: runs.filter(run => run.model_calls > 0).length,
    toolRuns: runs.filter(run => run.tool_calls > 0).length,
    modelCalls,
    toolCalls,
    avgDurationMs,
    successRate,
  }
}

function filterRuns(runs: RunSummary[], filter: RunFilter): RunSummary[] {
  if (filter === 'errors') return runs.filter(run => run.status === 'error')
  if (filter === 'running') return runs.filter(run => run.status === 'running')
  if (filter === 'models') return runs.filter(run => run.model_calls > 0)
  if (filter === 'tools') return runs.filter(run => run.tool_calls > 0)
  return runs
}

interface EventStats {
  nodeCount: number
  modelCalls: number
  toolCalls: number
  cached: number
  errors: number
}

function buildEventStats(events: RunEvent[]): EventStats {
  const nodes = new Set<string>()
  let modelCalls = 0
  let toolCalls = 0
  let cached = 0
  let errors = 0

  for (const event of events) {
    const nodeId = stringValue(event.node_id)
    if (nodeId) nodes.add(nodeId)
    if (event.type === 'model_call') modelCalls += 1
    if (event.type === 'tool_call') toolCalls += 1
    if (event.type === 'success' && Boolean(event.cached)) cached += 1
    if (event.type === 'error') errors += 1
  }

  return { nodeCount: nodes.size, modelCalls, toolCalls, cached, errors }
}

interface TimelineItem {
  index: number
  event: RunEvent
  offset: string
  gap: string
}

function buildTimeline(events: RunEvent[]): TimelineItem[] {
  const firstTime = eventTime(events[0])
  let previousTime = firstTime

  return events.map((event, index) => {
    const currentTime = eventTime(event)
    const offsetMs = firstTime != null && currentTime != null ? Math.max(0, currentTime - firstTime) : null
    const gapMs = previousTime != null && currentTime != null ? Math.max(0, currentTime - previousTime) : null
    if (currentTime != null) previousTime = currentTime

    return {
      index,
      event,
      offset: offsetMs == null ? `#${index + 1}` : `+${formatDuration(offsetMs)}`,
      gap: index > 0 && gapMs != null ? formatDuration(gapMs) : '',
    }
  })
}

function eventStyle(type: string, event: RunEvent): { label: string; color: string } {
  if (type === 'start') return { label: 'start', color: '#06b6d4' }
  if (type === 'success') return { label: Boolean(event.cached) ? 'cached' : 'success', color: Boolean(event.cached) ? 'var(--tx3)' : 'var(--ok)' }
  if (type === 'error') return { label: 'error', color: 'var(--err)' }
  if (type === 'done') return { label: 'done', color: 'var(--accent)' }
  if (type === 'model_call') return { label: 'model', color: '#a855f7' }
  if (type === 'tool_call') return { label: 'tool', color: '#14b8a6' }
  return { label: type || 'event', color: 'var(--tx3)' }
}

function eventDetails(event: RunEvent): string {
  const type = event.type as string
  if (type === 'start') {
    const port = stringValue(event.port)
    return port ? `port ${port}` : ''
  }
  if (type === 'success') {
    const outputs = objectValue(event.outputs)
    const port = stringValue(event.port)
    const parts = [
      port ? `port ${port}` : '',
      outputs ? `${Object.keys(outputs).length} outputs` : '',
      Boolean(event.cached) ? 'cache hit' : '',
    ].filter(Boolean)
    return parts.join(' / ')
  }
  if (type === 'error') return lastErrorLine(event.error)
  if (type === 'done') {
    const port = stringValue(event.port)
    return event.error ? lastErrorLine(event.error) : (port ? `port ${port}` : '')
  }
  if (type === 'model_call') {
    const parts = [
      stringValue(event.provider),
      stringValue(event.model),
      stringValue(event.action),
      typeof event.tool_count === 'number' ? `${event.tool_count} tools` : '',
    ].filter(Boolean)
    return parts.join(' / ')
  }
  if (type === 'tool_call') return stringValue(event.name)
  return ''
}

function eventPayload(event: RunEvent): unknown | undefined {
  const type = event.type as string
  if (type === 'tool_call' && event.arguments !== undefined) return event.arguments
  if (type === 'success') {
    if (event.outputs !== undefined) return event.outputs
    if (event.value !== undefined) return event.value
  }
  if (type === 'done') {
    if (event.error !== undefined) return event.error
    if (event.value !== undefined) return event.value
  }
  if (type === 'error' && event.error !== undefined) return event.error

  const metadata = Object.fromEntries(
    Object.entries(event).filter(([key]) => !['type', 'ts', 'node_id', 'node_type', 'port'].includes(key)),
  )
  return Object.keys(metadata).length ? metadata : undefined
}

function eventTime(event: RunEvent | undefined): number | null {
  if (!event?.ts) return null
  const parsed = new Date(event.ts).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 10)}...` : id
}

function lastErrorLine(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean)
  return lines.length ? lines[lines.length - 1] : ''
}

function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`
}

const miniButton: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '2px 8px',
  fontSize: 10,
  fontFamily: 'var(--font-ui)',
  borderRadius: 4,
  cursor: 'pointer',
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '--'
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = (Date.now() - then) / 1000
  if (diff < 5) return 'now'
  if (diff < 60) return `${Math.floor(diff)}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

function formatPayload(value: unknown, limit: number): { text: string; truncated: boolean; lengthLabel: string } {
  const full = stringifyPayload(value)
  if (full.length <= limit) {
    return { text: full, truncated: false, lengthLabel: `${full.length} chars` }
  }

  return {
    text: `${full.slice(0, limit)}\n\n... truncated ${full.length - limit} chars`,
    truncated: true,
    lengthLabel: `${full.length} chars`,
  }
}

function stringifyPayload(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
