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
    group,
    color,
    types: nodes.filter(t => nodeTypes.includes(t)),
  })).filter(g => g.types.length > 0)

  const ungrouped = nodeTypes.filter(t => !ALL_CATEGORISED.includes(t))

  return (
    <aside style={{
      width: 180,
      background: '#0f172a',
      borderRight: '1px solid #1e293b',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{ padding: '12px 12px 8px', color: '#64748b', fontSize: 11, fontFamily: 'monospace', letterSpacing: 1 }}>
        NODES
      </div>

      {groups.map(({ group, color, types }) => (
        <div key={group}>
          <div style={{ padding: '4px 12px', color, fontSize: 10, fontFamily: 'monospace', fontWeight: 600 }}>
            {group}
          </div>
          {types.map(type => (
            <div
              key={type}
              draggable
              onDragStart={e => handleDragStart(e, type)}
              style={{
                padding: '5px 16px',
                color: '#cbd5e1',
                fontSize: 12,
                fontFamily: 'monospace',
                cursor: 'grab',
                borderRadius: 4,
                margin: '1px 6px',
                userSelect: 'none',
                borderLeft: `2px solid transparent`,
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = '#1e293b'
                e.currentTarget.style.borderLeftColor = color
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.borderLeftColor = 'transparent'
              }}
            >
              {type}
            </div>
          ))}
        </div>
      ))}

      {ungrouped.length > 0 && (
        <div>
          <div style={{ padding: '4px 12px', color: '#475569', fontSize: 10, fontFamily: 'monospace', fontWeight: 600 }}>
            OTHER
          </div>
          {ungrouped.map(type => (
            <div
              key={type}
              draggable
              onDragStart={e => handleDragStart(e, type)}
              style={{
                padding: '5px 16px',
                color: '#cbd5e1',
                fontSize: 12,
                fontFamily: 'monospace',
                cursor: 'grab',
                borderRadius: 4,
                margin: '1px 6px',
                userSelect: 'none',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = '#1e293b')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              {type}
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
