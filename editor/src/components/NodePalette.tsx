import { useState } from 'react'
import { useStore } from '../store'
import { CATEGORIES } from '../categories'
import ScriptEditor from './ScriptEditor'
import TemplateGallery from './TemplateGallery'

const ALL_CATEGORISED = Object.values(CATEGORIES).flatMap(c => c.nodes)

type Tab = 'nodes' | 'script' | 'templates'

const TABS: { id: Tab; label: string }[] = [
  { id: 'nodes',     label: 'Nodes'     },
  { id: 'templates', label: 'Templates' },
  { id: 'script',    label: 'Script'    },
]

export default function NodePalette() {
  const { nodeTypes, addNode } = useStore()
  const [activeTab, setActiveTab] = useState<Tab>('nodes')

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
      width: 220,
      background: 'var(--panel)',
      borderRight: '1px solid var(--line)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      {/* tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--line)',
        flexShrink: 0,
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              flex: 1,
              padding: '10px 0',
              background: 'transparent',
              border: 'none',
              borderBottom: `2px solid ${activeTab === tab.id ? 'var(--accent)' : 'transparent'}`,
              color: activeTab === tab.id ? 'var(--tx1)' : 'var(--tx2)',
              cursor: 'pointer',
              fontFamily: 'var(--font-ui)',
              fontSize: 12,
              fontWeight: activeTab === tab.id ? 600 : 400,
              transition: 'color 0.15s',
              marginBottom: -1,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

        {/* ── NODES ── */}
        {activeTab === 'nodes' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {groups.map(({ group, color, types }) => (
              <div key={group} style={{ marginBottom: 4 }}>
                <div style={{
                  padding: '8px 14px 4px',
                  color,
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
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
                    onClick={() => addNode(type, { x: 200 + Math.random() * 200, y: 80 + Math.random() * 200 })}
                    style={{
                      padding: '6px 14px 6px 28px',
                      color: 'var(--tx2)',
                      fontSize: 14,
                      cursor: 'grab',
                      borderRadius: 6,
                      margin: '1px 6px',
                      userSelect: 'none',
                      borderLeft: '2px solid transparent',
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
                  padding: '8px 14px 4px',
                  color: 'var(--tx3)',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                }}>
                  Custom
                </div>
                {ungrouped.map(type => (
                  <div
                    key={type}
                    draggable
                    onDragStart={e => handleDragStart(e, type)}
                    style={{
                      padding: '6px 14px 6px 28px',
                      color: 'var(--tx2)',
                      fontSize: 14,
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
        )}

        {/* ── TEMPLATES ── */}
        {activeTab === 'templates' && (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <TemplateGallery />
          </div>
        )}

        {/* ── SCRIPT ── */}
        {activeTab === 'script' && (
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <ScriptEditor />
          </div>
        )}

      </div>
    </aside>
  )
}
