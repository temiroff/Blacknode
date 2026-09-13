import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { setupError } from './ActuatorSetupNode'

type SavedStates = { points?: Record<string, number>; poses?: Record<string, number>; dirty?: boolean }
type Limits = { min: number; home: number; max: number }
export type ServoFeedback = { live: boolean; raw_position?: number; torque_enabled?: boolean }

export default function ServoCalibrationControls({ id, selection, enabled, position, onArmedChange, onFeedback }: {
  id: string; selection: string; enabled: boolean; position?: number
  onArmedChange: (armed: boolean) => void
  onFeedback?: (feedback: ServoFeedback) => void
}) {
  const [states, setStates] = useState<SavedStates>({})
  const [limits, setLimits] = useState<Limits | null>(null)
  const [saved, setSaved] = useState(false)
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [target, setTarget] = useState(position ?? 2048)
  const [actual, setActual] = useState(position)
  const [torque, setTorque] = useState<boolean>()
  const [feedbackLive, setFeedbackLive] = useState(false)
  const [rawRange, setRawRange] = useState({ min: 0, max: 4095 })
  const [feedback, setFeedback] = useState('Reading live position…')
  const [poseName, setPoseName] = useState('')
  const [report, setReport] = useState('')
  const live = useRef({ generation: 0, armed: false, pendingArm: false })
  const motionQueue = useRef({ running: false, pending: undefined as { ticks: number; issued_at: number } | undefined })

  const apply = (outputs: Record<string, unknown>, updateTarget = true) => {
    if (outputs.states) setStates(outputs.states as SavedStates)
    if (outputs.test_limits) {
      const next = outputs.test_limits as Partial<Limits>
      setLimits(typeof next.min === 'number' && typeof next.home === 'number' && typeof next.max === 'number' ? next as Limits : null)
    }
    if (typeof outputs.saved === 'boolean') setSaved(outputs.saved)
    if (typeof outputs.raw_position === 'number') { setActual(outputs.raw_position); setFeedbackLive(true) }
    if (typeof outputs.torque_enabled === 'boolean') setTorque(outputs.torque_enabled)
    else if (outputs.armed === false) { setTorque(undefined); setFeedbackLive(false) }
    if (updateTarget && typeof outputs.target_ticks === 'number') setTarget(outputs.target_ticks)
    if (typeof outputs.armed === 'boolean') {
      live.current.armed = outputs.armed
      setArmed(outputs.armed); onArmedChange(outputs.armed)
    }
    if (outputs.ok === false && outputs.report) setReport(String(outputs.report))
  }
  const action = async (name: string, payload: Record<string, unknown> = {}) => {
    if (name === 'stop-test') {
      motionQueue.current.pending = undefined
      ++live.current.generation
      live.current.armed = false; setArmed(false); onArmedChange(false)
    }
    const generation = live.current.generation
    setReport('')
    setBusy(true)
    if (name === 'arm-test') live.current.pendingArm = true
    try {
      const result = await api.controlNode(id, name, payload)
      if (generation !== live.current.generation) {
        if (result.outputs.armed) await api.controlNode(id, 'stop-test')
        return
      }
      apply(result.outputs)
      if (!result.ok) setReport(String(result.outputs.report || 'Action failed'))
    } catch (error) {
      if (generation === live.current.generation) {
        setTorque(undefined); setFeedbackLive(false)
        setReport(setupError(error)); setArmed(false); live.current.armed = false; onArmedChange(false)
      }
      if (name === 'arm-test' || name === 'test-target') void api.controlNode(id, 'stop-test').catch(() => undefined)
    } finally {
      live.current.pendingArm = false
      if (generation === live.current.generation) setBusy(false)
    }
  }

  const queueMove = (ticks: number) => {
    if (!live.current.armed) return
    motionQueue.current.pending = { ticks, issued_at: Date.now() / 1000 }
    if (motionQueue.current.running) return
    motionQueue.current.running = true
    const generation = live.current.generation
    void (async () => {
      try {
        while (motionQueue.current.pending && live.current.armed && generation === live.current.generation) {
          const command = motionQueue.current.pending
          motionQueue.current.pending = undefined
          const result = await api.controlNode(id, 'test-target', command)
          if (generation !== live.current.generation) return
          apply(result.outputs, false)
          if (!result.ok || result.outputs.armed !== true) {
            motionQueue.current.pending = undefined
            break
          }
        }
      } catch (error) {
        if (generation === live.current.generation) {
          setTorque(undefined); setFeedbackLive(false)
          motionQueue.current.pending = undefined
          setReport(setupError(error)); live.current.armed = false; setArmed(false); onArmedChange(false)
          void api.controlNode(id, 'stop-test').catch(() => undefined)
        }
      } finally {
        motionQueue.current.running = false
        const pending = motionQueue.current.pending
        if (pending && live.current.armed) queueMove(pending.ticks)
      }
    })()
  }

  useEffect(() => {
    const generation = ++live.current.generation
    motionQueue.current.pending = undefined
    setStates({}); setLimits(null); setSaved(false); setArmed(false)
    setTorque(undefined); setFeedbackLive(false)
    live.current.armed = false; setActual(position); setTarget(position ?? 2048); setBusy(false)
    if (enabled) void api.controlNode(id, 'state-status').then(result => {
      if (live.current.generation === generation) apply(result.outputs)
    }).catch(error => { if (live.current.generation === generation) setReport(setupError(error)) })
    const stop = () => {
      motionQueue.current.pending = undefined
      if (live.current.armed || live.current.pendingArm) {
        ++live.current.generation
        live.current.armed = false; setArmed(false); onArmedChange(false)
        void api.controlNode(id, 'stop-test').catch(() => undefined)
      }
    }
    const hidden = () => { if (document.hidden) stop() }
    window.addEventListener('pagehide', stop)
    document.addEventListener('visibilitychange', hidden)
    return () => {
      ++live.current.generation
      stop()
      window.removeEventListener('pagehide', stop)
      document.removeEventListener('visibilitychange', hidden)
    }
  }, [id, selection, enabled])

  useEffect(() => {
    if (!enabled || armed || busy) return
    let cancelled = false
    let running = false
    let timer: ReturnType<typeof setTimeout>
    let staleTimer: ReturnType<typeof setTimeout>
    const poll = async () => {
      if (cancelled || document.hidden || running || live.current.pendingArm || live.current.armed) return
      running = true
      staleTimer = setTimeout(() => {
        if (!cancelled) { setActual(undefined); setTorque(undefined); setFeedbackLive(false); setFeedback('Position unavailable · waiting for fresh feedback') }
      }, 1000)
      try {
        const result = await api.controlNode(id, 'read-position', { confirm_read_only: true })
        if (cancelled || document.hidden || live.current.pendingArm || live.current.armed) return
        if (!result.ok || typeof result.outputs.raw_position !== 'number') {
          throw new Error(String(result.outputs.report || 'Live position unavailable'))
        }
        if (typeof result.outputs.sampled_at === 'number' && Date.now() / 1000 - result.outputs.sampled_at > 1.5) {
          throw new Error('Position feedback is stale')
        }
        setActual(result.outputs.raw_position)
        setTorque(typeof result.outputs.torque_enabled === 'boolean' ? result.outputs.torque_enabled : undefined)
        setFeedbackLive(true)
        const range = result.outputs.position_range as { min?: number; max?: number } | undefined
        if (typeof range?.min === 'number' && typeof range.max === 'number' && range.min < range.max) {
          setRawRange({ min: range.min, max: range.max })
        }
        setFeedback(result.outputs.report ? `Hardware warning: ${result.outputs.report}`
          : result.outputs.torque_enabled === false ? 'Live · move the motor by hand; the slider follows.'
            : 'Torque is on or unknown. Release torque before moving the motor by hand.')
      } catch (error) {
        if (!cancelled) { setActual(undefined); setTorque(undefined); setFeedbackLive(false); setFeedback(`Position unavailable · ${setupError(error)}`) }
      } finally {
        clearTimeout(staleTimer)
        running = false
        if (!cancelled && !document.hidden) timer = setTimeout(() => void poll(), 250)
      }
    }
    const visibility = () => {
      clearTimeout(timer)
      if (document.hidden) { setActual(undefined); setTorque(undefined); setFeedbackLive(false); setFeedback('Live position paused') }
      else void poll()
    }
    setFeedback('Reading live position…')
    void poll()
    document.addEventListener('visibilitychange', visibility)
    return () => { cancelled = true; clearTimeout(timer); clearTimeout(staleTimer); document.removeEventListener('visibilitychange', visibility) }
  }, [id, selection, enabled, armed, busy])

  useEffect(() => {
    if (!armed) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      const generation = live.current.generation
      try {
        const result = await api.controlNode(id, 'test-status')
        if (!cancelled && generation === live.current.generation) apply(result.outputs, false)
      } catch (error) {
        if (!cancelled && generation === live.current.generation) {
          setTorque(undefined); setFeedbackLive(false)
          setReport(setupError(error)); live.current.armed = false; setArmed(false); onArmedChange(false)
          void api.controlNode(id, 'stop-test').catch(() => undefined)
        }
      }
      if (!cancelled && live.current.armed) timer = setTimeout(() => void poll(), 100)
    }
    timer = setTimeout(() => void poll(), 100)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [id, armed])

  useEffect(() => {
    onFeedback?.({ live: feedbackLive && enabled && !busy, raw_position: actual, torque_enabled: torque })
  }, [actual, torque, feedbackLive, enabled, busy, onFeedback])
  useEffect(() => () => onFeedback?.({ live: false }), [onFeedback])

  const move = () => {
    if (armed && !busy) queueMove(target)
  }
  const armBlocked = !enabled ? 'Scan for a readable, supported servo before calibration or testing.'
    : !limits ? (['min', 'max'].every(point => states.points?.[point] != null)
      ? 'Captured endpoints are too close. Recapture a wider comfortable range.'
      : 'Capture Min and Max before testing. Home is optional.')
      : ''
  const visibleReport = report
  const reversed = (states.points?.min ?? 0) > (states.points?.max ?? 4095)
  const capturedMin = states.points?.min
  const capturedMax = states.points?.max
  const sliderMin = limits && capturedMin != null && capturedMax != null ? Math.min(capturedMin, capturedMax) : rawRange.min
  const sliderMax = limits && capturedMin != null && capturedMax != null ? Math.max(capturedMin, capturedMax) : rawRange.max
  return <fieldset className="bn-servo-calibration">
    <legend>Calibration and test</legend>
    <p>Support the robot. Capture with torque off; Arm saves the range and enables torque.</p>
    <div className="bn-actuator-actions">{(['min', 'home', 'max'] as const).map(point => <button key={point}
      disabled={!enabled || busy || armed} onClick={() => void action('capture-state', { point })}>
      Capture {point[0].toUpperCase() + point.slice(1)}{states.points?.[point] != null ? ` · ${states.points[point]}` : ''}
    </button>)}
      <button disabled={!enabled || busy || armed || (!Object.keys(states.points || {}).length && !Object.keys(states.poses || {}).length)} onClick={() => void action('save-states')}>Save states</button>
    </div>
    <small>{saved ? 'Saved' : states.dirty ? 'Captured · Arm to save and test' : 'Capture Min and Max'}</small>
    <details className="bn-servo-poses"><summary>Named poses</summary>
    <label>Pose name<input value={poseName} maxLength={64} disabled={!enabled || busy}
      onChange={event => setPoseName(event.target.value)} placeholder="e.g. Ready" /></label>
    <div className="bn-actuator-actions">
      <button disabled={!enabled || busy || !poseName.trim()} onClick={() => void action('capture-state', { point: 'pose', name: poseName.trim() })}>Capture pose</button>
    </div>
    <label>Saved pose<select defaultValue="" disabled={!limits || busy} onChange={event => {
      const value = states.poses?.[event.target.value]
      if (value != null && limits) setTarget(Math.max(limits.min, Math.min(limits.max, value)))
    }}><option value="">Choose a saved pose…</option>{Object.entries(states.poses || {}).map(([name, ticks]) =>
      <option key={name} value={name}>{name} · {ticks} ticks</option>)}</select></label>
      <button disabled={!armed || busy} onClick={move}>Move to target</button>
    </details>
    <div className="bn-servo-test-controls">
    {limits && <div className="bn-servo-slider-ends"><span>Min · {reversed ? sliderMax : sliderMin}</span><span>Max · {reversed ? sliderMin : sliderMax}</span></div>}
    <label className="bn-servo-test-target">{armed ? `Target · ${target}` : `Measured position · ${actual ?? '—'}`} ticks<input type="range" aria-label="Test position"
      min={sliderMin} max={sliderMax} step={1} value={armed ? target : actual ?? sliderMin}
      style={{ direction: reversed ? 'rtl' : 'ltr' }}
      disabled={!enabled || !armed || !limits || busy} onChange={event => {
        const value = Number(event.target.value)
        const ticks = limits ? Math.max(limits.min, Math.min(limits.max, value)) : value
        setTarget(ticks); queueMove(ticks)
      }} /></label>
    <small>{armed ? `Armed · drag the slider to move. Measured: ${actual ?? 'unknown'} ticks.` : feedback}</small>
    <div className="bn-actuator-actions">
      <button disabled={!enabled || busy || armed} title={armBlocked || undefined} onClick={() => void action('arm-test', { operator_action: 'arm-test', save_calibration: true })}>{busy && live.current.pendingArm ? 'Arming…' : 'Arm'}</button>
      <button disabled={!armed && !busy} title="Release torque" onClick={() => void action('stop-test')}>Stop</button>
    </div>
    {(visibleReport || (!armed && armBlocked)) && <div className="bn-actuator-report" role={visibleReport ? 'alert' : 'note'}>{visibleReport || armBlocked}</div>}
    </div>
  </fieldset>
}
