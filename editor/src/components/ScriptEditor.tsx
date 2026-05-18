import { useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

const STARTER = `from blacknode.node import node

@node(
    inputs=["text:Text", "times:Int"],
    outputs=["result:Text"],
    name="Repeat"
)
def repeat_text(ctx: dict) -> dict:
    return {"result": str(ctx.get("text", "")) * int(ctx.get("times", 1))}
`

export default function ScriptEditor() {
  const { loadNodeTypes } = useStore()
  const [code, setCode]     = useState(STARTER)
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null)
  const [running, setRunning] = useState(false)

  const run = async () => {
    setRunning(true)
    setStatus(null)
    try {
      const res = await api.execNode(code)
      if (res.new_types.length > 0) {
        setStatus({ ok: true, msg: `Registered: ${res.new_types.join(', ')}` })
      } else {
        setStatus({ ok: true, msg: 'Executed — no new node types registered.' })
      }
      await loadNodeTypes()
    } catch (e: any) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* hint */}
      <div style={{
        padding: '10px 14px 8px',
        color: 'var(--tx2)',
        fontSize: 12,
        lineHeight: 1.5,
        borderBottom: '1px solid var(--line)',
        flexShrink: 0,
      }}>
        Write a Python <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>@node</code> function.
        Hit <strong style={{ color: 'var(--tx1)' }}>Run</strong> — it appears in the palette instantly.
      </div>

      {/* code area */}
      <textarea
        value={code}
        onChange={e => setCode(e.target.value)}
        spellCheck={false}
        style={{
          flex: 1,
          background: 'var(--lift)',
          border: 'none',
          borderBottom: '1px solid var(--line)',
          color: 'var(--tx1)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          lineHeight: 1.7,
          padding: '12px 14px',
          resize: 'none',
          outline: 'none',
          tabSize: 4,
        }}
        onKeyDown={e => {
          if (e.key === 'Tab') {
            e.preventDefault()
            const el = e.currentTarget
            const start = el.selectionStart
            const end   = el.selectionEnd
            setCode(c => c.slice(0, start) + '    ' + c.slice(end))
            requestAnimationFrame(() => {
              el.selectionStart = el.selectionEnd = start + 4
            })
          }
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault()
            run()
          }
        }}
      />

      {/* status */}
      {status && (
        <div style={{
          padding: '8px 14px',
          background: status.ok ? 'rgba(34,197,94,.08)' : 'rgba(239,68,68,.08)',
          borderBottom: '1px solid var(--line)',
          color: status.ok ? 'var(--ok)' : 'var(--err)',
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          maxHeight: 120,
          overflowY: 'auto',
          flexShrink: 0,
        }}>
          {status.msg}
        </div>
      )}

      {/* actions */}
      <div style={{ padding: '10px 14px', display: 'flex', gap: 8, flexShrink: 0 }}>
        <button
          onClick={run}
          disabled={running}
          style={{
            flex: 1,
            padding: '7px 0',
            background: 'var(--accent)',
            border: 'none',
            borderRadius: 6,
            color: '#fff',
            fontFamily: 'var(--font-ui)',
            fontSize: 13,
            fontWeight: 600,
            cursor: running ? 'default' : 'pointer',
            opacity: running ? 0.6 : 1,
          }}
        >
          {running ? 'Running…' : '▶  Run  (Ctrl+Enter)'}
        </button>
        <button
          onClick={() => { setCode(STARTER); setStatus(null) }}
          style={{
            padding: '7px 12px',
            background: 'transparent',
            border: '1px solid var(--line2)',
            borderRadius: 6,
            color: 'var(--tx2)',
            fontFamily: 'var(--font-ui)',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Reset
        </button>
      </div>
    </div>
  )
}
