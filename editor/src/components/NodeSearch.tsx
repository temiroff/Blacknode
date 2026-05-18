import { useEffect, useRef, useState } from 'react'
import { CATEGORIES } from '../categories'
import { headerColor } from '../categories'

interface Props {
  screenPos: { x: number; y: number }
  onSelect: (type: string) => void
  onClose: () => void
}

// flat list with category metadata for rendering
const ALL_NODES = Object.entries(CATEGORIES).flatMap(([cat, { color, nodes }]) =>
  nodes.map(n => ({ type: n, category: cat, color }))
)

export default function NodeSearch({ screenPos, onSelect, onClose }: Props) {
  const [query, setQuery]       = useState('')
  const [cursor, setCursor]     = useState(0)
  const inputRef                = useRef<HTMLInputElement>(null)
  const listRef                 = useRef<HTMLDivElement>(null)

  const filtered = query.trim()
    ? ALL_NODES.filter(n => n.type.toLowerCase().includes(query.toLowerCase()))
    : ALL_NODES

  // clamp cursor when list shrinks
  const safeCursor = Math.min(cursor, Math.max(filtered.length - 1, 0))

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    // scroll active item into view
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

  // group filtered results by category for display
  const grouped: { cat: string; color: string; nodes: typeof ALL_NODES }[] = []
  for (const item of filtered) {
    const g = grouped.find(g => g.cat === item.category)
    if (g) g.nodes.push(item)
    else grouped.push({ cat: item.category, color: item.color, nodes: [item] })
  }

  // build a flat index map for cursor alignment
  const flatItems: typeof ALL_NODES = grouped.flatMap(g => g.nodes)

  // popup bounds: flip left if too close to right edge
  const left = screenPos.x + 240 > window.innerWidth ? screenPos.x - 240 : screenPos.x
  const top  = screenPos.y + 400 > window.innerHeight ? screenPos.y - Math.min(400, screenPos.y) : screenPos.y

  return (
    <>
      {/* backdrop — click outside to close */}
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 999 }}
        onMouseDown={onClose}
        onContextMenu={e => { e.preventDefault(); onClose() }}
      />

      <div
        style={{
          position: 'fixed',
          left, top,
          width: 240,
          background: '#0f172a',
          border: '1px solid #334155',
          borderRadius: 8,
          boxShadow: '0 8px 32px rgba(0,0,0,.6)',
          zIndex: 1000,
          overflow: 'hidden',
        }}
        onMouseDown={e => e.stopPropagation()}
      >
        {/* search input */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid #1e293b' }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0) }}
            onKeyDown={handleKey}
            placeholder="Search nodes…"
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: '#f8fafc',
              fontFamily: 'monospace',
              fontSize: 13,
            }}
          />
        </div>

        {/* results */}
        <div ref={listRef} style={{ maxHeight: 320, overflowY: 'auto' }}>
          {grouped.length === 0 && (
            <div style={{ padding: '10px 14px', color: '#475569', fontFamily: 'monospace', fontSize: 12 }}>
              no results
            </div>
          )}

          {grouped.map(({ cat, color, nodes }) => (
            <div key={cat}>
              <div style={{
                padding: '5px 12px 3px',
                color, fontSize: 9,
                fontFamily: 'monospace',
                fontWeight: 700,
                letterSpacing: 1,
                textTransform: 'uppercase',
              }}>
                {cat}
              </div>

              {nodes.map(item => {
                const idx = flatItems.indexOf(item)
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
                      gap: 8,
                      padding: '5px 14px',
                      background: active ? '#1e293b' : 'transparent',
                      cursor: 'pointer',
                      borderLeft: `2px solid ${active ? item.color : 'transparent'}`,
                    }}
                  >
                    <div style={{
                      width: 8, height: 8,
                      borderRadius: 2,
                      background: item.color,
                      flexShrink: 0,
                    }} />
                    <span style={{
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: active ? '#f8fafc' : '#94a3b8',
                    }}>
                      {item.type}
                    </span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* footer hint */}
        <div style={{
          padding: '5px 12px',
          borderTop: '1px solid #1e293b',
          display: 'flex', gap: 12,
          color: '#334155', fontSize: 10, fontFamily: 'monospace',
        }}>
          <span>↑↓ navigate</span>
          <span>↵ add</span>
          <span>esc close</span>
        </div>
      </div>
    </>
  )
}
