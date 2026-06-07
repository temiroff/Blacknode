import type { Edge, Node } from 'reactflow'
import type { BnNodeMeta } from './types'

export interface GraphRunTarget {
  id: string
  port: string
}

function runnablePort(node: Node<BnNodeMeta>): string | null {
  if (node.data.type === 'Output') return 'value'

  if (node.data.type === 'SubnetOutput') {
    return node.data.inputs[0] ?? null
  }

  return node.data.outputs[0] ?? null
}

export function inferGraphRunTargets(
  nodes: Node<BnNodeMeta>[],
  edges: Edge[],
): GraphRunTarget[] {
  const nodeIds = new Set(nodes.map(node => node.id))
  const nodesWithOutgoingEdges = new Set(
    edges
      .filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map(edge => edge.source),
  )

  return nodes
    .filter(node => !nodesWithOutgoingEdges.has(node.id))
    .map(node => ({ node, port: runnablePort(node) }))
    .filter((item): item is { node: Node<BnNodeMeta>; port: string } => Boolean(item.port))
    .sort((a, b) => {
      const x = (a.node.position?.x ?? 0) - (b.node.position?.x ?? 0)
      return x !== 0 ? x : (a.node.position?.y ?? 0) - (b.node.position?.y ?? 0)
    })
    .map(({ node, port }) => ({ id: node.id, port }))
}
