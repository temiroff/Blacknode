import { useMemo, useState, type FormEvent } from 'react'
import { useStore } from '../store'
import { appTargets, buildAppView, designerControls, type AppControl } from '../appDesigner'
import { isWorkflowOperatorView } from '../operatorView'
import './AppDesignerDialog.css'

export default function AppDesignerDialog({ onClose }: { onClose: () => void }) {
  const { nodes, edges, nodeDefs, workflowMetadata, tabs, activeTabId,
    setWorkflowOperatorView, saveActiveWorkflow, setActiveTabSurface } = useStore()
  const existing = isWorkflowOperatorView(workflowMetadata.operator_view) ? workflowMetadata.operator_view : null
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const [title, setTitle] = useState(existing?.title ?? activeTab?.name ?? 'My App')
  const [id, setId] = useState(existing?.id ?? `app-${crypto.randomUUID().slice(0, 8)}`)
  const [controls, setControls] = useState<AppControl[]>(() => designerControls(existing))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const targets = useMemo(() => appTargets(nodes.map(node => node.data), nodeDefs,
    new Set(edges.map(edge => JSON.stringify([edge.target, edge.targetHandle])))), [nodes, nodeDefs, edges])
  const update = (id: string, patch: Partial<AppControl>) => setControls(items => items.map(item => item.id === id ? { ...item, ...patch } : item))
  const add = (kind: AppControl['kind']) => {
    const choices = kind === 'setting' ? targets.settings : targets.outputs
    const preferred = kind === 'action'
      ? choices.find(item => item.node_id === useStore.getState().workflowEntrypoint?.node_id && item.port === useStore.getState().workflowEntrypoint?.port)
      : undefined
    setControls(items => [...items, { id: `control-${crypto.randomUUID().slice(0, 8)}`, kind,
      target: preferred?.key ?? '', label: kind === 'action' ? 'Run' : '', display: 'text', mode: 'once' }])
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const view = buildAppView(title, id, controls, targets, existing)
      await setWorkflowOperatorView(view)
      await saveActiveWorkflow(activeTab?.slug ? activeTab.name : title.trim())
      setActiveTabSurface('app')
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setSaving(false) }
  }
  return (
    <div className="bn-app-package-backdrop" role="dialog" aria-modal="true" aria-labelledby="bn-app-designer-title">
      <form className="bn-app-package-dialog bn-app-designer" onSubmit={submit}>
        <header><div><span>Build</span><h2 id="bn-app-designer-title">{existing ? 'Edit App' : 'Create App'}</h2></div>
          <button type="button" onClick={onClose} disabled={saving} aria-label="Close App designer">×</button></header>
        <p>Choose the parameters, results, and buttons people will use. Your workflow runs the App.</p>
        <fieldset disabled={saving}>
          <div className="bn-app-package-fields">
            <label>App name<input value={title} onChange={event => setTitle(event.target.value)} required autoFocus /></label>
            <label>App ID<input value={id} onChange={event => setId(event.target.value)} required /></label>
          </div>
          <div className="bn-app-designer-add">
            <button type="button" onClick={() => add('setting')}>+ Parameter</button>
            <button type="button" onClick={() => add('result')}>+ Result</button>
            <button type="button" onClick={() => add('action')}>+ Run button</button>
          </div>
          {existing && <p className="bn-app-designer-hint">Existing App sections and safety controls are retained. Controls added here can be edited below.</p>}
          {!controls.length && <p className="bn-app-designer-hint">Add a parameter to configure the task, a result to see its output, and a button to run it.</p>}
          <div className="bn-app-designer-controls">
            {controls.map((control, index) => {
              const choices = control.kind === 'setting' ? targets.settings : targets.outputs
              return <section className="bn-app-designer-control" key={control.id} aria-label={`Control ${index + 1}`}>
                <header><strong>{control.kind === 'setting' ? 'Parameter' : control.kind === 'action' ? 'Run button' : 'Result'}</strong>
                  <button type="button" onClick={() => setControls(items => items.filter(item => item.id !== control.id))} aria-label={`Remove control ${index + 1}`}>Remove</button></header>
                <label>Workflow {control.kind === 'setting' ? 'parameter' : 'output'}
                  <select value={control.target} onChange={event => {
                    const selected = choices.find(item => item.key === event.target.value)
                    update(control.id, { target: event.target.value, label: control.label || selected?.port.replace(/_/g, ' ') || '',
                      ...(control.kind === 'result' ? { display: selected?.type === 'Image' ? 'image' : selected?.port === 'viewer_url' ? 'viewer' : selected?.type === 'Bool' ? 'status' : 'text' } : {}) })
                  }} required>
                    <option value="">Choose {control.kind === 'setting' ? 'a parameter' : 'an output'}…</option>
                    {control.target && !choices.some(item => item.key === control.target) && <option value={control.target}>Unavailable — choose another</option>}
                    {choices.map(item => <option value={item.key} key={item.key}>{item.label}</option>)}
                  </select>
                </label>
                <label>Label<input value={control.label} onChange={event => update(control.id, { label: event.target.value })} required /></label>
                {control.kind === 'result' && <label>Show as<select value={control.display} onChange={event => update(control.id, { display: event.target.value as AppControl['display'] })}>
                  <option value="text">Text</option><option value="number">Metric</option><option value="status">Status</option><option value="image">Image</option><option value="viewer">Web viewer</option>
                </select></label>}
                {control.kind === 'action' && <>
                  <label>Run mode<select value={control.mode} onChange={event => update(control.id, { mode: event.target.value as 'once' | 'live' })}>
                    <option value="once">Run once</option><option value="live">Start live service</option>
                  </select></label>
                  <label>Confirmation message<input value={control.confirm ?? ''} onChange={event => update(control.id, { confirm: event.target.value })} placeholder="For actions needing operator confirmation" /></label>
                </>}
              </section>
            })}
          </div>
        </fieldset>
        {error && <p className="bn-app-package-error" role="alert">{error}</p>}
        <footer><span>Save, then try your App. Use Edit workflow to change its nodes.</span><div>
          <button type="button" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="is-primary" disabled={saving}>{saving ? 'Saving…' : 'Save & open App'}</button>
        </div></footer>
      </form>
    </div>
  )
}
