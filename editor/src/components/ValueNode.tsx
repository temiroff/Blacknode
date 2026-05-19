import { memo, useState, useEffect, useRef } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import NodeStatus from './NodeStatus'

interface NodeData {
  id: string
  type: 'Text' | 'Float' | 'Int' | 'Bool' | 'Dict'
  inputs: string[]
  outputs: string[]
  output_types: Record<string, string>
  params: Record<string, unknown>
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
  cookPort?: string
}

const formatFloat = (v: unknown): string => {
  const n = parseFloat(String(v))
  if (isNaN(n)) return '0.0'
  return Number.isInteger(n) ? `${n}.0` : String(n)
}

function ValueNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, selectNode, cookNode } = useStore()
  const color  = headerColor(data.type)
  const pColor = portColor(data.type)
  const isText  = data.type === 'Text'
  const isFloat = data.type === 'Float'
  const isInt   = data.type === 'Int'
  const isDict  = data.type === 'Dict'

  const rawValue  = data.params.value
  const initDraft = isFloat ? formatFloat(rawValue)
    : isInt  ? (rawValue ?? 0)
    : isDict ? (typeof rawValue === 'string' ? rawValue : JSON.stringify(rawValue ?? {}, null, 2))
    : (rawValue ?? '')
  const [draft, setDraft] = useState<string | number>(initDraft)
  const [jsonError, setJsonError] = useState(false)
  const commitRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setDraft(
      isFloat ? formatFloat(rawValue)
      : isInt  ? (rawValue ?? 0)
      : isDict ? (typeof rawValue === 'string' ? rawValue : JSON.stringify(rawValue ?? {}, null, 2))
      : (rawValue ?? '')
    )
  }, [rawValue])

  const commit = (val: unknown) => {
    if (commitRef.current) clearTimeout(commitRef.current)
    updateParam(id, 'value', val)
  }

  const scheduleCommit = (val: unknown) => {
    if (commitRef.current) clearTimeout(commitRef.current)
    commitRef.current = setTimeout(() => updateParam(id, 'value', val), 400)
  }

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        width:  (isText || isDict) ? '100%' : 170,
        height: (isText || isDict) ? '100%' : undefined,
        minWidth: (isText || isDict) ? 180 : undefined,
        minHeight: (isText || isDict) ? 80 : undefined,
        background: 'var(--node)',
        border: `1px solid ${selected ? color : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${color}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
        display: isText ? 'flex' : undefined,
        flexDirection: isText ? 'column' : undefined,
        boxSizing: 'border-box',
      }}
    >
      {/* resize handle — Text and Dict */}
      {(isText || isDict) && (
        <NodeResizer
          minWidth={180}
          minHeight={80}
          isVisible={selected}
          lineStyle={{ borderColor: color }}
          handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
        />
      )}
      <NodeStatus data={data} />

      {/* header */}
      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '4px 8px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-ui)' }}>
          {data.type}
        </span>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, 'value') }}
          style={{
            background: 'rgba(0,0,0,.2)', border: 'none', borderRadius: 3,
            color: '#fff', cursor: 'pointer', fontSize: 9, padding: '1px 5px',
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {/* value input */}
      <div style={{
        padding: isText ? '6px 8px' : '6px 8px',
        display: 'flex',
        alignItems: (isText || isDict) ? 'stretch' : 'center',
        flex: (isText || isDict) ? 1 : undefined,
      }}>
        {data.type === 'Bool' ? (
          <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', width: '100%' }}>
            <div
              onClick={e => { e.stopPropagation(); commit(!draft) }}
              style={{
                width: 34, height: 18, borderRadius: 9,
                background: draft ? pColor : 'var(--line2)',
                position: 'relative', transition: 'background .2s', flexShrink: 0,
                cursor: 'pointer',
              }}
            >
              <div style={{
                position: 'absolute', top: 2,
                left: draft ? 18 : 2,
                width: 14, height: 14,
                borderRadius: '50%',
                background: '#fff',
                transition: 'left .2s',
                boxShadow: '0 1px 3px rgba(0,0,0,.3)',
              }} />
            </div>
            <span style={{
              color: draft ? pColor : 'var(--tx2)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
            }}>
              {draft ? 'true' : 'false'}
            </span>
          </label>

        ) : isDict ? (
          <textarea
            value={String(draft)}
            placeholder={'{\n  "key": "value"\n}'}
            onClick={e => e.stopPropagation()}
            onChange={e => {
              setDraft(e.target.value)
              try { JSON.parse(e.target.value); setJsonError(false) } catch { setJsonError(true) }
              scheduleCommit(e.target.value)
            }}
            onBlur={() => {
              if (commitRef.current) clearTimeout(commitRef.current)
              try {
                JSON.parse(String(draft))
                setJsonError(false)
                commit(draft)
              } catch {
                setJsonError(true)
              }
            }}
            style={{
              width: '100%',
              flex: 1,
              background: 'transparent',
              border: 'none',
              borderTop: `1px solid ${jsonError ? 'var(--err)' : pColor + '40'}`,
              color: jsonError ? 'var(--err)' : 'var(--tx1)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              lineHeight: 1.6,
              outline: 'none',
              resize: 'none',
              padding: '6px 4px',
            }}
          />

        ) : isText ? (
          <textarea
            value={String(draft)}
            placeholder="enter text…"
            onClick={e => e.stopPropagation()}
            onChange={e => {
              setDraft(e.target.value)
              scheduleCommit(e.target.value)
            }}
            onBlur={() => {
              if (commitRef.current) clearTimeout(commitRef.current)
              commit(draft)
            }}
            style={{
              width: '100%',
              flex: 1,
              background: 'transparent',
              border: 'none',
              borderTop: `1px solid ${pColor}40`,
              color: 'var(--tx1)',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              lineHeight: 1.6,
              outline: 'none',
              resize: 'none',
              padding: '6px 4px',
            }}
          />

        ) : isFloat ? (
          <div style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 2 }}>
            <input
              type="text"
              inputMode="decimal"
              value={String(draft)}
              onClick={e => e.stopPropagation()}
              onMouseDown={e => e.stopPropagation()}
              onChange={e => {
                setDraft(e.target.value)
                const v = parseFloat(e.target.value)
                if (!isNaN(v)) scheduleCommit(v)
              }}
              onBlur={() => {
                if (commitRef.current) clearTimeout(commitRef.current)
                const v = parseFloat(String(draft)) || 0
                setDraft(formatFloat(v))
                commit(v)
              }}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                borderBottom: `1.5px solid ${pColor}60`,
                color: 'var(--tx1)',
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
                fontWeight: 600,
                outline: 'none',
                padding: '2px 0',
                minWidth: 0,
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
              {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
                <button
                  key={label}
                  onMouseDown={e => e.stopPropagation()}
                  onClick={e => {
                    e.stopPropagation()
                    const v = (parseFloat(String(draft)) || 0) + delta
                    setDraft(formatFloat(v))
                    commit(v)
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--tx2)',
                    cursor: 'pointer',
                    fontSize: 7,
                    lineHeight: 1.3,
                    padding: '0 3px',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 2 }}>
            <input
              type="text"
              inputMode="numeric"
              value={String(draft)}
              onClick={e => e.stopPropagation()}
              onMouseDown={e => e.stopPropagation()}
              onChange={e => {
                const raw = e.target.value.replace(/[^-\d]/g, '')
                setDraft(raw)
                const v = parseInt(raw)
                if (!isNaN(v)) scheduleCommit(v)
              }}
              onBlur={() => {
                if (commitRef.current) clearTimeout(commitRef.current)
                const v = parseInt(String(draft)) || 0
                setDraft(v)
                commit(v)
              }}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                borderBottom: `1.5px solid ${pColor}60`,
                color: 'var(--tx1)',
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
                fontWeight: 600,
                outline: 'none',
                padding: '2px 0',
                minWidth: 0,
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
              {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
                <button
                  key={label}
                  onMouseDown={e => e.stopPropagation()}
                  onClick={e => {
                    e.stopPropagation()
                    const v = (parseInt(String(draft)) || 0) + delta
                    setDraft(v)
                    commit(v)
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--tx2)',
                    cursor: 'pointer',
                    fontSize: 7,
                    lineHeight: 1.3,
                    padding: '0 3px',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        id="value"
        style={{
          right: -5,
          top: '50%',
          background: pColor,
          width: 9, height: 9,
          border: `1.5px solid ${pColor}`,
          borderRadius: 3,
        }}
      />
    </div>
  )
}

export default memo(ValueNode)
