import { useEffect, useState, type CSSProperties } from 'react'
import {
  api,
  type Deployment,
  type DeploymentPreflight,
  type DeploymentPreflightStatus,
  type DeploymentState,
  type HardwareDevice,
  type RemoteDeployment,
  type RemoteDeploymentState,
} from '../api'
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

const REMOTE_STATE_COLOR: Record<RemoteDeploymentState, string> = {
  staged: 'var(--accent)',
  running: 'var(--ok)',
  stopped: 'var(--tx3)',
  exited: 'var(--tx2)',
  failed: 'var(--err)',
}

const REMOTE_STATE_LABEL: Record<RemoteDeploymentState, string> = {
  staged: 'STAGED',
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
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  const [preflight, setPreflight] = useState<DeploymentPreflight | null>(null)
  const [remoteDeployments, setRemoteDeployments] = useState<RemoteDeployment[]>([])
  const [remoteOpenId, setRemoteOpenId] = useState<string | null>(null)
  const [remoteLogs, setRemoteLogs] = useState<Record<string, string>>({})
  const stopRuntimeServices = useStore(s => s.stopRuntimeServices)

  const refresh = async () => {
    try {
      const result = await api.listDeployments()
      setDeployments(result.deployments)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (!selectedDeviceId) {
      setRemoteDeployments([])
      return
    }
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.listRemoteDeployments(selectedDeviceId)
        if (!cancelled) setRemoteDeployments(result.deployments)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [selectedDeviceId])

  useEffect(() => {
    api.listDevices()
      .then(result => {
        setDevices(result.devices)
        setSelectedDeviceId(current => (
          current && result.devices.some(device => device.id === current)
            ? current
            : result.devices[0]?.id ?? ''
        ))
      })
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
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

  useEffect(() => {
    if (!selectedDeviceId || !remoteOpenId) return
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.remoteDeploymentLogs(selectedDeviceId, remoteOpenId)
        if (!cancelled) {
          setRemoteLogs(prev => ({ ...prev, [remoteOpenId]: result.logs }))
        }
      } catch {
        /* deployment state remains visible when a log tail is temporarily unavailable */
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [selectedDeviceId, remoteOpenId])

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

  const handleDeploy = async (autostart: boolean) => {
    const name = window.prompt('Name this deployment', 'Deployed graph')
    if (name === null) return
    const finalName = name.trim() || 'Deployed graph'
    await act(async () => {
      // Only a running deployment competes for the hardware, so stop the
      // editor's live graph first in that case. Save-only just writes the
      // files and runs nothing, so it leaves the live graph alone.
      if (autostart) {
        try { await stopRuntimeServices() } catch { /* deploy stops it too */ }
      }
      return api.deployGraph(finalName, autostart)
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

  const validateRemoteDeployment = async () => {
    if (!selectedDeviceId) return
    setBusy(true)
    setError(null)
    setPreflight(null)
    try {
      setPreflight(await api.validateDeviceDeployment(selectedDeviceId))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const refreshRemote = async () => {
    if (!selectedDeviceId) return
    const result = await api.listRemoteDeployments(selectedDeviceId)
    setRemoteDeployments(result.deployments)
  }

  const actRemote = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refreshRemote()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const stageRemote = async (
    start: boolean,
    existing?: RemoteDeployment,
  ) => {
    if (!selectedDeviceId || !preflight?.ready) return
    let name = existing?.name
    if (!name) {
      const entered = window.prompt('Name this remote deployment', preflight.workflow.name)
      if (entered === null) return
      name = entered.trim() || preflight.workflow.name || 'Deployed graph'
    }
    await actRemote(async () => {
      const result = await api.stageRemoteDeployment(
        selectedDeviceId,
        name!,
        preflight.workflow.hash,
        start,
        existing?.id,
      )
      setRemoteOpenId(result.deployment.id)
    })
  }

  const deleteRemote = async (deployment: RemoteDeployment) => {
    if (!selectedDeviceId) return
    if (!window.confirm(`Delete remote deployment "${deployment.name}"?`)) return
    await actRemote(() => api.deleteRemoteDeployment(selectedDeviceId, deployment.id))
    setRemoteOpenId(current => current === deployment.id ? null : current)
  }

  const running = deployments.filter(d => d.state === 'running').length
  const remoteRunning = remoteDeployments.filter(d => d.state === 'running').length

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
          <button onClick={() => handleDeploy(false)} disabled={busy} style={miniButton} title="Save the runnable script on this computer without running it">Save local</button>
          <button onClick={() => handleDeploy(true)} disabled={busy} style={primaryButton} title="Stop the live graph, then run it on this computer">Run local</button>
        </div>
      </div>

      <div className="bn-deploy-target">
        <div className="bn-deploy-target-head">
          <div>
            <div className="bn-deploy-target-title">Remote target</div>
            <div className="bn-runs-subtitle">Validate, stage, and control the selected device</div>
          </div>
          <div className="bn-runs-actions">
            <button
              onClick={validateRemoteDeployment}
              disabled={busy || !selectedDeviceId}
              style={preflight?.ready ? miniButton : primaryButton}
            >
              Validate
            </button>
            {preflight?.ready && (
              <>
                <button onClick={() => stageRemote(false)} disabled={busy} style={miniButton}>
                  Stage
                </button>
                <button onClick={() => stageRemote(true)} disabled={busy} style={primaryButton}>
                  Stage & run
                </button>
              </>
            )}
          </div>
        </div>
        {devices.length > 0 ? (
          <select
            className="bn-deploy-device-select"
            value={selectedDeviceId}
            onChange={event => {
              setSelectedDeviceId(event.target.value)
              setPreflight(null)
            }}
          >
            {devices.map(device => (
              <option key={device.id} value={device.id}>
                {device.name} · {device.base_url}
              </option>
            ))}
          </select>
        ) : (
          <div className="bn-device-help">Pair a Raspberry Pi in the Devices tab first.</div>
        )}
      </div>

      {preflight && <PreflightResult result={preflight} />}

      {error && <div className="bn-runs-error">{error}</div>}

      <div className="bn-deployment-section-head">
        <div>
          <strong>Remote deployments</strong>
          <span>{remoteDeployments.length} total · {remoteRunning} running</span>
        </div>
        <button onClick={() => actRemote(refreshRemote)} disabled={busy || !selectedDeviceId} style={miniButton}>
          Refresh
        </button>
      </div>
      <div className="bn-runs-list">
        {selectedDeviceId && remoteDeployments.length === 0 && (
          <div className="bn-runs-empty">
            No deployment is staged on this device. Validate the graph, then choose
            <strong> Stage</strong> or <strong>Stage &amp; run</strong>.
          </div>
        )}
        {remoteDeployments.map(deployment => (
          <RemoteDeploymentRow
            key={deployment.id}
            deployment={deployment}
            busy={busy}
            canStage={Boolean(preflight?.ready)}
            expanded={remoteOpenId === deployment.id}
            log={remoteLogs[deployment.id] ?? ''}
            onToggle={() => setRemoteOpenId(current => (
              current === deployment.id ? null : deployment.id
            ))}
            onStage={() => stageRemote(false, deployment)}
            onStart={() => actRemote(() => (
              api.startRemoteDeployment(selectedDeviceId, deployment.id)
            ))}
            onStop={() => actRemote(() => (
              api.stopRemoteDeployment(selectedDeviceId, deployment.id)
            ))}
            onRollback={() => {
              if (!window.confirm(`Roll back "${deployment.name}" to its previous revision?`)) return
              actRemote(() => api.rollbackRemoteDeployment(
                selectedDeviceId,
                deployment.id,
              ))
            }}
            onDelete={() => deleteRemote(deployment)}
          />
        ))}
      </div>

      <div className="bn-deployment-section-head">
        <div>
          <strong>Local deployments</strong>
          <span>Run by this editor computer</span>
        </div>
      </div>
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

const PREFLIGHT_LABEL: Record<DeploymentPreflightStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  warning: 'WARN',
  pending: 'WAIT',
}

function PreflightResult({ result }: { result: DeploymentPreflight }) {
  return (
    <div className="bn-preflight">
      <div className={`bn-preflight-summary ${result.ready ? 'is-ready' : 'is-blocked'}`}>
        <strong>{result.ready ? 'Ready' : 'Not ready'}</strong>
        <span>{result.summary}</span>
      </div>
      <div className="bn-preflight-checks">
        {result.checks.map(check => (
          <div className="bn-preflight-check" key={check.id}>
            <span className={`bn-preflight-pill is-${check.status}`}>
              {PREFLIGHT_LABEL[check.status]}
            </span>
            <div>
              <strong>{check.label}</strong>
              <span>{check.message}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RemoteDeploymentRow({
  deployment,
  busy,
  canStage,
  expanded,
  log,
  onToggle,
  onStage,
  onStart,
  onStop,
  onRollback,
  onDelete,
}: {
  deployment: RemoteDeployment
  busy: boolean
  canStage: boolean
  expanded: boolean
  log: string
  onToggle: () => void
  onStage: () => void
  onStart: () => void
  onStop: () => void
  onRollback: () => void
  onDelete: () => void
}) {
  const isRunning = deployment.state === 'running'
  const canRollback = deployment.revisions.length > 1
  const badges = [
    `${deployment.revisions.length} revision${deployment.revisions.length === 1 ? '' : 's'}`,
    `staged ${deployment.staged_revision}`,
    deployment.active_revision ? `active ${deployment.active_revision}` : null,
    deployment.pid ? `pid ${deployment.pid}` : null,
  ].filter(Boolean) as string[]

  return (
    <div
      className={`bn-run-row${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': REMOTE_STATE_COLOR[deployment.state] } as CSSProperties}
    >
      <button onClick={onToggle} className="bn-run-summary" type="button" aria-expanded={expanded}>
        <div className="bn-run-timeline-mark"><span /></div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-title" title={deployment.name}>{deployment.name}</span>
            <span className="bn-run-age">{formatTime(deployment.updated_at)}</span>
          </div>
          <div className="bn-run-node" title={deployment.id}>{deployment.id}</div>
          <div className="bn-run-badges">
            {badges.map(badge => <span key={badge}>{badge}</span>)}
          </div>
          {deployment.error && <div className="bn-run-error-line">{deployment.error}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{REMOTE_STATE_LABEL[deployment.state]}</span>
          <span>{describeRemoteState(deployment)}</span>
        </div>
      </button>

      {expanded && (
        <div className="bn-run-detail">
          <pre style={logStyle}>{log.trim() || 'No remote output captured yet.'}</pre>
          <div className="bn-run-detail-actions">
            {isRunning
              ? <button onClick={onStop} disabled={busy} style={miniButton}>Stop</button>
              : <button onClick={onStart} disabled={busy} style={primaryButton}>Run</button>}
            <button
              onClick={onStage}
              disabled={busy || !canStage || isRunning}
              style={miniButton}
              title={canStage ? 'Stage the validated graph as a new revision' : 'Validate the graph first'}
            >
              Stage update
            </button>
            <button
              onClick={onRollback}
              disabled={busy || !canRollback}
              style={miniButton}
              title={canRollback ? 'Stage the previous revision' : 'No previous revision exists'}
            >
              Rollback
            </button>
            <button onClick={onDelete} disabled={busy || isRunning} style={miniButton}>
              Delete
            </button>
          </div>
        </div>
      )}
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

function describeRemoteState(deployment: RemoteDeployment): string {
  switch (deployment.state) {
    case 'staged':
      return 'Ready to run'
    case 'running':
      return 'Running on device'
    case 'stopped':
      return 'Stopped'
    case 'exited':
      return deployment.exit_code == null ? 'Finished' : `Finished (exit ${deployment.exit_code})`
    case 'failed':
      return deployment.exit_code == null ? 'Failed' : `Failed (exit ${deployment.exit_code})`
  }
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
