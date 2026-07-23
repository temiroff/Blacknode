import { useEffect, useState, type CSSProperties } from 'react'
import { api, type Deployment, type DeploymentState } from '../api'
import { useStore } from '../store'

const REFRESH_INTERVAL_MS = 3000

const STATE_COLOR: Record<DeploymentState, string> = {
  running: 'var(--ok)',
  stopped: 'var(--tx3)',
  exited: 'var(--tx2)',
  failed: 'var(--err)',
}

const STATE_LABEL: Record<DeploymentState, string> = {
  running: 'LIVE',
  stopped: 'OFF',
  exited: 'DONE',
  failed: 'FAIL',
}

export default function DeploymentsPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [logs, setLogs] = useState<Record<string, string>>({})
  const stopRuntimeServices = useStore(s => s.stopRuntimeServices)

  const refresh = async () => {
    try {
      const result = await api.listDeployments()
      setDeployments(result.deployments)
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

  // Only the open row's log is fetched, and only while it is open, so a long
  // list of deployments does not turn into a log-tail storm every 3s.
  useEffect(() => {
    if (!openId) return
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.deploymentLogs(openId)
        if (!cancelled) setLogs(prev => ({ ...prev, [openId]: result.logs }))
      } catch {
        /* the row itself already shows state; a failed tail is not worth an error banner */
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [openId])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeploy = async () => {
    const name = window.prompt('Name this deployment', 'Deployed graph')
    if (name === null) return
    // Deploying hands the graph off to its own process. Stop the editor's live
    // run first so the top bar no longer shows it as live and the hardware is
    // freed, then deploy. The canvas graph itself is left in place.
    await act(async () => {
      try { await stopRuntimeServices() } catch { /* deploy stops it too */ }
      return api.deployGraph(name.trim() || 'Deployed graph')
    })
  }

  const handleExport = async (deployment: Deployment) => {
    setBusy(true); setError(null)
    try {
      const res = await api.exportDeployment(deployment.id)
      // Not an error, but the message row is the one visible surface for a path.
      setError(`Saved runnable script to ${res.path}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (deployment: Deployment) => {
    if (!window.confirm(`Delete "${deployment.name}"? This stops it and removes its snapshot.`)) return
    await act(() => api.deleteDeployment(deployment.id))
    setOpenId(prev => (prev === deployment.id ? null : prev))
  }

  const running = deployments.filter(d => d.state === 'running').length

  return (
    <div className="bn-runs-panel">
      <div className="bn-runs-toolbar">
        <div>
          <div className="bn-runs-title">Deployments</div>
          <div className="bn-runs-subtitle">
            {deployments.length} total · {running} running
          </div>
        </div>
        <div className="bn-runs-actions">
          <button onClick={refresh} style={miniButton}>Refresh</button>
          <button onClick={handleDeploy} disabled={busy} style={primaryButton}>Deploy graph</button>
        </div>
      </div>

      {error && <div className="bn-runs-error">{error}</div>}

      <div className="bn-runs-list">
        {deployments.length === 0 && !error && (
          <div className="bn-runs-empty">
            Nothing deployed. <strong>Deploy graph</strong> snapshots the current graph and runs
            it in the background, so it keeps running while you edit something else.
          </div>
        )}
        {deployments.map(deployment => (
          <DeploymentRow
            key={deployment.id}
            deployment={deployment}
            busy={busy}
            expanded={openId === deployment.id}
            log={logs[deployment.id] ?? ''}
            onToggle={() => setOpenId(prev => (prev === deployment.id ? null : deployment.id))}
            onStart={() => act(() => api.startDeployment(deployment.id))}
            onStop={() => act(() => api.stopDeployment(deployment.id))}
            onExport={() => handleExport(deployment)}
            onDelete={() => handleDelete(deployment)}
          />
        ))}
      </div>
    </div>
  )
}

function DeploymentRow({ deployment, busy, expanded, log, onToggle, onStart, onStop, onExport, onDelete }: {
  deployment: Deployment
  busy: boolean
  expanded: boolean
  log: string
  onToggle: () => void
  onStart: () => void
  onStop: () => void
  onExport: () => void
  onDelete: () => void
}) {
  const color = STATE_COLOR[deployment.state]
  const isRunning = deployment.state === 'running'
  const badges = [
    deployment.kind,
    `${deployment.node_count} ${deployment.node_count === 1 ? 'node' : 'nodes'}`,
    deployment.snapshot_hash,
    deployment.pid ? `pid ${deployment.pid}` : null,
  ].filter(Boolean) as string[]

  return (
    <div
      className={`bn-run-row${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': color } as CSSProperties}
    >
      <button onClick={onToggle} className="bn-run-summary" type="button" aria-expanded={expanded}>
        <div className="bn-run-timeline-mark"><span /></div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-title" title={deployment.name}>{deployment.name}</span>
            <span className="bn-run-age">{formatTime(deployment.started_at)}</span>
          </div>
          <div className="bn-run-node" title={deployment.id}>{deployment.id}</div>
          <div className="bn-run-badges">
            {badges.map(badge => <span key={badge}>{badge}</span>)}
          </div>
          {deployment.error && <div className="bn-run-error-line">{deployment.error}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{STATE_LABEL[deployment.state]}</span>
          <span>{describeState(deployment)}</span>
        </div>
      </button>

      {expanded && (
        <div className="bn-run-detail">
          <div className="bn-run-node">
            entrypoint {deployment.entrypoint?.node_id ?? '?'}.{deployment.entrypoint?.port ?? '?'}
            {deployment.live_node_types.length > 0 && ` · live: ${deployment.live_node_types.join(', ')}`}
          </div>

          <pre style={logStyle}>{log.trim() || 'No output captured yet.'}</pre>

          <div className="bn-run-detail-actions">
            {isRunning
              ? <button onClick={onStop} disabled={busy} style={miniButton}>Stop</button>
              : <button onClick={onStart} disabled={busy} style={miniButton}>Start</button>}
            <button onClick={onExport} disabled={busy} style={miniButton} title="Copy the runnable script to a folder Delete never touches">Export .py</button>
            <button onClick={onDelete} disabled={busy} style={miniButton}>Delete</button>
          </div>
        </div>
      )}
    </div>
  )
}

function describeState(deployment: Deployment): string {
  switch (deployment.state) {
    case 'running':
      return deployment.kind === 'service' ? 'Running' : 'Running (one-off)'
    case 'stopped':
      return 'Stopped by you'
    case 'exited':
      return 'Finished'
    case 'failed':
      return deployment.exit_code == null ? 'Failed' : `Failed (exit ${deployment.exit_code})`
    default:
      return deployment.state
  }
}

function formatTime(value: string | null): string {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString()
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

const primaryButton: CSSProperties = {
  ...miniButton,
  borderColor: 'var(--ok)',
  color: 'var(--ok)',
}

const logStyle: CSSProperties = {
  margin: '8px 0 0',
  padding: 8,
  maxHeight: 220,
  overflow: 'auto',
  background: 'var(--bg2)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  color: 'var(--tx2)',
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  lineHeight: 1.5,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}
