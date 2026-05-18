import { create } from 'zustand'
import {
  Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, Connection,
} from 'reactflow'
import { api } from './api'
import { BnNodeMeta } from './types'
import { VALUE_NODE_TYPES } from './categories'
import { portsCompatible, portColor } from './portColors'

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
  apiKeys: Record<string, string>
  customModels: string[]

  loadNodeTypes: () => Promise<void>
  loadGraph: () => Promise<void>
  loadApiKeys: () => Promise<void>
  setApiKey: (provider: string, key: string) => Promise<void>
  loadCustomModels: () => Promise<void>
  addCustomModel: (value: string) => Promise<void>
  removeCustomModel: (value: string) => Promise<void>
  checkServer: () => Promise<void>

  addNode: (typeName: string, pos: { x: number; y: number }) => Promise<void>
  removeNode: (id: string) => Promise<void>
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (conn: Connection) => Promise<void>
  disconnectEdge: (edgeId: string) => Promise<void>
  reconnectEdge: (oldEdge: Edge, newConn: Connection) => Promise<void>
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
  apiKeys: {},
  customModels: [],

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

  loadApiKeys: async () => {
    try {
      const keys = await api.getApiKeys()
      set({ apiKeys: keys })
    } catch {}
  },

  setApiKey: async (provider, key) => {
    await api.setApiKey(provider, key)
    set(s => ({ apiKeys: { ...s.apiKeys, [provider]: key } }))
  },

  loadCustomModels: async () => {
    try {
      const models = await api.getCustomModels()
      set({ customModels: models })
    } catch {}
  },

  addCustomModel: async (value) => {
    await api.addCustomModel(value)
    set(s => ({
      customModels: s.customModels.includes(value) ? s.customModels : [...s.customModels, value],
    }))
  },

  removeCustomModel: async (value) => {
    await api.removeCustomModel(value)
    set(s => ({ customModels: s.customModels.filter(m => m !== value) }))
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
    const edges: Edge[] = bnEdges.map((e: any, i: number) => {
      const fromType = bnNodes.find((n: BnNodeMeta) => n.id === e.from)?.output_types?.[e.from_port] ?? 'Any'
      return {
        id: `e${i}`,
        source: e.from,
        sourceHandle: e.from_port,
        target: e.to,
        targetHandle: e.to_port,
        style: { stroke: portColor(fromType), strokeWidth: 1.5 },
      }
    })
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
    set(s => ({ edges: addEdge({
      ...conn,
      id: `e${Date.now()}`,
      style: { stroke: portColor(fromType), strokeWidth: 1.5 },
    }, s.edges) }))
  },

  disconnectEdge: async (edgeId) => {
    const edge = get().edges.find(e => e.id === edgeId)
    if (!edge?.source || !edge.target || !edge.sourceHandle || !edge.targetHandle) return
    await api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
    set(s => ({ edges: s.edges.filter(e => e.id !== edgeId) }))
  },

  reconnectEdge: async (oldEdge, newConn) => {
    if (oldEdge.sourceHandle && oldEdge.targetHandle)
      await api.disconnect(oldEdge.source, oldEdge.sourceHandle, oldEdge.target, oldEdge.targetHandle)
    if (!newConn.source || !newConn.target || !newConn.sourceHandle || !newConn.targetHandle) return
    const { nodes } = get()
    const srcNode = nodes.find(n => n.id === newConn.source)
    const tgtNode = nodes.find(n => n.id === newConn.target)
    const fromType = srcNode?.data?.output_types?.[newConn.sourceHandle] ?? 'Any'
    const toType   = tgtNode?.data?.input_types?.[newConn.targetHandle]  ?? 'Any'
    if (!portsCompatible(fromType, toType)) return
    await api.connect(newConn.source, newConn.sourceHandle, newConn.target, newConn.targetHandle)
    set(s => ({
      edges: s.edges.map(e => e.id !== oldEdge.id ? e : {
        ...e,
        source: newConn.source!,
        sourceHandle: newConn.sourceHandle,
        target: newConn.target!,
        targetHandle: newConn.targetHandle,
        style: { stroke: portColor(fromType), strokeWidth: 1.5 },
      }),
    }))
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
