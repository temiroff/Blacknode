export interface BnNodeMeta {
  id: string
  type: string
  params: Record<string, unknown>
  pos: [number, number]
  inputs: string[]
  outputs: string[]
}

export interface BnEdge {
  from: string
  from_port: string
  to: string
  to_port: string
}

export interface CookResult {
  value: unknown
  port: string
}
