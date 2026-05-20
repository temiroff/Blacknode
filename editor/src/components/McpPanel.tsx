import { useEffect, useState } from 'react'
import { api } from '../api'

interface McpStatus {
  mcp_installed: boolean
  blacknode_cli: string | null
  install_command: string
  launch_command: string
}

const TOOLS: { name: string; desc: string }[] = [
  { name: 'list_nodes',       desc: 'List every Blacknode node type with category and ports' },
  { name: 'get_node_schema',  desc: 'Detailed port schema for one node type' },
  { name: 'list_templates',   desc: 'Workflow templates shipped in the repo' },
  { name: 'load_workflow',    desc: 'Read a workflow JSON file from disk' },
  { name: 'create_workflow',  desc: 'Empty workflow scaffold with an Output node' },
  { name: 'add_node',         desc: 'Add a node; rejects unknown types' },
  { name: 'connect_nodes',    desc: 'Add an edge; rejects incompatible port types' },
  { name: 'validate_workflow',desc: 'Full schema + port-type validation' },
  { name: 'run_workflow',     desc: 'Execute and return cooked value + event log' },
  { name: 'export_python',    desc: 'Convert workflow to a runnable Python script' },
  { name: 'create_editor_workflow_tab', desc: 'Open a new unsaved tab in the running editor UI' },
  { name: 'open_workflow_in_editor_tab', desc: 'Open a populated workflow as a new organized editor tab' },
  { name: 'cook_editor_node', desc: 'Cook a node in the running editor UI and update the canvas' },
]

const STARTER_PROMPTS: { title: string; body: string }[] = [
  {
    title: 'Hello World',
    body: 'Using the blacknode tools: list available node types, then build and run a workflow that concatenates "Hello" and " World" and prints the result through an Output node.',
  },
  {
    title: 'Research pipeline',
    body: 'Build a Blacknode workflow that fetches https://example.com with HTTPGet, summarizes the response with an LLMAgent using the nim:meta/llama-3.1-8b-instruct model, writes the summary to summary.txt with FileWrite, then runs the graph.',
  },
  {
    title: 'Explain a saved workflow',
    body: 'Load the workflow at templates/research-pipeline.json. List its nodes and edges, then export it as a Python script and explain what it does step by step.',
  },
]

const CONFIG_PATHS: Record<string, string> = {
  windows: '%APPDATA%\\Claude\\claude_desktop_config.json',
  mac: '~/Library/Application Support/Claude/claude_desktop_config.json',
  linux: '~/.config/Claude/claude_desktop_config.json',
}

function detectPlatform(): 'windows' | 'mac' | 'linux' {
  const p = navigator.platform.toLowerCase()
  if (p.includes('win')) return 'windows'
  if (p.includes('mac') || p.includes('darwin')) return 'mac'
  return 'linux'
}

const CONFIG_JSON = `{
  "mcpServers": {
    "blacknode": {
      "command": "blacknode",
      "args": ["mcp"]
    }
  }
}`

const INSPECTOR_CMD = 'npx @modelcontextprotocol/inspector blacknode mcp'

export default function McpPanel() {
  const [status, setStatus] = useState<McpStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const platform = detectPlatform()

  useEffect(() => {
    api.mcpStatus()
      .then(setStatus)
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      window.setTimeout(() => setCopied(prev => prev === key ? null : prev), 1500)
    } catch {
      setError('Could not access clipboard')
    }
  }

  const ready = status?.mcp_installed && !!status?.blacknode_cli

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px 24px' }}>
      <Section title="Status">
        {error && <div style={{ color: 'var(--err)', fontSize: 11, marginBottom: 6 }}>{error}</div>}
        {!status && !error && <div style={{ color: 'var(--tx3)', fontSize: 11 }}>Checking…</div>}
        {status && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Indicator
              ok={status.mcp_installed}
              label="mcp Python package"
              hint={status.mcp_installed ? 'installed' : `install with: ${status.install_command}`}
            />
            <Indicator
              ok={!!status.blacknode_cli}
              label="blacknode CLI on PATH"
              hint={status.blacknode_cli ?? 'pip install -e .'}
            />
            {ready && (
              <div style={{ marginTop: 6, color: 'var(--ok)', fontSize: 11 }}>
                Ready. Wire it into Claude Desktop below.
              </div>
            )}
          </div>
        )}
      </Section>

      <Section title="Claude Desktop config">
        <div style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 6 }}>
          Open <code style={inlineCode}>{CONFIG_PATHS[platform]}</code> (or Settings → Developer → Edit Config in Claude Desktop) and merge in:
        </div>
        <CodeBlock
          text={CONFIG_JSON}
          copied={copied === 'config'}
          onCopy={() => copy('config', CONFIG_JSON)}
        />
        <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 6 }}>
          Restart Claude Desktop after saving. Cursor and other MCP clients use the same JSON shape.
        </div>
      </Section>

      <Section title="Exposed tools">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {TOOLS.map(tool => (
            <div key={tool.name} style={{
              display: 'grid',
              gridTemplateColumns: '140px 1fr',
              gap: 8,
              fontSize: 11,
              lineHeight: 1.4,
            }}>
              <span style={{ color: 'var(--tx1)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                {tool.name}
              </span>
              <span style={{ color: 'var(--tx3)' }}>{tool.desc}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Starter prompts">
        <div style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 6 }}>
          Paste any of these into a Claude Desktop chat after you've wired up the config.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {STARTER_PROMPTS.map((prompt, i) => (
            <div key={i} style={{
              border: '1px solid var(--line)',
              borderRadius: 6,
              padding: '8px 10px',
              background: 'var(--bg)',
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 4,
              }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx2)' }}>{prompt.title}</span>
                <button onClick={() => copy(`prompt-${i}`, prompt.body)} style={miniButton}>
                  {copied === `prompt-${i}` ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div style={{ fontSize: 11, color: 'var(--tx2)', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
                {prompt.body}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Test without Claude Desktop">
        <div style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 6 }}>
          The official MCP Inspector gives you a browser UI to hand-call every tool.
        </div>
        <CodeBlock
          text={INSPECTOR_CMD}
          copied={copied === 'inspector'}
          onCopy={() => copy('inspector', INSPECTOR_CMD)}
        />
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: 'var(--tx3)',
        marginBottom: 6,
        fontFamily: 'var(--font-ui)',
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function Indicator({ ok, label, hint }: { ok: boolean; label: string; hint?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
      <span style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: ok ? 'var(--ok)' : 'var(--err)',
        flexShrink: 0,
      }} />
      <span style={{ color: 'var(--tx2)', fontWeight: 600 }}>{label}</span>
      {hint && (
        <span style={{
          color: 'var(--tx3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {hint}
        </span>
      )}
    </div>
  )
}

function CodeBlock({ text, copied, onCopy }: { text: string; copied: boolean; onCopy: () => void }) {
  return (
    <div style={{ position: 'relative' }}>
      <pre style={{
        margin: 0,
        padding: '8px 10px',
        background: 'var(--bg)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--tx1)',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
      }}>
        {text}
      </pre>
      <button onClick={onCopy} style={{
        ...miniButton,
        position: 'absolute',
        top: 6,
        right: 6,
      }}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

const miniButton: React.CSSProperties = {
  background: 'var(--panel)',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '2px 8px',
  fontSize: 10,
  fontFamily: 'var(--font-ui)',
  borderRadius: 4,
  cursor: 'pointer',
}

const inlineCode: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  padding: '1px 4px',
  background: 'var(--bg)',
  border: '1px solid var(--line)',
  borderRadius: 3,
}
