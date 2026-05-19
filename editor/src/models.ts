export interface ModelOption {
  label: string
  value: string  // full prefixed model string that routes through the provider registry
}

export interface ModelGroup {
  provider: string
  color: string
  models: ModelOption[]
}

export interface ModelProvider {
  id: string
  label: string
  color: string
  apiKeyProvider: string
  prefix: string
  placeholder: string
  help: string
}

export const MODEL_PROVIDERS: ModelProvider[] = [
  {
    id: 'anthropic',
    label: 'Anthropic',
    color: '#d97706',
    apiKeyProvider: 'Anthropic',
    prefix: '',
    placeholder: 'claude-...',
    help: 'Use the exact Anthropic model id.',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    color: '#19c37d',
    apiKeyProvider: 'OpenAI',
    prefix: '',
    placeholder: 'gpt-...',
    help: 'Use OpenAI model ids directly.',
  },
  {
    id: 'nim',
    label: 'NVIDIA NIM',
    color: '#76b900',
    apiKeyProvider: 'NVIDIA NIM',
    prefix: 'nim:',
    placeholder: 'nvidia/...',
    help: 'Enter the NIM model path without nim:; the node adds it.',
  },
  {
    id: 'ollama',
    label: 'Ollama',
    color: '#a855f7',
    apiKeyProvider: 'Ollama (local)',
    prefix: 'ollama:',
    placeholder: 'llama3.2',
    help: 'Enter the local Ollama model name without ollama:.',
  },
]

export const MODEL_GROUPS: ModelGroup[] = [
  {
    provider: 'Anthropic',
    color: '#d97706',
    models: [
      { label: 'claude-sonnet-4-6',  value: 'claude-sonnet-4-6' },
    ],
  },
  {
    provider: 'OpenAI',
    color: '#19c37d',
    models: [
      { label: 'gpt-4o',       value: 'gpt-4o' },
      { label: 'gpt-4o-mini',  value: 'gpt-4o-mini' },
    ],
  },
  {
    provider: 'NVIDIA NIM',
    color: '#76b900',
    models: [
      { label: 'llama-3.1-8b',        value: 'nim:meta/llama-3.1-8b-instruct' },
      { label: 'nemotron-super-49b',   value: 'nim:nvidia/llama-3.3-nemotron-super-49b-v1' },
    ],
  },
  {
    provider: 'Ollama (local)',
    color: '#a855f7',
    models: [
      { label: 'llama3.2',   value: 'ollama:llama3.2' },
      { label: 'mistral',    value: 'ollama:mistral' },
    ],
  },
]

// flat map: value → group color
const _colorMap: Record<string, string> = {}
for (const g of MODEL_GROUPS) {
  for (const m of g.models) _colorMap[m.value] = g.color
}

export function modelProviderColor(value: string): string {
  if (_colorMap[value]) return _colorMap[value]
  return modelProviderForValue(value).color
}

export function modelProviderForValue(value: string): ModelProvider {
  if (value.startsWith('nim:')) return MODEL_PROVIDERS.find(p => p.id === 'nim')!
  if (value.startsWith('ollama:')) return MODEL_PROVIDERS.find(p => p.id === 'ollama')!
  if (value.startsWith('claude')) return MODEL_PROVIDERS.find(p => p.id === 'anthropic')!
  if (value.startsWith('gpt') || value.startsWith('o1') || value.startsWith('o3') || value.startsWith('o4') || value.startsWith('chatgpt') || value.startsWith('text-') || value.startsWith('ft:gpt')) {
    return MODEL_PROVIDERS.find(p => p.id === 'openai')!
  }
  return {
    id: 'custom',
    label: 'Custom',
    color: '#6b7280',
    apiKeyProvider: 'OpenAI',
    prefix: '',
    placeholder: 'model-id',
    help: 'Unknown provider; routed as OpenAI-compatible by the backend.',
  }
}

export function modelProviderName(value: string): string {
  for (const g of MODEL_GROUPS) {
    if (g.models.some(m => m.value === value)) return g.provider
  }
  const provider = modelProviderForValue(value)
  return provider.id === 'ollama' ? 'Ollama (local)' : provider.label
}

export function modelProviderById(id: string): ModelProvider {
  return MODEL_PROVIDERS.find(p => p.id === id) ?? modelProviderForValue('')
}

export function modelNameForProvider(value: string, providerId = modelProviderForValue(value).id): string {
  const provider = modelProviderById(providerId)
  return provider.prefix && value.startsWith(provider.prefix)
    ? value.slice(provider.prefix.length)
    : value
}

export function modelValueForProvider(providerId: string, modelName: string): string {
  const provider = modelProviderById(providerId)
  const clean = modelName.trim()
  if (!clean) return ''
  if (provider.prefix && clean.startsWith(provider.prefix)) return clean
  if (!provider.prefix && (clean.startsWith('nim:') || clean.startsWith('ollama:'))) return clean
  return `${provider.prefix}${clean}`
}

export function starterModelsForProvider(providerId: string): ModelOption[] {
  const provider = modelProviderById(providerId)
  const group = MODEL_GROUPS.find(g => g.provider === provider.apiKeyProvider || g.provider === provider.label)
  return group?.models ?? []
}

export function savedModelsForProvider(models: string[], providerId: string): string[] {
  return models.filter(value => modelProviderForValue(value).id === providerId)
}

export function modelDisplayName(value: string): string {
  const known = MODEL_GROUPS.flatMap(g => g.models).find(m => m.value === value)
  if (known) return known.label
  return modelNameForProvider(value)
}

export function isKnownStarterModel(value: string): boolean {
  return MODEL_GROUPS.some(g => g.models.some(m => m.value === value))
}

export function shouldShowApiKeyForProvider(id: string): boolean {
  return modelProviderById(id).apiKeyProvider !== 'Ollama (local)'
}

export function providerIdForModelValue(value: string): string {
  return modelProviderForValue(value).id === 'custom' ? 'openai' : modelProviderForValue(value).id
}

export function providerHelpById(id: string): string {
  return modelProviderById(id).help
}

export function providerPlaceholderById(id: string): string {
  return modelProviderById(id).placeholder
}

export function modelProviderApiKeyNameById(id: string): string {
  return modelProviderById(id).apiKeyProvider
}

export function routeHintForProvider(id: string): string {
  const provider = modelProviderById(id)
  return provider.prefix ? `stored as ${provider.prefix}<model>` : 'stored as typed'
}

export const DEFAULT_MODEL = 'claude-sonnet-4-6'
