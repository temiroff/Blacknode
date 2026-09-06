import type { BnNodeDef, BnNodeMeta } from './types'
import type { OperatorWidget, WorkflowOperatorView } from './operatorView'

export const DESIGNER_SECTION = 'app-designer'
export const DESIGNER_SETTINGS = 'app-designer-settings'
export interface AppControl {
  id: string
  kind: 'setting' | 'result' | 'action'
  target: string
  label: string
  display?: 'text' | 'number' | 'status' | 'image' | 'viewer'
  mode?: 'once' | 'live'
  confirm?: string
}
export interface AppTarget {
  key: string
  node_id: string
  port: string
  label: string
  type: string
}

export function appTargets(nodes: BnNodeMeta[], definitions: Record<string, BnNodeDef>, connected: Set<string>) {
  const settings: AppTarget[] = []
  const outputs: AppTarget[] = []
  for (const node of nodes) {
    const definition = definitions[node.type]
    const name = String(node.params._label || `${node.type} (${node.id.slice(0, 8)})`)
    const types = { ...definition?.input_types, ...node.input_types }
    const inputs = new Set([...Object.keys(definition?.input_defaults ?? {}), ...(definition?.inputs ?? []), ...node.inputs, ...Object.keys(node.params)])
    for (const port of inputs) {
      const key = JSON.stringify([node.id, port])
      if (connected.has(key) || port.startsWith('_') || /api[_-]?key|token|secret|password|credential/i.test(port)) continue
      const value = node.params[port]
      const type = types[port] ?? (typeof value === 'string' ? 'Text' : typeof value === 'number' ? 'Number' : '')
      if (!['Text', 'Int', 'Float', 'Number', 'Enum'].includes(type)) continue
      settings.push({ key, node_id: node.id, port, label: `${name} · ${port}`, type })
    }
    // Terminal Output nodes expose their cooked value without an output handle.
    for (const port of node.type === 'Output' ? ['value'] : node.outputs) {
      outputs.push({ key: JSON.stringify([node.id, port]), node_id: node.id, port,
        label: `${name} · ${port}`, type: node.output_types[port] ?? definition?.output_types[port] ?? 'Any' })
    }
  }
  return { settings, outputs }
}

export function designerControls(view: WorkflowOperatorView | null): AppControl[] {
  return (view?.sections ?? [])
    .filter(section => [DESIGNER_SECTION, DESIGNER_SETTINGS].includes(section.id))
    .flatMap(section => section.widgets.map(widget => {
      if (widget.type === 'image' || widget.type === 'viewer') {
        return { id: widget.id, kind: 'result' as const, target: JSON.stringify([widget.source.node_id, widget.source.port]), label: widget.title, display: widget.type }
      }
      const item = widget.items[0]
      if (widget.type === 'fields') {
        const field = widget.items[0]
        return { id: widget.id, kind: 'setting' as const, target: JSON.stringify([field.node_id, field.param]), label: field.label }
      }
      if (widget.type === 'actions') {
        const action = widget.items[0]
        return { id: widget.id, kind: 'action' as const, target: JSON.stringify([action.cook_target?.node_id, action.cook_target?.port]), label: action.label, mode: action.cook_target?.mode ?? 'once', confirm: action.confirm }
      }
      const source = widget.items[0]
      return { id: widget.id, kind: 'result' as const, target: JSON.stringify([source.node_id, source.port]), label: item.label,
        display: widget.type === 'status' ? 'status' as const : widget.items[0].format === 'number' ? 'number' as const : 'text' as const }
    }))
}

export function buildAppView(title: string, id: string, controls: AppControl[], targets: ReturnType<typeof appTargets>, existing: WorkflowOperatorView | null): WorkflowOperatorView {
  if (!title.trim()) throw new Error('Give your App a name.')
  if (!/^[a-z][a-z0-9_-]{0,63}$/.test(id)) throw new Error('App ID must start with a lowercase letter and use letters, numbers, hyphens, or underscores.')
  const fields: OperatorWidget[] = []
  const widgets: OperatorWidget[] = []
  for (const control of controls) {
    const target = (control.kind === 'setting' ? targets.settings : targets.outputs).find(item => item.key === control.target)
    if (!target) throw new Error(`Choose an available workflow ${control.kind === 'setting' ? 'parameter' : 'output'} for ${control.label || 'each control'}.`)
    if (!control.label.trim()) throw new Error('Give each App control a label.')
    const label = control.label.trim()
    const source = { node_id: target.node_id, port: target.port }
    if (control.kind === 'setting') {
      fields.push({ type: 'fields', id: control.id, items: [{ node_id: target.node_id, param: target.port, label,
        input: ['Int', 'Float', 'Number'].includes(target.type) ? 'number' : 'text' }] })
    } else if (control.kind === 'action') {
      widgets.push({ type: 'actions', id: control.id, items: [{ id: control.id, label, tone: 'primary',
        ...(control.confirm?.trim() ? { confirm: control.confirm.trim() } : {}),
        cook_target: { ...source, mode: control.mode ?? 'once' } }] })
    } else if (control.display === 'image' || control.display === 'viewer') {
      widgets.push({ type: control.display, id: control.id, title: label, source })
    } else if (control.display === 'status') {
      widgets.push({ type: 'status', id: control.id, items: [{ ...source, label }] })
    } else {
      widgets.push({ type: 'metrics', id: control.id, items: [{ ...source, label, format: control.display === 'number' ? 'number' : 'text' }] })
    }
  }
  const sections = (existing?.sections ?? []).filter(section => ![DESIGNER_SECTION, DESIGNER_SETTINGS].includes(section.id))
  if (widgets.length) sections.push({ id: DESIGNER_SECTION, layout: 'stack', widgets })
  if (fields.length) sections.push({ id: DESIGNER_SETTINGS, title: 'Parameters', region: 'parameters', widgets: fields })
  if (!sections.length) throw new Error('Add a parameter, result, or run button to your App.')
  return { ...existing, schema_version: 1, id, title: title.trim(), icon: existing?.icon ?? 'workflow', sections }
}
