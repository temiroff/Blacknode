import { create } from 'zustand'
import {
  Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, Connection,
} from 'reactflow'
import { api } from './api'
import { BnNodeMeta } from './types'
import { VALUE_NODE_TYPES } from './categories'
import { portsCompatible } from './portColors'

const MODEL_NODE_TYPES  = new Set(['Model'])
const OUTPUT_NODE_TYPES = new Set(['Output'])

interface NodeData extends BnNodeMeta {
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
}

interface Store {
  nodes: Node<NodeData>[]
  edges: Edge[]
  nodeTypes: string[]
  selectedId: string | null
  serverOk: boolean

  loadNodeTypes: () => Promise<void>
  loadGraph: () => Promise<void>
  checkServer: () => Promise<void>

  addNode: (typeName: string, pos: { x: number; y: number }) => Promise<void>
  removeNode: (id: string) => Promise<void>
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (conn: Connection) => Promise<void>
  disconnectEdge: (edgeId: string) => Promise<void>
  updateParam: (id: string, key: string, value: unknown) => Promise<void>
  cookNode: (id: string, port?: string) => Promise<void>
  selectNode: (id: string | null) => void
  reset: () => Promise<void>
}

export const useStore = create<Store>((set, get) => ({
  nodes: [],
  edges: [],
  nodeTypes: [],
  selectedId: null,
  serverOk: false,

  checkServer: async () => {
    try {
      await api.nodeTypes()
      set({ serverOk: true })
    } catch {
      set({ serverOk: false })
    }
  },

  loadNodeTypes: async () => {
    const types = await api.nodeTypes()
    set({ nodeTypes: types })
  },

  loadGraph: async () => {
    const { nodes: bnNodes, edges: bnEdges } = await api.getGraph()
    const nodes: Node<NodeData>[] = bnNodes.map((n: BnNodeMeta) => ({
      id: n.id,
      type: OUTPUT_NODE_TYPES.has(n.type) ? 'outputnode' : MODEL_NODE_TYPES.has(n.type) ? 'modelnode' : VALUE_NODE_TYPES.has(n.type) ? 'valuenode' : 'blacknode',
      position: { x: n.pos[0], y: n.pos[1] },
      data: { ...n },
      ...(n.type === 'Text'   ? { style: { width: 220, height: 120 } } : {}),
      ...(n.type === 'Output' ? { style: { width: 320, height: 200 } } : {}),
    }))
    const edges: Edge[] = bnEdges.map((e: any, i: number) => ({
      id: `e${i}`,
      source: e.from,
      sourceHandle: e.from_port,
      target: e.to,
      targetHandle: e.to_port,
    }))
    set({ nodes, edges })
  },

  addNode: async (typeName, pos) => {
    const meta: BnNodeMeta = await api.addNode(typeName, [pos.x, pos.y]) as BnNodeMeta
    const node: Node<NodeData> = {
      id: meta.id,
      type: OUTPUT_NODE_TYPES.has(typeName) ? 'outputnode' : MODEL_NODE_TYPES.has(typeName) ? 'modelnode' : VALUE_NODE_TYPES.has(typeName) ? 'valuenode' : 'blacknode',
      position: pos,
      data: { ...meta },
      ...(typeName === 'Text'   ? { style: { width: 220, height: 120 } } : {}),
      ...(typeName === 'Output' ? { style: { width: 320, height: 200 } } : {}),
    }
    set(s => ({ nodes: [...s.nodes, node] }))
  },

  removeNode: async (id) => {
    await api.removeNode(id)
    set(s => ({
      nodes: s.nodes.filter(n => n.id !== id),
      edges: s.edges.filter(e => e.source !== id && e.target !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
    }))
  },

  onNodesChange: (changes) => {
    set(s => ({ nodes: applyNodeChanges(changes, s.nodes) }))
    changes.forEach(c => {
      if (c.type === 'position' && c.position) {
        api.updatePos(c.id, [c.position.x, c.position.y]).catch(() => {})
      }
      if (c.type === 'remove') {
        api.removeNode(c.id).catch(() => {})
        set(s => ({
          edges: s.edges.filter(e => e.source !== c.id && e.target !== c.id),
          selectedId: s.selectedId === c.id ? null : s.selectedId,
        }))
      }
    })
  },

  onEdgesChange: (changes) => {
    const { edges } = get()
    changes.forEach(c => {
      if (c.type === 'remove') {
        const edge = edges.find(e => e.id === c.id)
        if (edge?.source && edge.target && edge.sourceHandle && edge.targetHandle) {
          api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle).catch(() => {})
        }
      }
    })
    set(s => ({ edges: applyEdgeChanges(changes, s.edges) }))
  },

  onConnect: async (conn) => {
    if (!conn.source || !conn.target || !conn.sourceHandle || !conn.targetHandle) return
    const { nodes } = get()
    const srcNode = nodes.find(n => n.id === conn.source)
    const tgtNode = nodes.find(n => n.id === conn.target)
    const fromType = srcNode?.data?.output_types?.[conn.sourceHandle!] ?? 'Any'
    const toType   = tgtNode?.data?.input_types?.[conn.targetHandle!]  ?? 'Any'
    if (!portsCompatible(fromType, toType)) return
    await api.connect(conn.source, conn.sourceHandle, conn.target, conn.targetHandle)
    set(s => ({ edges: addEdge({ ...conn, id: `e${Date.now()}` }, s.edges) }))
  },

  disconnectEdge: async (edgeId) => {
    const edge = get().edges.find(e => e.id === edgeId)
    if (!edge?.source || !edge.target || !edge.sourceHandle || !edge.targetHandle) return
    await api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
    set(s => ({ edges: s.edges.filter(e => e.id !== edgeId) }))
  },

  updateParam: async (id, key, value) => {
    await api.updateParam(id, key, value)
    set(s => ({
      nodes: s.nodes.map(n =>
        n.id === id ? { ...n, data: { ...n.data, params: { ...n.data.params, [key]: value } } } : n
      ),
    }))
  },

  cookNode: async (id, port = 'output') => {
    set(s => ({
      nodes: s.nodes.map(n => n.id === id ? { ...n, data: { ...n.data, cooking: true, cookError: undefined } } : n),
    }))
    try {
      const res = await api.cook(id, port)
      set(s => ({
        nodes: s.nodes.map(n =>
          n.id === id ? { ...n, data: { ...n.data, cooking: false, cookResult: res.value } } : n
        ),
      }))
    } catch (e: any) {
      set(s => ({
        nodes: s.nodes.map(n =>
          n.id === id ? { ...n, data: { ...n.data, cooking: false, cookError: e.message } } : n
        ),
      }))
    }
  },

  selectNode: (id) => set({ selectedId: id }),

  reset: async () => {
    await api.reset()
    set({ nodes: [], edges: [], selectedId: null })
  },
}))
