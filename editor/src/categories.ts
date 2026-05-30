import { PYTHON_TOOL_TYPES } from './pythonToolPresets'

// value nodes each use their port color as header — see headerColor() below
export const CATEGORIES: Record<string, { color: string; nodes: string[] }> = {
  Values:   { color: '#6b7280', nodes: ['Text', 'Float', 'Int', 'Bool', 'Dict'] },
  AI:       { color: '#6366f1', nodes: [
    'Model', 'LLMAgent', 'AgentLoop', 'VisualAgentLoop',
    'AgentMessages', 'AgentChatStep', 'ToolDispatch',
    'AgentIteration', 'AgentAppendMessages', 'AgentStopCheck', 'AgentFinalAnswer',
    'EmbedText', 'LLMModelRouter',
  ] },
  Image:    { color: '#fb7185', nodes: ['LoadImage', 'OutputImage'] },
  NVIDIA:   { color: '#76b900', nodes: [
    'CUDAKernelLab', 'CUDACustomKernel', 'CUDAImageFilter', 'GPUCapability', 'GPURequirement',
    'NVIDIASystemCheck', 'NVIDIABlueprintPlan', 'NIMDockerCommand',
    'NIMHealthCheck', 'NIMAgent', 'NIMBenchmark', 'VideoFolderInput',
    'NVIDIADeploymentChoice', 'NVIDIAVideoSummaryPlan',
    'NVIDIARetrieverIndexPlan', 'NVIDIAQuestionAnswerPlan',
    'NVIDIAMissionReport',
  ] },
  Tools:    { color: '#14b8a6', nodes: ['PythonFn', 'SubnetAsTool', 'ToolBox', 'ToolCall'] },
  PythonTools: { color: '#0ea5e9', nodes: PYTHON_TOOL_TYPES },
  Search:   { color: '#ec4899', nodes: ['WebSearchURL', 'SearchResultExtractor', 'SearchResultsFormat'] },
  RAG:      { color: '#f97316', nodes: ['TextChunker', 'KeywordIndex', 'KeywordSearch', 'RAGContext'] },
  Database: { color: '#a855f7', nodes: ['SQLiteQuery', 'SQLiteExec'] },
  API:      { color: '#06b6d4', nodes: ['HTTPRequest', 'APIRequestBuilder'] },
  Learned:  { color: '#a78bfa', nodes: [] },
  Math:     { color: '#22c55e', nodes: ['Add', 'Subtract', 'Multiply', 'Divide'] },
  Flow:     { color: '#d97706', nodes: ['Branch', 'Switch', 'Gate', 'Map', 'Filter', 'Reduce', 'ForEach'] },
  IO:       { color: '#0891b2', nodes: ['FileRead', 'FileWrite', 'DirectoryList', 'FileInfo', 'CSVRead', 'CSVWrite', 'HTTPGet', 'JSONParse', 'JSONDump'] },
  Core:     { color: '#374151', nodes: ['Literal', 'Print', 'Concat'] },
  Output:   { color: '#8b5cf6', nodes: ['Output'] },
  Subnet:   { color: '#6366f1', nodes: ['SubnetInput', 'SubnetOutput'] },
}

export const VALUE_NODE_TYPES = new Set(CATEGORIES.Values.nodes)

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
  Dict:  '#a855f7',
}

export function headerColor(type: string): string {
  return VALUE_HEADER_COLORS[type] ?? _nodeColor[type] ?? '#1f2937'
}
