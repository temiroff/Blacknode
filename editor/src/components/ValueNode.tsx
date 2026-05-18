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
  const [draft, setDraft] = useState(rawValue ?? '')
  const commitRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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
        width: 170,
        background: 'var(--node)',
        border: `1px solid ${selected ? color : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${color}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
      }}
    >
      {/* header */}
      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '4px 8px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
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
      <div style={{ padding: '7px 8px', display: 'flex', alignItems: 'center' }}>
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
              color: draft ? pColor : 'var(--tx3)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
            }}>
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
            onBlur={() => {
              if (commitRef.current) clearTimeout(commitRef.current)
              commit(draft)
            }}
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              borderBottom: `1.5px solid ${pColor}55`,
              color: pColor,
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              fontWeight: 600,
              outline: 'none',
              padding: '2px 0',
            }}
          />
        )}
      </div>

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
