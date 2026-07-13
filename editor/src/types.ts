export interface SubgraphData {
  node_meta: Record<string, BnNodeMeta>
  edges: Array<{ from: string; from_port: string; to: string; to_port: string }>
}

export interface SubnetFrame {
  subnetId: string
  subnetLabel: string
  parentNodes: any[]
  parentEdges: any[]
}

export interface BnNodeMeta {
  id: string
  type: string
  params: Record<string, unknown>
  pos: [number, number]
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  input_defaults: Record<string, unknown>
  multi_input_ports?: string[]
  subgraph?: SubgraphData
}

export interface NodeCookState {
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
  cookPort?: string
  replayRunId?: string
  replayStatus?: 'running' | 'success' | 'error' | 'cached' | 'model' | 'tool' | 'done'
  replayFocused?: boolean
  replayLabel?: string
  replayPort?: string
  replayDurationMs?: number
  replayResult?: unknown
  replayError?: string
  replayStep?: number
  replayTotal?: number
  replayModelCalls?: number
  replayToolCalls?: number
  portResults?: Record<string, unknown>  // per-output-port values from the live run (for port hover)
}

export interface BnNodeDef {
  type: string
  category?: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  input_defaults: Record<string, unknown>
  input_choices?: Record<string, string[]>
  doc?: string
  source?: string
  color?: string    // category color declared by the owning extension package
  package?: string  // extension package name, '' for built-ins
}

export interface BnPackageGitStatus {
  is_git_repo: boolean
  ok: boolean
  error: string
  fetch_error?: string
  remote?: string
  branch?: string
  head?: string
  upstream?: string
  dirty?: boolean
  ahead?: number | null
  behind?: number | null
  update_available?: boolean
  can_fast_forward?: boolean
}

export interface BnPackageIndexPackage {
  name: string
  git_url: string
  node_types: string[]
  description?: string
}

export interface BnPackageIndex {
  schema_version: number
  packages: Record<string, BnPackageIndexPackage>
  nodes: Record<string, { package: string; git_url: string }>
}
export interface BnPackage {
  name: string
  version: string
  description: string
  path: string
  source: string  // 'folder' | 'entry-point'
  requires_blacknode: string
  categories: Record<string, string>
  pip_dependencies: string[]
  import_dependencies: string[]
  docker_images: string[]
  node_types: string[]
  expected_node_types: string[]
  missing_node_types: string[]
  git_status?: BnPackageGitStatus
  templates_dir: string
  ok: boolean
  error: string
  warnings: string[]
}

export interface BnEdge {
  from: string
  from_port: string
  to: string
  to_port: string
}

export interface ConnectionDraft {
  nodeId: string
  handleId: string
  handleType: 'source' | 'target'
  portType: string
}

export interface CookResult {
  value: unknown
  port: string
}
