import { useEffect, useRef, useState } from 'react'
import { CATEGORIES, familyColor } from '../categories'
import { PYTHON_TOOL_TYPES } from '../pythonToolPresets'
import type { BnNodeDef } from '../types'
import NodeGlyph from './NodeGlyph'

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
  accent: string
}

const KNOWN_NODES = Object.entries(CATEGORIES).flatMap(([cat, { color, nodes }]) =>
  nodes.map(n => ({ type: n, category: cat, color, accent: familyColor(cat, color) }))
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
      const color = nodeDefs?.[type]?.color || CATEGORIES[category]?.color || 'var(--tx3)'
      return { type, category, color, accent: familyColor(category, color) }
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
  const [categoryFilter, setCategoryFilter] = useState('')
  const inputRef            = useRef<HTMLInputElement>(null)
  const listRef             = useRef<HTMLDivElement>(null)
  const nodes               = buildNodeItems(nodeTypes, allowedTypes, nodeDefs)

  const categories = Array.from(new Set(nodes.map(node => node.category)))
  const filtered = nodes.filter(node => {
    const matchesCategory = !categoryFilter || node.category === categoryFilter
    const needle = query.trim().toLowerCase()
    const matchesQuery = !needle
      || node.type.toLowerCase().includes(needle)
      || node.category.toLowerCase().includes(needle)
    return matchesCategory && matchesQuery
  })

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

  const grouped: { cat: string; color: string; accent: string; nodes: SearchNode[] }[] = []
  for (const item of filtered) {
    const g = grouped.find(g => g.cat === item.category)
    if (g) g.nodes.push(item)
    else grouped.push({ cat: item.category, color: item.color, accent: item.accent, nodes: [item] })
  }

  const flatItems = grouped.flatMap(g => g.nodes)

  const viewportMargin = 8
  const menuWidth = Math.min(260, Math.max(180, window.innerWidth - viewportMargin * 2))
  const menuHeight = Math.min(420, Math.max(160, window.innerHeight - viewportMargin * 2))
  const left = Math.max(
    viewportMargin,
    Math.min(screenPos.x, window.innerWidth - menuWidth - viewportMargin),
  )
  const top = Math.max(
    viewportMargin,
    Math.min(screenPos.y, window.innerHeight - menuHeight - viewportMargin),
  )

  return (
    <>
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 999 }}
        onMouseDown={onClose}
        onContextMenu={e => { e.preventDefault(); onClose() }}
      />

      <div
        className="bn-node-search"
        style={{
          position: 'fixed',
          left, top,
          width: menuWidth,
          maxHeight: menuHeight,
          display: 'flex',
          flexDirection: 'column',
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
          flexShrink: 0,
        }}>
          <span style={{ color: 'var(--tx3)', fontSize: 16, flexShrink: 0 }}>⌕</span>
          {title && (
            <span style={{
              color: 'var(--tx3)',
              fontSize: 13,
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
              fontSize: 16,
              fontFamily: 'var(--font-ui)',
            }}
          />
        </div>

        <div className="bn-node-search-filters" aria-label="Filter nodes by category">
          <button
            className={!categoryFilter ? 'is-active' : undefined}
            onClick={() => { setCategoryFilter(''); setCursor(0) }}
            style={{ '--bn-search-filter': 'var(--accent)' } as React.CSSProperties}
          >
            All
          </button>
          {categories.map(category => {
            const categoryNode = nodes.find(node => node.category === category)
            return (
              <button
                key={category}
                className={categoryFilter === category ? 'is-active' : undefined}
                onClick={() => { setCategoryFilter(category); setCursor(0) }}
                style={{ '--bn-search-filter': categoryNode?.accent || 'var(--tx3)' } as React.CSSProperties}
              >
                {category}
              </button>
            )
          })}
        </div>

        {/* results */}
        <div ref={listRef} style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto' }}>
          {grouped.length === 0 && (
            <div style={{
              padding: '16px 14px',
              color: 'var(--tx3)',
              fontSize: 15,
              textAlign: 'center',
            }}>
              {query ? `No results for "${query}"` : emptyMessage ?? 'No nodes available'}
            </div>
          )}

          {grouped.map(({ cat, color, accent, nodes }) => (
            <div key={cat}>
              <div className="bn-node-search-group" style={{
                padding: '8px 14px 4px',
                color,
                fontSize: 14,
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                '--bn-search-accent': accent,
              } as React.CSSProperties}>
                <NodeGlyph type={cat} category={cat} className="bn-node-search-group-glyph" />
                {cat}
              </div>

              {nodes.map(item => {
                const idx    = flatItems.indexOf(item)
                const active = idx === safeCursor
                return (
                  <div
                    className={`bn-node-search-item${active ? ' is-active' : ''}`}
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
                      '--bn-search-accent': item.accent,
                    } as React.CSSProperties}
                  >
                    <NodeGlyph type={item.type} category={item.category} className="bn-node-search-item-glyph" />
                    <span style={{
                      fontSize: 16,
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
          flexWrap: 'wrap',
          gap: 14,
          color: 'var(--tx3)',
          fontSize: 13,
          flexShrink: 0,
        }}>
          <span>↑↓ navigate</span>
          <span>↵ {actionLabel}</span>
          <span>esc close</span>
        </div>
      </div>
    </>
  )
}
