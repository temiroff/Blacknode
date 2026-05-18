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

  const current   = String(data.params.value ?? DEFAULT_MODEL)
  const provColor = modelProviderColor(current)
  const provName  = modelProviderName(current)

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
      !search ||
      m.label.toLowerCase().includes(search.toLowerCase()) ||
      g.provider.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter(g => g.models.length > 0)

  return (
    <div
      onClick={() => selectNode(id)}
      style={{
        position: 'relative',
        width: 220,
        background: 'var(--node)',
        border: `1px solid ${selected ? provColor : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${provColor}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
      }}
    >
      {/* header */}
      <div style={{
        background: provColor,
        borderRadius: '8px 8px 0 0',
        padding: '5px 10px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 6,
      }}>
        <span style={{ fontWeight: 700, fontSize: 11, fontFamily: 'var(--font-ui)', letterSpacing: '0.08em' }}>
          MODEL
        </span>
        <span style={{
          fontSize: 10,
          background: 'rgba(0,0,0,.22)',
          padding: '1px 6px',
          borderRadius: 4,
          fontFamily: 'var(--font-ui)',
          fontWeight: 500,
        }}>
          {provName}
        </span>
      </div>

      {/* selector button */}
      <div style={{ padding: '6px 8px' }}>
        <button
          onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
          style={{
            width: '100%',
            background: 'var(--lift)',
            border: `1px solid ${open ? provColor : 'var(--line2)'}`,
            borderRadius: 6,
            color: provColor,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            fontWeight: 600,
            padding: '5px 8px',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            transition: 'border-color 0.15s',
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
            width: 220,
            background: 'var(--panel)',
            border: '1px solid var(--line2)',
            borderRadius: 8,
            boxShadow: '0 12px 40px rgba(0,0,0,.4)',
            zIndex: 9999,
            overflow: 'hidden',
            marginTop: 2,
          }}
        >
          {/* search */}
          <div style={{
            padding: '7px 10px',
            borderBottom: '1px solid var(--line)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            <span style={{ color: 'var(--tx3)', fontSize: 12 }}>⌕</span>
            <input
              ref={searchRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === 'Escape' && setOpen(false)}
              placeholder="filter…"
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--tx1)',
                fontFamily: 'var(--font-ui)',
                fontSize: 12,
              }}
            />
          </div>

          {/* grouped options */}
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {filtered.map(g => (
              <div key={g.provider}>
                <div style={{
                  padding: '6px 12px 3px',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  color: g.color,
                  textTransform: 'uppercase',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                }}>
                  <div style={{ width: 5, height: 5, borderRadius: 1, background: g.color }} />
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
                      fontSize: 12,
                      cursor: 'pointer',
                      color: m.value === current ? g.color : 'var(--tx2)',
                      background: hovered === m.value ? 'var(--hover)' : 'transparent',
                      borderLeft: `2px solid ${m.value === current ? g.color : 'transparent'}`,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {m.value === current && (
                      <span style={{ color: g.color, fontSize: 7 }}>●</span>
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
