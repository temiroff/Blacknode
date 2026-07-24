import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { api, type HardwareDevice, type HardwareDeviceStatus } from '../api'

type DeviceState = {
  status?: HardwareDeviceStatus
  error?: string
  loading?: boolean
}

export default function DevicesPanel() {
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [states, setStates] = useState<Record<string, DeviceState>>({})
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('http://192.168.1.87:8765')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshStatus = async (device: HardwareDevice) => {
    setStates(prev => ({ ...prev, [device.id]: { ...prev[device.id], loading: true } }))
    try {
      const status = await api.deviceStatus(device.id)
      setStates(prev => ({ ...prev, [device.id]: { status, loading: false } }))
    } catch (err) {
      setStates(prev => ({
        ...prev,
        [device.id]: {
          error: err instanceof Error ? err.message : String(err),
          loading: false,
        },
      }))
    }
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
    setBaseUrl(device?.base_url ?? 'http://192.168.1.87:8765')
    setToken('')
    setError(null)
    setShowForm(true)
  }

  const pair = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result = await api.pairDevice(name.trim(), baseUrl.trim(), token.trim())
      setShowForm(false)
      setToken('')
      await refresh()
      setStates(prev => ({
        ...prev,
        [result.device.id]: { status: result.status, loading: false },
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

  return (
    <div className="bn-runs-panel">
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
            On the Raspberry Pi, run <code>./pair.sh</code>, then paste its token here.
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
            <span>Device URL</span>
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
          <label>
            <span>Pairing token</span>
            <input
              value={token}
              onChange={event => setToken(event.target.value)}
              type="password"
              placeholder="Paste token from pair.sh"
              required
              autoComplete="new-password"
            />
          </label>
          <div className="bn-device-form-actions">
            <button type="button" onClick={() => { setShowForm(false); setToken('') }} style={miniButton}>
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
            onRepair={() => openPairForm(device)}
            onRemove={() => remove(device)}
          />
        ))}
      </div>
    </div>
  )
}

function DeviceRow({ device, state, busy, onRefresh, onRepair, onRemove }: {
  device: HardwareDevice
  state?: DeviceState
  busy: boolean
  onRefresh: () => void
  onRepair: () => void
  onRemove: () => void
}) {
  const status = state?.status
  const online = Boolean(status)
  const connected = Boolean(status?.connected)
  const color = online ? (connected ? 'var(--ok)' : 'var(--warn)') : 'var(--err)'
  const label = state?.loading ? 'CHECK' : online ? (connected ? 'READY' : 'ONLINE') : 'OFF'

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
            <span>token {device.token_fingerprint}</span>
            {status?.joint_names && <span>{status.joint_names.length} joints</span>}
          </div>
          {state?.error && <div className="bn-run-error-line">{state.error}</div>}
          {status?.error && <div className="bn-run-error-line">{status.error}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{label}</span>
          <span>{state?.loading ? 'Checking…' : online ? (connected ? 'Hardware connected' : 'Service connected') : 'Unavailable'}</span>
        </div>
      </div>
      <div className="bn-run-detail">
        <div className="bn-device-facts">
          <DeviceFact label="Armed" value={status ? (status.armed ? 'Yes' : 'No') : '—'} warn={Boolean(status?.armed)} />
          <DeviceFact label="Calibrated" value={status?.calibrated == null ? '—' : status.calibrated ? 'Yes' : 'No'} />
          <DeviceFact label="Capabilities" value={status?.capabilities?.join(', ') || '—'} />
        </div>
        <div className="bn-run-detail-actions">
          <button onClick={onRefresh} disabled={busy || state?.loading} style={miniButton}>Check</button>
          <button onClick={onRepair} disabled={busy} style={miniButton}>Re-pair</button>
          <button onClick={onRemove} disabled={busy} style={dangerButton}>Remove</button>
        </div>
      </div>
    </div>
  )
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
