import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import PointCloudViewer from './components/PointCloudViewer'

interface SlamState {
  running?: boolean
  live?: boolean
  scene?: unknown
  status?: { state?: string; error?: string }
  report?: string
}

type ControlAction = 'start' | 'clear' | 'pause' | 'resume' | 'stop' | 'set-goal'

function actionStyle(kind: 'start' | 'stop', disabled: boolean): CSSProperties {
  const active = kind === 'start' ? 'var(--ok)' : 'var(--err)'
  return {
    height: 29,
    padding: '0 11px',
    border: `1px solid color-mix(in srgb, ${active} 72%, transparent)`,
    borderRadius: 6,
    background: `color-mix(in srgb, ${active} 20%, var(--panel))`,
    color: active,
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 700,
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.45 : 1,
  }
}

export default function StandaloneSlam() {
  const [state, setState] = useState<SlamState>({})
  const [pending, setPending] = useState<ControlAction | ''>('')
  const [connectionError, setConnectionError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/state', { cache: 'no-store' })
      if (!response.ok) throw new Error(`viewer state returned HTTP ${response.status}`)
      setState(await response.json() as SlamState)
      setConnectionError('')
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error))
    }
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = 'dark'
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 100)
    return () => window.clearInterval(timer)
  }, [refresh])

  const control = useCallback(async (action: ControlAction, payload: Record<string, unknown> = {}) => {
    if (pending) return
    setPending(action)
    try {
      const response = await fetch(`/api/control/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(`control returned HTTP ${response.status}`)
      setState(await response.json() as SlamState)
      setConnectionError('')
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error))
    } finally {
      setPending('')
    }
  }, [pending])

  const scene = (state.scene && typeof state.scene === 'object' ? state.scene : {}) as {
    history_paused?: boolean
  }
  const statusState = connectionError ? 'disconnected' : String(state.status?.state || (state.running ? 'waiting' : 'stopped'))
  const statusColor = connectionError || statusState === 'error'
    ? 'var(--err)'
    : state.live
      ? 'var(--ok)'
      : 'var(--warn)'

  return (
    <main className="bn-standalone-slam">
      <header className="bn-standalone-slam__header">
        <div className="bn-standalone-slam__brand">
          <img src="/blacknode-logo-dark.png" alt="Blacknode" />
          <div>
            <strong>Warp SLAM</strong>
            <span>Jetson standalone viewer</span>
          </div>
        </div>
        <div className="bn-standalone-slam__status" style={{ color: statusColor }}>
          <i style={{ background: statusColor }} />
          {statusState.toUpperCase()}
          <span>{connectionError || state.status?.error || state.report || ''}</span>
        </div>
        <div className="bn-standalone-slam__actions">
          <button
            type="button"
            disabled={Boolean(pending) || Boolean(state.running)}
            style={actionStyle('start', Boolean(pending) || Boolean(state.running))}
            onClick={() => { void control('start') }}
          >
            {pending === 'start' ? 'Starting…' : 'Go live'}
          </button>
          <button
            type="button"
            disabled={Boolean(pending) || !state.running}
            style={actionStyle('stop', Boolean(pending) || !state.running)}
            onClick={() => { void control('stop') }}
          >
            {pending === 'stop' ? 'Stopping…' : 'Stop live'}
          </button>
        </div>
      </header>
      <section className="bn-standalone-slam__viewer">
        <PointCloudViewer
          scene={state.scene}
          viewerRole="map"
          onClear={() => { void control('clear') }}
          onAccumulationToggle={() => { void control(scene.history_paused ? 'resume' : 'pause') }}
          onGoalSet={(x, y) => { void control('set-goal', { goal_x_m: x, goal_y_m: y }) }}
          clearPending={pending === 'clear'}
          accumulationPending={pending === 'pause' || pending === 'resume'}
          goalPending={pending === 'set-goal'}
        />
      </section>
    </main>
  )
}
