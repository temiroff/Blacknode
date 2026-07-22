import type { Node } from 'reactflow'

const DEFAULT_W = 220
const DEFAULT_H = 140
const GAP = 40
const FIRST_NODE = { x: 200, y: 120 }

interface Box { x: number; y: number; w: number; h: number }

function boxOf(node: Node): Box {
  const styleW = typeof node.style?.width === 'number' ? node.style.width : undefined
  const styleH = typeof node.style?.height === 'number' ? node.style.height : undefined
  return {
    x: node.position.x,
    y: node.position.y,
    w: node.width ?? styleW ?? DEFAULT_W,
    h: node.height ?? styleH ?? DEFAULT_H,
  }
}

const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.w + GAP && a.x + a.w + GAP > b.x &&
  a.y < b.y + b.h + GAP && a.y + a.h + GAP > b.y

// Where a newly created node should land.
//
// Dropping every node on the same fixed coordinate buried them behind whatever
// was already there, and off-screen entirely once the canvas had been panned.
// Instead start beside the node the user is working with — the selected one, or
// the rightmost as a stand-in — and step outwards until nothing is in the way.
export function freeCanvasSpot(nodes: Node[], selectedId?: string | null): { x: number; y: number } {
  if (!nodes.length) return { ...FIRST_NODE }

  const boxes = nodes.map(boxOf)
  const selected = selectedId ? nodes.find(n => n.id === selectedId) : undefined
  const anchor = selected
    ?? nodes.reduce((far, n) => (n.position.x > far.position.x ? n : far), nodes[0])
  const from = boxOf(anchor)

  // Rightwards first so a graph reads left to right, then wrap downwards.
  for (let ring = 0; ring < 60; ring++) {
    const candidate: Box = {
      x: from.x + from.w + GAP,
      y: from.y + ring * (DEFAULT_H + GAP),
      w: DEFAULT_W,
      h: DEFAULT_H,
    }
    if (!boxes.some(b => overlaps(candidate, b))) return { x: candidate.x, y: candidate.y }

    const below: Box = { x: from.x, y: from.y + from.h + GAP + ring * (DEFAULT_H + GAP), w: DEFAULT_W, h: DEFAULT_H }
    if (!boxes.some(b => overlaps(below, b))) return { x: below.x, y: below.y }
  }
  // Everything nearby is taken; fall back to clear space below the graph.
  const lowest = Math.max(...boxes.map(b => b.y + b.h))
  return { x: from.x, y: lowest + GAP }
}
