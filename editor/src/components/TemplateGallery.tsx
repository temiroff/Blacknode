import { useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { organizeTemplateNodes } from '../graphLayout'

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
interface TemplateSubgraphNode {
  id: string
  type: string
  params: Record<string, unknown>
  pos: [number, number]
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  input_defaults: Record<string, unknown>
}
interface TemplateSubgraph {
  nodeMeta: Record<string, TemplateSubgraphNode>
  edges: TemplateEdge[]
}
interface Template {
  id: string
  name: string
  description: string
  color: string
  nodes: TemplateNode[]
  edges: TemplateEdge[]
  subgraphs?: Record<string, TemplateSubgraph>
}

const WEB_SEARCH_TOOL_CODE = `def run(query: str) -> str:
    import html
    import json
    import re
    import urllib.parse
    import urllib.request

    encoded = urllib.parse.quote_plus(query)

    def fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Blacknode/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def clean(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\\s+", " ", value).strip()

    try:
        instant_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        data = json.loads(fetch(instant_url))
        for key in ("AbstractText", "Definition", "Answer"):
            text = clean(str(data.get(key) or ""))
            if text:
                return text

        pending = list(data.get("RelatedTopics", []))
        while pending:
            item = pending.pop(0)
            pending.extend(item.get("Topics", []))
            text = clean(str(item.get("Text") or ""))
            if text:
                return text
    except Exception:
        pass

    page = fetch(f"https://duckduckgo.com/html/?q={encoded}")
    titles = [clean(match) for match in re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', page, re.I | re.S)]
    snippets = [
        clean(a or b)
        for a, b in re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
            page,
            re.I | re.S,
        )
    ]
    results = []
    for i, title in enumerate(titles[:3]):
        if not title:
            continue
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(f"{i + 1}. {title}" + (f" - {snippet}" if snippet else ""))
    if results:
        return "\\n".join(results)

    return f"No web snippets found for: {query}"
`

const CALCULATOR_SUBGRAPH: TemplateSubgraph = {
  nodeMeta: {
    calc_in: {
      id: 'calc_in',
      type: 'SubnetInput',
      params: {},
      pos: [40, 120],
      inputs: [],
      outputs: ['a', 'b'],
      input_types: {},
      output_types: { a: 'Float', b: 'Float' },
      input_defaults: {},
    },
    calc_add: {
      id: 'calc_add',
      type: 'Add',
      params: {},
      pos: [260, 120],
      inputs: ['a', 'b'],
      outputs: ['value'],
      input_types: { a: 'Float', b: 'Float' },
      output_types: { value: 'Float' },
      input_defaults: {},
    },
    calc_out: {
      id: 'calc_out',
      type: 'SubnetOutput',
      params: {},
      pos: [480, 120],
      inputs: ['result'],
      outputs: [],
      input_types: { result: 'Float' },
      output_types: {},
      input_defaults: {},
    },
  },
  edges: [
    { from: 'calc_in',  fromPort: 'a',     to: 'calc_add', toPort: 'a' },
    { from: 'calc_in',  fromPort: 'b',     to: 'calc_add', toPort: 'b' },
    { from: 'calc_add', fromPort: 'value', to: 'calc_out', toPort: 'result' },
  ],
}

const VISUAL_AGENT_LOOP_SUBGRAPH: TemplateSubgraph = {
  nodeMeta: {
    loop_in: {
      id: 'loop_in',
      type: 'SubnetInput',
      params: {},
      pos: [40, 220],
      inputs: [],
      outputs: ['prompt', 'system', 'model', 'tools', 'max_tokens', 'max_iter'],
      input_types: {},
      output_types: {
        prompt: 'Text',
        system: 'Text',
        model: 'Model',
        tools: 'List',
        max_tokens: 'Int',
        max_iter: 'Int',
      },
      input_defaults: {},
    },
    messages: {
      id: 'messages',
      type: 'AgentMessages',
      params: {},
      pos: [300, 120],
      inputs: ['prompt'],
      outputs: ['messages'],
      input_types: { prompt: 'Text' },
      output_types: { messages: 'List' },
      input_defaults: {},
    },
    chat: {
      id: 'chat',
      type: 'AgentChatStep',
      params: {},
      pos: [560, 100],
      inputs: ['messages', 'system', 'model', 'tools', 'max_tokens'],
      outputs: ['assistant_text', 'tool_calls', 'stop_reason', 'step'],
      input_types: {
        messages: 'List',
        system: 'Text',
        model: 'Model',
        tools: 'List',
        max_tokens: 'Int',
      },
      output_types: {
        assistant_text: 'Text',
        tool_calls: 'List',
        stop_reason: 'Text',
        step: 'Dict',
      },
      input_defaults: { model: 'claude-sonnet-4-6', max_tokens: 1024 },
    },
    iter_one: {
      id: 'iter_one',
      type: 'Int',
      params: { value: 1 },
      pos: [560, 360],
      inputs: [],
      outputs: ['value'],
      input_types: {},
      output_types: { value: 'Int' },
      input_defaults: {},
    },
    dispatch: {
      id: 'dispatch',
      type: 'ToolDispatch',
      params: {},
      pos: [840, 80],
      inputs: ['tool_calls', 'tools'],
      outputs: ['tool_results', 'steps'],
      input_types: { tool_calls: 'List', tools: 'List' },
      output_types: { tool_results: 'List', steps: 'List' },
      input_defaults: {},
    },
    stop: {
      id: 'stop',
      type: 'AgentStopCheck',
      params: {},
      pos: [840, 330],
      inputs: ['stop_reason', 'tool_calls', 'iteration', 'max_iter'],
      outputs: ['continue', 'done', 'reason'],
      input_types: {
        stop_reason: 'Text',
        tool_calls: 'List',
        iteration: 'Int',
        max_iter: 'Int',
      },
      output_types: { continue: 'Bool', done: 'Bool', reason: 'Text' },
      input_defaults: { iteration: 1, max_iter: 5 },
    },
    append: {
      id: 'append',
      type: 'AgentAppendMessages',
      params: {},
      pos: [1120, 120],
      inputs: ['messages', 'model', 'assistant_text', 'tool_calls', 'tool_results'],
      outputs: ['messages'],
      input_types: {
        messages: 'List',
        model: 'Model',
        assistant_text: 'Text',
        tool_calls: 'List',
        tool_results: 'List',
      },
      output_types: { messages: 'List' },
      input_defaults: { model: 'claude-sonnet-4-6' },
    },
    final: {
      id: 'final',
      type: 'AgentFinalAnswer',
      params: {},
      pos: [1400, 150],
      inputs: ['messages', 'system', 'model', 'max_tokens'],
      outputs: ['result', 'step'],
      input_types: {
        messages: 'List',
        system: 'Text',
        model: 'Model',
        max_tokens: 'Int',
      },
      output_types: { result: 'Text', step: 'Dict' },
      input_defaults: { model: 'claude-sonnet-4-6', max_tokens: 1024 },
    },
    loop_out: {
      id: 'loop_out',
      type: 'SubnetOutput',
      params: {},
      pos: [1680, 180],
      inputs: ['result', 'steps'],
      outputs: [],
      input_types: { result: 'Text', steps: 'List' },
      output_types: {},
      input_defaults: {},
    },
  },
  edges: [
    { from: 'loop_in',  fromPort: 'prompt',         to: 'messages', toPort: 'prompt' },
    { from: 'messages', fromPort: 'messages',       to: 'chat',     toPort: 'messages' },
    { from: 'loop_in',  fromPort: 'system',         to: 'chat',     toPort: 'system' },
    { from: 'loop_in',  fromPort: 'model',          to: 'chat',     toPort: 'model' },
    { from: 'loop_in',  fromPort: 'tools',          to: 'chat',     toPort: 'tools' },
    { from: 'loop_in',  fromPort: 'max_tokens',     to: 'chat',     toPort: 'max_tokens' },
    { from: 'chat',     fromPort: 'tool_calls',     to: 'dispatch', toPort: 'tool_calls' },
    { from: 'loop_in',  fromPort: 'tools',          to: 'dispatch', toPort: 'tools' },
    { from: 'messages', fromPort: 'messages',       to: 'append',   toPort: 'messages' },
    { from: 'loop_in',  fromPort: 'model',          to: 'append',   toPort: 'model' },
    { from: 'chat',     fromPort: 'assistant_text', to: 'append',   toPort: 'assistant_text' },
    { from: 'chat',     fromPort: 'tool_calls',     to: 'append',   toPort: 'tool_calls' },
    { from: 'dispatch', fromPort: 'tool_results',   to: 'append',   toPort: 'tool_results' },
    { from: 'chat',     fromPort: 'stop_reason',    to: 'stop',     toPort: 'stop_reason' },
    { from: 'chat',     fromPort: 'tool_calls',     to: 'stop',     toPort: 'tool_calls' },
    { from: 'iter_one', fromPort: 'value',          to: 'stop',     toPort: 'iteration' },
    { from: 'loop_in',  fromPort: 'max_iter',       to: 'stop',     toPort: 'max_iter' },
    { from: 'append',   fromPort: 'messages',       to: 'final',    toPort: 'messages' },
    { from: 'loop_in',  fromPort: 'system',         to: 'final',    toPort: 'system' },
    { from: 'loop_in',  fromPort: 'model',          to: 'final',    toPort: 'model' },
    { from: 'loop_in',  fromPort: 'max_tokens',     to: 'final',    toPort: 'max_tokens' },
    { from: 'final',    fromPort: 'result',         to: 'loop_out', toPort: 'result' },
    { from: 'dispatch', fromPort: 'steps',          to: 'loop_out', toPort: 'steps' },
  ],
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
    description: 'Run a prompt through NVIDIA NIM via LLMAgent',
    color: '#76b900',
    nodes: [
      { ref: 'model',  type: 'Model',    params: { value: 'nim:meta/llama-3.1-8b-instruct' },    pos: [60,  80] },
      { ref: 'system', type: 'Text',     params: { value: 'You are a helpful assistant.' },       pos: [60, 230] },
      { ref: 'prompt', type: 'Text',     params: { value: 'Explain quantum computing briefly.' }, pos: [60, 390] },
      { ref: 'agent',  type: 'LLMAgent', params: {},                                              pos: [340, 220] },
      { ref: 'out',    type: 'Output',   params: {},                                              pos: [630, 200] },
    ],
    edges: [
      { from: 'model',  fromPort: 'value', to: 'agent', toPort: 'model' },
      { from: 'system', fromPort: 'value', to: 'agent', toPort: 'system' },
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
      { ref: 'a',      type: 'Text',   params: { value: 'Hello' },  pos: [60,  60] },
      { ref: 'b',      type: 'Text',   params: { value: ' World' }, pos: [60, 240] },
      { ref: 'concat', type: 'Concat', params: {},                  pos: [360, 160] },
      { ref: 'out',    type: 'Output', params: {},                  pos: [660, 130] },
    ],
    edges: [
      { from: 'a',      fromPort: 'value',  to: 'concat', toPort: 'a' },
      { from: 'b',      fromPort: 'value',  to: 'concat', toPort: 'b' },
      { from: 'concat', fromPort: 'value',  to: 'out',    toPort: 'value' },
    ],
  },
  {
    id: 'python-tool-agent',
    name: 'Python Tool Agent',
    description: 'PythonFn tool collected by ToolBox and used by AgentLoop',
    color: '#14b8a6',
    nodes: [
      { ref: 'model',  type: 'Model',     params: { value: 'claude-sonnet-4-6' },                                                    pos: [60,  60] },
      { ref: 'system', type: 'Text',      params: { value: 'You are an agent. Use web_search when outside context would help.' },    pos: [60, 210] },
      { ref: 'task',   type: 'Text',      params: { value: 'Use web_search to learn what NVIDIA NIM is, then answer in one sentence.' }, pos: [60, 380] },
      { ref: 'tool',   type: 'PythonFn',  params: {
        code: WEB_SEARCH_TOOL_CODE,
        name: 'web_search',
        description: 'Searches DuckDuckGo and returns a compact result or top snippets.',
      },                                                                                                                            pos: [360,  80] },
      { ref: 'box',    type: 'ToolBox',   params: {},                                                                                pos: [620, 110] },
      { ref: 'loop',   type: 'AgentLoop', params: { max_iter: 3 },                                                                   pos: [620, 280] },
      { ref: 'out',    type: 'Output',    params: {},                                                                                pos: [900, 280] },
    ],
    edges: [
      { from: 'model',  fromPort: 'value',  to: 'loop', toPort: 'model' },
      { from: 'system', fromPort: 'value',  to: 'loop', toPort: 'system' },
      { from: 'task',   fromPort: 'value',  to: 'loop', toPort: 'prompt' },
      { from: 'tool',   fromPort: 'fn',     to: 'box',  toPort: 'tool_1' },
      { from: 'box',    fromPort: 'tools',  to: 'loop', toPort: 'tools' },
      { from: 'loop',   fromPort: 'result', to: 'out',  toPort: 'value' },
    ],
  },
  {
    id: 'visual-tool-agent',
    name: 'Visual Tool Agent',
    description: 'PythonFn tool collected by ToolBox and used by VisualAgentLoop',
    color: '#6366f1',
    nodes: [
      { ref: 'model',  type: 'Model',           params: { value: 'claude-sonnet-4-6' },                                                    pos: [60,  60] },
      { ref: 'system', type: 'Text',            params: { value: 'You are an agent. Use web_search when outside context would help.' },    pos: [60, 210] },
      { ref: 'task',   type: 'Text',            params: { value: 'Use web_search to learn what NVIDIA NIM is, then answer in one sentence.' }, pos: [60, 380] },
      { ref: 'tool',   type: 'PythonFn',        params: {
        code: WEB_SEARCH_TOOL_CODE,
        name: 'web_search',
        description: 'Searches DuckDuckGo and returns a compact result or top snippets.',
      },                                                                                                                            pos: [360,  80] },
      { ref: 'box',    type: 'ToolBox',         params: {},                                                                                pos: [620, 110] },
      { ref: 'loop',   type: 'VisualAgentLoop', params: { max_iter: 3 },                                                                   pos: [620, 280] },
      { ref: 'out',    type: 'Output',          params: {},                                                                                pos: [900, 280] },
    ],
    subgraphs: {
      loop: VISUAL_AGENT_LOOP_SUBGRAPH,
    },
    edges: [
      { from: 'model',  fromPort: 'value',  to: 'loop', toPort: 'model' },
      { from: 'system', fromPort: 'value',  to: 'loop', toPort: 'system' },
      { from: 'task',   fromPort: 'value',  to: 'loop', toPort: 'prompt' },
      { from: 'tool',   fromPort: 'fn',     to: 'box',  toPort: 'tool_1' },
      { from: 'box',    fromPort: 'tools',  to: 'loop', toPort: 'tools' },
      { from: 'loop',   fromPort: 'result', to: 'out',  toPort: 'value' },
    ],
  },
  {
    id: 'subnet-tool-call',
    name: 'Subnet Tool Call',
    description: 'Build a calculator inside SubnetAsTool and test it directly with ToolCall',
    color: '#0f766e',
    nodes: [
      { ref: 'tool',   type: 'SubnetAsTool', params: {
        name: 'add_numbers',
        description: 'Adds two numbers and returns the numeric result.',
      },                                                                                                                         pos: [80, 120] },
      { ref: 'args',   type: 'Dict',         params: { value: { a: 17, b: 42 } },                                                 pos: [80, 300] },
      { ref: 'call',   type: 'ToolCall',     params: {},                                                                          pos: [360, 220] },
      { ref: 'out',    type: 'Output',       params: {},                                                                          pos: [640, 210] },
    ],
    subgraphs: {
      tool: CALCULATOR_SUBGRAPH,
    },
    edges: [
      { from: 'tool',   fromPort: 'fn',     to: 'call',    toPort: 'fn' },
      { from: 'args',   fromPort: 'value',  to: 'call',    toPort: 'args' },
      { from: 'call',   fromPort: 'result', to: 'out',     toPort: 'value' },
    ],
  },
  {
    id: 'subnet-tool-agent',
    name: 'Subnet Tool Agent',
    description: 'Build a calculator inside SubnetAsTool and give it to AgentLoop',
    color: '#0f766e',
    nodes: [
      { ref: 'model',  type: 'Model',        params: { value: 'claude-sonnet-4-6' },                                              pos: [60,  60] },
      { ref: 'system', type: 'Text',         params: { value: 'You are an agent. Use tools for arithmetic.' },                    pos: [60, 210] },
      { ref: 'task',   type: 'Text',         params: { value: 'Use add_numbers to add 17 and 42. Answer with the result only.' }, pos: [60, 380] },
      { ref: 'tool',   type: 'SubnetAsTool', params: {
        name: 'add_numbers',
        description: 'Adds two numbers and returns the numeric result.',
      },                                                                                                                         pos: [360, 160] },
      { ref: 'box',    type: 'ToolBox',      params: {},                                                                          pos: [620, 190] },
      { ref: 'loop',   type: 'AgentLoop',    params: { max_iter: 3 },                                                             pos: [820, 220] },
      { ref: 'out',    type: 'Output',       params: {},                                                                          pos: [1080, 220] },
    ],
    subgraphs: {
      tool: CALCULATOR_SUBGRAPH,
    },
    edges: [
      { from: 'model',  fromPort: 'value',  to: 'loop', toPort: 'model' },
      { from: 'system', fromPort: 'value',  to: 'loop', toPort: 'system' },
      { from: 'task',   fromPort: 'value',  to: 'loop', toPort: 'prompt' },
      { from: 'tool',   fromPort: 'fn',     to: 'box',  toPort: 'tool_1' },
      { from: 'box',    fromPort: 'tools',  to: 'loop', toPort: 'tools' },
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
    const previousGraph = await api.getGraph().catch(() => null)
    try {
      await reset()
      const idMap: Record<string, string> = {}
      const templateNodes = organizeTemplateNodes(t.nodes, t.edges)
      for (const n of templateNodes) {
        const meta: any = await api.addNode(n.type, n.pos, n.params ?? {})
        idMap[n.ref] = meta.id
      }
      for (const [ref, subgraph] of Object.entries(t.subgraphs ?? {})) {
        const subnetId = idMap[ref]
        if (!subnetId) continue
        await api.updateSubgraph(
          subnetId,
          subgraph.nodeMeta,
          subgraph.edges.map(e => ({
            from: e.from,
            from_port: e.fromPort,
            to: e.to,
            to_port: e.toPort,
          })),
        )
      }
      for (const e of t.edges) {
        const fromId = idMap[e.from]
        const toId   = idMap[e.to]
        if (fromId && toId) await api.connect(fromId, e.fromPort, toId, e.toPort)
      }
      await loadGraph()
      await loadNodeTypes()
      window.dispatchEvent(new Event('blacknode:fit-view'))
      setLoaded(t.id)
    } catch (err) {
      console.error(err)
      if (previousGraph) {
        await api.setGraph(previousGraph.nodes, previousGraph.edges).catch(console.error)
        await loadGraph().catch(console.error)
      }
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: `Could not load ${t.name}`,
          message: err instanceof Error ? err.message : String(err),
        },
      }))
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
