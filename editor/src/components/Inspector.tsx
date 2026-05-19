import { useState, useEffect } from 'react'
import { useStore } from '../store'
import { portColor } from '../portColors'

const WIRE_ONLY = new Set(['List', 'Dict', 'Fn', 'Embedding'])

const formatFloat = (v: unknown): string => {
  const n = parseFloat(String(v))
  if (isNaN(n)) return '0.0'
  return Number.isInteger(n) ? `${n}.0` : String(n)
}

export default function Inspector() {
  const { nodes, edges, nodeDefs, selectedId, updateParam, cookNode, removeNode } = useStore()
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
  const connectedPorts = new Set(
    edges.filter(e => e.target === node.id).map(e => e.targetHandle).filter(Boolean)
  )

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
          color: 'var(--tx2)',
          fontSize: 12,
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
              color: 'var(--tx2)',
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: 10,
            }}>
              Parameters
            </div>
            {data.inputs.map(inp => {
              const type = (data.input_types as Record<string, string>)?.[inp] ?? 'Any'
              const def  = (data.input_defaults as Record<string, unknown>)?.[inp]
                        ?? nodeDefs[data.type]?.input_defaults?.[inp]
              return (
                <ParamRow
                  key={`${node.id}-${inp}`}
                  label={inp}
                  type={type}
                  value={data.params[inp]}
                  defaultValue={def}
                  connected={connectedPorts.has(inp)}
                  onChange={v => updateParam(node.id, inp, v)}
                />
              )
            })}
          </>
        ) : (
          <div style={{ color: 'var(--tx2)', fontSize: 13 }}>No inputs</div>
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

function ParamRow({ label, type, value, defaultValue, connected, onChange }: {
  label: string
  type: string
  value: unknown
  defaultValue: unknown
  connected: boolean
  onChange: (v: unknown) => void
}) {
  const color = portColor(type)
  const wireOnly = WIRE_ONLY.has(type)

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ color: 'var(--tx1)', fontSize: 12, fontWeight: 500, textTransform: 'capitalize' }}>
          {label}
        </span>
        <span style={{
          fontSize: 10,
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          color,
          background: `${color}22`,
          borderRadius: 4,
          padding: '1px 5px',
          letterSpacing: '0.02em',
        }}>
          {type}
        </span>
      </div>

      {connected ? (
        <div style={{
          background: 'var(--lift)',
          border: `1px solid ${color}44`,
          borderRadius: 6,
          padding: '5px 8px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          color: 'var(--tx3)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minHeight: 28,
          opacity: 0.7,
        }}>
          <span style={{ color, fontSize: 8 }}>●</span>
          connected
        </div>
      ) : wireOnly ? (
        <div style={{
          background: 'var(--lift)',
          border: '1px dashed var(--line2)',
          borderRadius: 6,
          padding: '5px 8px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          color: 'var(--tx3)',
          minHeight: 28,
          display: 'flex',
          alignItems: 'center',
        }}>
          ← connect a wire
        </div>
      ) : type === 'Bool' ? (
        <BoolControl value={value} onChange={onChange} />
      ) : type === 'Int' ? (
        <IntControl value={value} defaultValue={defaultValue} onChange={onChange} />
      ) : type === 'Float' ? (
        <FloatControl value={value} defaultValue={defaultValue} onChange={onChange} />
      ) : (
        <TextControl value={value} defaultValue={defaultValue} onChange={onChange} multiline={type !== 'Model'} />
      )}
    </div>
  )
}

function BoolControl({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const on = Boolean(value)
  const color = portColor('Bool')
  return (
    <div
      onClick={() => onChange(!on)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--lift)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        padding: '5px 8px',
        cursor: 'pointer',
        minHeight: 28,
      }}
    >
      <div style={{
        width: 30, height: 16, borderRadius: 8, position: 'relative', flexShrink: 0,
        background: on ? color : 'var(--line2)', transition: 'background .15s',
      }}>
        <div style={{
          position: 'absolute', top: 2, left: on ? 16 : 2,
          width: 12, height: 12, borderRadius: '50%', background: '#fff',
          transition: 'left .15s', boxShadow: '0 1px 3px rgba(0,0,0,.3)',
        }} />
      </div>
      <span style={{
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        color: on ? color : 'var(--tx2)',
      }}>
        {on ? 'true' : 'false'}
      </span>
    </div>
  )
}

function IntControl({ value, defaultValue, onChange }: { value: unknown; defaultValue: unknown; onChange: (v: unknown) => void }) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null ? String(Number(v))
    : defaultValue !== undefined && defaultValue !== null ? String(Number(defaultValue))
    : ''

  const [draft, setDraft] = useState<string>(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  const commit = (raw: string) => {
    const v = parseInt(raw)
    if (!isNaN(v)) onChange(v)
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
      padding: '4px 8px', minHeight: 28,
    }}>
      <input
        type="text"
        inputMode="numeric"
        value={draft}
        onChange={e => {
          const raw = e.target.value.replace(/[^-\d]/g, '')
          setDraft(raw)
          if (raw !== '') {
            const v = parseInt(raw)
            if (!isNaN(v)) onChange(v)
          }
        }}
        onBlur={() => commit(draft)}
        style={{
          flex: 1, background: 'transparent', border: 'none',
          color: 'var(--tx1)', fontFamily: 'var(--font-mono)',
          fontSize: 12, fontWeight: 600, outline: 'none', minWidth: 0,
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
          <button
            key={label}
            onClick={() => {
              const v = (parseInt(draft) || 0) + delta
              setDraft(String(v))
              onChange(v)
            }}
            style={{
              background: 'transparent', border: 'none', color: 'var(--tx2)',
              cursor: 'pointer', fontSize: 7, lineHeight: 1.3, padding: '0 2px',
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function FloatControl({ value, defaultValue, onChange }: { value: unknown; defaultValue: unknown; onChange: (v: unknown) => void }) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null ? formatFloat(v)
    : defaultValue !== undefined && defaultValue !== null ? formatFloat(defaultValue)
    : ''

  const [draft, setDraft] = useState<string>(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
      padding: '4px 8px', minHeight: 28,
    }}>
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onChange={e => {
          setDraft(e.target.value)
          const v = parseFloat(e.target.value)
          if (!isNaN(v)) onChange(v)
        }}
        onBlur={() => {
          if (draft === '') { onChange(undefined); return }
          const v = parseFloat(draft)
          if (!isNaN(v)) { setDraft(formatFloat(v)); onChange(v) }
          else setDraft('')
        }}
        style={{
          flex: 1, background: 'transparent', border: 'none',
          color: 'var(--tx1)', fontFamily: 'var(--font-mono)',
          fontSize: 12, fontWeight: 600, outline: 'none', minWidth: 0,
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
          <button
            key={label}
            onClick={() => {
              const v = (parseFloat(draft) || 0) + delta
              setDraft(formatFloat(v))
              onChange(v)
            }}
            style={{
              background: 'transparent', border: 'none', color: 'var(--tx2)',
              cursor: 'pointer', fontSize: 7, lineHeight: 1.3, padding: '0 2px',
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function TextControl({ value, defaultValue, onChange, multiline }: {
  value: unknown
  defaultValue: unknown
  onChange: (v: unknown) => void
  multiline: boolean
}) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null && v !== '' ? String(v)
    : defaultValue !== undefined && defaultValue !== null ? String(defaultValue)
    : ''

  const [draft, setDraft] = useState(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  const commit = () => onChange(draft)
  const sharedStyle: React.CSSProperties = {
    width: '100%',
    background: 'var(--lift)',
    border: '1px solid var(--line)',
    borderRadius: 6,
    color: 'var(--tx1)',
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    padding: '5px 8px',
    outline: 'none',
    boxSizing: 'border-box',
  }

  const placeholder = defaultValue !== undefined ? String(defaultValue) : undefined

  return multiline ? (
    <textarea
      value={draft}
      placeholder={placeholder}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() } }}
      rows={3}
      style={{ ...sharedStyle, resize: 'vertical' }}
    />
  ) : (
    <input
      type="text"
      value={draft}
      placeholder={placeholder}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commit() } }}
      style={sharedStyle}
    />
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
