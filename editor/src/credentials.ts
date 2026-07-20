export const NVIDIA_API_KEY_PROVIDER = 'NVIDIA NIM'
export const HUGGING_FACE_API_KEY_PROVIDER = 'Hugging Face'

const NVIDIA_CREDENTIAL_NODE_TYPES = new Set([
  'NIMHealthCheck',
  'NIMAgent',
  'NIMBenchmark',
  'NIMFineTune',
  'NIMFineTuneStatus',
  'NIMQueryRewrite',
  'NVIDIAEmbedding',
  'NVIDIARerank',
  'NIMCitationAnswer',
])

export function usesNvidiaCredential(nodeType?: string): boolean {
  return Boolean(nodeType && NVIDIA_CREDENTIAL_NODE_TYPES.has(nodeType))
}

export function usesHuggingFaceCredential(nodeType?: string): boolean {
  return nodeType === 'HuggingFaceDatasetUpload'
}
