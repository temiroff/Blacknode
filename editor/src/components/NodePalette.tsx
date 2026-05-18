import { useStore } from '../store'

const GROUPS: Record<string, string[]> = {
  AI:     ['LLMAgent', 'AgentLoop', 'EmbedText', 'ToolCall'],
  Flow:   ['Branch', 'Gate', 'Map', 'Filter', 'Reduce', 'ForEach'],
  IO:     ['FileRead', 'FileWrite', 'HTTPGet', 'JSONParse', 'JSONDump'],
  Core:   ['Literal', 'Print', 'Concat', 'Switch'],
}

export default function NodePalette() {
  const { nodeTypes, addNode } = useStore()

  const handleDragStart = (e: React.DragEvent, type: string) => {
    e.dataTransfer.setData('application/blacknode-type', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  const groupedTypes = Object.entries(GROUPS).map(([group, types]) => ({
    group,
    types: types.filter(t => nodeTypes.includes(t)),
  })).filter(g => g.types.length > 0)

  const ungrouped = nodeTypes.filter(t => !Object.values(GROUPS).flat().includes(t))

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

      {groupedTypes.map(({ group, types }) => (
        <div key={group}>
          <div style={{ padding: '4px 12px', color: '#475569', fontSize: 10, fontFamily: 'monospace' }}>
            {group}
          </div>
          {types.map(type => (
            <div
              key={type}
              draggable
              onDragStart={e => handleDragStart(e, type)}
              style={{
                padding: '6px 16px',
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
      ))}

      {ungrouped.length > 0 && (
        <div>
          <div style={{ padding: '4px 12px', color: '#475569', fontSize: 10, fontFamily: 'monospace' }}>
            OTHER
          </div>
          {ungrouped.map(type => (
            <div
              key={type}
              draggable
              onDragStart={e => handleDragStart(e, type)}
              style={{
                padding: '6px 16px',
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
