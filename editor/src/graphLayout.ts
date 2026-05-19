export interface FlowNodeLike {
  id: string
  position: { x: number; y: number }
  width?: number | null
  height?: number | null
  measured?: { width?: number | null; height?: number | null }
  style?: {
    width?: number | string
    height?: number | string
    minWidth?: number | string
    minHeight?: number | string
  }
  data?: {
    type?: string
    inputs?: string[]
    outputs?: string[]
  }
}

export interface FlowEdgeLike {
  source?: string
  target?: string
}

export interface TemplateNodeLike {
  ref: string
  type?: string
  inputs?: string[]
  outputs?: string[]
  pos: [number, number]
}

export interface TemplateEdgeLike {
  from: string
  to: string
}

const X0 = 80
const Y0 = 90
const MIN_X_STEP = 280
const X_GAP = 90
const Y_GAP = 52
const DEFAULT_W = 180
const DEFAULT_H = 92

interface NodeSize {
  width: number
  height: number
}

function edgeSource(edge: FlowEdgeLike | TemplateEdgeLike): string | undefined {
  return (edge as FlowEdgeLike).source ?? (edge as TemplateEdgeLike).from
}

function edgeTarget(edge: FlowEdgeLike | TemplateEdgeLike): string | undefined {
  return (edge as FlowEdgeLike).target ?? (edge as TemplateEdgeLike).to
}

function finiteSize(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value
  if (typeof value === 'string') {
    if (value.trim().endsWith('%')) return null
    const parsed = Number.parseFloat(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
  }
  return null
}

function fallbackSize(type?: string, inputs = 0, outputs = 0): NodeSize {
  const portRows = Math.max(inputs, outputs)
  const dynamicHeight = DEFAULT_H + Math.max(0, portRows - 2) * 18

  switch (type) {
    case 'Model':
      return { width: 300, height: 280 }
    case 'Text':
      return { width: 220, height: 120 }
    case 'Dict':
      return { width: 260, height: 180 }
    case 'Output':
      return { width: 320, height: 220 }
    case 'PythonFn':
      return { width: 220, height: 150 }
    case 'ToolBox':
      return { width: 180, height: Math.max(90, dynamicHeight) }
    case 'SubnetInput':
    case 'SubnetOutput':
      return { width: 170, height: Math.max(120, dynamicHeight) }
    case 'Subnet':
    case 'SubnetAsTool':
    case 'VisualAgentLoop':
      return { width: 190, height: Math.max(110, dynamicHeight) }
    default:
      return { width: DEFAULT_W, height: dynamicHeight }
  }
}

function nodeSizeFromFlow(node: FlowNodeLike): NodeSize {
  const fallback = fallbackSize(node.data?.type, node.data?.inputs?.length ?? 0, node.data?.outputs?.length ?? 0)
  return {
    width:
      finiteSize(node.measured?.width)
      ?? finiteSize(node.width)
      ?? finiteSize(node.style?.width)
      ?? finiteSize(node.style?.minWidth)
      ?? fallback.width,
    height:
      finiteSize(node.measured?.height)
      ?? finiteSize(node.height)
      ?? finiteSize(node.style?.height)
      ?? finiteSize(node.style?.minHeight)
      ?? fallback.height,
  }
}

function nodeSizeFromTemplate(node: TemplateNodeLike): NodeSize {
  return fallbackSize(node.type, node.inputs?.length ?? 0, node.outputs?.length ?? 0)
}

function layoutPositions(
  ids: string[],
  initialY: Map<string, number>,
  edges: Array<FlowEdgeLike | TemplateEdgeLike>,
  sizes: Map<string, NodeSize>,
): Map<string, { x: number; y: number }> {
  const idSet = new Set(ids)
  const incoming = new Map<string, string[]>()
  const outgoing = new Map<string, string[]>()
  const indegree = new Map<string, number>()
  const layer = new Map<string, number>()

  ids.forEach(id => {
    incoming.set(id, [])
    outgoing.set(id, [])
    indegree.set(id, 0)
    layer.set(id, 0)
  })

  edges.forEach(edge => {
    const source = edgeSource(edge)
    const target = edgeTarget(edge)
    if (!source || !target || !idSet.has(source) || !idSet.has(target)) return
    outgoing.get(source)!.push(target)
    incoming.get(target)!.push(source)
    indegree.set(target, (indegree.get(target) ?? 0) + 1)
  })

  const queue = ids
    .filter(id => (indegree.get(id) ?? 0) === 0)
    .sort((a, b) => (initialY.get(a) ?? 0) - (initialY.get(b) ?? 0))
  const visited = new Set<string>()

  while (queue.length) {
    const id = queue.shift()!
    visited.add(id)
    for (const next of outgoing.get(id) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, (layer.get(id) ?? 0) + 1))
      indegree.set(next, (indegree.get(next) ?? 0) - 1)
      if ((indegree.get(next) ?? 0) === 0) queue.push(next)
    }
    queue.sort((a, b) => (layer.get(a) ?? 0) - (layer.get(b) ?? 0) || (initialY.get(a) ?? 0) - (initialY.get(b) ?? 0))
  }

  ids.forEach(id => {
    if (!visited.has(id)) {
      const upstreamLayers = (incoming.get(id) ?? []).map(src => layer.get(src) ?? 0)
      layer.set(id, upstreamLayers.length ? Math.max(...upstreamLayers) + 1 : 0)
    }
  })

  const layers = new Map<number, string[]>()
  ids.forEach(id => {
    const l = layer.get(id) ?? 0
    layers.set(l, [...(layers.get(l) ?? []), id])
  })

  let order = new Map<string, number>()
  for (const [l, layerIds] of layers) {
    layerIds.sort((a, b) => (initialY.get(a) ?? 0) - (initialY.get(b) ?? 0))
    layerIds.forEach((id, i) => order.set(id, i))
    layers.set(l, layerIds)
  }

  for (let pass = 0; pass < 4; pass++) {
    const ascending = [...layers.keys()].sort((a, b) => a - b)
    for (const l of ascending) {
      const layerIds = layers.get(l) ?? []
      layerIds.sort((a, b) => {
        const aSources = incoming.get(a) ?? []
        const bSources = incoming.get(b) ?? []
        const aAvg = aSources.length ? aSources.reduce((sum, id) => sum + (order.get(id) ?? 0), 0) / aSources.length : (initialY.get(a) ?? 0)
        const bAvg = bSources.length ? bSources.reduce((sum, id) => sum + (order.get(id) ?? 0), 0) / bSources.length : (initialY.get(b) ?? 0)
        return aAvg - bAvg
      })
      layerIds.forEach((id, i) => order.set(id, i))
    }

    const descending = [...layers.keys()].sort((a, b) => b - a)
    for (const l of descending) {
      const layerIds = layers.get(l) ?? []
      layerIds.sort((a, b) => {
        const aTargets = outgoing.get(a) ?? []
        const bTargets = outgoing.get(b) ?? []
        const aAvg = aTargets.length ? aTargets.reduce((sum, id) => sum + (order.get(id) ?? 0), 0) / aTargets.length : (initialY.get(a) ?? 0)
        const bAvg = bTargets.length ? bTargets.reduce((sum, id) => sum + (order.get(id) ?? 0), 0) / bTargets.length : (initialY.get(b) ?? 0)
        return aAvg - bAvg
      })
      layerIds.forEach((id, i) => order.set(id, i))
    }
  }

  const positions = new Map<string, { x: number; y: number }>()
  const sortedLayerKeys = [...layers.keys()].sort((a, b) => a - b)
  const layerWidths = new Map<number, number>()
  const layerHeights = new Map<number, number>()

  for (const l of sortedLayerKeys) {
    const layerIds = layers.get(l) ?? []
    const layerSizes = layerIds.map(id => sizes.get(id) ?? { width: DEFAULT_W, height: DEFAULT_H })
    layerWidths.set(l, Math.max(DEFAULT_W, ...layerSizes.map(size => size.width)))
    layerHeights.set(
      l,
      layerSizes.reduce((sum, size) => sum + size.height, 0) + Math.max(0, layerSizes.length - 1) * Y_GAP,
    )
  }

  const layerX = new Map<number, number>()
  let nextX = X0
  for (const l of sortedLayerKeys) {
    const width = layerWidths.get(l) ?? DEFAULT_W
    layerX.set(l, nextX)
    nextX += Math.max(MIN_X_STEP, width + X_GAP)
  }

  const maxLayerHeight = Math.max(DEFAULT_H, ...[...layerHeights.values()])
  for (const l of sortedLayerKeys) {
    const layerIds = layers.get(l) ?? []
    const totalHeight = layerHeights.get(l) ?? DEFAULT_H
    let nextY = Y0 + Math.max(0, (maxLayerHeight - totalHeight) / 2)
    layerIds.forEach(id => {
      const size = sizes.get(id) ?? { width: DEFAULT_W, height: DEFAULT_H }
      positions.set(id, { x: layerX.get(l) ?? X0, y: nextY })
      nextY += size.height + Y_GAP
    })
  }
  return positions
}

export function organizeFlowNodes<T extends FlowNodeLike>(nodes: T[], edges: FlowEdgeLike[]): T[] {
  const initialY = new Map(nodes.map(node => [node.id, node.position.y]))
  const sizes = new Map(nodes.map(node => [node.id, nodeSizeFromFlow(node)]))
  const positions = layoutPositions(nodes.map(node => node.id), initialY, edges, sizes)
  return nodes.map(node => ({ ...node, position: positions.get(node.id) ?? node.position }))
}

export function organizeTemplateNodes<T extends TemplateNodeLike>(nodes: T[], edges: TemplateEdgeLike[]): T[] {
  const initialY = new Map(nodes.map(node => [node.ref, node.pos[1]]))
  const sizes = new Map(nodes.map(node => [node.ref, nodeSizeFromTemplate(node)]))
  const positions = layoutPositions(nodes.map(node => node.ref), initialY, edges, sizes)
  return nodes.map(node => {
    const pos = positions.get(node.ref)
    return pos ? { ...node, pos: [pos.x, pos.y] } : node
  })
}
