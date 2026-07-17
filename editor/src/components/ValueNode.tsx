import { memo, useState, useEffect, useRef } from 'react'
import { Handle, Position, NodeProps, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

interface NodeData extends NodeCookState {
  id: string
  type: 'Text' | 'Float' | 'Int' | 'Bool' | 'Color' | 'List' | 'Dict'
  inputs: string[]
  outputs: string[]
  output_types: Record<string, string>
  input_types: Record<string, string>
  params: Record<string, unknown>
  variadic_input?: { prefix: string; type: string } | null
  promoted_outputs?: string[] | null
}

const formatFloat = (v: unknown): string => {
  const n = parseFloat(String(v))
  if (isNaN(n)) return '0.0'
  return Number.isInteger(n) ? `${n}.0` : String(n)
}

function normalizeHexColor(value: unknown): string | null {
  const text = String(value ?? '').trim()
  const six = text.match(/^#?([0-9a-f]{6})$/i)
  if (six) return `#${six[1].toLowerCase()}`
  const three = text.match(/^#?([0-9a-f]{3})$/i)
  if (!three) return null
  return `#${three[1].split('').map(ch => ch + ch).join('').toLowerCase()}`
}

function ValueNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, cookNode, edges, disconnectEdge } = useStore()
  const updateNodeInternals = useUpdateNodeInternals()
  const color  = headerColor(data.type)
  const pColor = portColor(data.type)
  const isText  = data.type === 'Text'
  const isFloat = data.type === 'Float'
  const isInt   = data.type === 'Int'
  const isColor = data.type === 'Color'
  const isList  = data.type === 'List'
  const isDict  = data.type === 'Dict'
  const isStructured = isDict || isList
  const isLargeText = isText || isStructured
  const variadicPorts = isList ? (data.inputs ?? []).filter(port =>
    new RegExp(`^${data.variadic_input?.prefix || 'item'}_[0-9]+$`).test(port)
  ) : []
  const nextVariadic = (() => {
    const prefix = data.variadic_input?.prefix || 'item'
    let index = 1
    while (variadicPorts.includes(`${prefix}_${index}`)) index += 1
    return `${prefix}_${index}`
  })()
  const showValueOutput = data.promoted_outputs == null
    || data.promoted_outputs.includes('value')
    || edges.some(edge => edge.source === id && edge.sourceHandle === 'value')

  useEffect(() => { updateNodeInternals(id) }, [id, variadicPorts.join('|'), showValueOutput, updateNodeInternals])

  const rawValue  = data.params.value
  const resolveDraft = (value: unknown): string | number => isFloat ? formatFloat(value)
    : isInt  ? Number(value ?? 0)
    : isColor ? normalizeHexColor(value) ?? '#22c55e'
    : isList ? (typeof value === 'string' ? value : JSON.stringify(value ?? [], null, 2))
    : isDict ? (typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2))
    : typeof value === 'string' || typeof value === 'number' ? value
    : value === undefined || value === null ? ''
    : String(value)
  const initDraft = resolveDraft(rawValue)
  const [draft, setDraft] = useState<string | number>(initDraft)
  const [jsonError, setJsonError] = useState(false)
  const commitRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setDraft(resolveDraft(rawValue))
  }, [rawValue])

  const commit = (val: unknown) => {
    if (commitRef.current) clearTimeout(commitRef.current)
    updateParam(id, 'value', val)
  }

  const scheduleCommit = (val: unknown) => {
    if (commitRef.current) clearTimeout(commitRef.current)
    commitRef.current = setTimeout(() => updateParam(id, 'value', val), 400)
  }
  const validateStructuredDraft = (text: string): boolean => {
    try {
      const parsed = JSON.parse(text)
      return isList ? Array.isArray(parsed) : Boolean(parsed && typeof parsed === 'object' && !Array.isArray(parsed))
    } catch {
      return false
    }
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={color}
      style={{
        width:  isLargeText ? '100%' : 170,
        height: isLargeText ? '100%' : undefined,
        minWidth: isLargeText ? 180 : undefined,
        minHeight: isLargeText ? 80 : undefined,
        display: isLargeText ? 'flex' : undefined,
        flexDirection: isLargeText ? 'column' : undefined,
      }}
    >
      {/* resize handle — Text, List, and Dict */}
      {isLargeText && (
        <NodeResizer
          minWidth={180}
          minHeight={80}
          isVisible={selected}
          lineStyle={{ borderColor: color }}
          handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
        />
      )}

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
      {isList && data.variadic_input && (
        <div style={{ padding: '4px 8px 0 16px', display: 'flex', flexDirection: 'column', gap: 3, flexShrink: 0 }}>
          <div style={{ position: 'relative', color: portColor(data.variadic_input.type), fontSize: 9, fontFamily: 'var(--font-ui)' }}>
            <Handle type="target" position={Position.Left} id="__new__" style={{ left: -21, width: 11, height: 11, background: 'var(--node)', border: `2px dashed ${portColor(data.variadic_input.type)}` }} />
            {nextVariadic} · connect to add
          </div>
          {variadicPorts.map(port => {
            const edge = edges.find(candidate => candidate.target === id && candidate.targetHandle === port)
            return (
              <div key={port} style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', color: 'var(--tx2)', fontSize: 9, fontFamily: 'var(--font-mono)' }}>
                <Handle type="target" position={Position.Left} id={port} style={{ left: -21, width: 9, height: 9, background: portColor(data.variadic_input?.type || 'Any') }} />
                <span>{port}</span>
                {edge && <button onClick={event => { event.stopPropagation(); void disconnectEdge(edge.id) }} style={{ border: 0, background: 'transparent', color: 'var(--tx3)', cursor: 'pointer', fontSize: 9 }}>×</button>}
              </div>
            )
          })}
        </div>
      )}
      <div style={{
        padding: '6px 8px',
        display: 'flex',
        alignItems: isLargeText ? 'stretch' : 'center',
        flex: isLargeText ? 1 : undefined,
        minHeight: isLargeText ? 0 : undefined,
        boxSizing: 'border-box',
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

        ) : isStructured ? (
          <textarea
            value={String(draft)}
            placeholder={isList ? '[\n  "item"\n]' : '{\n  "key": "value"\n}'}
            onClick={e => e.stopPropagation()}
            onChange={e => {
              setDraft(e.target.value)
              setJsonError(!validateStructuredDraft(e.target.value))
              scheduleCommit(e.target.value)
            }}
            onBlur={() => {
              if (commitRef.current) clearTimeout(commitRef.current)
              if (validateStructuredDraft(String(draft))) {
                setJsonError(false)
                commit(draft)
              } else {
                setJsonError(true)
              }
            }}
            style={{
              width: '100%',
              flex: 1,
              minHeight: 0,
              height: '100%',
              background: 'transparent',
              border: 'none',
              borderTop: `1px solid ${jsonError ? 'var(--err)' : pColor + '40'}`,
              color: jsonError ? 'var(--err)' : 'var(--tx1)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              lineHeight: 1.6,
              outline: 'none',
              resize: 'none',
              overflow: 'auto',
              padding: '6px 4px',
              boxSizing: 'border-box',
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
              minHeight: 0,
              height: '100%',
              background: 'transparent',
              border: 'none',
              borderTop: `1px solid ${pColor}40`,
              color: 'var(--tx1)',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              lineHeight: 1.6,
              outline: 'none',
              resize: 'none',
              overflow: 'auto',
              padding: '6px 4px',
              boxSizing: 'border-box',
            }}
          />

        ) : isColor ? (
          <input
            type="color"
            value={normalizeHexColor(draft) ?? '#22c55e'}
            aria-label="Pick color"
            onClick={e => e.stopPropagation()}
            onMouseDown={e => e.stopPropagation()}
            onChange={e => {
              setDraft(e.target.value)
              commit(e.target.value)
            }}
            style={{
              width: '100%',
              height: 32,
              padding: 2,
              background: 'var(--lift)',
              border: `1px solid ${pColor}80`,
              borderRadius: 6,
              cursor: 'pointer',
              boxSizing: 'border-box',
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

      {showValueOutput && (
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
      )}
    </NodeFrame>
  )
}

export default memo(ValueNode)
