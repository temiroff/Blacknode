import { useState } from 'react'
import { useStore } from '../store'

export default function Inspector() {
  const { nodes, selectedId, updateParam, cookNode, removeNode } = useStore()
  const node = nodes.find(n => n.id === selectedId)

  if (!node) {
    return (
      <aside style={{
        width: 240,
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#334155',
        fontSize: 14,
        fontFamily: 'monospace',
      }}>
        select a node
      </aside>
    )
  }

  const { data } = node

  return (
    <aside style={{
      width: 240,
      background: '#0f172a',
      borderLeft: '1px solid #1e293b',
      overflowY: 'auto',
      fontFamily: 'monospace',
      fontSize: 14,
      color: '#cbd5e1',
    }}>
      {/* header */}
      <div style={{ padding: '12px 14px', borderBottom: '1px solid #1e293b' }}>
        <div style={{ color: '#f8fafc', fontWeight: 600, marginBottom: 4 }}>{data.type}</div>
        <div style={{ color: '#475569', fontSize: 12 }}>{data.id.slice(0, 12)}…</div>
      </div>

      {/* params */}
      <div style={{ padding: '10px 14px' }}>
        <div style={{ color: '#64748b', fontSize: 12, marginBottom: 8, letterSpacing: 1 }}>PARAMS</div>
        {data.inputs.map(inp => (
          <ParamRow
            key={inp}
            label={inp}
            value={data.params[inp] ?? ''}
            onChange={v => updateParam(node.id, inp, v)}
          />
        ))}
        {data.inputs.length === 0 && (
          <div style={{ color: '#334155' }}>no inputs</div>
        )}
      </div>

      {/* cook result */}
      {(data.cookResult !== undefined || data.cookError) && (
        <div style={{ padding: '10px 14px', borderTop: '1px solid #1e293b' }}>
          <div style={{ color: '#64748b', fontSize: 12, marginBottom: 6, letterSpacing: 1 }}>RESULT</div>
          <pre style={{
            background: '#0a0f1a',
            border: '1px solid #1e293b',
            borderRadius: 4,
            padding: 8,
            color: data.cookError ? '#f87171' : '#4ade80',
            fontSize: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxHeight: 200,
            overflowY: 'auto',
          }}>
            {data.cookError
              ? data.cookError
              : typeof data.cookResult === 'object'
                ? JSON.stringify(data.cookResult, null, 2)
                : String(data.cookResult)}
          </pre>
        </div>
      )}

      {/* actions */}
      <div style={{ padding: '10px 14px', borderTop: '1px solid #1e293b', display: 'flex', gap: 8 }}>
        <button
          onClick={() => cookNode(node.id, data.outputs[0] ?? 'output')}
          style={btnStyle('#6366f1')}
        >
          {data.cooking ? 'cooking…' : 'Cook'}
        </button>
        <button
          onClick={() => removeNode(node.id)}
          style={btnStyle('#7f1d1d')}
        >
          Delete
        </button>
      </div>
    </aside>
  )
}

function ParamRow({ label, value, onChange }: { label: string; value: unknown; onChange: (v: unknown) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(value ?? ''))

  const commit = () => {
    setEditing(false)
    let parsed: unknown = draft
    if (draft === 'true') parsed = true
    else if (draft === 'false') parsed = false
    else if (!isNaN(Number(draft)) && draft !== '') parsed = Number(draft)
    onChange(parsed)
  }

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ color: '#64748b', fontSize: 12, marginBottom: 2 }}>{label}</div>
      {editing ? (
        <textarea
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() } }}
          rows={2}
          style={{
            width: '100%',
            background: '#1e293b',
            border: '1px solid #6366f1',
            borderRadius: 4,
            color: '#f8fafc',
            fontFamily: 'monospace',
            fontSize: 13,
            padding: 4,
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />
      ) : (
        <div
          onClick={() => { setDraft(String(value ?? '')); setEditing(true) }}
          style={{
            background: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: 4,
            padding: '3px 6px',
            color: value !== '' && value !== undefined ? '#e2e8f0' : '#334155',
            cursor: 'text',
            minHeight: 24,
            wordBreak: 'break-all',
          }}
        >
          {value !== '' && value !== undefined ? String(value) : '—'}
        </div>
      )}
    </div>
  )
}

function btnStyle(bg: string) {
  return {
    background: bg,
    border: 'none',
    borderRadius: 4,
    color: '#fff',
    cursor: 'pointer',
    fontFamily: 'monospace',
    fontSize: 13,
    padding: '6px 12px',
    flex: 1,
  } as React.CSSProperties
}
