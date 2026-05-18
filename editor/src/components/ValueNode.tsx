import { memo, useState, useEffect, useRef } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'

interface NodeData {
  id: string
  type: 'Text' | 'Float' | 'Int' | 'Bool'
  inputs: string[]
  outputs: string[]
  output_types: Record<string, string>
  params: Record<string, unknown>
  cookResult?: unknown
  cookError?: string
  cooking?: boolean
}

function ValueNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, selectNode, cookNode } = useStore()
  const color  = headerColor(data.type)
  const pColor = portColor(data.type)

  const rawValue = data.params.value
  const [draft, setDraft]   = useState(rawValue ?? '')
  const commitRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // keep draft in sync if value changes externally
  useEffect(() => { setDraft(rawValue ?? '') }, [rawValue])

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
        width: 160,
        background: '#111827',
        border: `1px solid ${selected ? '#f9fafb' : color + '55'}`,
        borderRadius: 8,
        fontFamily: 'monospace',
        fontSize: 12,
        color: '#f9fafb',
        boxShadow: selected ? `0 0 0 2px ${color}` : '0 2px 8px rgba(0,0,0,.5)',
        cursor: 'default',
      }}
    >
      {/* compact header */}
      <div style={{
        background: color,
        borderRadius: '7px 7px 0 0',
        padding: '3px 8px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: 10, fontWeight: 600, opacity: 0.9 }}>{data.type}</span>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, 'value') }}
          style={{
            background: 'rgba(255,255,255,.15)', border: 'none', borderRadius: 3,
            color: '#fff', cursor: 'pointer', fontSize: 9, padding: '1px 5px',
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {/* value input */}
      <div style={{ padding: '6px 8px 6px 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
        {data.type === 'Bool' ? (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', width: '100%' }}>
            <div
              onClick={e => { e.stopPropagation(); commit(!draft) }}
              style={{
                width: 32, height: 17, borderRadius: 9,
                background: draft ? pColor : '#374151',
                position: 'relative', transition: 'background .2s', flexShrink: 0,
                cursor: 'pointer',
              }}
            >
              <div style={{
                position: 'absolute', top: 2,
                left: draft ? 17 : 2,
                width: 13, height: 13,
                borderRadius: '50%',
                background: '#fff',
                transition: 'left .2s',
              }} />
            </div>
            <span style={{ color: draft ? pColor : '#6b7280', fontSize: 11 }}>
              {draft ? 'true' : 'false'}
            </span>
          </label>
        ) : (
          <input
            type={data.type === 'Text' ? 'text' : 'number'}
            step={data.type === 'Float' ? 'any' : 1}
            value={String(draft)}
            onClick={e => e.stopPropagation()}
            onChange={e => {
              const v = data.type === 'Text' ? e.target.value
                      : data.type === 'Float' ? parseFloat(e.target.value) || 0
                      : parseInt(e.target.value) || 0
              setDraft(v)
              scheduleCommit(v)
            }}
            onBlur={e => {
              if (commitRef.current) clearTimeout(commitRef.current)
              commit(draft)
            }}
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              borderBottom: `1px solid ${color}55`,
              color: pColor,
              fontFamily: 'monospace',
              fontSize: 13,
              fontWeight: 600,
              outline: 'none',
              padding: '2px 0',
            }}
          />
        )}
      </div>

      {/* single output handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="value"
        style={{
          right: 4, top: '50%',
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
