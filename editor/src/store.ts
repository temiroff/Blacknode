import { create } from 'zustand'
import {
  Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, Connection,
} from 'reactflow'
import { api, type CookEvent, type RunRecord } from './api'
import { BnNodeDef, BnNodeMeta, ConnectionDraft, NodeCookState, SubnetFrame } from './types'
import { VALUE_NODE_TYPES } from './categories'
import { portsCompatible, portColor } from './portColors'
import { organizeFlowNodes } from './graphLayout'
import { createVisualAgentLoopSubgraph } from './defaultSubgraphs'

const MODEL_NODE_TYPES  = new Set(['Model'])
const OUTPUT_NODE_TYPES = new Set(['Output'])
const SUBGRAPH_NODE_TYPES = new Set(['Subnet', 'SubnetAsTool', 'VisualAgentLoop'])

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

export interface NodeData extends BnNodeMeta, NodeCookState {}

export interface GraphClipboard {
  nodes: Node<NodeData>[]
  edges: Edge[]
}

export interface CookLogEntry {
  id: string
  kind: 'start' | 'success' | 'error' | 'done' | 'info'
  label: string
  message: string
  nodeId?: string
  port?: string
  cached?: boolean
  ts: number
}

export interface RunReplayState {
  runId: string | null
  cursor: number
  total: number
  playing: boolean
  currentNodeId?: string
  currentEventType?: string
  message?: string
}

interface UndoSnapshot {
  activeTabId: string
  graph: GraphSnapshot
  nodes: Node<NodeData>[]
  edges: Edge[]
  subnetStack: SubnetFrame[]
  selectedId: string | null
}

const UNDO_LIMIT = 80
let dragUndoActive = false

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
  undoHistory: UndoSnapshot[]
  cookLog: CookLogEntry[]
  cookActive: boolean
  runReplay: RunReplayState

  loadNodeTypes: () => Promise<void>
  loadGraph: () => Promise<void>
  loadApiKeys: () => Promise<void>
  setApiKey: (provider: string, key: string) => Promise<void>
  loadCustomModels: () => Promise<void>
  addCustomModel: (value: string) => Promise<void>
  removeCustomModel: (value: string) => Promise<void>
  checkServer: () => Promise<void>

  newTab: (name?: string) => Promise<void>
  insertTab: (tabId: string) => Promise<void>
  switchTab: (tabId: string) => Promise<void>
  closeTab: (tabId: string) => Promise<void>
  duplicateTab: (tabId: string) => Promise<void>
  openWorkflowAsTab: (slug: string, name: string) => Promise<void>
  openGraphAsTab: (name: string, graph: GraphSnapshot) => Promise<void>
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
    recordHistory?: boolean,
  ) => Promise<void>
  updateSubgraphBoundaryPorts: (
    innerNodeId: string,
    outputs?: string[],
    inputs?: string[],
    outputTypes?: Record<string, string>,
    inputTypes?: Record<string, string>,
    recordHistory?: boolean,
  ) => Promise<void>

  addNode: (typeName: string, pos: { x: number; y: number }, params?: Record<string, unknown>) => Promise<void>
  addNodeFromConnection: (typeName: string, pos: { x: number; y: number }, draft: ConnectionDraft, params?: Record<string, unknown>) => Promise<void>
  removeNode: (id: string) => Promise<void>
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (conn: Connection) => Promise<void>
  disconnectEdge: (edgeId: string) => Promise<void>
  reconnectEdge: (oldEdge: Edge, newConn: Connection) => Promise<void>
  copySelection: () => GraphClipboard | null
  pasteClipboard: (clipboard: GraphClipboard, targetPos: { x: number; y: number }) => Promise<void>
  beginAltDragCopy: (
    nodeIds: string[],
    originalPositions: Record<string, { x: number; y: number }>,
  ) => Promise<Record<string, string> | null>
  finishAltDragCopy: (
    nodeIds: string[],
    originalPositions: Record<string, { x: number; y: number }>,
    copyIdMap: Record<string, string> | null,
  ) => Promise<void>
  updateParam: (id: string, key: string, value: unknown) => Promise<void>
  cookNode: (id: string, port?: string) => Promise<void>
  applyRunReplay: (record: RunRecord, cursor: number, playing: boolean) => void
  clearRunReplay: () => void
  selectNode: (id: string | null) => void
  undoGraph: () => Promise<void>
  reset: () => Promise<void>
}

function reactNodeType(typeName: string): string {
  if (SUBGRAPH_NODE_TYPES.has(typeName)) return 'subnetnode'
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
  const parsed = parseGraph(metaList, subgraph.edges)
  return { nodes: ensureConnectedToolBoxSlots(parsed.nodes, parsed.edges), edges: parsed.edges }
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

function toolInputIndex(name: string): number {
  const n = Number(name.split('_').pop())
  return Number.isFinite(n) ? n : Number.MAX_SAFE_INTEGER
}

function sortToolInputs(inputs: string[]): string[] {
  return [...inputs].sort((a, b) => toolInputIndex(a) - toolInputIndex(b) || a.localeCompare(b))
}

function cloneDeep<T>(value: T): T {
  if (value === undefined || value === null) return value
  return JSON.parse(JSON.stringify(value)) as T
}

function stripRuntimeNodeData(data: NodeData): BnNodeMeta {
  const {
    cookResult: _cookResult,
    cookError: _cookError,
    cooking: _cooking,
    cookPort: _cookPort,
    replayRunId: _replayRunId,
    replayStatus: _replayStatus,
    replayFocused: _replayFocused,
    replayLabel: _replayLabel,
    replayPort: _replayPort,
    replayDurationMs: _replayDurationMs,
    replayResult: _replayResult,
    replayError: _replayError,
    replayStep: _replayStep,
    replayTotal: _replayTotal,
    replayModelCalls: _replayModelCalls,
    replayToolCalls: _replayToolCalls,
    ...meta
  } = data
  return meta
}

function clearReplayData(data: NodeData): NodeData {
  const {
    replayRunId: _replayRunId,
    replayStatus: _replayStatus,
    replayFocused: _replayFocused,
    replayLabel: _replayLabel,
    replayPort: _replayPort,
    replayDurationMs: _replayDurationMs,
    replayResult: _replayResult,
    replayError: _replayError,
    replayStep: _replayStep,
    replayTotal: _replayTotal,
    replayModelCalls: _replayModelCalls,
    replayToolCalls: _replayToolCalls,
    ...rest
  } = data
  return rest
}

function flowEdgesToBackend(edges: Edge[]): any[] {
  return edges
    .filter(e => e.source && e.target && e.sourceHandle && e.targetHandle)
    .map(e => ({
      from: e.source,
      from_port: e.sourceHandle,
      to: e.target,
      to_port: e.targetHandle,
    }))
}

function nodeToMeta(node: Node<NodeData>): BnNodeMeta {
  return {
    ...cloneDeep(stripRuntimeNodeData(node.data)),
    pos: [node.position.x, node.position.y],
  }
}

function nodesToMeta(nodes: Node<NodeData>[]): Record<string, BnNodeMeta> {
  const meta: Record<string, BnNodeMeta> = {}
  nodes.forEach(node => { meta[node.id] = nodeToMeta(node) })
  return meta
}

function subgraphFromFlow(nodes: Node<NodeData>[], edges: Edge[]): { node_meta: Record<string, BnNodeMeta>; edges: any[] } {
  return {
    node_meta: nodesToMeta(nodes),
    edges: flowEdgesToBackend(edges),
  }
}

const INNER_NODE_LABELS: Record<string, string> = {
  loop_in: 'SubnetInput',
  messages: 'AgentMessages',
  chat: 'AgentChatStep',
  iteration: 'AgentIteration',
  iter_one: 'Int',
  dispatch: 'ToolDispatch',
  stop: 'AgentStopCheck',
  append: 'AgentAppendMessages',
  final: 'AgentFinalAnswer',
  loop_out: 'SubnetOutput',
}

function nodeRunLabel(nodes: Node<NodeData>[], nodeId?: string): string {
  if (!nodeId) return 'Graph'
  const node = nodes.find(n => n.id === nodeId)
  if (node) {
    const type = node.data.type
    if (type === 'SubnetAsTool') return String(node.data.params?.name ?? 'SubnetAsTool')
    if (type === 'Subnet') return String(node.data.params?.label ?? 'Subnet')
    if (type === 'VisualAgentLoop') return 'VisualAgentLoop'
    return type
  }
  return INNER_NODE_LABELS[nodeId] ?? nodeId.slice(0, 8)
}

function shortText(value: unknown, max = 120): string {
  if (value === undefined || value === null) return ''
  const encoded = typeof value === 'string' ? value : JSON.stringify(value)
  const text = encoded === undefined ? String(value) : encoded
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function cookEventLogEntry(event: CookEvent, nodes: Node<NodeData>[]): CookLogEntry {
  const ts = Date.now()
  if (event.type === 'done') {
    return {
      id: `${ts}-done`,
      kind: 'done',
      label: 'Graph',
      message: event.error ? 'Run stopped with error' : `Run complete${event.value !== undefined ? `: ${shortText(event.value)}` : ''}`,
      ts,
    }
  }

  const label = nodeRunLabel(nodes, event.node_id)
  if (event.type === 'model_call') {
    return {
      id: `${ts}-${event.node_id}-model`,
      kind: 'info',
      label,
      message: `${label} model: ${event.model}`,
      nodeId: event.node_id,
      ts,
    }
  }
  if (event.type === 'tool_call') {
    return {
      id: `${ts}-${event.node_id}-tool`,
      kind: 'info',
      label,
      message: `${label} tool: ${event.name}`,
      nodeId: event.node_id,
      ts,
    }
  }

  const port = event.port ? `.${event.port}` : ''
  if (event.type === 'start') {
    return {
      id: `${ts}-${event.node_id}-${event.port}-start`,
      kind: 'start',
      label,
      message: `Cooking ${label}${port}`,
      nodeId: event.node_id,
      port: event.port,
      ts,
    }
  }
  if (event.type === 'success') {
    return {
      id: `${ts}-${event.node_id}-${event.port}-success`,
      kind: 'success',
      label,
      message: `${label}${port} ${event.cached ? 'cached' : 'done'}${event.value !== undefined ? `: ${shortText(event.value)}` : ''}`,
      nodeId: event.node_id,
      port: event.port,
      cached: event.cached,
      ts,
    }
  }
  return {
    id: `${ts}-${event.node_id}-${event.port}-error`,
    kind: 'error',
    label,
    message: `${label}${port} error: ${shortText(event.error, 180)}`,
    nodeId: event.node_id,
    port: event.port,
    ts,
  }
}

function appendCookLog(log: CookLogEntry[], entry: CookLogEntry): CookLogEntry[] {
  return [...log, entry].slice(-80)
}

const EMPTY_REPLAY: RunReplayState = {
  runId: null,
  cursor: -1,
  total: 0,
  playing: false,
}

type ReplayEvent = RunRecord['events'][number]

type ReplayNodePatch = Pick<
  NodeData,
  | 'replayRunId'
  | 'replayStatus'
  | 'replayFocused'
  | 'replayLabel'
  | 'replayPort'
  | 'replayDurationMs'
  | 'replayResult'
  | 'replayError'
  | 'replayStep'
  | 'replayTotal'
  | 'replayModelCalls'
  | 'replayToolCalls'
>

function buildReplayPatches(record: RunRecord, cursor: number): Map<string, ReplayNodePatch> {
  const patches = new Map<string, ReplayNodePatch>()
  const events = record.events
  const maxIndex = Math.min(Math.max(cursor, 0), events.length - 1)
  const current = events[maxIndex]
  const currentNodeId = eventNodeId(current) || (current?.type === 'done' ? record.node_id : '')
  const startTimes = new Map<string, number>()

  for (let index = 0; index <= maxIndex; index += 1) {
    const event = events[index]
    const nodeId = eventNodeId(event) || (event.type === 'done' ? record.node_id : '')
    if (!nodeId) continue

    const port = eventPort(event) || (event.type === 'done' ? record.port : undefined)
    const key = `${nodeId}.${port ?? ''}`
    const ts = replayEventTime(event)
    if (event.type === 'start' && ts != null) startTimes.set(key, ts)

    const previous = patches.get(nodeId)
    const next: ReplayNodePatch = {
      ...previous,
      replayRunId: record.run_id,
      replayFocused: nodeId === currentNodeId,
      replayPort: port,
      replayStep: index + 1,
      replayTotal: events.length,
      replayModelCalls: previous?.replayModelCalls ?? 0,
      replayToolCalls: previous?.replayToolCalls ?? 0,
    }

    if (event.type === 'start') {
      next.replayStatus = 'running'
      next.replayLabel = port ? `running ${port}` : 'running'
      next.replayError = undefined
    } else if (event.type === 'success') {
      const cached = Boolean(event.cached)
      next.replayStatus = cached ? 'cached' : 'success'
      next.replayDurationMs = eventDurationMs(event, startTimes.get(key))
      next.replayResult = event.value ?? outputValueForPort(event.outputs, port)
      next.replayError = undefined
      next.replayLabel = cached ? 'cache hit' : 'finished'
    } else if (event.type === 'error') {
      next.replayStatus = 'error'
      next.replayDurationMs = eventDurationMs(event, startTimes.get(key))
      next.replayError = stringValue(event.error)
      next.replayLabel = 'error'
    } else if (event.type === 'model_call') {
      next.replayStatus = 'model'
      next.replayModelCalls = (next.replayModelCalls ?? 0) + 1
      next.replayLabel = [stringValue(event.provider), stringValue(event.model)].filter(Boolean).join(' / ') || 'model call'
    } else if (event.type === 'tool_call') {
      next.replayStatus = 'tool'
      next.replayToolCalls = (next.replayToolCalls ?? 0) + 1
      next.replayLabel = stringValue(event.name) || 'tool call'
    } else if (event.type === 'done') {
      next.replayStatus = event.error ? 'error' : 'done'
      next.replayResult = event.value
      next.replayError = stringValue(event.error)
      next.replayLabel = event.error ? 'run failed' : 'run done'
    }

    patches.set(nodeId, next)
  }

  return patches
}

function eventNodeId(event: ReplayEvent | undefined): string {
  return stringValue(event?.node_id)
}

function eventPort(event: ReplayEvent | undefined): string | undefined {
  return stringValue(event?.port) || undefined
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function outputValueForPort(outputs: unknown, port: string | undefined): unknown {
  if (!port || !outputs || typeof outputs !== 'object' || Array.isArray(outputs)) return undefined
  return (outputs as Record<string, unknown>)[port]
}

function eventDurationMs(event: ReplayEvent, startedAt: number | undefined): number | undefined {
  if (typeof event.duration_ms === 'number') return event.duration_ms
  if (startedAt == null) return undefined
  const finishedAt = replayEventTime(event)
  return finishedAt == null ? undefined : Math.max(0, finishedAt - startedAt)
}

function replayEventTime(event: ReplayEvent | undefined): number | null {
  if (!event?.ts) return null
  if (typeof event.ts === 'number') {
    return event.ts < 1_000_000_000_000 ? event.ts * 1000 : event.ts
  }
  if (typeof event.ts === 'string') {
    const parsed = new Date(event.ts).getTime()
    return Number.isNaN(parsed) ? null : parsed
  }
  return null
}

function graphSnapshotFromState(s: Store): GraphSnapshot {
  let current = subgraphFromFlow(s.nodes, s.edges)

  for (let i = s.subnetStack.length - 1; i >= 0; i--) {
    const frame = s.subnetStack[i]
    const parentNodes = cloneDeep(frame.parentNodes) as Node<NodeData>[]
    const parentEdges = cloneDeep(frame.parentEdges) as Edge[]
    const nextParentNodes = parentNodes.map(node => (
      node.id === frame.subnetId
        ? { ...node, data: { ...node.data, subgraph: current } }
        : node
    ))
    current = subgraphFromFlow(nextParentNodes, parentEdges)
  }

  return {
    nodes: Object.values(current.node_meta),
    edges: current.edges,
  }
}

function makeUndoSnapshot(s: Store): UndoSnapshot {
  return {
    activeTabId: s.activeTabId,
    graph: cloneGraph(graphSnapshotFromState(s)),
    nodes: cloneDeep(s.nodes),
    edges: cloneDeep(s.edges),
    subnetStack: cloneDeep(s.subnetStack),
    selectedId: s.selectedId,
  }
}

function pushUndoSnapshot(s: Store): Pick<Store, 'undoHistory'> {
  const snapshot = makeUndoSnapshot(s)
  const undoHistory = [...s.undoHistory, snapshot]
  return { undoHistory: undoHistory.slice(Math.max(0, undoHistory.length - UNDO_LIMIT)) }
}

function shouldRecordNodeChange(changes: NodeChange[]): boolean {
  if (changes.some(c => c.type === 'remove')) {
    dragUndoActive = false
    return true
  }

  const positionChanges = changes.filter(c => c.type === 'position' && c.position)
  if (positionChanges.length === 0) return false

  const dragging = positionChanges.some(c => Boolean((c as any).dragging))
  if (dragging) {
    if (dragUndoActive) return false
    dragUndoActive = true
    return true
  }

  if (dragUndoActive) {
    dragUndoActive = false
    return false
  }

  return true
}

function pruneDisconnectedDynamicPorts(
  nodes: Node<NodeData>[],
  edges: Edge[],
  removedEdges: Edge[] = [],
): { nodes: Node<NodeData>[]; changedIds: Set<string> } {
  const connectedToolPorts = new Map<string, Set<string>>()
  edges.forEach(edge => {
    if (!edge.targetHandle?.startsWith('tool_')) return
    if (!connectedToolPorts.has(edge.target)) connectedToolPorts.set(edge.target, new Set())
    connectedToolPorts.get(edge.target)!.add(edge.targetHandle)
  })

  const removedInputs = new Map<string, Set<string>>()
  const removedOutputs = new Map<string, Set<string>>()
  const addRemoved = (map: Map<string, Set<string>>, nodeId: string | undefined, port: string | null | undefined) => {
    if (!nodeId || !port || port === '__new__') return
    if (!map.has(nodeId)) map.set(nodeId, new Set())
    map.get(nodeId)!.add(port)
  }
  removedEdges.forEach(edge => {
    const source = nodes.find(n => n.id === edge.source)
    const target = nodes.find(n => n.id === edge.target)
    if (target?.data.type === 'SubnetOutput' || target?.data.type === 'Subnet') {
      addRemoved(removedInputs, edge.target, edge.targetHandle)
    }
    if (source?.data.type === 'SubnetInput' || source?.data.type === 'Subnet') {
      addRemoved(removedOutputs, edge.source, edge.sourceHandle)
    }
  })

  const changedIds = new Set<string>()
  const nextNodes = nodes.map(node => {
    if (node.data.type === 'ToolBox') {
      const connected = sortToolInputs(Array.from(connectedToolPorts.get(node.id) ?? []))
      if (
        connected.length === (node.data.inputs ?? []).length
        && connected.every((port, i) => port === node.data.inputs[i])
      ) {
        return node
      }

      changedIds.add(node.id)
      const inputTypes: Record<string, string> = {}
      connected.forEach(port => { inputTypes[port] = node.data.input_types?.[port] ?? 'Fn' })
      return {
        ...node,
        data: {
          ...node.data,
          inputs: connected,
          input_types: inputTypes,
          input_defaults: {},
        },
      }
    }

    if (node.data.type === 'SubnetOutput') {
      const removed = removedInputs.get(node.id)
      if (!removed) return node
      const removePorts = new Set(
        Array.from(removed).filter(port =>
          (node.data.inputs ?? []).includes(port)
          && !edges.some(edge => edge.target === node.id && edge.targetHandle === port)
        )
      )
      if (removePorts.size === 0) return node
      changedIds.add(node.id)
      const inputs = (node.data.inputs ?? []).filter(port => !removePorts.has(port))
      const inputTypes = Object.fromEntries(
        Object.entries(node.data.input_types ?? {}).filter(([port]) => !removePorts.has(port))
      )
      const inputDefaults = Object.fromEntries(
        Object.entries(node.data.input_defaults ?? {}).filter(([port]) => !removePorts.has(port))
      )
      return { ...node, data: { ...node.data, inputs, input_types: inputTypes, input_defaults: inputDefaults } }
    }

    if (node.data.type === 'SubnetInput') {
      const removed = removedOutputs.get(node.id)
      if (!removed) return node
      const removePorts = new Set(
        Array.from(removed).filter(port =>
          (node.data.outputs ?? []).includes(port)
          && !edges.some(edge => edge.source === node.id && edge.sourceHandle === port)
        )
      )
      if (removePorts.size === 0) return node
      changedIds.add(node.id)
      const outputs = (node.data.outputs ?? []).filter(port => !removePorts.has(port))
      const outputTypes = Object.fromEntries(
        Object.entries(node.data.output_types ?? {}).filter(([port]) => !removePorts.has(port))
      )
      return { ...node, data: { ...node.data, outputs, output_types: outputTypes } }
    }

    if (node.data.type === 'Subnet') {
      const removedIn = removedInputs.get(node.id)
      const removedOut = removedOutputs.get(node.id)
      if (!removedIn && !removedOut) return node

      const removeInputs = new Set(
        Array.from(removedIn ?? []).filter(port =>
          (node.data.inputs ?? []).includes(port)
          && !edges.some(edge => edge.target === node.id && edge.targetHandle === port)
        )
      )
      const removeOutputs = new Set(
        Array.from(removedOut ?? []).filter(port =>
          (node.data.outputs ?? []).includes(port)
          && !edges.some(edge => edge.source === node.id && edge.sourceHandle === port)
        )
      )
      if (removeInputs.size === 0 && removeOutputs.size === 0) return node

      const subgraph = cloneDeep(node.data.subgraph ?? { node_meta: {}, edges: [] })
      const subnetInputIds = new Set<string>()
      const subnetOutputIds = new Set<string>()
      Object.values(subgraph.node_meta).forEach((meta: any) => {
        if (meta.type === 'SubnetInput' && removeInputs.size > 0) {
          subnetInputIds.add(meta.id)
          meta.outputs = (meta.outputs ?? []).filter((port: string) => !removeInputs.has(port))
          meta.output_types = Object.fromEntries(
            Object.entries(meta.output_types ?? {}).filter(([port]) => !removeInputs.has(port))
          )
        }
        if (meta.type === 'SubnetOutput' && removeOutputs.size > 0) {
          subnetOutputIds.add(meta.id)
          meta.inputs = (meta.inputs ?? []).filter((port: string) => !removeOutputs.has(port))
          meta.input_types = Object.fromEntries(
            Object.entries(meta.input_types ?? {}).filter(([port]) => !removeOutputs.has(port))
          )
          meta.input_defaults = Object.fromEntries(
            Object.entries(meta.input_defaults ?? {}).filter(([port]) => !removeOutputs.has(port))
          )
        }
      })
      subgraph.edges = (subgraph.edges ?? []).filter(edge =>
        !(removeInputs.size > 0 && subnetInputIds.has(edge.from) && removeInputs.has(edge.from_port))
        && !(removeOutputs.size > 0 && subnetOutputIds.has(edge.to) && removeOutputs.has(edge.to_port))
      )

      changedIds.add(node.id)
      const inputs = (node.data.inputs ?? []).filter(port => !removeInputs.has(port))
      const outputs = (node.data.outputs ?? []).filter(port => !removeOutputs.has(port))
      const inputTypes = Object.fromEntries(
        Object.entries(node.data.input_types ?? {}).filter(([port]) => !removeInputs.has(port))
      )
      const outputTypes = Object.fromEntries(
        Object.entries(node.data.output_types ?? {}).filter(([port]) => !removeOutputs.has(port))
      )
      const inputDefaults = Object.fromEntries(
        Object.entries(node.data.input_defaults ?? {}).filter(([port]) => !removeInputs.has(port))
      )
      return {
        ...node,
        data: { ...node.data, inputs, outputs, input_types: inputTypes, output_types: outputTypes, input_defaults: inputDefaults, subgraph },
      }
    }

    return node
  })

  return { nodes: nextNodes, changedIds }
}

function ensureConnectedToolBoxSlots(nodes: Node<NodeData>[], edges: Edge[]): Node<NodeData>[] {
  const connectedPorts = new Map<string, Set<string>>()
  edges.forEach(edge => {
    if (!edge.targetHandle?.startsWith('tool_')) return
    if (!connectedPorts.has(edge.target)) connectedPorts.set(edge.target, new Set())
    connectedPorts.get(edge.target)!.add(edge.targetHandle)
  })

  return nodes.map(node => {
    if (node.data.type !== 'ToolBox') return node
    const connected = sortToolInputs(Array.from(connectedPorts.get(node.id) ?? []))
    if (
      connected.length === (node.data.inputs ?? []).length
      && connected.every((port, i) => port === node.data.inputs[i])
    ) {
      return node
    }

    const inputTypes: Record<string, string> = {}
    connected.forEach(port => { inputTypes[port] = 'Fn' })
    return {
      ...node,
      data: {
        ...node.data,
        inputs: connected,
        input_types: inputTypes,
        input_defaults: {},
      },
    }
  })
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
  undoHistory: [],
  cookLog: [],
  cookActive: false,
  runReplay: EMPTY_REPLAY,
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
    const parsed = parseGraph(bnNodes, bnEdges)
    set({ nodes: ensureConnectedToolBoxSlots(parsed.nodes, parsed.edges), edges: parsed.edges, selectedId: null })
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

  newTab: async (name) => {
    await get().saveActiveTabSnapshot()
    const id = makeTabId()
    const tabName = cleanWorkflowName(name)
    set(s => ({ tabs: [...s.tabs, { id, name: tabName, slug: null, dirty: false, graph: blankGraph() }], activeTabId: id, undoHistory: [] }))
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
    set({ tabs: nextTabs, activeTabId: id, selectedId: null, undoHistory: [] })
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
    set({ activeTabId: tabId, selectedId: null, undoHistory: [] })
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
    const idx = tabs.findIndex(t => t.id === tabId)
    if (idx < 0) return
    if (tabs.length <= 1) {
      const tab = tabs[idx]
      await api.reset()
      set({
        tabs: [{ ...tab, name: 'Untitled', slug: null, dirty: false, graph: blankGraph() }],
        activeTabId: tab.id,
        nodes: [],
        edges: [],
        selectedId: null,
        subnetStack: [],
        undoHistory: [],
        cookLog: [],
        cookActive: false,
        runReplay: EMPTY_REPLAY,
      })
      return
    }
    const newTabs = tabs.filter(t => t.id !== tabId)
    if (tabId === activeTabId) {
      const next = newTabs[Math.max(0, idx - 1)]
      set({ tabs: newTabs, activeTabId: next.id, selectedId: null, undoHistory: [] })
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
    set({ tabs: nextTabs, activeTabId: id, selectedId: null, undoHistory: [] })
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
    set(s => ({ tabs: [...s.tabs, { id, name, slug, dirty: false, graph: cloneGraph(graph) }], activeTabId: id, selectedId: null, undoHistory: [] }))
    await get().loadGraph()
  },

  openGraphAsTab: async (name, graph) => {
    await get().saveActiveTabSnapshot()
    const id = makeTabId()
    const nextGraph = cloneGraph(graph)
    set(s => ({
      tabs: [...s.tabs, { id, name: cleanWorkflowName(name), slug: null, dirty: true, graph: nextGraph }],
      activeTabId: id,
      selectedId: null,
      undoHistory: [],
    }))
    await api.setGraph(nextGraph.nodes, nextGraph.edges)
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
    set(s => pushUndoSnapshot(s))
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
      subnetNode.data.type === 'VisualAgentLoop'
        ? 'VisualAgentLoop'
        : subnetNode.data.type === 'SubnetAsTool'
        ? subnetNode.data.params?.name ?? 'tool'
        : subnetNode.data.params?.label ?? 'Subnet'
    )
    // Always fetch fresh inner graph from server
    let subgraph = await api.getSubgraph(subnetId)
    let parentNodes = nodes
    let initializedDefault = false
    if (subnetNode.data.type === 'VisualAgentLoop' && Object.keys(subgraph.node_meta ?? {}).length === 0) {
      subgraph = createVisualAgentLoopSubgraph()
      initializedDefault = true
      parentNodes = nodes.map(n =>
        n.id === subnetId ? { ...n, data: { ...n.data, subgraph } } : n
      )
      api.updateSubgraph(subnetId, subgraph.node_meta, subgraph.edges).catch(() => {})
    }
    const { nodes: innerNodes, edges: innerEdges } = parseSubgraph(subgraph as any)
    set(s => ({
      subnetStack: [...s.subnetStack, {
        subnetId,
        subnetLabel: label,
        parentNodes,
        parentEdges: edges,
      }],
      nodes: innerNodes,
      edges: innerEdges,
      selectedId: null,
      ...(initializedDefault ? markActiveTabDirty(s) : {}),
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
      set({ subnetStack: [], nodes: ensureConnectedToolBoxSlots(nodes, edges), edges, selectedId: null })
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
    set({ subnetStack: [], nodes: ensureConnectedToolBoxSlots(nodes, edges), edges, selectedId: null })
  },

  collapseToSubnet: async (nodeIds, label) => {
    set(s => pushUndoSnapshot(s))
    await api.collapseToSubnet(nodeIds, label)
    const graphData = await api.getGraph()
    const { nodes: newNodes, edges: newEdges } = parseGraph(graphData.nodes, graphData.edges)
    set(s => ({ nodes: ensureConnectedToolBoxSlots(newNodes, newEdges), edges: newEdges, ...markActiveTabDirty(s) }))
  },

  organizeNodes: async () => {
    const { subnetStack, nodes, edges } = get()
    const nextNodes = organizeFlowNodes(nodes, edges)
    set(s => pushUndoSnapshot(s))

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

  updateNodePorts: async (nodeId, inputs, outputs, inputTypes, outputTypes, inputDefaults, multiInputPorts, recordHistory = true) => {
    const { subnetStack, nodes, edges } = get()
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return
    if (recordHistory) set(s => pushUndoSnapshot(s))

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

  updateSubgraphBoundaryPorts: async (innerNodeId, outputs, inputs, outputTypes, inputTypes, recordHistory = true) => {
    const { subnetStack, nodes, edges } = get()
    if (subnetStack.length === 0) return
    const frame = subnetStack[subnetStack.length - 1]
    if (recordHistory) set(s => pushUndoSnapshot(s))

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

  addNode: async (typeName, pos, params = {}) => {
    set(s => pushUndoSnapshot(s))
    const { subnetStack } = get()
    if (subnetStack.length > 0) {
      // Add node inside current subnet
      const frame = subnetStack[subnetStack.length - 1]
      const meta = await api.addNode(typeName, [pos.x, pos.y], params)
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
    const meta = await api.addNode(typeName, [pos.x, pos.y], params)
    const node = makeReactNode(meta)
    set(s => ({ nodes: [...s.nodes, node], ...markActiveTabDirty(s) }))
  },

  addNodeFromConnection: async (typeName, pos, draft, params = {}) => {
    const { nodes } = get()
    const existing = nodes.find(n => n.id === draft.nodeId)
    if (!existing) return
    set(s => pushUndoSnapshot(s))

    const meta = await api.addNode(typeName, [pos.x, pos.y], params)
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
    if (!nodes.some(n => n.id === id)) return
    set(s => pushUndoSnapshot(s))
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
    const shouldRecordHistory = shouldRecordNodeChange(changes)
    if (shouldRecordHistory) set(s => pushUndoSnapshot(s))
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
    const shouldSyncSubgraphPositions = subnetStack.length > 0
      && changes.some(c => c.type === 'position' && c.position && !Boolean((c as any).dragging))
    if (shouldSyncSubgraphPositions) {
      const frame = subnetStack[subnetStack.length - 1]
      const newNodes = applyNodeChanges(changes, nodes)
      const innerMeta: Record<string, any> = {}
      newNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = edges.map(e => ({
        from: e.source, from_port: e.sourceHandle ?? '',
        to: e.target,   to_port:   e.targetHandle ?? '',
      }))
      api.updateSubgraph(frame.subnetId, innerMeta, innerEdges).catch(() => {})
    }
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
    if (shouldMarkDirty) set(s => pushUndoSnapshot(s))
    const removedEdges = changes
      .filter(c => c.type === 'remove')
      .map(c => edges.find(e => e.id === (c as any).id))
      .filter(Boolean) as Edge[]

    const newEdges = applyEdgeChanges(changes, edges)
    const { nodes: nextNodes, changedIds: prunedDynamicNodes } = pruneDisconnectedDynamicPorts(nodes, newEdges, removedEdges)

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
      prunedDynamicNodes.forEach(id => {
        const node = nextNodes.find(n => n.id === id)
        if (!node) return
        if (node.data.type === 'ToolBox') {
          api.updatePorts(id, {
            inputs: node.data.inputs,
            input_types: node.data.input_types,
            input_defaults: node.data.input_defaults,
          }).catch(() => {})
        } else if (node.data.type === 'Subnet' && node.data.subgraph) {
          api.updateSubgraph(id, node.data.subgraph.node_meta, node.data.subgraph.edges).catch(() => {})
        }
      })
    }

    set(s => ({
      nodes: nextNodes,
      edges: newEdges,
      ...(shouldMarkDirty || prunedDynamicNodes.size > 0 ? markActiveTabDirty(s) : {}),
    }))
  },

  onConnect: async (rawConn) => {
    if (!rawConn.source || !rawConn.target || !rawConn.sourceHandle || !rawConn.targetHandle) return
    let conn = rawConn
    let { nodes, edges, subnetStack } = get()
    let srcNode = nodes.find(n => n.id === conn.source)
    let tgtNode = nodes.find(n => n.id === conn.target)
    if (!srcNode || !tgtNode) return
    set(s => pushUndoSnapshot(s))

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
        { ...(srcNode.data.output_types ?? {}), [portName]: portType }, undefined, false,
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
        undefined, { ...(tgtNode.data.input_types ?? {}), [portName]: portType }, false,
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
        const newPortName = nextToolInputName(existing)
        nodes = nodes.map(n =>
          n.id === conn.target
            ? {
                ...n,
                data: {
                  ...n.data,
                  inputs: sortToolInputs([...existing, newPortName]),
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

    if (
      tgtNode?.data?.type === 'ToolBox'
      && conn.targetHandle?.startsWith('tool_')
      && !(tgtNode.data.inputs ?? []).includes(conn.targetHandle)
    ) {
      const nextInputs = sortToolInputs([...(tgtNode.data.inputs ?? []), conn.targetHandle])
      nodes = nodes.map(n =>
        n.id === conn.target
          ? {
              ...n,
              data: {
                ...n.data,
                inputs: nextInputs,
                input_types: { ...(n.data.input_types ?? {}), [conn.targetHandle!]: 'Fn' },
              },
            }
          : n
      )
      tgtNode = nodes.find(n => n.id === conn.target)
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

    const nextNodes = ensureConnectedToolBoxSlots(nodes, updatedEdges)
    set(s => ({ nodes: nextNodes, edges: updatedEdges, ...markActiveTabDirty(s) }))
  },

  disconnectEdge: async (edgeId) => {
    const { nodes, edges, subnetStack } = get()
    const edge = edges.find(e => e.id === edgeId)
    if (!edge?.source || !edge.target || !edge.sourceHandle || !edge.targetHandle) return
    set(s => pushUndoSnapshot(s))
    const nextEdges = edges.filter(e => e.id !== edgeId)
    const { nodes: nextNodes, changedIds: prunedDynamicNodes } = pruneDisconnectedDynamicPorts(nodes, nextEdges, [edge])

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
      for (const id of prunedDynamicNodes) {
        const node = nextNodes.find(n => n.id === id)
        if (!node) continue
        if (node.data.type === 'Subnet' && node.data.subgraph) {
          await api.updateSubgraph(id, node.data.subgraph.node_meta, node.data.subgraph.edges)
        }
      }
    }

    set(s => ({ nodes: nextNodes, edges: nextEdges, ...markActiveTabDirty(s) }))
  },

  reconnectEdge: async (oldEdge, newConn) => {
    if (!newConn.source || !newConn.target || !newConn.sourceHandle || !newConn.targetHandle) return
    set(s => pushUndoSnapshot(s))
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
    const removedForPrune = [oldEdge, conflictingEdge].filter(Boolean) as Edge[]
    const { nodes: nextNodes, changedIds: prunedDynamicNodes } = pruneDisconnectedDynamicPorts(nodes, nextEdges, removedForPrune)

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
      for (const id of prunedDynamicNodes) {
        const node = nextNodes.find(n => n.id === id)
        if (!node) continue
        if (node.data.type === 'Subnet' && node.data.subgraph) {
          await api.updateSubgraph(id, node.data.subgraph.node_meta, node.data.subgraph.edges)
        }
      }
    }

    set(s => ({
      nodes: nextNodes,
      edges: nextEdges,
      ...markActiveTabDirty(s),
    }))
  },

  copySelection: () => {
    const { nodes, edges, selectedId } = get()
    let selectedNodes = nodes.filter(n => n.selected)
    if (selectedNodes.length === 0 && selectedId) {
      selectedNodes = nodes.filter(n => n.id === selectedId)
    }
    if (selectedNodes.length === 0) return null

    const selectedIds = new Set(selectedNodes.map(n => n.id))
    return {
      nodes: cloneDeep(selectedNodes),
      edges: cloneDeep(edges.filter(e => selectedIds.has(e.source) && selectedIds.has(e.target))),
    }
  },

  pasteClipboard: async (clipboard, targetPos) => {
    if (clipboard.nodes.length === 0) return
    const { subnetStack } = get()
    set(s => pushUndoSnapshot(s))
    dragUndoActive = false

    const minX = Math.min(...clipboard.nodes.map(n => n.position.x))
    const minY = Math.min(...clipboard.nodes.map(n => n.position.y))
    const pastedSourceIds = new Set(clipboard.nodes.map(n => n.id))
    const idMap: Record<string, string> = {}
    const pastedNodes: Node<NodeData>[] = []

    for (const source of clipboard.nodes) {
      const x = targetPos.x + source.position.x - minX
      const y = targetPos.y + source.position.y - minY
      const meta = await api.addNode(
        source.data.type,
        [x, y],
        cloneDeep(source.data.params ?? {}),
      )
      const cloneMeta = SUBGRAPH_NODE_TYPES.has(source.data.type)
        ? await api.updateSubgraph(
            meta.id,
            cloneDeep(source.data.subgraph?.node_meta ?? {}),
            cloneDeep(source.data.subgraph?.edges ?? []),
          )
        : meta
      idMap[source.id] = cloneMeta.id

      const pasted = makeReactNode({ ...cloneMeta, pos: [x, y] })
      pastedNodes.push({
        ...pasted,
        style: cloneDeep(source.style),
        selected: true,
        data: subnetStack.length > 0
          ? {
              ...pasted.data,
              inputs: cloneDeep(source.data.inputs ?? pasted.data.inputs),
              outputs: cloneDeep(source.data.outputs ?? pasted.data.outputs),
              input_types: cloneDeep(source.data.input_types ?? pasted.data.input_types),
              output_types: cloneDeep(source.data.output_types ?? pasted.data.output_types),
              input_defaults: cloneDeep(source.data.input_defaults ?? pasted.data.input_defaults),
              ...(source.data.multi_input_ports ? { multi_input_ports: cloneDeep(source.data.multi_input_ports) } : {}),
              ...(source.data.subgraph ? { subgraph: cloneDeep(source.data.subgraph) } : {}),
              pos: [x, y],
            }
          : pasted.data,
      })
    }

    const pastedEdges: Edge[] = clipboard.edges
      .filter(e => pastedSourceIds.has(e.source) && pastedSourceIds.has(e.target) && e.sourceHandle && e.targetHandle)
      .map(e => ({
        ...cloneDeep(e),
        id: nextEdgeId(),
        source: idMap[e.source],
        target: idMap[e.target],
      }))
      .filter(e => e.source && e.target)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const live = get()
      const nextEdges = [...live.edges, ...pastedEdges]
      const nextNodes = ensureConnectedToolBoxSlots([
        ...live.nodes.map(n => ({ ...n, selected: false })),
        ...pastedNodes,
      ], nextEdges)
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })

      await api.updateSubgraph(frame.subnetId, innerMeta, flowEdgesToBackend(nextEdges))
      for (const pasted of pastedNodes) {
        await api.removeNode(pasted.id)
      }

      set(s => ({
        nodes: nextNodes,
        edges: nextEdges,
        selectedId: pastedNodes[0]?.id ?? null,
        ...markActiveTabDirty(s),
      }))
      return
    }

    for (const edge of pastedEdges) {
      if (edge.source && edge.sourceHandle && edge.target && edge.targetHandle) {
        await api.connect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
      }
    }

    const live = get()
    const nextEdges = [...live.edges, ...pastedEdges]
    const nextNodes = ensureConnectedToolBoxSlots([
      ...live.nodes.map(n => ({ ...n, selected: false })),
      ...pastedNodes,
    ], nextEdges)
    set(s => ({
      nodes: nextNodes,
      edges: nextEdges,
      selectedId: pastedNodes[0]?.id ?? null,
      ...markActiveTabDirty(s),
    }))
  },

  beginAltDragCopy: async (nodeIds, originalPositions) => {
    const { nodes, edges, subnetStack } = get()
    const copyIds = new Set(nodeIds)
    const sourceNodes = nodes.filter(n => copyIds.has(n.id))
    if (sourceNodes.length === 0) return null

    set(s => pushUndoSnapshot(s))
    dragUndoActive = true

    const idMap: Record<string, string> = {}
    const cloneNodes: Node<NodeData>[] = []

    for (const source of sourceNodes) {
      const start = originalPositions[source.id] ?? source.position
      const meta = await api.addNode(
        source.data.type,
        [start.x, start.y],
        cloneDeep(source.data.params ?? {}),
      )
      const cloneMeta = SUBGRAPH_NODE_TYPES.has(source.data.type)
        ? await api.updateSubgraph(
            meta.id,
            cloneDeep(source.data.subgraph?.node_meta ?? {}),
            cloneDeep(source.data.subgraph?.edges ?? []),
          )
        : meta
      idMap[source.id] = cloneMeta.id
      cloneNodes.push({
        ...makeReactNode({ ...cloneMeta, pos: [start.x, start.y] }),
        style: cloneDeep(source.style),
        selected: false,
      })
    }

    const cloneEdges: Edge[] = edges
      .filter(e => copyIds.has(e.source) && copyIds.has(e.target) && e.sourceHandle && e.targetHandle)
      .map(e => ({
        ...cloneDeep(e),
        id: nextEdgeId(),
        source: idMap[e.source],
        target: idMap[e.target],
      }))
      .filter(e => e.source && e.target)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const live = get()
      const nextEdges = [...live.edges, ...cloneEdges]
      const nextNodes = ensureConnectedToolBoxSlots([...live.nodes, ...cloneNodes], nextEdges)
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      const innerEdges = flowEdgesToBackend(nextEdges)

      await api.updateSubgraph(frame.subnetId, innerMeta, innerEdges)
      for (const clone of cloneNodes) {
        await api.removeNode(clone.id)
      }

      set(s => ({
        nodes: nextNodes,
        edges: nextEdges,
        ...markActiveTabDirty(s),
      }))
      return idMap
    }

    for (const edge of cloneEdges) {
      if (edge.source && edge.sourceHandle && edge.target && edge.targetHandle) {
        await api.connect(edge.source, edge.sourceHandle, edge.target, edge.targetHandle)
      }
    }

    const live = get()
    const nextEdges = [...live.edges, ...cloneEdges]
    const nextNodes = ensureConnectedToolBoxSlots([...live.nodes, ...cloneNodes], nextEdges)
    set(s => ({
      nodes: nextNodes,
      edges: nextEdges,
      ...markActiveTabDirty(s),
    }))
    return idMap
  },

  finishAltDragCopy: async (nodeIds, originalPositions, copyIdMap) => {
    if (!copyIdMap) return
    const { nodes, edges, subnetStack } = get()
    const sourceIds = new Set(nodeIds)
    const cloneIds = new Set(Object.values(copyIdMap))
    const sourceNodes = nodes.filter(n => sourceIds.has(n.id))
    const cloneNodes = nodes.filter(n => cloneIds.has(n.id))
    if (sourceNodes.length === 0 || cloneNodes.length === 0) return

    const moved = sourceNodes.some(n => {
      const start = originalPositions[n.id]
      return start && (Math.abs(n.position.x - start.x) > 2 || Math.abs(n.position.y - start.y) > 2)
    })

    if (!moved) {
      const nextEdges = edges.filter(e => !cloneIds.has(e.source) && !cloneIds.has(e.target))
      const nextNodes = nodes.filter(n => !cloneIds.has(n.id))
      if (subnetStack.length > 0) {
        const frame = subnetStack[subnetStack.length - 1]
        const innerMeta: Record<string, any> = {}
        nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
        await api.updateSubgraph(frame.subnetId, innerMeta, flowEdgesToBackend(nextEdges))
      } else {
        for (const cloneId of cloneIds) {
          await api.removeNode(cloneId)
        }
      }
      set(s => ({ nodes: nextNodes, edges: nextEdges, ...markActiveTabDirty(s) }))
      return
    }

    const destinationByClone = new Map<string, { x: number; y: number }>()
    sourceNodes.forEach(source => {
      const cloneId = copyIdMap[source.id]
      if (cloneId) destinationByClone.set(cloneId, { x: source.position.x, y: source.position.y })
    })

    const nextNodes = ensureConnectedToolBoxSlots(nodes.map(n => {
      const start = originalPositions[n.id]
      if (start) {
        return {
          ...n,
          position: { x: start.x, y: start.y },
          data: { ...n.data, pos: [start.x, start.y] as [number, number] },
          selected: false,
        }
      }
      const destination = destinationByClone.get(n.id)
      if (destination) {
        return {
          ...n,
          position: { x: destination.x, y: destination.y },
          data: { ...n.data, pos: [destination.x, destination.y] as [number, number] },
          selected: true,
        }
      }
      return n
    }), edges)

    if (subnetStack.length > 0) {
      const frame = subnetStack[subnetStack.length - 1]
      const innerMeta: Record<string, any> = {}
      nextNodes.forEach(n => { innerMeta[n.id] = { ...n.data, pos: [n.position.x, n.position.y] } })
      await api.updateSubgraph(frame.subnetId, innerMeta, flowEdgesToBackend(edges))
    } else {
      await Promise.all(nextNodes.map(n => {
        if (sourceIds.has(n.id) || cloneIds.has(n.id)) {
          return api.updatePos(n.id, [n.position.x, n.position.y])
        }
        return Promise.resolve()
      }))
    }

    set(s => ({
      nodes: nextNodes,
      edges,
      selectedId: Object.values(copyIdMap)[0] ?? null,
      ...markActiveTabDirty(s),
    }))
  },

  updateParam: async (id, key, value) => {
    const node = get().nodes.find(n => n.id === id)
    if (!node || node.data.params?.[key] === value) return
    set(s => pushUndoSnapshot(s))
    await api.updateParam(id, key, value)
    set(s => ({
      nodes: s.nodes.map(n =>
        n.id === id ? { ...n, data: { ...n.data, params: { ...n.data.params, [key]: value } } } : n
      ),
      ...markActiveTabDirty(s),
    }))
  },

  cookNode: async (id, port = 'output') => {
    const stack = get().subnetStack
    const activeSubnetId = stack.length > 0 ? stack[stack.length - 1].subnetId : null
    const startNode = get().nodes.find(n => n.id === id)
    const liveRunId = `live-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const liveStartedAt = new Date().toISOString()
    const liveEvents: RunRecord['events'] = []
    let liveReplayDelay = 0
    const queueLiveReplay = (event: CookEvent) => {
      const stamped = { ...event, ts: new Date().toISOString() }
      liveEvents.push(stamped)
      const eventIndex = liveEvents.length - 1
      const record: RunRecord = {
        run_id: liveRunId,
        started_at: liveStartedAt,
        finished_at: stamped.type === 'done' ? stamped.ts as string : null,
        duration_ms: null,
        status: stamped.type === 'done' ? (stamped.error ? 'error' : 'success') : 'running',
        node_id: id,
        port,
        node_type: startNode?.data.type ?? '',
        node_count: new Set(liveEvents.map(e => stringValue(e.node_id)).filter(Boolean)).size,
        model_calls: liveEvents.filter(e => e.type === 'model_call').length,
        tool_calls: liveEvents.filter(e => e.type === 'tool_call').length,
        cached_nodes: liveEvents.filter(e => e.type === 'success' && Boolean(e.cached)).length,
        events: liveEvents.slice(),
        value: stamped.type === 'done' ? stamped.value : undefined,
        error: stamped.type === 'done' && stamped.error ? stringValue(stamped.error) : undefined,
      }
      const delay = liveReplayDelay
      liveReplayDelay += 170
      window.setTimeout(() => {
        if (get().runReplay.runId !== liveRunId) return
        get().applyRunReplay(record, eventIndex, stamped.type !== 'done')
      }, delay)
    }
    const applyCookEvent = (event: CookEvent) => {
      queueLiveReplay(event)
      if (event.type === 'done') {
        set(s => ({
          cookActive: false,
          cookLog: appendCookLog(s.cookLog, cookEventLogEntry(event, s.nodes)),
          nodes: s.nodes.map(n => ({
            ...n,
            data: { ...n.data, cooking: false },
          })),
        }))
        return
      }
      if (event.type === 'model_call' || event.type === 'tool_call') {
        set(s => ({
          cookLog: appendCookLog(s.cookLog, cookEventLogEntry(event, s.nodes)),
        }))
        return
      }
      set(s => ({
        cookActive: true,
        cookLog: appendCookLog(s.cookLog, cookEventLogEntry(event, s.nodes)),
        nodes: s.nodes.map(n => {
          if (n.id !== event.node_id) return n
          if (event.type === 'start') {
            return {
              ...n,
              data: {
                ...n.data,
                cooking: true,
                cookError: undefined,
                cookResult: undefined,
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
      cookActive: true,
      runReplay: {
        runId: liveRunId,
        cursor: -1,
        total: 0,
        playing: true,
        currentNodeId: id,
        currentEventType: 'queued',
        message: `Queued ${nodeRunLabel(s.nodes, id)}.${port}`,
      },
      cookLog: [{
        id: `${Date.now()}-${id}-queued`,
        kind: 'start',
        label: nodeRunLabel(s.nodes, id),
        message: `Queued ${nodeRunLabel(s.nodes, id)}.${port}`,
        nodeId: id,
        port,
        ts: Date.now(),
      }],
      nodes: s.nodes.map(n => ({
        ...n,
        data: {
          ...clearReplayData(n.data),
          cooking: n.id === id,
          cookError: undefined,
          cookResult: undefined,
          cookPort: n.id === id ? port : undefined,
        },
      })),
    }))

    try {
      if (activeSubnetId) {
        await api.cookSubgraphStream(activeSubnetId, id, port, applyCookEvent)
      } else {
        await api.cookStream(id, port, applyCookEvent)
      }
    } catch (e: any) {
      set(s => ({
        cookActive: false,
        cookLog: appendCookLog(s.cookLog, {
          id: `${Date.now()}-${id}-client-error`,
          kind: 'error',
          label: nodeRunLabel(s.nodes, id),
          message: `${nodeRunLabel(s.nodes, id)}.${port} error: ${e.message}`,
          nodeId: id,
          port,
          ts: Date.now(),
        }),
        nodes: s.nodes.map(n =>
          n.id === id ? { ...n, data: { ...n.data, cooking: false, cookError: e.message, cookPort: port } } : n
        ),
      }))
    }
  },

  applyRunReplay: (record, cursor, playing) => {
    const total = record.events.length
    const nextCursor = total > 0 ? Math.min(Math.max(cursor, 0), total - 1) : -1
    const currentEvent = nextCursor >= 0 ? record.events[nextCursor] : undefined
    const currentNodeId = eventNodeId(currentEvent) || (currentEvent?.type === 'done' ? record.node_id : undefined)
    const patches = nextCursor >= 0 ? buildReplayPatches(record, nextCursor) : new Map<string, ReplayNodePatch>()
    const status = currentEvent?.type ? String(currentEvent.type) : undefined
    const message = currentEvent
      ? [status, currentNodeId ? nodeRunLabel(get().nodes, currentNodeId) : '', eventPort(currentEvent) ?? record.port]
          .filter(Boolean)
          .join(' / ')
      : undefined

    set(s => ({
      runReplay: {
        runId: record.run_id,
        cursor: nextCursor,
        total,
        playing,
        currentNodeId,
        currentEventType: status,
        message,
      },
      nodes: s.nodes.map(node => ({
        ...node,
        data: {
          ...clearReplayData(node.data),
          ...patches.get(node.id),
        },
      })),
    }))
  },

  clearRunReplay: () => {
    set(s => ({
      runReplay: EMPTY_REPLAY,
      nodes: s.nodes.map(node => ({
        ...node,
        data: clearReplayData(node.data),
      })),
    }))
  },

  selectNode: (id) => set({ selectedId: id }),

  undoGraph: async () => {
    const { undoHistory, activeTabId } = get()
    let idx = undoHistory.length - 1
    while (idx >= 0 && undoHistory[idx].activeTabId !== activeTabId) idx--
    if (idx < 0) return

    const snapshot = undoHistory[idx]
    await api.setGraph(snapshot.graph.nodes, snapshot.graph.edges)
    dragUndoActive = false
    set(s => ({
      nodes: cloneDeep(snapshot.nodes),
      edges: cloneDeep(snapshot.edges),
      subnetStack: cloneDeep(snapshot.subnetStack),
      selectedId: snapshot.selectedId,
      undoHistory: undoHistory.slice(0, idx),
      ...markActiveTabDirty(s),
    }))
  },

  reset: async () => {
    set(s => pushUndoSnapshot(s))
    await api.reset()
    set(s => ({ nodes: [], edges: [], selectedId: null, ...markActiveTabDirty(s) }))
  },
}))
