import { useEffect, useRef, useState } from 'react'
import { CATEGORIES } from '../categories'

interface Props {
  screenPos: { x: number; y: number }
  onSelect: (type: string) => void
  onClose: () => void
}

const ALL_NODES = Object.entries(CATEGORIES).flatMap(([cat, { color, nodes }]) =>
  nodes.map(n => ({ type: n, category: cat, color }))
)

export default function NodeSearch({ screenPos, onSelect, onClose }: Props) {
  const [query, setQuery]   = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef            = useRef<HTMLInputElement>(null)
  const listRef             = useRef<HTMLDivElement>(null)

  const filtered = query.trim()
    ? ALL_NODES.filter(n =>
        n.type.toLowerCase().includes(query.toLowerCase()) ||
        n.category.toLowerCase().includes(query.toLowerCase())
      )
    : ALL_NODES

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

  const grouped: { cat: string; color: string; nodes: typeof ALL_NODES }[] = []
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
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0) }}
            onKeyDown={handleKey}
            placeholder="Search nodes…"
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
              No results for "{query}"
            </div>
          )}

          {grouped.map(({ cat, color, nodes }) => (
            <div key={cat}>
              <div style={{
                padding: '8px 14px 4px',
                color,
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.08em',
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
          <span>↵ add node</span>
          <span>esc close</span>
        </div>
      </div>
    </>
  )
}
