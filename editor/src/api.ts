import type { BnNodeDef, BnNodeMeta, BnPackage, BnPackageIndex } from './types'
import type { GraphRunTarget } from './graphRun'

const BASE = (import.meta.env.VITE_BLACKNODE_API_BASE ?? '/api').replace(/\/$/, '')

export type CookEvent =
  | { type: 'start'; node_id: string; port: string; node_type?: string }
  | { type: 'success'; node_id: string; port: string; value: unknown; cached?: boolean; outputs?: Record<string, unknown>; node_type?: string }
  | { type: 'error'; node_id: string; port: string; error: string; node_type?: string }
  | { type: 'done'; port: string; value?: unknown; error?: string }
  | { type: 'model_call'; node_id: string; model: string; action?: string; provider?: string; tool_count?: number; node_type?: string }
  | { type: 'tool_call'; node_id: string; name: string; arguments?: Record<string, unknown>; node_type?: string }
  | { type: 'log'; node_id: string; stream: 'stdout' | 'stderr'; text: string; node_type?: string }

export interface TemplateMeta {
  slug: string
  name: string
  description: string
  color: string
  group: string
  group_color: string
  saved_at: string
  node_count: number
}

export interface MissingTemplatePackage {
  name: string
  git_url: string
  node_types: string[]
  source: 'core_index' | 'template'
  installed: boolean
  load_error: string
}

export interface TemplateDependencyError {
  ok: false
  code: 'missing_packages' | 'missing_node_types'
  message: string
  missing_node_types: string[]
  missing_packages: MissingTemplatePackage[]
  unresolved_node_types: string[]
}

export interface DriverStatus {
  name: string
  workflow: string
  label: string        // connected bot identity, e.g. '@BlacknodeAgentBot'
  state: string        // 'listening' | 'processing' | 'starting' | 'stopped'
  processed: number
  live: boolean        // computed server-side from heartbeat freshness
}

export interface DriverInfo {
  name: string
  description: string
  status: string       // 'ready' | 'needs env' | 'needs install'
  extra: string        // e.g. 'blacknode[telegram]'
  packages_installed: boolean
  required_packages: string[]
  env: Record<string, boolean>
  missing_env: string[]
}

export interface DriverInstallResult {
  ok: boolean
  returncode: number
  log: string
  status: DriverInfo
}

export interface ApiKeyStatus {
  configured: boolean
  source: 'saved' | 'environment' | 'missing' | 'local'
  env_var: string
}

export type RunStatus = 'success' | 'error' | 'running'

export interface RunSummary {
  run_id: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  status: RunStatus
  node_id: string
  port: string
  node_type: string
  node_count: number
  model_calls: number
  tool_calls: number
  cached_nodes: number
  has_workflow?: boolean
  error?: string
}

export interface WorkflowSnapshot {
  kind?: string
  schema_version?: number
  name?: string
  saved_at?: string
  entrypoint?: { node_id: string; port: string }
  metadata?: Record<string, unknown>
  node_meta?: Record<string, BnNodeMeta>
  edges?: Array<Record<string, unknown>>
}

export interface RunRecord extends RunSummary {
  events: Array<Record<string, unknown> & { type: string; ts?: string | number }>
  workflow?: WorkflowSnapshot
  value?: unknown
}

export interface EditorAction {
  id: string
  type: string
  created_at: string
  payload?: Record<string, unknown>
}

export interface FrameworkExportTarget {
  id: string
  label: string
  description: string
  extension: string
}

export interface FrameworkExportResult {
  target: string
  label: string
  description: string
  filename: string
  code: string
  warnings: string[]
}

export interface LearnedNodeSummary {
  name: string
  description: string
  category: string
  inputs: string[]
  outputs: string[]
  permissions: { network: boolean }
  created_at: string
}

export interface LearnedNodeSource {
  status: string
  node_type: string
  path: string
  source: string
}

export interface WorkflowValidation {
  ok: boolean
  errors: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
}

export interface RuntimeStatus {
  ok: boolean
  active?: boolean
  streams?: Array<Record<string, unknown>>
  cv2_streams?: Array<Record<string, unknown>>
  reasoning_streams?: Array<Record<string, unknown>>
  managed_runs?: Array<Record<string, unknown>>
  modules?: Record<string, Record<string, unknown>>
  detached_count?: number
  report?: string
  error?: string
}

export interface RuntimeStopResult {
  ok: boolean
  stopped?: {
    streams?: number
    cv2_streams?: number
    reasoning_streams?: number
    managed_runs?: number
    detached?: number
  }
  runtime?: RuntimeStopResult
  report?: string
  error?: string
}

export interface PythonImportResult {
  workflow: WorkflowSnapshot
  validation: WorkflowValidation
}

function bodyPreview(text: string): string {
  return text.replace(/[^\x20-\x7E]+/g, ' ').trim().slice(0, 180)
}

function backendRequestError(path: string, err: unknown): Error {
  const message = err instanceof Error ? err.message : String(err)
  return new Error(
    `Backend disconnected while calling ${path}. Start or restart the Blacknode backend, then try again. ${message}`,
  )
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function templateDependencyError(err: unknown): TemplateDependencyError | null {
  if (!(err instanceof ApiError) || err.status !== 409 || !err.detail || typeof err.detail !== 'object') {
    return null
  }
  const detail = err.detail as Partial<TemplateDependencyError>
  if (detail.code !== 'missing_packages' && detail.code !== 'missing_node_types') return null
  return detail as TemplateDependencyError
}

async function fetchBackend(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BASE}${path}`, init)
  } catch (err) {
    if ((err as { name?: string } | null)?.name === 'AbortError') throw err
    throw backendRequestError(path, err)
  }
}

async function responseJson<T>(res: Response, path: string): Promise<T> {
  const text = await res.text().catch(err => {
    throw backendRequestError(path, err)
  })

  if (!res.ok) {
    let detail: unknown = res.statusText
    if (text.trim()) {
      try {
        const payload = JSON.parse(text)
        detail = payload.detail ?? payload
      } catch {
        detail = bodyPreview(text) || res.statusText
      }
    }
    const message = typeof detail === 'string'
      ? detail
      : (
          detail
          && typeof detail === 'object'
          && typeof (detail as { message?: unknown }).message === 'string'
        )
        ? String((detail as { message: string }).message)
        : JSON.stringify(detail)
    throw new ApiError(message, res.status, detail)
  }

  if (!text.trim()) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(
      `Backend returned invalid JSON for ${path}. This usually means the backend errored or sent binary data instead of an API response. Response preview: ${bodyPreview(text) || '(binary data)'}`,
    )
  }
}

function parseCookEventLine(line: string, label: string): CookEvent {
  try {
    return JSON.parse(line) as CookEvent
  } catch {
    throw new Error(
      `Backend stream returned invalid JSON while cooking ${label}. The backend may have errored or disconnected. Response preview: ${bodyPreview(line) || '(binary data)'}`,
    )
  }
}

async function req<T>(method: string, path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null
  const timeout = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null
  try {
    const res = await fetchBackend(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller?.signal,
    })
    return responseJson<T>(res, path)
  } finally {
    if (timeout !== null) window.clearTimeout(timeout)
  }
}

async function streamCook(
  path: string,
  body: unknown,
  label: string,
  onEvent: (event: CookEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetchBackend(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) await responseJson<never>(res, path)
  if (!res.body) return

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      onEvent(parseCookEventLine(line, label))
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) onEvent(parseCookEventLine(buffer, label))
}

export const api = {
  nodeTypes: ()                              => req<string[]>('GET', '/node-types'),
  nodeDefs:  ()                              => req<Record<string, BnNodeDef>>('GET', '/node-defs'),
  packages:  ()                              => req<{ packages: BnPackage[] }>('GET', '/packages'),
  packageIndex: ()                           => req<BnPackageIndex>('GET', '/packages/index'),
  reloadPackages: ()                         => req<{ ok: boolean }>('POST', '/packages/reload'),
  installPackage: (url: string)              => req<{ ok: boolean; package: BnPackage | null; error: string; log: string[] }>('POST', '/packages/install', { url }),
  setupPackage: (name: string)               => req<{ ok: boolean; package: BnPackage | null; log: string[] }>('POST', `/packages/${encodeURIComponent(name)}/setup`),
  setPackageComponent: (name: string, component: string, enabled: boolean) =>
    req<{ ok: boolean; package: BnPackage }>(
      'POST',
      `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/${enabled ? 'enable' : 'disable'}`,
    ),
  deletePackage: (name: string)              => req<{ ok: boolean }>('DELETE', `/packages/${encodeURIComponent(name)}`),
  getGraph:  ()                              => req<{ nodes: any[]; edges: any[] }>('GET', '/graph'),
  setGraph:  (nodes: any[], edges: any[])    => req<{ nodes: any[]; edges: any[] }>('POST', '/graph', { nodes, edges }),
  addNode:   (type_name: string, pos: [number,number], params = {}) =>
    req<BnNodeMeta>('POST', '/nodes', { type_name, pos, params }),
  removeNode: (id: string)                  => req('DELETE', `/nodes/${id}`),
  updateParam:(id: string, key: string, value: unknown) =>
    req('PATCH', `/nodes/${id}/params`, { key, value }),
  controlNode:(id: string, action: string) =>
    req<{ ok: boolean; node_id: string; outputs: Record<string, unknown> }>('POST', `/nodes/${id}/control`, { action }),
  pickDirectory:(initialPath = '') =>
    req<{ selected: string; cancelled: boolean }>('POST', '/filesystem/pick-directory', { initial_path: initialPath }),
  datasetFrame:(token: string, index: number) =>
    req<Record<string, unknown>>('GET', `/dataset/frame/${encodeURIComponent(token)}?index=${Math.max(0, Math.floor(index))}`),
  trimDatasetEpisode:(token: string, frameIndex: number, side: 'before' | 'after') =>
    req<Record<string, unknown>>('POST', '/dataset/trim', { token, frame_index: Math.max(0, Math.floor(frameIndex)), side }, 120000),
  publishDatasetReplayFrame:(token: string, frameIndex: number, event: 'play' | 'seek') =>
    req<Record<string, unknown>>('POST', '/dataset/replay-event', {
      token, frame_index: Math.max(0, Math.floor(frameIndex)), event,
    }),
  updatePorts:(id: string, patch: Partial<Pick<BnNodeMeta, 'inputs' | 'outputs' | 'input_types' | 'output_types' | 'input_defaults' | 'multi_input_ports'>>) =>
    req<BnNodeMeta>('PATCH', `/nodes/${id}/ports`, patch),
  updatePortVisibility:(id: string, patch: Pick<BnNodeMeta, 'promoted_inputs' | 'promoted_outputs'>) =>
    req<BnNodeMeta>('PATCH', `/nodes/${id}/presentation`, patch),
  updatePos:  (id: string, pos: [number,number]) =>
    req('PATCH', `/nodes/${id}/pos`, pos),
  connect:    (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('POST', '/edges', { from_id, from_port, to_id, to_port }),
  disconnect: (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('DELETE', `/edges?from_id=${from_id}&from_port=${from_port}&to_id=${to_id}&to_port=${to_port}`),
  cook:       (node_id: string, port = 'output') =>
    req<{ value: unknown; port: string }>('POST', '/cook', { node_id, port }),
  stopCook:   () => req<RuntimeStopResult>('POST', '/cook/stop'),
  runtimeStatus: () => req<RuntimeStatus>('GET', '/runtime/status'),
  ollamaModels: (endpointUrl: string) =>
    req<{ ok: boolean; models: string[]; error?: string }>('GET', `/ollama/models?endpoint_url=${encodeURIComponent(endpointUrl)}`),
  stopRuntime: () => req<RuntimeStopResult>('POST', '/runtime/stop'),
  cookStream: (node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-stream', { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookGraphStream: (targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-graph-stream', { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} terminal nodes`, onEvent, signal),
  cookSubgraphStream: (subnet_id: string, node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-stream`, { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookSubgraphGraphStream: (subnet_id: string, targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-graph-stream`, { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} subnet terminal nodes`, onEvent, signal),
  reset:      ()                             => req('POST', '/reset'),
  execNode:   (code: string)                 => req<{ ok: boolean; new_types: string[] }>('POST', '/exec-node', { code }),
  saveCustomNode: (filename: string, code: string) =>
    req<{ ok: boolean; path: string; new_types: string[] }>('POST', '/custom-nodes', { filename, code }),
  reloadCustomNodes: () =>
    req<{ ok: boolean; loaded: Array<Record<string, unknown>>; failed: Array<Record<string, unknown>> }>('POST', '/custom-nodes/reload'),
  listCustomNodes: () =>
    req<{ directory: string; files: string[]; registered: BnNodeDef[] }>('GET', '/custom-nodes'),
  getDriverStatus:  () => req<Record<string, DriverStatus>>('GET', '/drivers/status', undefined, 3000),
  listDrivers:      () => req<DriverInfo[]>('GET', '/drivers'),
  installDriver:    (name: string) => req<DriverInstallResult>('POST', `/drivers/${name}/install`),
  startDriver:      (name: string) => req<{ ok: boolean; pid?: number }>('POST', `/drivers/${name}/start`),
  stopDriver:       (name: string) => req<{ ok: boolean }>('POST', `/drivers/${name}/stop`, undefined, 8000),
  getDriverLogs:    (name: string) => req<{ running: boolean; lines: string[] }>('GET', `/drivers/${name}/logs`),
  getApiKeys:       () => req<Record<string, string>>('GET', '/settings/api-keys'),
  getApiKeyStatus:  () => req<Record<string, ApiKeyStatus>>('GET', '/settings/api-key-status'),
  setApiKey:        (provider: string, key: string) =>
    req<{ ok: boolean; restarted?: string | null; credential?: ApiKeyStatus }>('POST', '/settings/api-key', { provider, key }),
  getOnboarding:    () => req<{ package_welcome_seen: boolean }>('GET', '/settings/onboarding'),
  setOnboarding:    (packageWelcomeSeen: boolean) =>
    req<{ ok: boolean; package_welcome_seen: boolean }>('POST', '/settings/onboarding', { package_welcome_seen: packageWelcomeSeen }),
  getCustomModels:  () => req<string[]>('GET', '/settings/custom-models'),
  addCustomModel:   (value: string) => req('POST', '/settings/custom-models', { value }),
  removeCustomModel:(value: string) => req('DELETE', `/settings/custom-models?value=${encodeURIComponent(value)}`),

  listWorkflows: () =>
    req<{ slug: string; name: string; saved_at: string }[]>('GET', '/workflows'),
  saveWorkflow: (name: string, previousSlug?: string | null) =>
    req<{ ok: boolean; slug: string }>('POST', '/workflows', { name, previous_slug: previousSlug ?? null }),
  loadWorkflow: (slug: string) =>
    req<{ nodes: any[]; edges: any[] }>('POST', `/workflows/${encodeURIComponent(slug)}/load`),
  insertWorkflow: (slug: string) =>
    req<{ nodes: any[]; edges: any[] }>('POST', `/workflows/${encodeURIComponent(slug)}/insert`),
  renameWorkflow: (slug: string, name: string) =>
    req<{ slug: string; name: string; saved_at: string }>('PATCH', `/workflows/${encodeURIComponent(slug)}`, { name }),
  duplicateWorkflow: (slug: string) =>
    req<{ slug: string; name: string; saved_at: string }>('POST', `/workflows/${encodeURIComponent(slug)}/duplicate`),
  deleteWorkflow: (slug: string) =>
    req('DELETE', `/workflows/${encodeURIComponent(slug)}`),

  listTemplates: () =>
    req<TemplateMeta[]>('GET', '/templates'),
  loadTemplate: (slug: string) =>
    req<{ nodes: any[]; edges: any[] }>('POST', `/templates/${encodeURIComponent(slug)}/load`),

  listFrameworkExportTargets: () =>
    req<{ targets: FrameworkExportTarget[] }>('GET', '/export/frameworks'),
  exportFramework: (target: string, workflow?: WorkflowSnapshot) =>
    req<FrameworkExportResult>('POST', '/export/framework', { target, workflow }),
  importPython: (code: string, name = 'Imported Python Workflow') =>
    req<PythonImportResult>('POST', '/import/python', { code, name }),

  mcpStatus:  () =>
    req<{ mcp_installed: boolean; blacknode_cli: string | null; install_command: string; launch_command: string }>('GET', '/mcp/status'),
  consumeEditorActions: () =>
    req<{ actions: EditorAction[] }>('GET', '/editor/actions'),

  listLearnedNodes: () =>
    req<{ nodes: LearnedNodeSummary[]; count: number }>('GET', '/learned-nodes'),
  getLearnedNodeSource: (name: string) =>
    req<LearnedNodeSource>('GET', `/learned-nodes/${encodeURIComponent(name)}/source`),
  promoteLearnedNode: (name: string) =>
    req<{ status: string; node_type: string; category: string; path: string }>('POST', `/learned-nodes/${encodeURIComponent(name)}/promote`),
  deleteLearnedNode: (name: string) =>
    req<{ status: string; node_type: string }>('DELETE', `/learned-nodes/${encodeURIComponent(name)}`),
  learnedNodeEventsUrl: () => `${BASE}/learned-nodes/events`,

  listRuns:   (limit = 50) =>
    req<{ runs: RunSummary[] }>('GET', `/runs?limit=${limit}`),
  getRun:     (runId: string) =>
    req<RunRecord>('GET', `/runs/${encodeURIComponent(runId)}`),
  deleteRun:  (runId: string) =>
    req<{ ok: boolean; run_id: string }>('DELETE', `/runs/${encodeURIComponent(runId)}`),
  clearRuns:  () =>
    req<{ ok: boolean; removed: number }>('DELETE', '/runs'),

  getSubgraph: (nodeId: string) =>
    req<{ node_meta: Record<string, any>; edges: any[] }>('GET', `/nodes/${nodeId}/subgraph`),
  updateSubgraph: (nodeId: string, node_meta: Record<string, any>, edges: any[]) =>
    req<any>('PATCH', `/nodes/${nodeId}/subgraph`, { node_meta, edges }),
  collapseToSubnet: (nodeIds: string[], label: string) =>
    req<{ subnet: any; removed_node_ids: string[] }>('POST', '/subnets', { node_ids: nodeIds, label }),
}
