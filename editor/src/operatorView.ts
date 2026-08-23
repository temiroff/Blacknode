export interface OperatorValueSource {
  node_id: string
  port: string
}

export interface OperatorRunTarget {
  node_id: string
  port: string
  mode?: 'once' | 'live'
  label?: string
  confirm?: string
}

export interface OperatorStatusItem extends OperatorValueSource {
  label: string
  true_label?: string
  false_label?: string
  tone?: 'neutral' | 'success' | 'warning' | 'danger'
}

export interface OperatorMetricItem extends OperatorValueSource {
  label: string
  suffix?: string
  format?: 'number' | 'duration' | 'text'
}

export interface OperatorFieldItem {
  node_id: string
  param: string
  label: string
  input?: 'text' | 'number' | 'textarea' | 'calibration_file'
  placeholder?: string
  min?: number
  max?: number
  step?: number
  apply_to?: Array<{ node_id: string; param: string }>
}

export interface OperatorSettingsGroup {
  id: string
  title: string
  description?: string
  items: OperatorFieldItem[]
}

export interface OperatorSettings {
  title?: string
  description?: string
  groups: OperatorSettingsGroup[]
}

export interface OperatorActionItem {
  id: string
  label: string
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger'
  confirm?: string
  updates?: Array<{ node_id: string; param: string; value: unknown }>
  control?: { node_id: string; action: string; payload?: Record<string, unknown> }
  cook_target?: OperatorRunTarget
}

export type OperatorWidget =
  | {
      type: 'image'
      id: string
      title: string
      source: OperatorValueSource
      empty?: string
      aspect?: 'video' | 'dashboard'
    }
  | { type: 'status'; id: string; title?: string; items: OperatorStatusItem[] }
  | { type: 'metrics'; id: string; title?: string; items: OperatorMetricItem[] }
  | { type: 'fields'; id: string; title?: string; items: OperatorFieldItem[] }
  | { type: 'actions'; id: string; title?: string; items: OperatorActionItem[] }

export interface OperatorViewSection {
  id: string
  title?: string
  description?: string
  region?: 'main' | 'parameters'
  layout?: 'grid' | 'stack'
  widgets: OperatorWidget[]
}

export interface WorkflowOperatorView {
  schema_version: 1
  id?: string
  title: string
  description?: string
  accent?: string
  icon?: 'record' | 'camera' | 'robot' | 'workflow' | 'play'
  settings?: OperatorSettings
  run_target?: OperatorRunTarget
  sections: OperatorViewSection[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function isWorkflowOperatorView(value: unknown): value is WorkflowOperatorView {
  if (!isRecord(value) || value.schema_version !== 1 || typeof value.title !== 'string') return false
  if (!Array.isArray(value.sections) || value.sections.length === 0) return false
  const sectionsValid = value.sections.every(section => (
    isRecord(section)
    && typeof section.id === 'string'
    && (section.region === undefined || section.region === 'main' || section.region === 'parameters')
    && Array.isArray(section.widgets)
    && section.widgets.every(widget => isRecord(widget) && typeof widget.type === 'string' && typeof widget.id === 'string')
  ))
  if (!sectionsValid || value.settings === undefined) return sectionsValid
  if (!isRecord(value.settings) || !Array.isArray(value.settings.groups)) return false
  return value.settings.groups.every(group => (
    isRecord(group)
    && typeof group.id === 'string'
    && typeof group.title === 'string'
    && Array.isArray(group.items)
    && group.items.every(item => (
      isRecord(item)
      && typeof item.node_id === 'string'
      && typeof item.param === 'string'
      && typeof item.label === 'string'
      && (item.input === undefined || ['text', 'number', 'textarea', 'calibration_file'].includes(String(item.input)))
      && (item.apply_to === undefined || (
        Array.isArray(item.apply_to)
        && item.apply_to.every(target => isRecord(target) && typeof target.node_id === 'string' && typeof target.param === 'string')
      ))
    ))
  ))
}
