import { memo, useRef, useState, useEffect } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { MODEL_GROUPS, modelProviderColor, modelProviderName, DEFAULT_MODEL } from '../models'
import NodeStatus from './NodeStatus'

interface NodeData {
  id: string
  type: string
  params: Record<string, unknown>
  outputs: string[]
  output_types: Record<string, string>
  cooking?: boolean
  cookResult?: unknown
  cookError?: string
  cookPort?: string
}

function ModelNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, selectNode, apiKeys, setApiKey, customModels, addCustomModel, removeCustomModel } = useStore()

  const current   = String(data.params.value ?? DEFAULT_MODEL)
  const provColor = modelProviderColor(current)
  const provName  = modelProviderName(current)
  const apiKey    = apiKeys[provName] ?? ''

  const currentLabel = MODEL_GROUPS
    .flatMap(g => g.models)
    .find(m => m.value === current)?.label ?? current

  const [open, setOpen]       = useState(false)
  const [search, setSearch]   = useState('')
  const [hovered, setHovered] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const searchRef             = useRef<HTMLInputElement>(null)
  const dropRef               = useRef<HTMLDivElement>(null)

  // native wheel listener so scroll inside dropdown doesn't zoom the RF canvas
  useEffect(() => {
    const el = dropRef.current
    if (!el || !open) return
    const stop = (e: WheelEvent) => e.stopPropagation()
    el.addEventListener('wheel', stop)
    return () => el.removeEventListener('wheel', stop)
  }, [open])

  const handleApiKeyChange = (val: string) => {
    setApiKey(provName, val)
  }

  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 30)
  }, [open])

  // close on outside click — capture phase so React Flow pane clicks are caught too
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!dropRef.current?.contains(e.target as Node)) {
        setOpen(false); setSearch('')
      }
    }
    window.addEventListener('mousedown', handler, true)
    return () => window.removeEventListener('mousedown', handler, true)
  }, [open])

  const allKnownValues = new Set(MODEL_GROUPS.flatMap(g => g.models.map(m => m.value)))

  const select = (value: string) => {
    updateParam(id, 'value', value)
    if (!allKnownValues.has(value)) addCustomModel(value)
    setOpen(false)
    setSearch('')
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
        width: '100%',
        minWidth: 200,
        boxSizing: 'border-box' as const,
        background: 'var(--node)',
        border: `1px solid ${selected ? provColor : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${provColor}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        overflow: 'visible',
      }}
    >
      <NodeResizer
        minWidth={200}
        minHeight={100}
        isVisible={selected}
        lineStyle={{ borderColor: provColor }}
        handleStyle={{ background: provColor, borderColor: provColor, width: 8, height: 8, borderRadius: 2 }}
      />
      <NodeStatus data={data} />

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
      <div style={{ padding: '6px 8px 4px' }}>
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

      {/* api key */}
      <div style={{ padding: '2px 8px 8px', display: 'flex', alignItems: 'center', gap: 4 }}>
        <input
          value={apiKey}
          placeholder="API key (saved per provider)"
          onClick={e => e.stopPropagation()}
          onChange={e => handleApiKeyChange(e.target.value)}
          type={showKey ? 'text' : 'password'}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            borderBottom: `1px solid ${apiKey ? provColor + '60' : 'var(--line2)'}`,
            color: apiKey ? 'var(--tx1)' : 'var(--tx3)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            outline: 'none',
            padding: '3px 2px',
            minWidth: 0,
          }}
        />
        <button
          onClick={e => { e.stopPropagation(); setShowKey(s => !s) }}
          title={showKey ? 'Hide key' : 'Show key'}
          style={{
            background: 'transparent',
            border: 'none',
            color: showKey ? provColor : 'var(--tx3)',
            cursor: 'pointer',
            fontSize: 13,
            padding: '2px 3px',
            flexShrink: 0,
            lineHeight: 1,
          }}
        >
          {showKey ? '🙈' : '👁'}
        </button>
      </div>

      {/* dropdown */}
      {open && (
        <div
          ref={dropRef}
          // stop mousedown so React Flow doesn't start dragging the node
          onMouseDown={e => e.stopPropagation()}
          // stop click so it doesn't bubble up to toggle button
          onClick={e => e.stopPropagation()}
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            width: '100%',
            minWidth: 200,
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
              onKeyDown={e => {
                if (e.key === 'Escape') { setOpen(false); setSearch('') }
                if (e.key === 'Enter' && search.trim()) select(search.trim())
              }}
              placeholder="filter or type custom model…"
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

          {/* grouped options — onWheel stops React Flow canvas zoom */}
          <div style={{ maxHeight: 280, overflowY: 'auto' }}
               onWheel={e => e.stopPropagation()}>
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
                    // onClick closes correctly; onMouseDown just stops node drag
                    onMouseDown={e => e.stopPropagation()}
                    onClick={() => select(m.value)}
                    style={{
                      padding: '6px 14px',
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
                      <span style={{ color: g.color, fontSize: 7, flexShrink: 0 }}>●</span>
                    )}
                    {m.label}
                  </div>
                ))}
              </div>
            ))}

            {/* saved custom models */}
            {customModels.filter(m => !search || m.toLowerCase().includes(search.toLowerCase())).length > 0 && (
              <div>
                <div style={{
                  padding: '6px 12px 3px',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  color: '#6b7280',
                  textTransform: 'uppercase',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                }}>
                  <div style={{ width: 5, height: 5, borderRadius: 1, background: '#6b7280' }} />
                  Custom
                </div>
                {customModels
                  .filter(m => !search || m.toLowerCase().includes(search.toLowerCase()))
                  .map(m => (
                    <div
                      key={m}
                      onMouseEnter={() => setHovered(m)}
                      onMouseLeave={() => setHovered(null)}
                      onMouseDown={e => e.stopPropagation()}
                      style={{
                        padding: '5px 8px 5px 14px',
                        fontSize: 12,
                        cursor: 'pointer',
                        color: m === current ? modelProviderColor(m) : 'var(--tx2)',
                        background: hovered === m ? 'var(--hover)' : 'transparent',
                        borderLeft: `2px solid ${m === current ? modelProviderColor(m) : 'transparent'}`,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      <span
                        onClick={() => select(m)}
                        style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {m === current && <span style={{ color: modelProviderColor(m), fontSize: 7, marginRight: 6 }}>●</span>}
                        {m}
                      </span>
                      <button
                        onClick={e => { e.stopPropagation(); removeCustomModel(m) }}
                        title="Remove"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--tx3)',
                          cursor: 'pointer',
                          fontSize: 11,
                          padding: '1px 3px',
                          flexShrink: 0,
                          lineHeight: 1,
                          opacity: hovered === m ? 1 : 0,
                          transition: 'opacity 0.1s',
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
              </div>
            )}

            {/* custom entry row */}
            {search.trim() && !customModels.includes(search.trim()) && !allKnownValues.has(search.trim()) && (
              <div
                onMouseDown={e => e.stopPropagation()}
                onClick={() => select(search.trim())}
                style={{
                  padding: '7px 14px',
                  borderTop: '1px solid var(--line)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  background: hovered === '__custom__' ? 'var(--hover)' : 'transparent',
                }}
                onMouseEnter={() => setHovered('__custom__')}
                onMouseLeave={() => setHovered(null)}
              >
                <span style={{ color: 'var(--tx3)', fontSize: 11, flexShrink: 0 }}>↵ use</span>
                <span style={{
                  color: 'var(--tx1)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {search.trim()}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* output handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="value"
        style={{
          right: -5,
          background: portColor('Model'),
          width: 9, height: 9,
          border: `1.5px solid ${portColor('Model')}`,
          borderRadius: 3,
        }}
      />
    </div>
  )
}

export default memo(ModelNode)
