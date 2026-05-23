import { useEffect, useRef, useState } from 'react'
import { CATEGORIES } from '../categories'
import { PYTHON_TOOL_TYPES } from '../pythonToolPresets'
import type { BnNodeDef } from '../types'

interface Props {
  screenPos: { x: number; y: number }
  nodeTypes?: string[]
  nodeDefs?: Record<string, BnNodeDef>
  allowedTypes?: string[]
  title?: string
  emptyMessage?: string
  actionLabel?: string
  onSelect: (type: string) => void
  onClose: () => void
}

interface SearchNode {
  type: string
  category: string
  color: string
}

const KNOWN_NODES = Object.entries(CATEGORIES).flatMap(([cat, { color, nodes }]) =>
  nodes.map(n => ({ type: n, category: cat, color }))
)
const KNOWN_BY_TYPE = new Map(KNOWN_NODES.map(n => [n.type, n]))

function buildNodeItems(
  nodeTypes?: string[],
  allowedTypes?: string[],
  nodeDefs?: Record<string, BnNodeDef>,
): SearchNode[] {
  const allowed = allowedTypes ? new Set(allowedTypes) : null
  const source = nodeTypes && nodeTypes.length > 0
    ? [...nodeTypes, ...PYTHON_TOOL_TYPES.filter(type => !nodeTypes.includes(type))]
    : KNOWN_NODES.map(n => n.type)
  return source
    .filter(type => !allowed || allowed.has(type))
    .map(type => {
      const known = KNOWN_BY_TYPE.get(type)
      if (known) return known
      const category = nodeDefs?.[type]?.category || 'Custom'
      return { type, category, color: CATEGORIES[category]?.color || 'var(--tx3)' }
    })
}

export default function NodeSearch({
  screenPos,
  nodeTypes,
  nodeDefs,
  allowedTypes,
  title,
  emptyMessage,
  actionLabel = 'add node',
  onSelect,
  onClose,
}: Props) {
  const [query, setQuery]   = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef            = useRef<HTMLInputElement>(null)
  const listRef             = useRef<HTMLDivElement>(null)
  const nodes               = buildNodeItems(nodeTypes, allowedTypes, nodeDefs)

  const filtered = query.trim()
    ? nodes.filter(n =>
        n.type.toLowerCase().includes(query.toLowerCase()) ||
        n.category.toLowerCase().includes(query.toLowerCase())
      )
    : nodes

  const safeCursor = Math.min(cursor, Math.max(filtered.length - 1, 0))

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${safeCursor}"]`) as HTMLElement
    el?.scrollIntoView({ block: 'nearest' })
  }, [safeCursor])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape')     { e.preventDefault(); onClose() }
    if (e.key === 'ArrowDown')  { e.preventDefault(); setCursor(c => Math.min(c + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp')    { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    if (e.key === 'Enter' && filtered[safeCursor]) {
      e.preventDefault()
      onSelect(filtered[safeCursor].type)
    }
  }

  const grouped: { cat: string; color: string; nodes: SearchNode[] }[] = []
  for (const item of filtered) {
    const g = grouped.find(g => g.cat === item.category)
    if (g) g.nodes.push(item)
    else grouped.push({ cat: item.category, color: item.color, nodes: [item] })
  }

  const flatItems = grouped.flatMap(g => g.nodes)

  const left = screenPos.x + 260 > window.innerWidth  ? screenPos.x - 260 : screenPos.x
  const top  = screenPos.y + 420 > window.innerHeight ? screenPos.y - Math.min(420, screenPos.y) : screenPos.y

  return (
    <>
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 999 }}
        onMouseDown={onClose}
        onContextMenu={e => { e.preventDefault(); onClose() }}
      />

      <div
        style={{
          position: 'fixed',
          left, top,
          width: 260,
          background: 'var(--panel)',
          border: '1px solid var(--line2)',
          borderRadius: 10,
          boxShadow: '0 12px 40px rgba(0,0,0,.35)',
          zIndex: 1000,
          overflow: 'hidden',
        }}
        onMouseDown={e => e.stopPropagation()}
      >
        {/* search */}
        <div style={{
          padding: '10px 12px',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <span style={{ color: 'var(--tx3)', fontSize: 14, flexShrink: 0 }}>⌕</span>
          {title && (
            <span style={{
              color: 'var(--tx3)',
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 0,
              textTransform: 'uppercase',
              flexShrink: 0,
            }}>
              {title}
            </span>
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0) }}
            onKeyDown={handleKey}
            placeholder="Search nodes..."
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--tx1)',
              fontSize: 14,
              fontFamily: 'var(--font-ui)',
            }}
          />
        </div>

        {/* results */}
        <div ref={listRef} style={{ maxHeight: 340, overflowY: 'auto' }}>
          {grouped.length === 0 && (
            <div style={{
              padding: '16px 14px',
              color: 'var(--tx3)',
              fontSize: 13,
              textAlign: 'center',
            }}>
              {query ? `No results for "${query}"` : emptyMessage ?? 'No nodes available'}
            </div>
          )}

          {grouped.map(({ cat, color, nodes }) => (
            <div key={cat}>
              <div style={{
                padding: '8px 14px 4px',
                color,
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}>
                <div style={{ width: 6, height: 6, borderRadius: 2, background: color }} />
                {cat}
              </div>

              {nodes.map(item => {
                const idx    = flatItems.indexOf(item)
                const active = idx === safeCursor
                return (
                  <div
                    key={item.type}
                    data-idx={idx}
                    onMouseEnter={() => setCursor(idx)}
                    onMouseDown={() => onSelect(item.type)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '7px 14px',
                      background: active ? 'var(--hover)' : 'transparent',
                      cursor: 'pointer',
                      borderLeft: `2px solid ${active ? item.color : 'transparent'}`,
                    }}
                  >
                    <span style={{
                      fontSize: 14,
                      fontWeight: active ? 500 : 400,
                      color: active ? 'var(--tx1)' : 'var(--tx2)',
                    }}>
                      {item.type}
                    </span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* footer */}
        <div style={{
          padding: '7px 14px',
          borderTop: '1px solid var(--line)',
          display: 'flex',
          gap: 14,
          color: 'var(--tx3)',
          fontSize: 11,
        }}>
          <span>↑↓ navigate</span>
          <span>↵ {actionLabel}</span>
          <span>esc close</span>
        </div>
      </div>
    </>
  )
}
