export interface FlowNodeLike {
  id: string
  position: { x: number; y: number }
}

export interface FlowEdgeLike {
  source?: string
  target?: string
}

export interface TemplateNodeLike {
  ref: string
  pos: [number, number]
}

export interface TemplateEdgeLike {
  from: string
  to: string
}

const X0 = 80
const Y0 = 90
const X_STEP = 280
const Y_STEP = 170

function edgeSource(edge: FlowEdgeLike | TemplateEdgeLike): string | undefined {
  return (edge as FlowEdgeLike).source ?? (edge as TemplateEdgeLike).from
}

function edgeTarget(edge: FlowEdgeLike | TemplateEdgeLike): string | undefined {
  return (edge as FlowEdgeLike).target ?? (edge as TemplateEdgeLike).to
}

function layoutPositions(
  ids: string[],
  initialY: Map<string, number>,
  edges: Array<FlowEdgeLike | TemplateEdgeLike>,
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
  const maxLayerSize = Math.max(1, ...[...layers.values()].map(layerIds => layerIds.length))
  for (const [l, layerIds] of layers) {
    const offset = ((maxLayerSize - layerIds.length) * Y_STEP) / 2
    layerIds.forEach((id, i) => {
      positions.set(id, { x: X0 + l * X_STEP, y: Y0 + offset + i * Y_STEP })
    })
  }
  return positions
}

export function organizeFlowNodes<T extends FlowNodeLike>(nodes: T[], edges: FlowEdgeLike[]): T[] {
  const initialY = new Map(nodes.map(node => [node.id, node.position.y]))
  const positions = layoutPositions(nodes.map(node => node.id), initialY, edges)
  return nodes.map(node => ({ ...node, position: positions.get(node.id) ?? node.position }))
}

export function organizeTemplateNodes<T extends TemplateNodeLike>(nodes: T[], edges: TemplateEdgeLike[]): T[] {
  const initialY = new Map(nodes.map(node => [node.ref, node.pos[1]]))
  const positions = layoutPositions(nodes.map(node => node.ref), initialY, edges)
  return nodes.map(node => {
    const pos = positions.get(node.ref)
    return pos ? { ...node, pos: [pos.x, pos.y] } : node
  })
}
