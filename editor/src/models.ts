export interface ModelOption {
  label: string
  value: string  // full prefixed model string that routes through the provider registry
}

export interface ModelGroup {
  provider: string
  color: string
  models: ModelOption[]
}

export const MODEL_GROUPS: ModelGroup[] = [
  {
    provider: 'Anthropic',
    color: '#d97706',
    models: [
      { label: 'claude-opus-4-7',    value: 'claude-opus-4-7' },
      { label: 'claude-sonnet-4-6',  value: 'claude-sonnet-4-6' },
      { label: 'claude-haiku-4-5',   value: 'claude-haiku-4-5-20251001' },
    ],
  },
  {
    provider: 'OpenAI',
    color: '#19c37d',
    models: [
      { label: 'gpt-4o',       value: 'gpt-4o' },
      { label: 'gpt-4o-mini',  value: 'gpt-4o-mini' },
      { label: 'o1',           value: 'o1' },
      { label: 'o3-mini',      value: 'o3-mini' },
      { label: 'o4-mini',      value: 'o4-mini' },
    ],
  },
  {
    provider: 'NVIDIA NIM',
    color: '#76b900',
    models: [
      { label: 'nemotron-70b',    value: 'nim:nvidia/llama-3.1-nemotron-70b-instruct' },
      { label: 'llama-3.1-8b',    value: 'nim:meta/llama-3.1-8b-instruct' },
      { label: 'llama-3.1-70b',   value: 'nim:meta/llama-3.1-70b-instruct' },
      { label: 'llama-3.1-405b',  value: 'nim:meta/llama-3.1-405b-instruct' },
      { label: 'llama-3.2-3b',    value: 'nim:meta/llama-3.2-3b-instruct' },
      { label: 'deepseek-r1',     value: 'nim:deepseek-ai/deepseek-r1' },
      { label: 'mixtral-8x7b',    value: 'nim:mistralai/mixtral-8x7b-instruct-v0.1' },
      { label: 'phi-3-mini',      value: 'nim:microsoft/phi-3-mini-128k-instruct' },
      { label: 'gemma-2-27b',     value: 'nim:google/gemma-2-27b-it' },
      { label: 'qwen2.5-72b',     value: 'nim:qwen/qwen2.5-72b-instruct' },
    ],
  },
  {
    provider: 'Ollama (local)',
    color: '#a855f7',
    models: [
      { label: 'llama3.2',   value: 'ollama:llama3.2' },
      { label: 'llama3.1',   value: 'ollama:llama3.1' },
      { label: 'mistral',    value: 'ollama:mistral' },
      { label: 'phi3',       value: 'ollama:phi3' },
      { label: 'gemma2',     value: 'ollama:gemma2' },
      { label: 'codellama',  value: 'ollama:codellama' },
      { label: 'deepseek-r1', value: 'ollama:deepseek-r1' },
    ],
  },
]

// flat map: value → group color
const _colorMap: Record<string, string> = {}
for (const g of MODEL_GROUPS) {
  for (const m of g.models) _colorMap[m.value] = g.color
}

export function modelProviderColor(value: string): string {
  return _colorMap[value] ?? '#6b7280'
}

export function modelProviderName(value: string): string {
  for (const g of MODEL_GROUPS) {
    if (g.models.some(m => m.value === value)) return g.provider
  }
  return 'Custom'
}

export const DEFAULT_MODEL = 'claude-sonnet-4-6'
