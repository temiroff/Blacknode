// value nodes each use their port color as header — see headerColor() below
export const CATEGORIES: Record<string, { color: string; nodes: string[] }> = {
  Values:   { color: '#6b7280', nodes: ['Text', 'Float', 'Int', 'Bool', 'Dict'] },
  AI:       { color: '#6366f1', nodes: [
    'Model', 'LLMAgent', 'AgentLoop', 'VisualAgentLoop',
    'AgentMessages', 'AgentChatStep', 'ToolDispatch',
    'AgentAppendMessages', 'AgentStopCheck', 'AgentFinalAnswer',
    'EmbedText',
  ] },
  Tools:    { color: '#14b8a6', nodes: ['PythonFn', 'SubnetAsTool', 'ToolBox', 'ToolCall'] },
  Math:     { color: '#22c55e', nodes: ['Add', 'Subtract', 'Multiply', 'Divide'] },
  Flow:     { color: '#d97706', nodes: ['Branch', 'Switch', 'Gate', 'Map', 'Filter', 'Reduce', 'ForEach'] },
  IO:       { color: '#0891b2', nodes: ['FileRead', 'FileWrite', 'HTTPGet', 'JSONParse', 'JSONDump'] },
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
