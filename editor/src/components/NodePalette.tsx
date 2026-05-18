import { useStore } from '../store'
import { CATEGORIES } from '../categories'

const ALL_CATEGORISED = Object.values(CATEGORIES).flatMap(c => c.nodes)

export default function NodePalette() {
  const { nodeTypes, addNode } = useStore()

  const handleDragStart = (e: React.DragEvent, type: string) => {
    e.dataTransfer.setData('application/blacknode-type', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  const groups = Object.entries(CATEGORIES).map(([group, { color, nodes }]) => ({
    group, color,
    types: nodes.filter(t => nodeTypes.includes(t)),
  })).filter(g => g.types.length > 0)

  const ungrouped = nodeTypes.filter(t => !ALL_CATEGORISED.includes(t))

  return (
    <aside style={{
      width: 200,
      background: 'var(--panel)',
      borderRight: '1px solid var(--line)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      <div style={{
        padding: '14px 14px 10px',
        color: 'var(--tx3)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        borderBottom: '1px solid var(--line)',
      }}>
        Nodes
      </div>

      <div style={{ padding: '8px 0', flex: 1 }}>
        {groups.map(({ group, color, types }) => (
          <div key={group} style={{ marginBottom: 4 }}>
            <div style={{
              padding: '6px 14px 4px',
              color,
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <div style={{ width: 6, height: 6, borderRadius: 2, background: color, flexShrink: 0 }} />
              {group}
            </div>

            {types.map(type => (
              <div
                key={type}
                draggable
                onDragStart={e => handleDragStart(e, type)}
                onClick={() => addNode(type, { x: 200 + Math.random() * 200, y: 100 + Math.random() * 200 })}
                style={{
                  padding: '6px 14px 6px 26px',
                  color: 'var(--tx2)',
                  fontSize: 13,
                  cursor: 'grab',
                  borderRadius: 6,
                  margin: '1px 6px',
                  userSelect: 'none',
                  borderLeft: '2px solid transparent',
                  transition: 'background 0.1s, color 0.1s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'var(--hover)'
                  e.currentTarget.style.color = 'var(--tx1)'
                  e.currentTarget.style.borderLeftColor = color
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--tx2)'
                  e.currentTarget.style.borderLeftColor = 'transparent'
                }}
              >
                {type}
              </div>
            ))}
          </div>
        ))}

        {ungrouped.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              padding: '6px 14px 4px',
              color: 'var(--tx3)',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}>
              Other
            </div>
            {ungrouped.map(type => (
              <div
                key={type}
                draggable
                onDragStart={e => handleDragStart(e, type)}
                style={{
                  padding: '6px 14px 6px 26px',
                  color: 'var(--tx2)',
                  fontSize: 13,
                  cursor: 'grab',
                  borderRadius: 6,
                  margin: '1px 6px',
                  userSelect: 'none',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--hover)'; e.currentTarget.style.color = 'var(--tx1)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--tx2)' }}
              >
                {type}
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
