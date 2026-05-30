import type { BnNodeDef, BnNodeMeta } from './types'

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
  saved_at: string
  node_count: number
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

export interface PythonImportResult {
  workflow: WorkflowSnapshot
  validation: WorkflowValidation
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail ?? res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

export const api = {
  nodeTypes: ()                              => req<string[]>('GET', '/node-types'),
  nodeDefs:  ()                              => req<Record<string, BnNodeDef>>('GET', '/node-defs'),
  getGraph:  ()                              => req<{ nodes: any[]; edges: any[] }>('GET', '/graph'),
  setGraph:  (nodes: any[], edges: any[])    => req<{ nodes: any[]; edges: any[] }>('POST', '/graph', { nodes, edges }),
  addNode:   (type_name: string, pos: [number,number], params = {}) =>
    req<BnNodeMeta>('POST', '/nodes', { type_name, pos, params }),
  removeNode: (id: string)                  => req('DELETE', `/nodes/${id}`),
  updateParam:(id: string, key: string, value: unknown) =>
    req('PATCH', `/nodes/${id}/params`, { key, value }),
  updatePorts:(id: string, patch: Partial<Pick<BnNodeMeta, 'inputs' | 'outputs' | 'input_types' | 'output_types' | 'input_defaults' | 'multi_input_ports'>>) =>
    req<BnNodeMeta>('PATCH', `/nodes/${id}/ports`, patch),
  updatePos:  (id: string, pos: [number,number]) =>
    req('PATCH', `/nodes/${id}/pos`, pos),
  connect:    (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('POST', '/edges', { from_id, from_port, to_id, to_port }),
  disconnect: (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('DELETE', `/edges?from_id=${from_id}&from_port=${from_port}&to_id=${to_id}&to_port=${to_port}`),
  cook:       (node_id: string, port = 'output') =>
    req<{ value: unknown; port: string }>('POST', '/cook', { node_id, port }),
  cookStream: async (node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal) => {
    const res = await fetch(`${BASE}/cook-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id, port }),
      signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail ?? res.statusText)
    }
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
        onEvent(JSON.parse(line) as CookEvent)
      }
    }

    buffer += decoder.decode()
    if (buffer.trim()) onEvent(JSON.parse(buffer) as CookEvent)
  },
  cookSubgraphStream: async (subnet_id: string, node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal) => {
    const res = await fetch(`${BASE}/nodes/${subnet_id}/cook-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id, port }),
      signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail ?? res.statusText)
    }
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
        onEvent(JSON.parse(line) as CookEvent)
      }
    }

    buffer += decoder.decode()
    if (buffer.trim()) onEvent(JSON.parse(buffer) as CookEvent)
  },
  reset:      ()                             => req('POST', '/reset'),
  execNode:   (code: string)                 => req<{ ok: boolean; new_types: string[] }>('POST', '/exec-node', { code }),
  saveCustomNode: (filename: string, code: string) =>
    req<{ ok: boolean; path: string; new_types: string[] }>('POST', '/custom-nodes', { filename, code }),
  reloadCustomNodes: () =>
    req<{ ok: boolean; loaded: Array<Record<string, unknown>>; failed: Array<Record<string, unknown>> }>('POST', '/custom-nodes/reload'),
  listCustomNodes: () =>
    req<{ directory: string; files: string[]; registered: BnNodeDef[] }>('GET', '/custom-nodes'),
  getApiKeys:       () => req<Record<string, string>>('GET', '/settings/api-keys'),
  setApiKey:        (provider: string, key: string) => req('POST', '/settings/api-key', { provider, key }),
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
