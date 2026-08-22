import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type KeyboardEvent,
} from 'react'

import { useStore } from '../store'
import type {
  OperatorActionItem,
  OperatorFieldItem,
  OperatorMetricItem,
  OperatorStatusItem,
  OperatorValueSource,
  OperatorWidget,
  WorkflowOperatorView,
} from '../operatorView'

interface WorkflowOperatorViewProps {
  config: WorkflowOperatorView
  onEditWorkflow: () => void
}

type OperatorActionBinding =
  | { kind: 'keyboard'; code: string; label: string }
  | { kind: 'gamepad'; button: number; label: string }

type OperatorActionBindings = Record<string, OperatorActionBinding[]>
type BindingCapture = { actionId: string; kind: OperatorActionBinding['kind'] }

const OPERATOR_BINDINGS_STORAGE_PREFIX = 'blacknode-operator-action-bindings:'

function operatorBindingScope(config: WorkflowOperatorView): string {
  return String(config.id || config.title || 'workflow-app').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-')
}

function readOperatorBindings(scope: string): OperatorActionBindings {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(`${OPERATOR_BINDINGS_STORAGE_PREFIX}${scope}`) || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result: OperatorActionBindings = {}
    for (const [actionId, values] of Object.entries(parsed)) {
      if (!Array.isArray(values)) continue
      const bindings: OperatorActionBinding[] = []
      for (const value of values) {
        if (!value || typeof value !== 'object') continue
        const binding = value as Record<string, unknown>
        if (binding.kind === 'keyboard' && typeof binding.code === 'string') {
          bindings.push({ kind: 'keyboard', code: binding.code, label: String(binding.label || binding.code) })
        }
        if (binding.kind === 'gamepad' && typeof binding.button === 'number' && Number.isInteger(binding.button)) {
          bindings.push({
            kind: 'gamepad',
            button: binding.button,
            label: String(binding.label || `Pedal ${binding.button + 1}`),
          })
        }
      }
      if (bindings.length) result[actionId] = bindings
    }
    return result
  } catch {
    return {}
  }
}

function keyboardLabel(event: globalThis.KeyboardEvent): string {
  if (event.code === 'Space') return 'Space'
  if (event.code.startsWith('Key')) return event.code.slice(3)
  if (event.code.startsWith('Digit')) return event.code.slice(5)
  return event.key.length === 1 ? event.key.toUpperCase() : event.key
}

function bindingIdentity(binding: OperatorActionBinding): string {
  return binding.kind === 'keyboard' ? `keyboard:${binding.code}` : `gamepad:${binding.button}`
}

function isEditableBindingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return ['input', 'textarea', 'select'].includes(target.tagName.toLowerCase())
}

function notice(kind: 'error' | 'info', title: string, message: string) {
  window.dispatchEvent(new CustomEvent('blacknode:notice', { detail: { kind, title, message } }))
}

function valueFor(source: OperatorValueSource, nodes: ReturnType<typeof useStore.getState>['nodes']): unknown {
  const node = nodes.find(candidate => candidate.id === source.node_id)
  if (!node) return undefined
  if (node.data.portResults && source.port in node.data.portResults) {
    return node.data.portResults[source.port]
  }
  if (node.data.cookPort === source.port) return node.data.cookResult
  return undefined
}

function imageUrl(value: unknown): string {
  if (typeof value === 'string') {
    const candidate = value.trim()
    if (/^(data:image\/|blob:|https?:\/\/|\/)/i.test(candidate)) return candidate
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of ['image_url', 'data_url', 'preview', 'url']) {
      const candidate = String(record[key] ?? '').trim()
      if (/^(data:image\/|blob:|https?:\/\/|\/)/i.test(candidate)) return candidate
    }
  }
  return ''
}

function OperatorImage({ widget, nodes }: {
  widget: Extract<OperatorWidget, { type: 'image' }>
  nodes: ReturnType<typeof useStore.getState>['nodes']
}) {
  const url = imageUrl(valueFor(widget.source, nodes))
  return (
    <article className={`bn-operator-card bn-operator-image-card is-${widget.aspect ?? 'dashboard'}`}>
      <header><strong>{widget.title}</strong><span className={url ? 'is-live' : ''}>{url ? 'LIVE' : 'WAITING'}</span></header>
      <div className="bn-operator-image-frame">
        {url
          ? <img src={url} alt={widget.title} />
          : <div className="bn-operator-image-empty"><i aria-hidden="true" />{widget.empty ?? 'Start the workflow to show this view.'}</div>}
      </div>
    </article>
  )
}

function statusLabel(item: OperatorStatusItem, value: unknown): string {
  if (value === true) return item.true_label ?? 'Ready'
  if (value === false) return item.false_label ?? 'Not ready'
  if (value === undefined || value === null || value === '') return 'Waiting'
  return String(value)
}

function OperatorStatus({ widget, nodes }: {
  widget: Extract<OperatorWidget, { type: 'status' }>
  nodes: ReturnType<typeof useStore.getState>['nodes']
}) {
  return (
    <article className="bn-operator-card bn-operator-status-card">
      {widget.title && <h3>{widget.title}</h3>}
      <div className="bn-operator-status-list">
        {widget.items.map(item => {
          const value = valueFor(item, nodes)
          const state = value === true ? 'is-on' : value === false ? 'is-off' : 'is-idle'
          return (
            <div className={`${state} is-${item.tone ?? 'neutral'}`} key={`${item.node_id}:${item.port}`}>
              <i aria-hidden="true" />
              <span>{item.label}</span>
              <strong>{statusLabel(item, value)}</strong>
            </div>
          )
        })}
      </div>
    </article>
  )
}

function metricValue(item: OperatorMetricItem, value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  if (item.format === 'duration') {
    const seconds = Number(value)
    if (!Number.isFinite(seconds)) return String(value)
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
  }
  if (item.format === 'number' && Number.isFinite(Number(value))) {
    return Number(value).toLocaleString()
  }
  return String(value)
}

function OperatorMetrics({ widget, nodes }: {
  widget: Extract<OperatorWidget, { type: 'metrics' }>
  nodes: ReturnType<typeof useStore.getState>['nodes']
}) {
  return (
    <article className="bn-operator-card bn-operator-metrics-card">
      {widget.title && <h3>{widget.title}</h3>}
      <div className="bn-operator-metrics-grid">
        {widget.items.map(item => (
          <div key={`${item.node_id}:${item.port}`}>
            <span>{item.label}</span>
            <strong>{metricValue(item, valueFor(item, nodes))}{item.suffix ?? ''}</strong>
          </div>
        ))}
      </div>
    </article>
  )
}

function OperatorField({ item }: { item: OperatorFieldItem }) {
  const node = useStore(state => state.nodes.find(candidate => candidate.id === item.node_id))
  const updateParam = useStore(state => state.updateParam)
  const storedValue = node?.data.params?.[item.param]
  const [draft, setDraft] = useState(String(storedValue ?? ''))

  useEffect(() => setDraft(String(storedValue ?? '')), [storedValue])

  const commit = async () => {
    const value = item.input === 'number' ? Number(draft) : draft
    if (item.input === 'number' && !Number.isFinite(value)) return
    try {
      await updateParam(item.node_id, item.param, value)
    } catch (error) {
      notice('error', `Could not update ${item.label}`, error instanceof Error ? error.message : String(error))
    }
  }

  const common = {
    value: draft,
    placeholder: item.placeholder,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(event.target.value),
    onBlur: () => void commit(),
    onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && item.input !== 'textarea') {
        event.preventDefault()
        event.currentTarget.blur()
      }
    },
  }

  return (
    <label>
      <span>{item.label}</span>
      {item.input === 'textarea'
        ? <textarea {...common} rows={3} />
        : <input {...common} type={item.input === 'number' ? 'number' : 'text'} min={item.min} max={item.max} step={item.step} />}
    </label>
  )
}

function OperatorFields({ widget }: { widget: Extract<OperatorWidget, { type: 'fields' }> }) {
  return (
    <article className="bn-operator-card bn-operator-fields-card">
      {widget.title && <h3>{widget.title}</h3>}
      <div className="bn-operator-fields-grid">
        {widget.items.map(item => <OperatorField item={item} key={`${item.node_id}:${item.param}`} />)}
      </div>
    </article>
  )
}

function OperatorActions({ widget, busyId, bindings, onRun }: {
  widget: Extract<OperatorWidget, { type: 'actions' }>
  busyId: string | null
  bindings: OperatorActionBindings
  onRun: (item: OperatorActionItem) => void
}) {
  return (
    <article className="bn-operator-card bn-operator-actions-card">
      {widget.title && <h3>{widget.title}</h3>}
      <div>
        {widget.items.map(item => (
          <button
            type="button"
            className={`is-${item.tone ?? 'neutral'}`}
            disabled={Boolean(busyId)}
            onClick={() => onRun(item)}
            key={item.id}
          >
            <span>{busyId === item.id ? 'Working…' : item.label}</span>
            {(bindings[item.id] ?? []).length > 0 && (
              <small>{bindings[item.id].map(binding => binding.label).join(' · ')}</small>
            )}
          </button>
        ))}
      </div>
    </article>
  )
}

function OperatorWidgetView({ widget, nodes, busyId, bindings, onRun }: {
  widget: OperatorWidget
  nodes: ReturnType<typeof useStore.getState>['nodes']
  busyId: string | null
  bindings: OperatorActionBindings
  onRun: (item: OperatorActionItem) => void
}) {
  if (widget.type === 'image') return <OperatorImage widget={widget} nodes={nodes} />
  if (widget.type === 'status') return <OperatorStatus widget={widget} nodes={nodes} />
  if (widget.type === 'metrics') return <OperatorMetrics widget={widget} nodes={nodes} />
  if (widget.type === 'fields') return <OperatorFields widget={widget} />
  return <OperatorActions widget={widget} busyId={busyId} bindings={bindings} onRun={onRun} />
}

function OperatorBindingsDialog({ actions, bindings, capture, onCapture, onRemove, onClear, onClose }: {
  actions: OperatorActionItem[]
  bindings: OperatorActionBindings
  capture: BindingCapture | null
  onCapture: (capture: BindingCapture | null) => void
  onRemove: (actionId: string, binding: OperatorActionBinding) => void
  onClear: () => void
  onClose: () => void
}) {
  return (
    <div className="bn-operator-bindings-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="bn-operator-bindings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bn-operator-bindings-title"
        onMouseDown={event => event.stopPropagation()}
      >
        <header>
          <div>
            <span>Input bindings</span>
            <h2 id="bn-operator-bindings-title">Shortcuts & pedals</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close shortcuts and pedals">×</button>
        </header>
        <p>
          Assign a keyboard key or a USB pedal exposed as a keyboard or game controller.
          Action confirmations and workflow safety checks still apply.
        </p>
        {capture && (
          <div className="bn-operator-binding-capture" role="status">
            <i aria-hidden="true" />
            {capture.kind === 'keyboard'
              ? 'Press a key now. Press Escape to cancel.'
              : 'Release the pedal, then press its game-controller button.'}
            <button type="button" onClick={() => onCapture(null)}>Cancel</button>
          </div>
        )}
        <div className="bn-operator-binding-list">
          {actions.map(action => (
            <div key={action.id}>
              <strong>{action.label}</strong>
              <div className="bn-operator-binding-chips">
                {(bindings[action.id] ?? []).map(binding => (
                  <button
                    type="button"
                    title={`Remove ${binding.label}`}
                    onClick={() => onRemove(action.id, binding)}
                    key={bindingIdentity(binding)}
                  >
                    {binding.label}<span aria-hidden="true">×</span>
                  </button>
                ))}
                {(bindings[action.id] ?? []).length === 0 && <span>Not assigned</span>}
              </div>
              <div className="bn-operator-binding-assign">
                <button type="button" onClick={() => onCapture({ actionId: action.id, kind: 'keyboard' })}>
                  Assign key
                </button>
                <button type="button" onClick={() => onCapture({ actionId: action.id, kind: 'gamepad' })}>
                  Assign pedal
                </button>
              </div>
            </div>
          ))}
        </div>
        <footer>
          <button type="button" onClick={onClear} disabled={Object.keys(bindings).length === 0}>Clear all</button>
          <button className="is-primary" type="button" onClick={onClose}>Done</button>
        </footer>
      </section>
    </div>
  )
}

export default function WorkflowOperatorView({ config, onEditWorkflow }: WorkflowOperatorViewProps) {
  const { nodes, updateParam, controlNode, cookNode, stopRuntimeServices, cookActive } = useStore()
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [bindingsOpen, setBindingsOpen] = useState(false)
  const [capture, setCapture] = useState<BindingCapture | null>(null)
  const bindingScope = useMemo(() => operatorBindingScope(config), [config])
  const [bindings, setBindings] = useState<OperatorActionBindings>(() => readOperatorBindings(bindingScope))
  const busyActionRef = useRef<string | null>(null)
  const actions = useMemo(() => config.sections.flatMap(section => (
    section.widgets.flatMap(widget => widget.type === 'actions' ? widget.items : [])
  )), [config])
  const actionById = useMemo(() => new Map(actions.map(action => [action.id, action])), [actions])

  useEffect(() => {
    try {
      window.localStorage.setItem(`${OPERATOR_BINDINGS_STORAGE_PREFIX}${bindingScope}`, JSON.stringify(bindings))
    } catch {
      // Shortcuts still work for the current page when browser storage is disabled.
    }
  }, [bindingScope, bindings])

  const assignBinding = useCallback((actionId: string, binding: OperatorActionBinding) => {
    const identity = bindingIdentity(binding)
    setBindings(current => {
      const next: OperatorActionBindings = {}
      for (const [currentActionId, currentBindings] of Object.entries(current)) {
        const filtered = currentBindings.filter(candidate => (
          bindingIdentity(candidate) !== identity
          && !(currentActionId === actionId && candidate.kind === binding.kind)
        ))
        if (filtered.length) next[currentActionId] = filtered
      }
      next[actionId] = [...(next[actionId] ?? []), binding]
      return next
    })
    setCapture(null)
  }, [])

  const removeBinding = useCallback((actionId: string, binding: OperatorActionBinding) => {
    setBindings(current => {
      const remaining = (current[actionId] ?? []).filter(candidate => bindingIdentity(candidate) !== bindingIdentity(binding))
      const next = { ...current }
      if (remaining.length) next[actionId] = remaining
      else delete next[actionId]
      return next
    })
  }, [])

  const runAction = useCallback(async (item: OperatorActionItem) => {
    if (busyActionRef.current || (item.confirm && !window.confirm(item.confirm))) return
    busyActionRef.current = item.id
    setBusyId(item.id)
    try {
      for (const update of item.updates ?? []) {
        await updateParam(update.node_id, update.param, update.value)
      }
      if (item.control) {
        await controlNode(item.control.node_id, item.control.action, item.control.payload)
      }
      if (item.cook_target) {
        await cookNode(
          item.cook_target.node_id,
          item.cook_target.port,
          undefined,
          item.cook_target.mode ?? 'once',
        )
      }
    } catch (error) {
      notice('error', `${item.label} failed`, error instanceof Error ? error.message : String(error))
    } finally {
      busyActionRef.current = null
      setBusyId(null)
    }
  }, [controlNode, cookNode, updateParam])

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (capture?.kind === 'keyboard') {
        event.preventDefault()
        event.stopPropagation()
        if (event.code === 'Escape') setCapture(null)
        else if (/^(Shift|Control|Alt|Meta)/.test(event.code)) return
        else assignBinding(capture.actionId, { kind: 'keyboard', code: event.code, label: keyboardLabel(event) })
        return
      }
      if (bindingsOpen || event.repeat || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || isEditableBindingTarget(event.target)) return
      const match = Object.entries(bindings).find(([, assigned]) => (
        assigned.some(binding => binding.kind === 'keyboard' && binding.code === event.code)
      ))
      const action = match ? actionById.get(match[0]) : null
      if (action) {
        event.preventDefault()
        void runAction(action)
      }
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [actionById, assignBinding, bindings, bindingsOpen, capture, runAction])

  useEffect(() => {
    if (typeof navigator.getGamepads !== 'function') return
    let frame = 0
    let initialized = false
    const pressed = new Map<string, boolean>()
    const poll = () => {
      const next = new Map<string, boolean>()
      let triggered = false
      for (const gamepad of navigator.getGamepads()) {
        if (!gamepad) continue
        gamepad.buttons.forEach((button, buttonIndex) => {
          const key = `${gamepad.index}:${buttonIndex}`
          next.set(key, button.pressed)
          if (triggered || !initialized || !button.pressed || pressed.get(key)) return
          if (capture?.kind === 'gamepad') {
            assignBinding(capture.actionId, { kind: 'gamepad', button: buttonIndex, label: `Pedal ${buttonIndex + 1}` })
            triggered = true
            return
          }
          if (bindingsOpen) return
          const match = Object.entries(bindings).find(([, assigned]) => (
            assigned.some(binding => binding.kind === 'gamepad' && binding.button === buttonIndex)
          ))
          const action = match ? actionById.get(match[0]) : null
          if (action) {
            triggered = true
            void runAction(action)
          }
        })
      }
      initialized = true
      pressed.clear()
      next.forEach((value, key) => pressed.set(key, value))
      frame = window.requestAnimationFrame(poll)
    }
    frame = window.requestAnimationFrame(poll)
    return () => window.cancelAnimationFrame(frame)
  }, [actionById, assignBinding, bindings, bindingsOpen, capture, runAction])

  const start = async () => {
    const target = config.run_target
    if (!target || starting || (target.confirm && !window.confirm(target.confirm))) return
    setStarting(true)
    try {
      await cookNode(target.node_id, target.port, undefined, target.mode ?? 'once')
    } catch (error) {
      notice('error', 'Could not start workflow app', error instanceof Error ? error.message : String(error))
    } finally {
      setStarting(false)
    }
  }

  const stop = async () => {
    if (stopping || !window.confirm('Stop all live services? Support the robot before continuing because shutdown may release actuator torque.')) return
    setStopping(true)
    try {
      await stopRuntimeServices()
    } catch (error) {
      notice('error', 'Could not stop live services', error instanceof Error ? error.message : String(error))
    } finally {
      setStopping(false)
    }
  }

  return (
    <main className="bn-operator-view" style={{ '--bn-operator-accent': config.accent ?? 'var(--accent)' } as CSSProperties}>
      <aside className="bn-operator-sidebar">
        <div>
          <span>Workflow app</span>
          <h1>{config.title}</h1>
          {config.description && <p>{config.description}</p>}
        </div>
        <div className="bn-operator-sidebar-actions">
          {config.run_target && (
            <button className="is-primary" type="button" disabled={starting || cookActive} onClick={() => void start()}>
              {starting || cookActive ? 'Starting…' : config.run_target.label ?? 'Start live'}
            </button>
          )}
          <button type="button" disabled={stopping} onClick={() => void stop()}>{stopping ? 'Stopping…' : 'Stop all'}</button>
          <button type="button" onClick={() => setBindingsOpen(true)}>Shortcuts & pedals</button>
          <button type="button" onClick={onEditWorkflow}>Edit workflow</button>
        </div>
      </aside>

      <div className="bn-operator-sections">
        {config.sections.map(section => (
          <section className={`bn-operator-section is-${section.layout ?? 'grid'}`} key={section.id}>
            {(section.title || section.description) && (
              <header>
                {section.title && <h2>{section.title}</h2>}
                {section.description && <p>{section.description}</p>}
              </header>
            )}
            <div>
              {section.widgets.map(widget => (
                <OperatorWidgetView
                  widget={widget}
                  nodes={nodes}
                  busyId={busyId}
                  bindings={bindings}
                  onRun={item => void runAction(item)}
                  key={widget.id}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      {bindingsOpen && (
        <OperatorBindingsDialog
          actions={actions}
          bindings={bindings}
          capture={capture}
          onCapture={setCapture}
          onRemove={removeBinding}
          onClear={() => { setBindings({}); setCapture(null) }}
          onClose={() => { setBindingsOpen(false); setCapture(null) }}
        />
      )}
    </main>
  )
}
