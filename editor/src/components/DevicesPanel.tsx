import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import {
  api,
  type DeviceRuntimeStatus,
  type HardwareDevice,
  type HardwareDeviceStatus,
} from '../api'

type DeviceState = {
  status?: HardwareDeviceStatus
  runtime?: DeviceRuntimeStatus
  error?: string
  loading?: boolean
  checkedAt?: number
}

const DEFAULT_HARDWARE_URL = 'http://192.168.1.87:8765'
const FIRST_HARDWARE_PORT = 8765
const RUNTIME_PORT = 8766

function suggestedHardwareUrl(devices: HardwareDevice[]): string {
  const latest = devices[devices.length - 1]
  if (!latest) return DEFAULT_HARDWARE_URL
  try {
    const latestUrl = new URL(latest.base_url)
    const usedPorts = new Set(
      devices.flatMap(device => {
        try {
          const parsed = new URL(device.base_url)
          if (parsed.protocol !== latestUrl.protocol || parsed.hostname !== latestUrl.hostname) {
            return []
          }
          return parsed.port ? [Number(parsed.port)] : []
        } catch {
          return []
        }
      }),
    )
    let port = FIRST_HARDWARE_PORT
    while (port === RUNTIME_PORT || usedPorts.has(port)) port += 1
    const host = latestUrl.hostname.includes(':')
      ? `[${latestUrl.hostname}]`
      : latestUrl.hostname
    return `${latestUrl.protocol}//${host}:${port}`
  } catch {
    return DEFAULT_HARDWARE_URL
  }
}

function hardwareUrlError(value: string): string | null {
  let parsed: URL
  try {
    parsed = new URL(value.trim())
  } catch {
    return 'Enter the complete hardware URL printed by pair.sh.'
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    return 'Hardware URL must start with http:// or https://.'
  }
  if (!parsed.port) {
    return 'Include the hardware service port printed by pair.sh.'
  }
  if (Number(parsed.port) === RUNTIME_PORT) {
    return 'Port 8766 is the shared Blacknode runtime. Use the robot hardware port printed by pair.sh, such as 8765 or 8767.'
  }
  return null
}

function runtimeUrlForHardware(value: string): string {
  try {
    const parsed = new URL(value.trim())
    parsed.port = String(RUNTIME_PORT)
    parsed.pathname = ''
    parsed.search = ''
    parsed.hash = ''
    return parsed.toString().replace(/\/$/, '')
  } catch {
    return ''
  }
}

export default function DevicesPanel() {
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [states, setStates] = useState<Record<string, DeviceState>>({})
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState(DEFAULT_HARDWARE_URL)
  const [token, setToken] = useState('')
  const [runtimeToken, setRuntimeToken] = useState('')
  const [changeRuntimeToken, setChangeRuntimeToken] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshStatus = async (device: HardwareDevice) => {
    setStates(prev => ({ ...prev, [device.id]: { ...prev[device.id], loading: true } }))
    const [hardwareResult, runtimeResult] = await Promise.allSettled([
      api.deviceStatus(device.id),
      api.deviceRuntimeStatus(device.id),
    ])
    setStates(prev => ({
      ...prev,
      [device.id]: {
        status: hardwareResult.status === 'fulfilled' ? hardwareResult.value : undefined,
        runtime: runtimeResult.status === 'fulfilled'
          ? runtimeResult.value
          : {
              ok: false,
              runtime_url: device.runtime_url,
              error: runtimeResult.reason instanceof Error
                ? runtimeResult.reason.message
                : String(runtimeResult.reason),
            },
        error: hardwareResult.status === 'rejected'
          ? (
              hardwareResult.reason instanceof Error
                ? hardwareResult.reason.message
                : String(hardwareResult.reason)
            )
          : undefined,
        loading: false,
        checkedAt: Date.now(),
      },
    }))
  }

  const refresh = async () => {
    setError(null)
    try {
      const result = await api.listDevices()
      setDevices(result.devices)
      await Promise.all(result.devices.map(refreshStatus))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => { refresh() }, [])

  const openPairForm = (device?: HardwareDevice) => {
    setName(device?.name ?? '')
    setBaseUrl(device?.base_url ?? suggestedHardwareUrl(devices))
    setToken('')
    setRuntimeToken('')
    setChangeRuntimeToken(false)
    setError(null)
    setShowForm(true)
  }

  const pair = async (event: FormEvent) => {
    event.preventDefault()
    const urlError = hardwareUrlError(baseUrl)
    if (urlError) {
      setError(urlError)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api.pairDevice(
        name.trim(),
        baseUrl.trim(),
        token.trim(),
        runtimeToken.trim(),
      )
      setShowForm(false)
      setToken('')
      setRuntimeToken('')
      setChangeRuntimeToken(false)
      const listed = await api.listDevices()
      setDevices(listed.devices)
      setStates(prev => ({
        ...prev,
        [result.device.id]: {
          status: result.status,
          runtime: result.runtime,
          loading: false,
          checkedAt: Date.now(),
        },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (device: HardwareDevice) => {
    if (!window.confirm(`Remove "${device.name}" from this Blacknode editor?`)) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteDevice(device.id)
      setDevices(prev => prev.filter(item => item.id !== device.id))
      setStates(prev => {
        const next = { ...prev }
        delete next[device.id]
        return next
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const rename = async (device: HardwareDevice) => {
    const name = window.prompt('Name this robot', device.name)
    if (name === null || name.trim() === device.name) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.renameDevice(device.id, name.trim())
      setDevices(prev => prev.map(item => (
        item.id === device.id ? result.device : item
      )))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const stopDeployment = async (device: HardwareDevice, deploymentId: string) => {
    if (!window.confirm(
      `Stop the deployment using "${device.name}" and reconnect its hardware monitor?`,
    )) return
    setBusy(true)
    setError(null)
    try {
      await api.stopRemoteDeployment(device.id, deploymentId)
      await refreshStatus(device)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const pairUrlError = showForm ? hardwareUrlError(baseUrl) : null
  const pairRuntimeUrl = runtimeUrlForHardware(baseUrl)
  const reusableRuntimeDevice = devices.find(device => (
    device.runtime_url === pairRuntimeUrl
    && device.runtime_token_configured
    && states[device.id]?.runtime?.ok
  ))
  const reuseRuntimeToken = Boolean(reusableRuntimeDevice) && !changeRuntimeToken

  return (
    <div className="bn-runs-panel bn-devices-panel">
      <div className="bn-runs-toolbar">
        <div>
          <div className="bn-runs-title">Devices</div>
          <div className="bn-runs-subtitle">{devices.length} paired</div>
        </div>
        <div className="bn-runs-actions">
          <button onClick={refresh} disabled={busy} style={miniButton}>Refresh</button>
          <button onClick={() => openPairForm()} disabled={busy} style={primaryButton}>Pair device</button>
        </div>
      </div>

      {showForm && (
        <form className="bn-device-form" onSubmit={pair}>
          <div className="bn-device-form-title">Pair hardware service</div>
          <div className="bn-device-help">
            On the hardware computer, run <code>./pair.sh --all --show</code>, then copy
            one robot’s name, complete hardware URL, and token. The computer runtime
            on port 8766 is connected once and reused for its other robots.
          </div>
          <label>
            <span>Name</span>
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="Workshop robot"
              autoComplete="off"
            />
          </label>
          <label>
            <span>Hardware service URL · port required</span>
            <input
              value={baseUrl}
              onChange={event => setBaseUrl(event.target.value)}
              placeholder="http://192.168.1.87:8765"
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
            />
          </label>
          {pairUrlError && (
            <div className="bn-device-recovery-hint" role="alert">
              {pairUrlError}
            </div>
          )}
          <label>
            <span>Hardware token · selected robot</span>
            <input
              value={token}
              onChange={event => setToken(event.target.value)}
              type="password"
              placeholder="Paste token from pair.sh"
              required
              autoComplete="new-password"
            />
          </label>
          {reuseRuntimeToken ? (
            <div className="bn-device-runtime-reuse">
              <div>
                <strong>Computer runtime already connected</strong>
                <span>
                  {reusableRuntimeDevice?.runtime_url} will be reused automatically.
                  Only this robot’s hardware token is needed.
                </span>
              </div>
              <button
                type="button"
                onClick={() => setChangeRuntimeToken(true)}
                style={miniButton}
              >
                Change
              </button>
            </div>
          ) : (
            <>
              <label>
                <span>Computer runtime token · once per computer</span>
                <input
                  value={runtimeToken}
                  onChange={event => setRuntimeToken(event.target.value)}
                  type="password"
                  placeholder="Paste token from service.sh pairing"
                  autoComplete="new-password"
                />
              </label>
              <div className="bn-device-help">
                Enter this once for port 8766. Future robots on this computer reuse
                it automatically. Leave it empty only when runtime intentionally
                shares the hardware token.
              </div>
            </>
          )}
          <div className="bn-device-form-actions">
            <button
              type="button"
              onClick={() => {
                setShowForm(false)
                setToken('')
                setRuntimeToken('')
                setChangeRuntimeToken(false)
              }}
              style={miniButton}
            >
              Cancel
            </button>
            <button type="submit" disabled={busy} style={primaryButton}>
              {busy ? 'Checking…' : 'Pair and verify'}
            </button>
          </div>
        </form>
      )}

      {error && <div className="bn-runs-error">{error}</div>}

      <div className="bn-runs-list">
        {devices.length === 0 && !showForm && !error && (
          <div className="bn-runs-empty">
            No hardware device is paired. Run <strong>./pair.sh</strong> on the device,
            then add its network address and token here.
          </div>
        )}
        {devices.map(device => (
          <DeviceRow
            key={device.id}
            device={device}
            state={states[device.id]}
            busy={busy}
            onRefresh={() => refreshStatus(device)}
            onRename={() => rename(device)}
            onRepair={() => openPairForm(device)}
            onRemove={() => remove(device)}
            onStopDeployment={deploymentId => stopDeployment(device, deploymentId)}
          />
        ))}
      </div>
    </div>
  )
}

function DeviceRow({
  device,
  state,
  busy,
  onRefresh,
  onRename,
  onRepair,
  onRemove,
  onStopDeployment,
}: {
  device: HardwareDevice
  state?: DeviceState
  busy: boolean
  onRefresh: () => void
  onRename: () => void
  onRepair: () => void
  onRemove: () => void
  onStopDeployment: (deploymentId: string) => void
}) {
  const status = state?.status
  const runtime = state?.runtime
  const serviceOnline = Boolean(status)
  const connected = Boolean(status?.connected)
  const deploymentLease = status?.deployment_lease
  const leased = Boolean(status?.leased_to_deployment || deploymentLease)
  const runtimeReady = runtime?.ok === true
  const ready = connected && runtimeReady
  const color = ready
    ? 'var(--ok)'
    : serviceOnline || runtime
      ? 'var(--warn)'
      : 'var(--err)'
  const label = state?.loading
    ? 'CHECK'
    : leased
      ? 'IN USE'
      : ready
        ? 'READY'
        : serviceOnline
          ? 'NEEDS SETUP'
          : 'OFF'
  const recoveryHint = hardwareRecoveryHint(status?.error)

  return (
    <div className="bn-run-row is-expanded" style={{ '--run-status': color } as CSSProperties}>
      <div className="bn-device-summary">
        <div className="bn-run-timeline-mark"><span /></div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-title">{device.name}</span>
          </div>
          <div className="bn-run-node" title={device.base_url}>{device.base_url}</div>
          <div className="bn-run-node" title={device.runtime_url}>runtime {device.runtime_url}</div>
          <div className="bn-run-badges">
            <span>{device.remote_device_id}</span>
            <span>hardware token {device.token_fingerprint}</span>
            <span>
              runtime token {device.runtime_token_fingerprint || device.token_fingerprint}
            </span>
            {status?.joint_names && <span>{status.joint_names.length} joints</span>}
          </div>
          {state?.error && (
            <div className="bn-run-error-line bn-device-error" role="alert">{state.error}</div>
          )}
          {status?.error && (
            <div className="bn-device-error-action" role="alert">
              <div className="bn-run-error-line bn-device-error">{status.error}</div>
              {deploymentLease?.id && (
                <button
                  onClick={() => onStopDeployment(deploymentLease.id)}
                  disabled={busy || state?.loading}
                  style={dangerButton}
                >
                  Stop “{deploymentLease.name}” and check again
                </button>
              )}
            </div>
          )}
          {runtime && !runtime.ok && (
            <>
              <div className="bn-run-error-line bn-device-error" role="alert">
                Runtime: {runtime.error || 'Unavailable'}
              </div>
              <div className="bn-device-recovery-hint">
                On the device, run <code>blacknode-runtime/service.sh pairing</code>,
                then choose Re-pair and paste its runtime token.
              </div>
            </>
          )}
          {recoveryHint && <div className="bn-device-recovery-hint">{recoveryHint}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{label}</span>
          <span>
            {state?.loading
              ? 'Checking hardware and runtime…'
              : deploymentLease
                ? `Running deployment: ${deploymentLease.name}`
                : ready
                  ? 'Hardware and runtime ready'
                  : serviceOnline
                    ? 'Hardware ready · runtime needs attention'
                    : 'Unavailable'}
          </span>
        </div>
      </div>
      <div className="bn-run-detail">
        <div className="bn-device-facts">
          <DeviceFact label="Armed" value={status ? (status.armed ? 'Yes' : 'No') : '—'} warn={Boolean(status?.armed)} />
          <DeviceFact label="Calibrated" value={status?.calibrated == null ? '—' : status.calibrated ? 'Yes' : 'No'} />
          <DeviceFact
            label="Hardware"
            value={deploymentLease ? `Used by ${deploymentLease.name}` : connected ? 'Connected' : 'Unavailable'}
            warn={leased || (status != null && !connected)}
          />
          <DeviceFact
            label="Deployment runtime"
            value={runtime == null ? '—' : runtime.ok ? 'Ready' : 'Needs token'}
            warn={runtime != null && !runtime.ok}
          />
          <DeviceFact label="Capabilities" value={status?.capabilities?.join(', ') || '—'} />
          <DeviceFact label="Last check" value={formatCheckedAt(state?.checkedAt)} />
        </div>
        <div className="bn-run-detail-actions">
          <button onClick={onRefresh} disabled={busy || state?.loading} style={miniButton}>Check</button>
          <button onClick={onRename} disabled={busy} style={miniButton}>Rename</button>
          <button onClick={onRepair} disabled={busy} style={miniButton}>Re-pair</button>
          <button onClick={onRemove} disabled={busy} style={dangerButton}>Remove</button>
        </div>
      </div>
    </div>
  )
}

function hardwareRecoveryHint(error?: string): string | null {
  if (!error) return null
  const normalized = error.toLowerCase()
  if (normalized.includes('no response from servo') || normalized.includes('no position response from servo')) {
    return 'The latest check reached the device service, but the servo bus did not answer. Check servo power, bus wiring, the configured serial port, baud rate, and servo IDs. On the device, run ./probe.sh --servos 6.'
  }
  if (normalized.includes('leased') && normalized.includes('deployment')) {
    return 'The hardware monitor is paused for a deployment. Restore the deployment runtime connection, then press Check so Blacknode can identify the owner or recover a stale lease.'
  }
  return null
}

function formatCheckedAt(checkedAt?: number): string {
  return checkedAt ? new Date(checkedAt).toLocaleTimeString() : '—'
}

function DeviceFact({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="bn-device-fact">
      <span>{label}</span>
      <strong style={warn ? { color: 'var(--warn)' } : undefined}>{value}</strong>
    </div>
  )
}

const miniButton: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '3px 8px',
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

const dangerButton: CSSProperties = {
  ...miniButton,
  borderColor: 'var(--err)',
  color: 'var(--err)',
}
