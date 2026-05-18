import { useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

interface TemplateNode {
  ref: string
  type: string
  params?: Record<string, unknown>
  pos: [number, number]
}
interface TemplateEdge {
  from: string; fromPort: string
  to: string;   toPort: string
}
interface Template {
  id: string
  name: string
  description: string
  color: string
  nodes: TemplateNode[]
  edges: TemplateEdge[]
}

const TEMPLATES: Template[] = [
  {
    id: 'llm-chat',
    name: 'LLM Chat',
    description: 'System prompt + user message → any LLM',
    color: '#6366f1',
    nodes: [
      { ref: 'model',  type: 'Model',    params: { value: 'claude-sonnet-4-6' },              pos: [60,  80] },
      { ref: 'system', type: 'Text',     params: { value: 'You are a helpful assistant.' },    pos: [60, 220] },
      { ref: 'prompt', type: 'Text',     params: { value: 'Hello! What can you do?' },          pos: [60, 380] },
      { ref: 'agent',  type: 'LLMAgent', params: {},                                            pos: [340, 220] },
      { ref: 'out',    type: 'Output',   params: {},                                            pos: [620, 200] },
    ],
    edges: [
      { from: 'model',  fromPort: 'value', to: 'agent', toPort: 'model' },
      { from: 'system', fromPort: 'value', to: 'agent', toPort: 'system' },
      { from: 'prompt', fromPort: 'value', to: 'agent', toPort: 'prompt' },
      { from: 'agent',  fromPort: 'text',  to: 'out',   toPort: 'value' },
    ],
  },
  {
    id: 'nim-demo',
    name: 'NVIDIA NIM',
    description: 'Run a prompt through NVIDIA NIM API',
    color: '#76b900',
    nodes: [
      { ref: 'model',  type: 'Model',    params: { value: 'nim:meta/llama-3.1-8b-instruct' }, pos: [60,  80] },
      { ref: 'prompt', type: 'Text',     params: { value: 'Explain quantum computing briefly.' },          pos: [60, 230] },
      { ref: 'agent',  type: 'NIMAgent', params: {},                                                       pos: [340, 150] },
      { ref: 'out',    type: 'Output',   params: {},                                                       pos: [620, 130] },
    ],
    edges: [
      { from: 'model',  fromPort: 'value', to: 'agent', toPort: 'model' },
      { from: 'prompt', fromPort: 'value', to: 'agent', toPort: 'prompt' },
      { from: 'agent',  fromPort: 'text',  to: 'out',   toPort: 'value' },
    ],
  },
  {
    id: 'text-pipeline',
    name: 'Text Pipeline',
    description: 'Concatenate two strings and print',
    color: '#0891b2',
    nodes: [
      { ref: 'a',      type: 'Text',   params: { value: 'Hello' },  pos: [60,  80] },
      { ref: 'b',      type: 'Text',   params: { value: ' World' }, pos: [60, 200] },
      { ref: 'concat', type: 'Concat', params: {},                  pos: [280, 140] },
      { ref: 'out',    type: 'Output', params: {},                  pos: [500, 110] },
    ],
    edges: [
      { from: 'a',      fromPort: 'value',  to: 'concat', toPort: 'a' },
      { from: 'b',      fromPort: 'value',  to: 'concat', toPort: 'b' },
      { from: 'concat', fromPort: 'value',  to: 'out',    toPort: 'value' },
    ],
  },
  {
    id: 'agent-loop',
    name: 'Agent Loop',
    description: 'Multi-turn reasoning loop with system + task',
    color: '#d97706',
    nodes: [
      { ref: 'model',  type: 'Model',     params: { value: 'claude-sonnet-4-6' },                              pos: [60,  60] },
      { ref: 'system', type: 'Text',      params: { value: 'You are a reasoning agent. Think step by step.' }, pos: [60, 200] },
      { ref: 'task',   type: 'Text',      params: { value: 'What is 17 × 42? Show your work.' },                pos: [60, 370] },
      { ref: 'loop',   type: 'AgentLoop', params: {},                                                           pos: [360, 200] },
      { ref: 'out',    type: 'Output',    params: {},                                                           pos: [640, 180] },
    ],
    edges: [
      { from: 'model',  fromPort: 'value',  to: 'loop', toPort: 'model' },
      { from: 'system', fromPort: 'value',  to: 'loop', toPort: 'system' },
      { from: 'task',   fromPort: 'value',  to: 'loop', toPort: 'prompt' },
      { from: 'loop',   fromPort: 'result', to: 'out',  toPort: 'value' },
    ],
  },
]

export default function TemplateGallery() {
  const { reset, loadGraph, loadNodeTypes } = useStore()
  const [loading, setLoading] = useState<string | null>(null)
  const [loaded,  setLoaded]  = useState<string | null>(null)

  const loadTemplate = async (t: Template) => {
    setLoading(t.id)
    setLoaded(null)
    try {
      await reset()
      const idMap: Record<string, string> = {}
      for (const n of t.nodes) {
        const meta: any = await api.addNode(n.type, n.pos, n.params ?? {})
        idMap[n.ref] = meta.id
      }
      for (const e of t.edges) {
        const fromId = idMap[e.from]
        const toId   = idMap[e.to]
        if (fromId && toId) await api.connect(fromId, e.fromPort, toId, e.toPort)
      }
      await loadGraph()
      await loadNodeTypes()
      setLoaded(t.id)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div style={{ padding: '10px 10px', display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
      <div style={{
        color: 'var(--tx2)',
        fontSize: 12,
        padding: '2px 4px 8px',
        lineHeight: 1.5,
      }}>
        One-click starter graphs. Loads into the canvas.
      </div>

      {TEMPLATES.map(t => {
        const isLoading = loading === t.id
        const wasLoaded = loaded  === t.id
        return (
          <div
            key={t.id}
            style={{
              background: 'var(--lift)',
              border: `1px solid ${wasLoaded ? t.color : 'var(--line2)'}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: isLoading ? 'default' : 'pointer',
              transition: 'border-color 0.2s',
            }}
            onMouseEnter={e => {
              if (!isLoading) (e.currentTarget as HTMLElement).style.borderColor = t.color
            }}
            onMouseLeave={e => {
              if (!wasLoaded) (e.currentTarget as HTMLElement).style.borderColor = 'var(--line2)'
            }}
            onClick={() => !isLoading && loadTemplate(t)}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{
                color: t.color,
                fontSize: 13,
                fontWeight: 600,
              }}>
                {t.name}
              </span>
              <span style={{
                fontSize: 11,
                color: wasLoaded ? t.color : 'var(--tx3)',
                fontFamily: 'var(--font-ui)',
              }}>
                {isLoading ? 'loading…' : wasLoaded ? '✓ loaded' : `${t.nodes.length} nodes`}
              </span>
            </div>
            <div style={{ color: 'var(--tx2)', fontSize: 12, lineHeight: 1.4 }}>
              {t.description}
            </div>
          </div>
        )
      })}
    </div>
  )
}
