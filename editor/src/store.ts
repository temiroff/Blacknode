import { create } from 'zustand'
import {
  Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, Connection,
} from 'reactflow'
import { api, type CookEvent } from './api'
import { BnNodeDef, BnNodeMeta, ConnectionDraft, SubnetFrame } from './types'
import { VALUE_NODE_TYPES } from './categories'
import { portsCompatible, portColor } from './portColors'
import { organizeFlowNodes } from './graphLayout'

const MODEL_NODE_TYPES  = new Set(['Model'])
const OUTPUT_NODE_TYPES = new Set(['Output'])

export interface WorkflowTab {
  id: string
  name: string
  slug: string | null  // null = unsaved
  dirty: boolean
  graph: GraphSnapshot | null
}

interface GraphSnapshot {
  nodes: any[]
  edges: any[]
}

interface NodeData extends BnNodeMeta {
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
  cookPort?: string
}

interface Store {
  nodes: Node<NodeData>[]
  edges: Edge[]
  nodeTypes: string[]
  nodeDefs: Record<string, BnNodeDef>
  selectedId: string | null
  serverOk: boolean
  apiKeys: Record<string, string>
  customModels: string[]
  tabs: WorkflowTab[]
  activeTabId: string
  workflowRevision: number

  loadNodeTypes: () => Promise<void>
  loadGraph: () => Promise<void>
  loadApiKeys: () => Promise<void>
  setApiKey: (provider: string, key: string) => Promise<void>
  loadCustomModels: () => Promise<void>
  addCustomModel: (value: string) => Promise<void>
  removeCustomModel: (value: string) => Promise<void>
  checkServer: () => Promise<void>

  newTab: () => Promise<void>
  insertTab: (tabId: string) => Promise<void>
  switchTab: (tabId: string) => Promise<void>
  closeTab: (tabId: string) => Promise<void>
  duplicateTab: (tabId: string) => Promise<void>
  openWorkflowAsTab: (slug: string, name: string) => Promise<void>
  renameTab: (tabId: string, name: string) => void
  saveActiveWorkflow: (name?: string) => Promise<{ name: string; slug: string }>
  insertSavedWorkflow: (slug: string) => Promise<void>
  renameSavedWorkflow: (slug: string, name: string) => Promise<{ name: string; slug: string }>
  duplicateSavedWorkflow: (slug: string) => Promise<{ name: string; slug: string }>
  deleteWorkflow: (slug: string) => Promise<void>
  saveActiveTabSnapshot: () => Promise<GraphSnapshot | null>

  subnetStack: SubnetFrame[]
  diveIntoSubnet: (subnetId: string) => Promise<void>
  exitSubnet: () => Promise<void>
  exitToRoot: () => Promise<void>
  collapseToSubnet: (nodeIds: string[], label: string) => Promise<void>
  organizeNodes: () => Promise<void>
  updateNodePorts: (
    nodeId: string,
    inputs?: string[],
    outputs?: string[],
    inputTypes?: Record<string, string>,
    outputTypes?: Record<string, string>,
    inputDefaults?: Record<string, unknown>,
    multiInputPorts?: string[],
  ) => Promise<void>
  updateSubgraphBoundaryPorts: (
    innerNodeId: string,
    outputs?: string[],
    inputs?: string[],
    outputTypes?: Record<string, string>,
    inputTypes?: Record<string, string>,
  ) => Promise<void>

  addNode: (typeName: string, pos: { x: number; y: number }) => Promise<void>
  addNodeFromConnection: (typeName: string, pos: { x: number; y: number }, draft: ConnectionDraft) => Promise<void>
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

function reactNodeType(typeName: string): string {
  if (typeName === 'Subnet' || typeName === 'SubnetAsTool') return 'subnetnode'
  if (typeName === 'SubnetInput') return 'subnetinput'
  if (typeName === 'SubnetOutput') return 'subnetoutput'
  return OUTPUT_NODE_TYPES.has(typeName) ? 'outputnode' : MODEL_NODE_TYPES.has(typeName) ? 'modelnode' : VALUE_NODE_TYPES.has(typeName) ? 'valuenode' : 'blacknode'
}

function makeReactNode(meta: BnNodeMeta): Node<NodeData> {
  return {
    id: meta.id,
    type: reactNodeType(meta.type),
    position: { x: meta.pos[0], y: meta.pos[1] },
    data: { ...meta },
    ...(meta.type === 'Text'   ? { style: { width: 220, height: 120 } } : {}),
    ...(meta.type === 'Dict'   ? { style: { width: 260, height: 150 } } : {}),
    ...(meta.type === 'Output' ? { style: { width: 320, height: 200 } } : {}),
  }
}

function parseGraph(bnNodes: BnNodeMeta[], bnEdges: any[]): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const nodes: Node<NodeData>[] = bnNodes.map(n => makeReactNode(n))
  const edges: Edge[] = bnEdges.map((e: any, i: number) => {
    const fromType = bnNodes.find(n => n.id === e.from)?.output_types?.[e.from_port] ?? 'Any'
    return {
      id: `e${i}`,
      source: e.from,
      sourceHandle: e.from_port,
      target: e.to,
      targetHandle: e.to_port,
      style: { stroke: portColor(fromType), strokeWidth: 1.5 },
    }
  })
  return { nodes, edges }
}

function parseSubgraph(subgraph: { node_meta: Record<string, BnNodeMeta>; edges: any[] }): { nodes: any[]; edges: any[] } {
  const metaList = Object.values(subgraph.node_meta) as BnNodeMeta[]
  return parseGraph(metaList, subgraph.edges)
}

function firstCompatibleInput(def: BnNodeDef, fromType: string): string | undefined {
  return def.inputs.find(port => portsCompatible(fromType, def.input_types?.[port] ?? 'Any'))
}

function firstCompatibleOutput(def: BnNodeDef, toType: string): string | undefined {
  return def.outputs.find(port => portsCompatible(def.output_types?.[port] ?? 'Any', toType))
}

function defFromMeta(meta: BnNodeMeta): BnNodeDef {
  return {
    type: meta.type,
    inputs: meta.inputs,
    outputs: meta.outputs,
    input_types: meta.input_types,
    output_types: meta.output_types,
    input_defaults: meta.input_defaults ?? {},
  }
}

function nextEdgeId(): string {
  return `e${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function nextToolInputName(inputs: string[]): string {
  let i = 1
  while (inputs.includes(`tool_${i}`)) i++
  return `tool_${i}`
}

function pruneEmptyToolBoxSlots(nodes: Node<NodeData>[], edges: Edge[]): { nodes: Node<NodeData>[]; changedIds: Set<string> } {
  const connectedPorts = new Map<string, Set<string>>()
  edges.forEach(edge => {
    if (!edge.targetHandle?.startsWith('tool_')) return
    if (!connectedPorts.has(edge.target)) connectedPorts.set(edge.target, new Set())
    connectedPorts.get(edge.target)!.add(edge.targetHandle)
  })

  const changedIds = new Set<string>()
  const nextNodes = nodes.map(node => {
    if (node.data.type !== 'ToolBox') return node
    const connected = connectedPorts.get(node.id) ?? new Set<string>()
    const inputs = (node.data.inputs ?? []).filter(port => connected.has(port))
    if (
      inputs.length === (node.data.inputs ?? []).length
      && inputs.every((port, i) => port === node.data.inputs[i])
    ) {
      return node
    }

    changedIds.add(node.id)
    const inputTypes: Record<string, string> = {}
    inputs.forEach(port => { inputTypes[port] = node.data.input_types?.[port] ?? 'Fn' })
    return {
      ...node,
      data: {
        ...node.data,
        inputs,
        input_types: inputTypes,
        input_defaults: {},
      },
    }
  })

  return { nodes: nextNodes, changedIds }
}

function makeTabId(): string {
  return `tab-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function cleanWorkflowName(name: string | undefined | null): string {
  return name?.trim() || 'Untitled'
}

function cloneGraph(graph: GraphSnapshot): GraphSnapshot {
  return JSON.parse(JSON.stringify(graph)) as GraphSnapshot
}

function blankGraph(): GraphSnapshot {
  return { nodes: [], edges: [] }
}

function markActiveTabDirty(s: Store): Pick<Store, 'tabs'> {
  return {
    tabs: s.tabs.map(t => t.id === s.activeTabId ? { ...t, dirty: true } : t),
  }
}

export const useStore = create<Store>((set, get) => ({
  nodes: [],
  edges: [],
  nodeTypes: [],
  nodeDefs: {},
  selectedId: null,
  serverOk: false,
  apiKeys: {},
  customModels: [],
  tabs: [{ id: 'default', name: 'Untitled', slug: null, dirty: false, graph: null }],
  activeTabId: 'default',
  workflowRevision: 0,
  subnetStack: [],

  checkServer: async () => {
    try {
      await api.nodeTypes()
      set({ serverOk: true })
    } catch {
      set({ serverOk: false })
    }
  },

  loadNodeTypes: async () => {
    try {
      const defs = await api.nodeDefs()
      set({ nodeTypes: Object.keys(defs).sort(), nodeDefs: defs })
    } catch {
      const types = await api.nodeTypes()
      set({ nodeTypes: types, nodeDefs: {} })
    }
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
    set({ ...parseGraph(bnNodes, bnEdges), selectedId: null })
  },

  // ── Tab management ────────────────────────────────────────────────────────

  saveActiveTabSnapshot: async () => {
    try {
      const { activeTabId } = get()
      const graph = await api.getGraph()
      set(s => ({
        tabs: s.tabs.map(t => t.id === activeTabId ? { ...t, graph: cloneGraph(graph) } : t),
      }))
      return graph
    } catch {
      return null
    }
  },

  newTab: async () => {
    await get().saveActiveTabSnapshot()
    const id = makeTabId()
    set(s => ({ tabs: [...s.tabs, { id, name: 'Untitled', slug: null, dirty: false, graph: blankGraph() }], activeTabId: id }))
    await api.reset()
    set({ nodes: [], edges: [], selectedId: null })
  },

  insertTab: async (tabId) => {
    await get().saveActiveTabSnapshot()
    const id = makeTabId()
    const { tabs } = get()
    const idx = tabs.findIndex(t => t.id === tabId)
    const insertAt = idx < 0 ? tabs.length : idx + 1
    const nextTabs = [...tabs]
    nextTabs.splice(insertAt, 0, { id, name: 'Untitled', slug: null, dirty: false, graph: blankGraph() })
    set({ tabs: nextTabs, activeTabId: id, selectedId: null })
    await api.reset()
    set({ nodes: [], edges: [] })
  },

  switchTab: async (tabId) => {
    const { tabs, activeTabId } = get()
    if (tabId === activeTabId) return
    await get().saveActiveTabSnapshot()
    const nextTabs = get().tabs
    const tab = tabs.find(t => t.id === tabId)
      ?? nextTabs.find(t => t.id === tabId)
    if (!tab) return
    set({ activeTabId: tabId, selectedId: null })
    if (tab.graph) {
      const graph = cloneGraph(tab.graph)
      await api.setGraph(graph.nodes, graph.edges)
      await get().loadGraph()
    } else if (tab.slug) {
      const graph = await api.loadWorkflow(tab.slug)
      set(s => ({ tabs: s.tabs.map(t => t.id === tabId ? { ...t, graph: cloneGraph(graph), dirty: false } : t) }))
      await get().loadGraph()
    } else {
      await api.reset()
      set({ nodes: [], edges: [], selectedId: null })
    }
  },

  closeTab: async (tabId) => {
    const { tabs, activeTabId } = get()
    if (tabs.length <= 1) return
    const idx = tabs.findIndex(t => t.id === tabId)
    const newTabs = tabs.filter(t => t.id !== tabId)
    if (tabId === activeTabId) {
      const next = newTabs[Math.max(0, idx - 1)]
      set({ tabs: newTabs, activeTabId: next.id, selectedId: null })
      if (next.graph) {
        const graph = cloneGraph(next.graph)
        await api.setGraph(graph.nodes, graph.edges)
        await get().loadGraph()
      } else if (next.slug) {
        const graph = await api.loadWorkflow(next.slug)
        set(s => ({ tabs: s.tabs.map(t => t.id === next.id ? { ...t, graph: cloneGraph(graph), dirty: false } : t) }))
        await get().loadGraph()
      } else {
        await api.reset()
        set({ nodes: [], edges: [], selectedId: null })
      }
    } else {
      set({ tabs: newTabs })
    }
  },

  duplicateTab: async (tabId) => {
    await get().saveActiveTabSnapshot()
    const { tabs } = get()
    const tab = tabs.find(t => t.id === tabId)
    if (!tab) return

    let graph = tab.graph ? cloneGraph(tab.graph) : null
    if (!graph && tab.slug) {
      graph = await api.loadWorkflow(tab.slug)
    }
    if (!graph) graph = blankGraph()

    const id = makeTabId()
    const idx = tabs.findIndex(t => t.id === tabId)
    const nextTabs = [...tabs]
    nextTabs.splice(idx + 1, 0, {
      id,
      name: `${tab.name} copy`,
      slug: null,
      dirty: true,
      graph: cloneGraph(graph),
    })
    set({ tabs: nextTabs, activeTabId: id, selectedId: null })
    await api.setGraph(graph.nodes, graph.edges)
    await get().loadGraph()
  },

  openWorkflowAsTab: async (slug, name) => {
    await get().saveActiveTabSnapshot()
    const { tabs } = get()
    const existing = tabs.find(t => t.slug === slug)
    if (existing) {
      await get().switchTab(existing.id)
      return
    }
    const id = makeTabId()
    const graph = await api.loadWorkflow(slug)
    set(s => ({ tabs: [...s.tabs, { id, name, slug, dirty: false, graph: cloneGraph(graph) }], activeTabId: id, selectedId: null }))
    await get().loadGraph()
  },

  renameTab: (tabId, name) => {
    const nextName = cleanWorkflowName(name)
    set(s => ({
      tabs: s.tabs.map(t => t.id === tabId ? { ...t, name: nextName, dirty: t.dirty || t.name !== nextName } : t),
    }))
  },

  saveActiveWorkflow: async (name) => {
    const { tabs, activeTabId } = get()
    const active = tabs.find(t => t.id === activeTabId)
    const nextName = cleanWorkflowName(name ?? active?.name)
    const res = await api.saveWorkflow(nextName, active?.slug)
    const graph = await api.getGraph()
    set(s => ({
      tabs: s.tabs.map(t =>
        t.id === activeTabId ? { ...t, name: nextName, slug: res.slug, dirty: false, graph: cloneGraph(graph) } : t
      ),
      workflowRevision: s.workflowRevision + 1,
    }))
    return { name: nextName, slug: res.slug }
  },

  insertSavedWorkflow: async (slug) => {
    const graph = await api.insertWorkflow(slug)
    set(s => ({
      ...parseGraph(graph.nodes, graph.edges),
      selectedId: null,
      tabs: s.tabs.map(t =>
        t.id === s.activeTabId ? { ...t, dirty: true, graph: cloneGraph(graph) } : t
      ),
    }))
  },

  renameSavedWorkflow: async (slug, name) => {
    const res = await api.renameWorkflow(slug, cleanWorkflowName(name))
    set(s => ({
      tabs: s.tabs.map(t =>
        t.slug === slug ? { ...t, name: res.name, slug: res.slug } : t
      ),
      workflowRevision: s.workflowRevision + 1,
    }))
    return { name: res.name, slug: res.slug }
  },

  duplicateSavedWorkflow: async (slug) => {
    const res = await api.duplicateWorkflow(slug)
    set(s => ({ workflowRevision: s.workflowRevision + 1 }))
    return { name: res.name, slug: res.slug }
  },

  deleteWorkflow: async (slug) => {
    await api.deleteWorkflow(slug)
    set(s => ({
      tabs: s.tabs.map(t => t.slug === slug ? { ...t, slug: null, dirty: true } : t),
      workflowRevision: s.workflowRevision + 1,
    }))
  },

  // ── Graph actions ─────────────────────────────────────────────────────────

  diveIntoSubnet: async (subnetId) => {
    const { nodes, edges } = get()
    const subnetNode = nodes.find(n => n.id === subnetId)
    if (!subnetNode) return
    const label = String(
      subnetNode.data.type === 'SubnetAsTool'
        ? subnetNode.data.params?.name ?? 'tool'
        : subnetNode.data.params?.label ?? 'Subnet'
    )
    // Always fetch fresh inner graph from server
    const subgraph = await api.getSubgraph(subnetId)
    const { nodes: innerNodes, edges: innerEdges } = parseSubgraph(subgraph as any)
    set(s => ({
      subnetStack: [...s.subnetStack, {
        subnetId,
        subnetLabel: label,
        parentNodes: nodes,
        parentEdges: edges,
      }],
      nodes: innerNodes,
      edges: innerEdges,
      selectedId: null,
    }))
  },

  exitSubnet: async () => {
    const { subnetStack } = get()
    if (subnetStack.length === 0) return
    const newStack = subnetStack.slice(0, -1)
    if (newStack.length === 0) {
      // Back to root — reload from server so subnet node shows fresh ports
      const graphData = await api.getGraph()
      const { nodes, edges } = parseGraph(graphData.nodes, graphData.edges)
      set({ subnetStack: [], nodes, edges, selectedId: null })
    } else {
      // Back to parent subnet — reload its inner graph from server
      const parentFrame = newStack[newStack.length - 1]
      const subgraph = await api.getSubgraph(parentFrame.subnetId)
      const { nodes: innerNodes, edges: innerEdges } = parseSubgraph(subgraph as any)
      set({ subnetStack: newStack, nodes: innerNodes, edges: innerEdges, selectedId: null })
    }
  },

  exitToRoot: async () => {
    const graphData = await api.getGraph()
    const { nodes, edges } = parseGraph(graphData.nodes, graphData.edges)
    set({ subnetStack: [], nodes, edges, selectedId: null })
  },

  collapseToSubnet: async (nodeIds, label) => {
    await api.collapseToSubnet(nodeIds, label)
    const graphData = await api.getGraph()
    const { nodes: newNodes, edges: newEdges } = parseGraph(graphData.nodes, graphData.edges)
    set(s => ({ nodes: newNodes, edges: newEdges, ...markActiveTabDirty(s) }))
  },

  organizeNodes: async () => {
    const { subnetStack, nodes, edges } = get()
    const nextNodes = organizeFlowNodes(nodes, edges)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = edges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
      set(s => ({ nodes: nextNodes, ...markActiveTabDirty(s) }))
      return
    }

    await Promise.all(nextNodes.map(n => api.updatePos(n.id, [n.position.x, n.position.y])))
    set(s => ({ nodes: nextNodes, ...markActiveTabDirty(s) }))
  },

  updateNodePorts: async (nodeId, inputs, outputs, inputTypes, outputTypes, inputDefaults, multiInputPorts) => {
    const { subnetStack, nodes, edges } = get()
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return

    const nextData = {
      ...node.data,
      ...(inputs !== undefined ? { inputs } : {}),
      ...(outputs !== undefined ? { outputs } : {}),
      ...(inputTypes !== undefined ? { input_types: inputTypes } : {}),
      ...(outputTypes !== undefined ? { output_types: outputTypes } : {}),
      ...(inputDefaults !== undefined ? { input_defaults: inputDefaults } : {}),
      ...(multiInputPorts !== undefined ? { multi_input_ports: multiInputPorts } : {}),
    }
    const nextInputSet = inputs !== undefined ? new Set(inputs) : null
    const nextOutputSet = outputs !== undefined ? new Set(outputs) : null
    const nextEdges = edges.filter(e => {
      if (nextInputSet && e.target === nodeId && !nextInputSet.has(e.targetHandle ?? '')) return false
      if (nextOutputSet && e.source === nodeId && !nextOutputSet.has(e.sourceHandle ?? '')) return false
      return true
    })
    const removedEdges = edges.filter(e => !nextEdges.includes(e))
    const nextNodes = nodes.map(n => n.id === nodeId ? { ...n, data: nextData } : n)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = nextEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
      set(s => ({ nodes: nextNodes, edges: nextEdges, ...markActiveTabDirty(s) }))
      return
    }

    const meta = await api.updatePorts(nodeId, {
      ...(inputs !== undefined ? { inputs } : {}),
      ...(outputs !== undefined ? { outputs } : {}),
      ...(inputTypes !== undefined ? { input_types: inputTypes } : {}),
      ...(outputTypes !== undefined ? { output_types: outputTypes } : {}),
      ...(inputDefaults !== undefined ? { input_defaults: inputDefaults } : {}),
      ...(multiInputPorts !== undefined ? { multi_input_ports: multiInputPorts } : {}),
    })
    for (const edge of removedEdges) {
      if (edge.source && edge.sourceHandle && edge.target && edge.targetHandle) {
        await api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
      }
    }
    set(s => ({
      nodes: s.nodes.map(n => n.id === nodeId ? { ...n, data: { ...n.data, ...meta } } : n),
      edges: nextEdges,
      ...markActiveTabDirty(s),
    }))
  },

  updateSubgraphBoundaryPorts: async (innerNodeId, outputs, inputs, outputTypes, inputTypes) => {
    const { subnetStack, nodes, edges } = get()
    if (subnetStack.length === 0) return
    const frame = subnetStack[subnetStack.length - 1]

    const updatedNodes = nodes.map(n => {
      if (n.id !== innerNodeId) return n
      return {
        ...n,
        data: {
          ...n.data,
          ...(outputs    !== undefined ? { outputs }    : {}),
          ...(inputs     !== undefined ? { inputs }     : {}),
          ...(outputTypes !== undefined ? { output_types: outputTypes } : {}),
          ...(inputTypes  !== undefined ? { input_types:  inputTypes  } : {}),
        },
      }
    })

    const innerMeta: Record<string, any> = {}
    updatedNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
    const innerEdges = edges.map(e => ({
      from: e.source, from_port: e.sourceHandle ?? '',
      to: e.target,   to_port:   e.targetHandle ?? '',
    }))

    const freshSubnetMeta = await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)

    // Patch the subnet node in parentNodes so the outer canvas reflects new ports immediately
    const updatedSubnetStack = subnetStack.map((f, i) => {
      if (i !== subnetStack.length - 1) return f
      const updatedParentNodes = (f.parentNodes as any[]).map((pn: any) => {
        if (pn.id !== frame.subnetId) return pn
        return {
          ...pn,
          data: {
            ...pn.data,
            inputs:       freshSubnetMeta.inputs       ?? pn.data.inputs,
            outputs:      freshSubnetMeta.outputs      ?? pn.data.outputs,
            input_types:  freshSubnetMeta.input_types  ?? pn.data.input_types,
            output_types: freshSubnetMeta.output_types ?? pn.data.output_types,
          },
        }
      })
      return { ...f, parentNodes: updatedParentNodes }
    })

    set(s => ({ nodes: updatedNodes, subnetStack: updatedSubnetStack, ...markActiveTabDirty(s) }))
  },

  addNode: async (typeName, pos) => {
    const { subnetStack } = get()
    if (subnetStack.length > 0) {
      // Add node inside current subnet
      const frame = subnetStack[subnetStack.length - 1]
      const meta = await api.addNode(typeName, [pos.x, pos.y])
      // We need to add it to the inner graph in memory and push subgraph update
      const { nodes, edges } = get()
      const newNode = makeReactNode(meta)
      const newNodes = [...nodes, newNode]
      // Build updated subgraph from current inner state
      const innerMeta: Record<string, any> = {}
      newNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = edges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port: e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
      // Also remove the node from the root graph (it was added there by api.addNode)
      await api.removeNode(meta.id)
      set(s => ({ nodes: newNodes, ...markActiveTabDirty(s) }))
      return
    }
    const meta = await api.addNode(typeName, [pos.x, pos.y])
    const node = makeReactNode(meta)
    set(s => ({ nodes: [...s.nodes, node], ...markActiveTabDirty(s) }))
  },

  addNodeFromConnection: async (typeName, pos, draft) => {
    const { nodes } = get()
    const existing = nodes.find(n => n.id === draft.nodeId)
    if (!existing) return

    const meta = await api.addNode(typeName, [pos.x, pos.y])
    const node = makeReactNode(meta)
    const def = defFromMeta(meta)
    let nextConn: Connection | null = null
    let edgeType = draft.portType

    if (draft.handleType === 'source') {
      const fromType = existing.data.output_types?.[draft.handleId] ?? draft.portType
      const toPort = firstCompatibleInput(def, fromType)
      if (!toPort) {
        set(s => ({ nodes: [...s.nodes, node], ...markActiveTabDirty(s) }))
        return
      }
      edgeType = fromType
      nextConn = {
        source: draft.nodeId,
        sourceHandle: draft.handleId,
        target: meta.id,
        targetHandle: toPort,
      }
    } else {
      const toType = existing.data.input_types?.[draft.handleId] ?? draft.portType
      const fromPort = firstCompatibleOutput(def, toType)
      if (!fromPort) {
        set(s => ({ nodes: [...s.nodes, node], ...markActiveTabDirty(s) }))
        return
      }
      edgeType = def.output_types?.[fromPort] ?? 'Any'
      nextConn = {
        source: meta.id,
        sourceHandle: fromPort,
        target: draft.nodeId,
        targetHandle: draft.handleId,
      }
    }

    if (nextConn?.source && nextConn.sourceHandle && nextConn.target && nextConn.targetHandle) {
      await api.connect(nextConn.source, nextConn.sourceHandle, nextConn.target, nextConn.targetHandle)
    }

    set(s => ({
      nodes: [...s.nodes, node],
      edges: nextConn?.source && nextConn.target ? addEdge({
        ...nextConn,
        id: nextEdgeId(),
        style: { stroke: portColor(edgeType), strokeWidth: 1.5 },
      }, s.edges) : s.edges,
      ...markActiveTabDirty(s),
    }))
  },

  removeNode: async (id) => {
    const { subnetStack, nodes, edges } = get()
    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const newNodes = nodes.filter(n => n.id !== id)
      const newEdges = edges.filter(e => e.source !== id && e.target !== id)
      const innerMeta: Record<string, any> = {}
      newNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = newEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
      set(s => ({
        nodes: newNodes, edges: newEdges,
        selectedId: s.selectedId === id ? null : s.selectedId,
        ...markActiveTabDirty(s),
      }))
      return
    }
    await api.removeNode(id)
    set(s => ({
      nodes: s.nodes.filter(n => n.id !== id),
      edges: s.edges.filter(e => e.source !== id && e.target !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
      ...markActiveTabDirty(s),
    }))
  },

  onNodesChange: (changes) => {
    const shouldMarkDirty = changes.some(c => c.type === 'position' || c.type === 'dimensions' || c.type === 'remove')
    const { subnetStack, nodes, edges } = get()

    const removeChanges = changes.filter((c): c is { type: 'remove'; id: string } => c.type === 'remove')

    if (subnetStack.length > 0 && removeChanges.length > 0) {
      const removedIds = new Set(removeChanges.map(c => c.id))
      const frame = subnetStack[subnetStack.length - 1]
      const newNodes = applyNodeChanges(changes, nodes).filter(n => !removedIds.has(n.id))
      const newEdges = edges.filter(e => !removedIds.has(e.source) && !removedIds.has(e.target))
      const innerMeta: Record<string, any> = {}
      newNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = newEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      api.updateSubgraph(frame.subnetId, innerMeta, innerEdges).catch(() => {})
      set(s => ({
        nodes: newNodes, edges: newEdges,
        selectedId: removedIds.has(s.selectedId ?? '') ? null : s.selectedId,
        ...markActiveTabDirty(s),
      }))
      return
    }

    set(s => ({
      nodes: applyNodeChanges(changes, s.nodes),
      ...(shouldMarkDirty ? markActiveTabDirty(s) : {}),
    }))
    changes.forEach(c => {
      if (c.type === 'position' && c.position) {
        if (subnetStack.length === 0) {
          api.updatePos(c.id, [c.position.x, c.position.y]).catch(() => {})
        }
      }
      if (c.type === 'remove' && subnetStack.length === 0) {
        api.removeNode(c.id).catch(() => {})
        set(s => ({
          edges: s.edges.filter(e => e.source !== c.id && e.target !== c.id),
          selectedId: s.selectedId === c.id ? null : s.selectedId,
          ...markActiveTabDirty(s),
        }))
      }
    })
  },

  onEdgesChange: (changes) => {
    const { edges, nodes, subnetStack } = get()
    const shouldMarkDirty = changes.some(c => c.type === 'remove')
    const removedEdges = changes
      .filter(c => c.type === 'remove')
      .map(c => edges.find(e => e.id === (c as any).id))
      .filter(Boolean) as Edge[]

    const newEdges = applyEdgeChanges(changes, edges)
    const { nodes: nextNodes, changedIds: prunedToolBoxes } = pruneEmptyToolBoxSlots(nodes, newEdges)

    if (subnetStack.length > 0 && removedEdges.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = newEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      api.updateSubgraph(frame.subnetId, innerMeta, innerEdges).catch(() => {})
    } else {
      removedEdges.forEach(edge => {
        if (edge.sourceHandle && edge.targetHandle) {
          api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle).catch(() => {})
        }
      })
      prunedToolBoxes.forEach(id => {
        const node = nextNodes.find(n => n.id === id)
        if (!node) return
        api.updatePorts(id, {
          inputs: node.data.inputs,
          input_types: node.data.input_types,
          input_defaults: node.data.input_defaults,
        }).catch(() => {})
      })
    }

    set(s => ({
      nodes: nextNodes,
      edges: newEdges,
      ...(shouldMarkDirty || prunedToolBoxes.size > 0 ? markActiveTabDirty(s) : {}),
    }))
  },

  onConnect: async (rawConn) => {
    if (!rawConn.source || !rawConn.target || !rawConn.sourceHandle || !rawConn.targetHandle) return
    let conn = rawConn
    let { nodes, edges, subnetStack } = get()
    let srcNode = nodes.find(n => n.id === conn.source)
    let tgtNode = nodes.find(n => n.id === conn.target)

    // __new__ source handle on SubnetInput: auto-create output port named after the target handle
    if (conn.sourceHandle === '__new__' && srcNode?.data?.type === 'SubnetInput') {
      let portName = conn.targetHandle!
      const existing: string[] = srcNode.data.outputs ?? []
      if (existing.includes(portName)) {
        let i = 1
        while (existing.includes(`${portName}_${i}`)) i++
        portName = `${portName}_${i}`
      }
      const portType = tgtNode?.data?.input_types?.[conn.targetHandle!] ?? 'Any'
      await get().updateSubgraphBoundaryPorts(
        conn.source!, [...existing, portName], undefined,
        { ...(srcNode.data.output_types ?? {}), [portName]: portType }, undefined,
      )
      ;({ nodes, edges, subnetStack } = get())
      srcNode = nodes.find(n => n.id === conn.source)
      conn = { ...conn, sourceHandle: portName }
    }

    // __new__ target handle on SubnetOutput: auto-create input port named after the source handle
    if (conn.targetHandle === '__new__' && tgtNode?.data?.type === 'SubnetOutput') {
      let portName = conn.sourceHandle!
      const existing: string[] = tgtNode.data.inputs ?? []
      if (existing.includes(portName)) {
        let i = 1
        while (existing.includes(`${portName}_${i}`)) i++
        portName = `${portName}_${i}`
      }
      const portType = srcNode?.data?.output_types?.[conn.sourceHandle!] ?? 'Any'
      await get().updateSubgraphBoundaryPorts(
        conn.target!, undefined, [...existing, portName],
        undefined, { ...(tgtNode.data.input_types ?? {}), [portName]: portType },
      )
      ;({ nodes, edges, subnetStack } = get())
      tgtNode = nodes.find(n => n.id === conn.target)
      conn = { ...conn, targetHandle: portName }
    }

    // __new__ target handle on ToolBox: connect to the first empty tool slot,
    // creating a new tool_N input when all visible slots are already used.
    if (conn.targetHandle === '__new__' && tgtNode?.data?.type === 'ToolBox') {
      const fromType = srcNode?.data?.output_types?.[conn.sourceHandle!] ?? 'Any'
      if (!portsCompatible(fromType, 'Fn')) return
      const existing: string[] = tgtNode.data.inputs ?? []
      const occupied = new Set(
        edges
          .filter(e => e.target === conn.target && e.targetHandle)
          .map(e => e.targetHandle!)
      )
      let portName = existing.find(p => !occupied.has(p))
      if (!portName) {
        portName = nextToolInputName(existing)
        await get().updateNodePorts(
          conn.target!, [...existing, portName], undefined,
          { ...(tgtNode.data.input_types ?? {}), [portName]: 'Fn' }, undefined,
        )
        ;({ nodes, edges, subnetStack } = get())
        tgtNode = nodes.find(n => n.id === conn.target)
      }
      conn = { ...conn, targetHandle: portName }
    }

    if (!conn.sourceHandle || !conn.targetHandle) return
    const fromType = srcNode?.data?.output_types?.[conn.sourceHandle] ?? 'Any'
    const toType   = tgtNode?.data?.input_types?.[conn.targetHandle]  ?? 'Any'
    if (!portsCompatible(fromType, toType)) return
    const multiInputPorts: string[] = tgtNode?.data?.multi_input_ports ?? []
    const existingEdge = multiInputPorts.includes(conn.targetHandle!) ? null
      : edges.find(e => e.target === conn.target && e.targetHandle === conn.targetHandle)

    const newEdge = {
      ...conn,
      id: nextEdgeId(),
      style: { stroke: portColor(fromType), strokeWidth: 1.5 },
    }
    const updatedEdges = addEdge(newEdge, existingEdge ? edges.filter(e => e.id !== existingEdge.id) : edges)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = updatedEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
    } else {
      if (existingEdge?.source && existingEdge.sourceHandle && existingEdge.target && existingEdge.targetHandle) {
        await api.disconnect(existingEdge.source, existingEdge.sourceHandle, existingEdge.target, existingEdge.targetHandle)
      }
      await api.connect(conn.source!, conn.sourceHandle!, conn.target!, conn.targetHandle!)
    }

    set(s => ({ edges: updatedEdges, ...markActiveTabDirty(s) }))
  },

  disconnectEdge: async (edgeId) => {
    const { nodes, edges, subnetStack } = get()
    const edge = edges.find(e => e.id === edgeId)
    if (!edge?.source || !edge.target || !edge.sourceHandle || !edge.targetHandle) return
    const nextEdges = edges.filter(e => e.id !== edgeId)
    const { nodes: nextNodes, changedIds: prunedToolBoxes } = pruneEmptyToolBoxSlots(nodes, nextEdges)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = nextEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
    } else {
      await api.disconnect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
      for (const id of prunedToolBoxes) {
        const node = nextNodes.find(n => n.id === id)
        if (!node) continue
        await api.updatePorts(id, {
          inputs: node.data.inputs,
          input_types: node.data.input_types,
          input_defaults: node.data.input_defaults,
        })
      }
    }

    set(s => ({ nodes: nextNodes, edges: nextEdges, ...markActiveTabDirty(s) }))
  },

  reconnectEdge: async (oldEdge, newConn) => {
    if (!newConn.source || !newConn.target || !newConn.sourceHandle || !newConn.targetHandle) return
    let { nodes, edges, subnetStack } = get()
    let conn = {
      source: newConn.source,
      target: newConn.target,
      sourceHandle: newConn.sourceHandle,
      targetHandle: newConn.targetHandle,
    }
    let srcNode = nodes.find(n => n.id === conn.source)
    let tgtNode = nodes.find(n => n.id === conn.target)

    if (conn.targetHandle === '__new__' && tgtNode?.data?.type === 'ToolBox') {
      const fromType = srcNode?.data?.output_types?.[conn.sourceHandle] ?? 'Any'
      if (!portsCompatible(fromType, 'Fn')) return
      const existing: string[] = tgtNode.data.inputs ?? []
      const occupied = new Set(
        edges
          .filter(e => e.id !== oldEdge.id && e.target === conn.target && e.targetHandle)
          .map(e => e.targetHandle!)
      )
      let portName = existing.find(p => !occupied.has(p))
      if (!portName) {
        const newPortName = nextToolInputName(existing)
        nodes = nodes.map(n =>
          n.id === conn.target
            ? {
                ...n,
                data: {
                  ...n.data,
                  inputs: [...existing, newPortName],
                  input_types: { ...(n.data.input_types ?? {}), [newPortName]: 'Fn' },
                },
              }
            : n
        )
        portName = newPortName
        tgtNode = nodes.find(n => n.id === conn.target)
      }
      conn = { ...conn, targetHandle: portName }
    }

    const fromType = srcNode?.data?.output_types?.[conn.sourceHandle] ?? 'Any'
    const toType   = tgtNode?.data?.input_types?.[conn.targetHandle]  ?? 'Any'
    if (!portsCompatible(fromType, toType)) return
    const multiInputPorts: string[] = tgtNode?.data?.multi_input_ports ?? []
    const conflictingEdge = multiInputPorts.includes(conn.targetHandle) ? null
      : edges.find(e => e.id !== oldEdge.id && e.target === conn.target && e.targetHandle === conn.targetHandle)
    const nextEdges = edges
      .filter(e => e.id !== oldEdge.id && e.id !== conflictingEdge?.id)
      .concat([{
        id: oldEdge.id,
        source: conn.source!,
        sourceHandle: conn.sourceHandle,
        target: conn.target!,
        targetHandle: conn.targetHandle,
        style: { stroke: portColor(fromType), strokeWidth: 1.5 },
      }])
    const { nodes: nextNodes, changedIds: prunedToolBoxes } = pruneEmptyToolBoxSlots(nodes, nextEdges)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = nextEdges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
    } else {
      if (oldEdge.sourceHandle && oldEdge.targetHandle) {
        await api.disconnect(oldEdge.source, oldEdge.sourceHandle, oldEdge.target, oldEdge.targetHandle)
      }
      if (conflictingEdge?.source && conflictingEdge.sourceHandle && conflictingEdge.target && conflictingEdge.targetHandle) {
        await api.disconnect(conflictingEdge.source, conflictingEdge.sourceHandle, conflictingEdge.target, conflictingEdge.targetHandle)
      }
      await api.connect(conn.source, conn.sourceHandle, conn.target, conn.targetHandle)
      for (const id of prunedToolBoxes) {
        const node = nextNodes.find(n => n.id === id)
        if (!node) continue
        await api.updatePorts(id, {
          inputs: node.data.inputs,
          input_types: node.data.input_types,
          input_defaults: node.data.input_defaults,
        })
      }
    }

    set(s => ({
      nodes: nextNodes,
      edges: nextEdges,
      ...markActiveTabDirty(s),
    }))
  },

  updateParam: async (id, key, value) => {
    await api.updateParam(id, key, value)
    set(s => ({
      nodes: s.nodes.map(n =>
        n.id === id ? { ...n, data: { ...n.data, params: { ...n.data.params, [key]: value } } } : n
      ),
      ...markActiveTabDirty(s),
    }))
  },

  cookNode: async (id, port = 'output') => {
    const applyCookEvent = (event: CookEvent) => {
      if (event.type === 'done') return
      set(s => ({
        nodes: s.nodes.map(n => {
          if (n.id !== event.node_id) return n
          if (event.type === 'start') {
            return {
              ...n,
              data: {
                ...n.data,
                cooking: true,
                cookError: undefined,
                cookPort: event.port,
              },
            }
          }
          if (event.type === 'success') {
            return {
              ...n,
              data: {
                ...n.data,
                cooking: false,
                cookResult: event.value,
                cookError: undefined,
                cookPort: event.port,
              },
            }
          }
          return {
            ...n,
            data: {
              ...n.data,
              cooking: false,
              cookError: event.error,
              cookPort: event.port,
            },
          }
        }),
      }))
    }

    set(s => ({
      nodes: s.nodes.map(n => ({
        ...n,
        data: {
          ...n.data,
          cooking: n.id === id,
          cookError: n.id === id ? undefined : n.data.cookError,
          cookPort: n.id === id ? port : n.data.cookPort,
        },
      })),
    }))

    try {
      await api.cookStream(id, port, applyCookEvent)
    } catch (e: any) {
      set(s => ({
        nodes: s.nodes.map(n =>
          n.id === id ? { ...n, data: { ...n.data, cooking: false, cookError: e.message, cookPort: port } } : n
        ),
      }))
    }
  },

  selectNode: (id) => set({ selectedId: id }),

  reset: async () => {
    await api.reset()
    set(s => ({ nodes: [], edges: [], selectedId: null, ...markActiveTabDirty(s) }))
  },
}))
