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
  variadic_input?: { prefix: string; type: string } | null
  promoted_inputs?: string[] | null
  promoted_outputs?: string[] | null
  live_capable?: boolean
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
  component?: string  // package component the node ships in, '' when uncomponentised
  adapter?: string    // component adapter (e.g. 'ros2'), '' for the component's own nodes
  hidden?: boolean  // compatibility node: loadable in saved graphs, omitted from the palette
  live_capable?: boolean // keeps producing runtime output when the graph is in Live mode
  variadic_input?: { prefix: string; type: string } | null
  primary_inputs?: string[] | null
  primary_outputs?: string[] | null
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
  layer?: string
  components?: Record<string, BnPackageComponent>
}

export interface BnPackageComponent {
  name: string
  description: string
  default: boolean
  capabilities: string[]
  node_types?: string[]
  node_paths?: string[]
  template_paths?: string[]
  setup_hooks?: string[]
  pip_dependencies?: string[]
  import_dependencies?: string[]
  docker_images?: string[]
  requirements?: Array<{
    package: string
    component: string
    version: string
  }>
  requirement_errors?: string[]
  enabled?: boolean
  adapters?: Record<string, BnPackageAdapter>
}

export type BnPackageAdapter = Omit<BnPackageComponent, 'adapters'>

export interface BnPackageIndex {
  schema_version: number
  packages: Record<string, BnPackageIndexPackage>
  nodes: Record<string, { package: string; git_url: string }>
}
export interface BnPackage {
  name: string
  version: string
  description: string
  layer: string
  components: Record<string, BnPackageComponent>
  component_mode: boolean
  enabled_components: string[]
  enabled_adapters: string[]
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
  template_dirs: string[]
  setup_hooks: string[]
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
