import { useEffect, useState, type ChangeEvent, type CSSProperties, type KeyboardEvent } from 'react'

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

function OperatorActions({ widget }: { widget: Extract<OperatorWidget, { type: 'actions' }> }) {
  const { updateParam, controlNode, cookNode } = useStore()
  const [busyId, setBusyId] = useState<string | null>(null)

  const run = async (item: OperatorActionItem) => {
    if (busyId || (item.confirm && !window.confirm(item.confirm))) return
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
      setBusyId(null)
    }
  }

  return (
    <article className="bn-operator-card bn-operator-actions-card">
      {widget.title && <h3>{widget.title}</h3>}
      <div>
        {widget.items.map(item => (
          <button
            type="button"
            className={`is-${item.tone ?? 'neutral'}`}
            disabled={Boolean(busyId)}
            onClick={() => void run(item)}
            key={item.id}
          >
            {busyId === item.id ? 'Working…' : item.label}
          </button>
        ))}
      </div>
    </article>
  )
}

function OperatorWidgetView({ widget, nodes }: {
  widget: OperatorWidget
  nodes: ReturnType<typeof useStore.getState>['nodes']
}) {
  if (widget.type === 'image') return <OperatorImage widget={widget} nodes={nodes} />
  if (widget.type === 'status') return <OperatorStatus widget={widget} nodes={nodes} />
  if (widget.type === 'metrics') return <OperatorMetrics widget={widget} nodes={nodes} />
  if (widget.type === 'fields') return <OperatorFields widget={widget} />
  return <OperatorActions widget={widget} />
}

export default function WorkflowOperatorView({ config, onEditWorkflow }: WorkflowOperatorViewProps) {
  const { nodes, cookNode, stopRuntimeServices, cookActive } = useStore()
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

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
      <header className="bn-operator-header">
        <div>
          <span>Workflow app</span>
          <h1>{config.title}</h1>
          {config.description && <p>{config.description}</p>}
        </div>
        <div className="bn-operator-header-actions">
          {config.run_target && (
            <button className="is-primary" type="button" disabled={starting || cookActive} onClick={() => void start()}>
              {starting || cookActive ? 'Starting…' : config.run_target.label ?? 'Start live'}
            </button>
          )}
          <button type="button" disabled={stopping} onClick={() => void stop()}>{stopping ? 'Stopping…' : 'Stop all'}</button>
          <button type="button" onClick={onEditWorkflow}>Edit workflow</button>
        </div>
      </header>

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
              {section.widgets.map(widget => <OperatorWidgetView widget={widget} nodes={nodes} key={widget.id} />)}
            </div>
          </section>
        ))}
      </div>
    </main>
  )
}
