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
  live_source?: OperatorValueSource
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
  input?: 'text' | 'number' | 'textarea' | 'file_path' | 'calibration_file' | 'swap'
  placeholder?: string
  button_label?: string
  picker_title?: string
  extensions?: string[]
  confirm?: string
  min?: number
  max?: number
  step?: number
  apply_to?: Array<{ node_id: string; param: string }>
  swap_pairs?: Array<{
    left: { node_id: string; param: string }
    right: { node_id: string; param: string }
  }>
  disabled_when?: OperatorValueSource
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
  state?: OperatorValueSource
  active_label?: string
  active_tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger'
  active_confirm?: string
  deactivate_control?: { node_id: string; action: string; payload?: Record<string, unknown> }
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
  | {
      type: 'viewer'
      id: string
      title: string
      source: OperatorValueSource
      empty?: string
      trusted_origins?: string[]
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

function hasText(record: Record<string, unknown>, key: string): boolean {
  return typeof record[key] === 'string' && String(record[key]).trim().length > 0
}

function optionalText(record: Record<string, unknown>, key: string): boolean {
  return record[key] === undefined || typeof record[key] === 'string'
}

function optionalEnum(record: Record<string, unknown>, key: string, values: readonly string[]): boolean {
  return record[key] === undefined || values.includes(String(record[key]))
}

function isSource(value: unknown): value is OperatorValueSource {
  return isRecord(value) && hasText(value, 'node_id') && hasText(value, 'port')
}

function isRunTarget(value: unknown): value is OperatorRunTarget {
  return isRecord(value)
    && hasText(value, 'node_id')
    && hasText(value, 'port')
    && optionalEnum(value, 'mode', ['once', 'live'])
    && optionalText(value, 'label')
    && optionalText(value, 'confirm')
    && (value.live_source === undefined || isSource(value.live_source))
}

function isField(value: unknown): value is OperatorFieldItem {
  if (!isRecord(value) || !hasText(value, 'node_id') || !hasText(value, 'param') || !hasText(value, 'label')) return false
  if (!optionalEnum(value, 'input', ['text', 'number', 'textarea', 'file_path', 'calibration_file', 'swap'])) return false
  if (!['placeholder', 'button_label', 'picker_title', 'confirm'].every(key => optionalText(value, key))) return false
  if (!['min', 'max', 'step'].every(key => value[key] === undefined || typeof value[key] === 'number')) return false
  if (value.extensions !== undefined && (!Array.isArray(value.extensions) || value.extensions.length === 0 || !value.extensions.every(item => typeof item === 'string' && item.trim()))) return false
  if (value.input === 'file_path' && !Array.isArray(value.extensions)) return false
  const isParamTarget = (target: unknown) => isRecord(target) && hasText(target, 'node_id') && hasText(target, 'param')
  if (value.apply_to !== undefined && (!Array.isArray(value.apply_to) || !value.apply_to.every(isParamTarget))) return false
  if (value.swap_pairs !== undefined && (
    !Array.isArray(value.swap_pairs)
    || value.swap_pairs.length === 0
    || !value.swap_pairs.every(pair => isRecord(pair) && isParamTarget(pair.left) && isParamTarget(pair.right))
  )) return false
  return value.disabled_when === undefined || isSource(value.disabled_when)
}

function isControl(value: unknown): boolean {
  return isRecord(value)
    && hasText(value, 'node_id')
    && hasText(value, 'action')
    && (value.payload === undefined || isRecord(value.payload))
}

function isAction(value: unknown): value is OperatorActionItem {
  if (!isRecord(value) || !hasText(value, 'id') || !hasText(value, 'label')) return false
  if (!optionalEnum(value, 'tone', ['neutral', 'primary', 'success', 'warning', 'danger'])) return false
  if (!optionalEnum(value, 'active_tone', ['neutral', 'primary', 'success', 'warning', 'danger'])) return false
  if (!['confirm', 'active_label', 'active_confirm'].every(key => optionalText(value, key))) return false
  if (value.updates !== undefined && (
    !Array.isArray(value.updates)
    || value.updates.length === 0
    || !value.updates.every(update => isRecord(update) && hasText(update, 'node_id') && hasText(update, 'param') && Object.prototype.hasOwnProperty.call(update, 'value'))
  )) return false
  if (value.control !== undefined && !isControl(value.control)) return false
  if (value.deactivate_control !== undefined && !isControl(value.deactivate_control)) return false
  if (value.cook_target !== undefined && !isRunTarget(value.cook_target)) return false
  if (value.state !== undefined && !isSource(value.state)) return false
  return value.updates !== undefined || value.control !== undefined || value.cook_target !== undefined
}

function isWidget(value: unknown): value is OperatorWidget {
  if (!isRecord(value) || !hasText(value, 'id') || !hasText(value, 'type') || !optionalText(value, 'title')) return false
  if (value.type === 'image' || value.type === 'viewer') {
    if (!hasText(value, 'title') || !isSource(value.source) || !optionalText(value, 'empty')) return false
    if (value.type === 'image') return optionalEnum(value, 'aspect', ['video', 'dashboard'])
    return value.trusted_origins === undefined || (
      Array.isArray(value.trusted_origins)
      && value.trusted_origins.every(origin => {
        if (typeof origin !== 'string') return false
        try {
          const url = new URL(origin)
          return ['http:', 'https:'].includes(url.protocol)
            && !url.username && !url.password
            && (url.pathname === '/' || url.pathname === '')
            && !url.search && !url.hash
            && origin.replace(/\/$/, '') === url.origin
        } catch {
          return false
        }
      })
    )
  }
  if (!['status', 'metrics', 'fields', 'actions'].includes(String(value.type))) return false
  if (!Array.isArray(value.items) || value.items.length === 0) return false
  if (value.type === 'fields') return value.items.every(isField)
  if (value.type === 'actions') return value.items.every(isAction)
  return value.items.every(item => {
    if (!isRecord(item) || !isSource(item) || !hasText(item, 'label')) return false
    if (value.type === 'status') {
      return optionalEnum(item, 'tone', ['neutral', 'success', 'warning', 'danger'])
        && optionalText(item, 'true_label') && optionalText(item, 'false_label')
    }
    return optionalText(item, 'suffix') && optionalEnum(item, 'format', ['number', 'duration', 'text'])
  })
}

export function isWorkflowOperatorView(value: unknown): value is WorkflowOperatorView {
  if (!isRecord(value) || value.schema_version !== 1 || !hasText(value, 'title')) return false
  if (!['id', 'description', 'accent'].every(key => optionalText(value, key))) return false
  if (!optionalEnum(value, 'icon', ['record', 'camera', 'robot', 'workflow', 'play'])) return false
  if (value.run_target !== undefined && !isRunTarget(value.run_target)) return false
  if (!Array.isArray(value.sections) || value.sections.length === 0) return false
  const sectionIds = new Set<string>()
  const widgetIds = new Set<string>()
  const sectionsValid = value.sections.every(section => {
    if (!isRecord(section) || !hasText(section, 'id') || !optionalText(section, 'title') || !optionalText(section, 'description')) return false
    if (!optionalEnum(section, 'region', ['main', 'parameters']) || !optionalEnum(section, 'layout', ['grid', 'stack'])) return false
    if (!Array.isArray(section.widgets) || section.widgets.length === 0 || !section.widgets.every(isWidget)) return false
    const sectionId = String(section.id)
    if (sectionIds.has(sectionId)) return false
    sectionIds.add(sectionId)
    for (const widget of section.widgets) {
      if (widgetIds.has(widget.id)) return false
      widgetIds.add(widget.id)
    }
    return true
  })
  if (!sectionsValid || value.settings === undefined) return sectionsValid
  if (!isRecord(value.settings) || !Array.isArray(value.settings.groups)) return false
  if (!optionalText(value.settings, 'title') || !optionalText(value.settings, 'description') || value.settings.groups.length === 0) return false
  const groupIds = new Set<string>()
  return value.settings.groups.every(group => {
    if (!isRecord(group) || !hasText(group, 'id') || !hasText(group, 'title') || !optionalText(group, 'description')) return false
    if (!Array.isArray(group.items) || group.items.length === 0 || !group.items.every(isField)) return false
    const groupId = String(group.id)
    if (groupIds.has(groupId)) return false
    groupIds.add(groupId)
    return true
  })
}

function isPrivateIpv4(hostname: string): boolean {
  const octets = hostname.split('.').map(Number)
  if (octets.length !== 4 || octets.some(value => !Number.isInteger(value) || value < 0 || value > 255)) return false
  return octets[0] === 10
    || octets[0] === 127
    || (octets[0] === 192 && octets[1] === 168)
    || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
    || (octets[0] === 169 && octets[1] === 254)
}

export function normalizeViewerUrl(value: unknown, trustedOrigins: string[] = []): string {
  const candidates: unknown[] = [value]
  if (isRecord(value)) candidates.push(value.viewer_url, value.url)
  for (const candidate of candidates) {
    if (typeof candidate !== 'string') continue
    const trimmed = candidate.trim()
    if (!trimmed || trimmed.length > 2048 || /^\/\//.test(trimmed)) continue
    if (/^\/(?!\/)/.test(trimmed)) return trimmed
    try {
      const url = new URL(trimmed)
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) continue
      const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, '')
      const trusted = trustedOrigins.some(origin => {
        try { return new URL(origin).origin === url.origin } catch { return false }
      })
      if (hostname === 'localhost' || hostname === '::1' || hostname.endsWith('.local') || isPrivateIpv4(hostname) || trusted) {
        return url.toString()
      }
    } catch {
      continue
    }
  }
  return ''
}

export function viewerSandbox(url: string, baseOrigin: string = window.location.origin): string {
  const capabilities = ['allow-forms', 'allow-pointer-lock', 'allow-scripts']
  try {
    if (new URL(url, baseOrigin).origin !== new URL(baseOrigin).origin) {
      capabilities.push('allow-same-origin')
    }
  } catch {
    // Invalid URLs never reach the iframe; retain the strict same-origin set.
  }
  return capabilities.join(' ')
}
