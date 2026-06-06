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
