import { memo, useRef, useState, useEffect } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { MODEL_GROUPS, modelProviderColor, modelProviderName, DEFAULT_MODEL } from '../models'

interface NodeData {
  id: string
  type: string
  params: Record<string, unknown>
  outputs: string[]
  output_types: Record<string, string>
  cooking?: boolean
  cookResult?: unknown
  cookError?: string
}

function ModelNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, selectNode } = useStore()

  const current  = String(data.params.value ?? DEFAULT_MODEL)
  const provColor = modelProviderColor(current)
  const provName  = modelProviderName(current)

  // label shown in the button
  const currentLabel = MODEL_GROUPS
    .flatMap(g => g.models)
    .find(m => m.value === current)?.label ?? current

  const [open, setOpen]       = useState(false)
  const [search, setSearch]   = useState('')
  const [hovered, setHovered] = useState<string | null>(null)
  const searchRef             = useRef<HTMLInputElement>(null)
  const dropRef               = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 30)
  }, [open])

  // close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!dropRef.current?.contains(e.target as Node)) {
        setOpen(false); setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const select = (value: string) => {
    updateParam(id, 'value', value)
    setOpen(false); setSearch('')
  }

  const filtered = MODEL_GROUPS.map(g => ({
    ...g,
    models: g.models.filter(m =>
      !search || m.label.toLowerCase().includes(search.toLowerCase()) ||
      g.provider.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter(g => g.models.length > 0)

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        width: 210,
        background: '#111827',
        border: `1px solid ${selected ? '#f9fafb' : provColor + '55'}`,
        borderRadius: 8,
        fontFamily: 'monospace',
        fontSize: 12,
        color: '#f9fafb',
        boxShadow: selected ? `0 0 0 2px ${provColor}` : '0 2px 8px rgba(0,0,0,.5)',
      }}
    >
      {/* header */}
      <div style={{
        background: provColor,
        borderRadius: '7px 7px 0 0',
        padding: '4px 10px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 6,
      }}>
        <span style={{ fontWeight: 700, fontSize: 10, letterSpacing: 1 }}>MODEL</span>
        <span style={{
          fontSize: 9,
          background: 'rgba(0,0,0,.25)',
          padding: '1px 5px',
          borderRadius: 3,
          opacity: 0.9,
        }}>
          {provName}
        </span>
      </div>

      {/* current model button */}
      <div style={{ padding: '6px 8px' }}>
        <button
          onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
          style={{
            width: '100%',
            background: '#0f172a',
            border: `1px solid ${open ? provColor : '#334155'}`,
            borderRadius: 5,
            color: provColor,
            fontFamily: 'monospace',
            fontSize: 11,
            fontWeight: 600,
            padding: '5px 8px',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {currentLabel}
          </span>
          <span style={{ opacity: 0.5, flexShrink: 0, marginLeft: 4 }}>{open ? '▲' : '▼'}</span>
        </button>
      </div>

      {/* dropdown */}
      {open && (
        <div
          ref={dropRef}
          onMouseDown={e => e.stopPropagation()}
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            width: 210,
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: 6,
            boxShadow: '0 8px 32px rgba(0,0,0,.7)',
            zIndex: 9999,
            overflow: 'hidden',
          }}
        >
          {/* search */}
          <div style={{ padding: '6px 8px', borderBottom: '1px solid #1e293b' }}>
            <input
              ref={searchRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === 'Escape' && setOpen(false)}
              placeholder="filter…"
              style={{
                width: '100%', background: 'transparent', border: 'none',
                outline: 'none', color: '#f8fafc',
                fontFamily: 'monospace', fontSize: 11,
              }}
            />
          </div>

          {/* grouped options */}
          <div style={{ maxHeight: 260, overflowY: 'auto' }}>
            {filtered.map(g => (
              <div key={g.provider}>
                <div style={{
                  padding: '5px 10px 2px',
                  fontSize: 9, fontWeight: 700,
                  letterSpacing: 1, color: g.color,
                  textTransform: 'uppercase',
                }}>
                  {g.provider}
                </div>
                {g.models.map(m => (
                  <div
                    key={m.value}
                    onMouseEnter={() => setHovered(m.value)}
                    onMouseLeave={() => setHovered(null)}
                    onMouseDown={() => select(m.value)}
                    style={{
                      padding: '5px 14px',
                      fontSize: 11,
                      cursor: 'pointer',
                      color: m.value === current ? g.color : '#94a3b8',
                      background: hovered === m.value ? '#1e293b' : 'transparent',
                      borderLeft: `2px solid ${m.value === current ? g.color : 'transparent'}`,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    {m.value === current && (
                      <span style={{ color: g.color, fontSize: 8 }}>●</span>
                    )}
                    {m.label}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* output handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="value"
        style={{
          right: 4,
          background: portColor('Text'),
          width: 9, height: 9,
          border: `1.5px solid ${portColor('Text')}`,
          borderRadius: 3,
        }}
      />
    </div>
  )
}

export default memo(ModelNode)
