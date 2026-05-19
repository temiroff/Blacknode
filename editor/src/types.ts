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

export interface BnNodeDef {
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  input_defaults: Record<string, unknown>
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
