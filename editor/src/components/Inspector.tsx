import { useState } from 'react'
import { useStore } from '../store'

export default function Inspector() {
  const { nodes, selectedId, updateParam, cookNode, removeNode } = useStore()
  const node = nodes.find(n => n.id === selectedId)

  if (!node) {
    return (
      <aside style={{
        width: 260,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--tx3)',
        fontSize: 13,
        flexShrink: 0,
      }}>
        Select a node
      </aside>
    )
  }

  const { data } = node

  return (
    <aside style={{
      width: 260,
      background: 'var(--panel)',
      borderLeft: '1px solid var(--line)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      {/* header */}
      <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--line)' }}>
        <div style={{ color: 'var(--tx1)', fontWeight: 600, fontSize: 15, marginBottom: 4 }}>
          {data.type}
        </div>
        <div style={{
          color: 'var(--tx3)',
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.03em',
        }}>
          {data.id.slice(0, 14)}…
        </div>
      </div>

      {/* params */}
      <div style={{ padding: '12px 16px', flex: 1 }}>
        {data.inputs.length > 0 ? (
          <>
            <div style={{
              color: 'var(--tx3)',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              marginBottom: 10,
            }}>
              Parameters
            </div>
            {data.inputs.map(inp => (
              <ParamRow
                key={inp}
                label={inp}
                value={data.params[inp] ?? ''}
                onChange={v => updateParam(node.id, inp, v)}
              />
            ))}
          </>
        ) : (
          <div style={{ color: 'var(--tx3)', fontSize: 13 }}>No inputs</div>
        )}
      </div>

      {/* cook result */}
      {(data.cookResult !== undefined || data.cookError) && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)' }}>
          <div style={{
            color: 'var(--tx3)',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}>
            Result
          </div>
          <pre style={{
            background: 'var(--lift)',
            border: `1px solid ${data.cookError ? 'var(--err)' : 'var(--line2)'}`,
            borderRadius: 6,
            padding: '8px 10px',
            color: data.cookError ? 'var(--err)' : 'var(--ok)',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
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
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)', display: 'flex', gap: 8 }}>
        <button
          onClick={() => cookNode(node.id, data.outputs[0] ?? 'output')}
          style={btnStyle('var(--accent)', true)}
        >
          {data.cooking ? 'Cooking…' : '▶  Cook'}
        </button>
        <button
          onClick={() => removeNode(node.id)}
          style={btnStyle('var(--err)', false)}
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
    <div style={{ marginBottom: 10 }}>
      <div style={{
        color: 'var(--tx2)',
        fontSize: 12,
        fontWeight: 500,
        marginBottom: 4,
        textTransform: 'capitalize',
      }}>
        {label}
      </div>
      {editing ? (
        <textarea
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() } }}
          rows={3}
          style={{
            width: '100%',
            background: 'var(--lift)',
            border: '1px solid var(--accent)',
            borderRadius: 6,
            color: 'var(--tx1)',
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
            padding: '6px 8px',
            resize: 'vertical',
            boxSizing: 'border-box',
            outline: 'none',
          }}
        />
      ) : (
        <div
          onClick={() => { setDraft(String(value ?? '')); setEditing(true) }}
          style={{
            background: 'var(--lift)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            padding: '6px 8px',
            color: value !== '' && value !== undefined ? 'var(--tx1)' : 'var(--tx3)',
            cursor: 'text',
            minHeight: 32,
            fontSize: 13,
            fontFamily: 'var(--font-mono)',
            wordBreak: 'break-all',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--line2)')}
          onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--line)')}
        >
          {value !== '' && value !== undefined ? String(value) : '—'}
        </div>
      )}
    </div>
  )
}

function btnStyle(color: string, primary: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: '7px 12px',
    border: `1px solid ${color}`,
    borderRadius: 6,
    background: primary ? color : 'transparent',
    color: primary ? '#fff' : color,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    fontFamily: 'var(--font-ui)',
    transition: 'opacity 0.15s',
  }
}
