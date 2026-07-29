import { PYTHON_TOOL_TYPES } from './pythonToolPresets'

// value nodes each use their port color as header — see headerColor() below
export const CATEGORIES: Record<string, { color: string; nodes: string[] }> = {
  Values:   { color: '#6b7280', nodes: ['Text', 'Float', 'Int', 'Bool', 'Color', 'List', 'Dict'] },
  AI:       { color: '#6366f1', nodes: [
    'Model', 'LLMAgent', 'AgentLoop', 'VisualAgentLoop',
    'AgentMessages', 'AgentChatStep', 'ToolDispatch',
    'AgentIteration', 'AgentAppendMessages', 'AgentStopCheck', 'AgentFinalAnswer',
    'TrajectoryRecorder', 'RateOutput', 'EmbedText', 'LLMModelRouter',
  ] },
  Image:    { color: '#fb7185', nodes: ['LoadImage', 'OutputImage'] },
  // CUDA compute nodes (CUDAKernelLab, TensorCoreGEMM, ...) ship in the
  // blacknode-cuda extension package and color themselves via its manifest.
  NVIDIA:   { color: '#76b900', nodes: [
    'NVIDIASystemCheck', 'NIMDockerCommand',
    'NIMHealthCheck', 'NIMAgent', 'NIMBenchmark', 'NIMFineTune', 'NIMFineTuneStatus', 'VideoFolderInput',
    'NIMQueryRewrite', 'NVIDIAEmbedding', 'NVIDIAVectorSearch', 'NVIDIARerank',
    'NIMCitationAnswer', 'RetrievalCompare',
  ] },
  // Advisory nodes design/plan an NVIDIA pipeline as text — they run no
  // inference (no Cosmos/VLM, NeMo Retriever, or NIM call). Muted green so the
  // palette reads them as planning aids, distinct from the executing NVIDIA nodes.
  'NVIDIA Advisory': { color: '#5a7d1e', nodes: [
    'NVIDIABlueprintPlan', 'NVIDIADeploymentChoice', 'NVIDIAVideoSummaryPlan',
    'NVIDIARetrieverIndexPlan', 'NVIDIAQuestionAnswerPlan', 'NVIDIAMissionReport',
  ] },
  Tools:    { color: '#14b8a6', nodes: ['PythonFn', 'SubnetAsTool', 'ToolBox', 'ToolCall'] },
  PythonTools: { color: '#0ea5e9', nodes: PYTHON_TOOL_TYPES },
  Search:   { color: '#ec4899', nodes: ['WebSearchURL', 'SearchResultExtractor', 'SearchResultsFormat'] },
  RAG:      { color: '#f97316', nodes: ['TextChunker', 'KeywordIndex', 'KeywordSearch', 'RAGContext'] },
  Database: { color: '#a855f7', nodes: ['SQLiteQuery', 'SQLiteExec'] },
  API:      { color: '#06b6d4', nodes: ['HTTPRequest', 'APIRequestBuilder'] },
  Integrations: { color: '#4a90d9', nodes: ['SlackMessage', 'SlackReply', 'TelegramMessage', 'TelegramReply', 'ConversationMemory'] },
  Learned:  { color: '#a78bfa', nodes: [] },
  Math:     { color: '#22c55e', nodes: ['Add', 'Subtract', 'Multiply', 'Divide'] },
  Flow:     { color: '#d97706', nodes: ['Branch', 'Switch', 'Gate', 'Map', 'Filter', 'Reduce', 'ForEach', 'ListIndex'] },
  IO:       { color: '#0891b2', nodes: ['FileRead', 'FileWrite', 'DirectoryList', 'FileInfo', 'CSVRead', 'CSVWrite', 'HTTPGet', 'JSONParse', 'JSONDump'] },
  Core:     { color: '#374151', nodes: ['Literal', 'Print', 'Concat'] },
  Output:   { color: '#ec4899', nodes: ['Output'] },
  Subnet:   { color: '#6366f1', nodes: ['SubnetInput', 'SubnetOutput'] },
}

export const VALUE_NODE_TYPES = new Set(CATEGORIES.Values.nodes)

// TestUI uses one stable family palette across nodes, the palette, templates,
// and search surfaces. Package manifests remain the source of truth for the
// standard interface; these colors are the visual-language experiment.
export const FAMILY_COLORS: Record<string, string> = {
  Core: '#06b6d4',
  Robot: '#14b8a6',
  Perception: '#22c55e',
  Camera: '#22c55e',
  Tracking: '#22c55e',
  Detection: '#22c55e',
  'ROS 2': '#3b82f6',
  ROS2: '#3b82f6',
  'NVIDIA CUDA': '#84cc16',
  NVIDIA: '#84cc16',
  CUDA: '#84cc16',
  Agent: '#a855f7',
  AI: '#a855f7',
  Controllers: '#f97316',
  Controller: '#f97316',
  Motion: '#f97316',
  Drivers: '#64748b',
  Driver: '#64748b',
  Output: '#ec4899',
  Values: '#f59e0b',
  Dataset: '#6366f1',
}

export const PACKAGE_FAMILY_NAMES: Record<string, string> = {
  'blacknode-agent': 'Agent',
  'blacknode-motion': 'Motion',
  'blacknode-cuda': 'CUDA',
  'blacknode-dataset': 'Dataset',
  'blacknode-drivers': 'Drivers',
  'blacknode-isaac': 'Isaac Sim',
  'blacknode-perception': 'Perception',
  'blacknode-robot': 'Robot',
  'blacknode-ros2': 'ROS2',
  'blacknode-skills': 'Skills',
  'blacknode-training': 'Training',
}

export function packageFamilyName(name: string): string {
  if (PACKAGE_FAMILY_NAMES[name]) return PACKAGE_FAMILY_NAMES[name]
  return name
    .replace(/^blacknode-/, '')
    .split(/[-_]/)
    .filter(Boolean)
    .map(part => part[0]?.toUpperCase() + part.slice(1))
    .join(' ')
}

export function familyColor(category: string, fallback: string): string {
  const exact = FAMILY_COLORS[category]
  if (exact) return exact
  const normalized = category.toLowerCase()
  const match = Object.entries(FAMILY_COLORS).find(([name]) => normalized.includes(name.toLowerCase()))
  return match?.[1] ?? fallback
}

// node type → header color, derived from CATEGORIES
const _nodeColor: Record<string, string> = {}
for (const { color, nodes } of Object.values(CATEGORIES)) {
  for (const n of nodes) _nodeColor[n] = color
}

// Value nodes use their own port color so each type is visually distinct
const VALUE_HEADER_COLORS: Record<string, string> = {
  Text:  '#f59e0b',
  Int:   '#22c55e',
  Float: '#06b6d4',
  Bool:  '#e879f9',
  Color: '#e11d48',
  List:  '#f97316',
  Dict:  '#a855f7',
}

// Colors for node types that arrive from extension packages, populated from
// /node-defs at runtime (def.color comes from the package manifest).
const _dynamicNodeColor: Record<string, string> = {}
const _dynamicNodeFamilyColor: Record<string, string> = {}

export function registerDynamicColors(defs: Record<string, { category?: string; color?: string }>) {
  for (const [type, def] of Object.entries(defs)) {
    const color = def.color || (def.category ? CATEGORIES[def.category]?.color : undefined)
    if (!_nodeColor[type] && color) _dynamicNodeColor[type] = color
    _dynamicNodeFamilyColor[type] = familyColor(def.category || type, color || '#1f2937')
  }
}

export function headerColor(type: string): string {
  return VALUE_HEADER_COLORS[type] ?? _nodeColor[type] ?? _dynamicNodeColor[type] ?? '#1f2937'
}

export function nodeFamilyColor(type: string, fallback = headerColor(type)): string {
  if (_dynamicNodeFamilyColor[type]) return _dynamicNodeFamilyColor[type]
  const category = Object.entries(CATEGORIES).find(([, value]) => value.nodes.includes(type))?.[0] || type
  return familyColor(category, fallback)
}
