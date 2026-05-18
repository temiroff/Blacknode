import { useState, useRef } from 'react'
import { useStore } from '../store'
import { CATEGORIES } from '../categories'
import ScriptEditor from './ScriptEditor'
import TemplateGallery from './TemplateGallery'
import WorkflowManager from './WorkflowManager'

const ALL_CATEGORISED = Object.values(CATEGORIES).flatMap(c => c.nodes)

type Tab = 'nodes' | 'templates' | 'workflows' | 'script'

const ICON_NODES = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <circle cx="4" cy="9" r="2.5" fill="currentColor" opacity="0.85"/>
    <circle cx="14" cy="4" r="2.5" fill="currentColor"/>
    <circle cx="14" cy="14" r="2.5" fill="currentColor"/>
    <line x1="6.4" y1="8.1" x2="11.6" y2="5.0" stroke="currentColor" strokeWidth="1.2"/>
    <line x1="6.4" y1="9.9" x2="11.6" y2="13.0" stroke="currentColor" strokeWidth="1.2"/>
  </svg>
)
const ICON_TEMPLATES = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <rect x="2" y="2" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="1.3"/>
    <rect x="7" y="7" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="1.3"/>
  </svg>
)
const ICON_WORKFLOWS = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <rect x="1" y="6" width="5" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
    <rect x="12" y="6" width="5" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M6 9h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <path d="M10 7l2 2-2 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
const ICON_SCRIPT = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M6 5L2 9l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 5l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'nodes',     label: 'Nodes',     icon: ICON_NODES     },
  { id: 'templates', label: 'Templates', icon: ICON_TEMPLATES },
  { id: 'workflows', label: 'Workflows', icon: ICON_WORKFLOWS },
  { id: 'script',    label: 'Script',    icon: ICON_SCRIPT    },
]

export default function NodePalette() {
  const { nodeTypes, addNode } = useStore()
  const [activeTab, setActiveTab] = useState<Tab | null>('nodes')
  const [panelWidth, setPanelWidth] = useState(220)
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: panelWidth }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPanelWidth(Math.max(160, Math.min(520, dragRef.current.startW + ev.clientX - dragRef.current.startX)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

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
    <div style={{ display: 'flex', flexShrink: 0, height: '100%' }}>

      {/* ── Icon rail ── */}
      <div style={{
        width: 52,
        background: 'var(--panel)',
        borderRight: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 8,
        gap: 2,
        flexShrink: 0,
      }}>
        {TABS.map(tab => {
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(active ? null : tab.id)}
              title={tab.label}
              style={{
                width: 40,
                height: 46,
                background: active ? 'var(--hover)' : 'transparent',
                border: 'none',
                borderRadius: 8,
                color: active ? 'var(--accent)' : 'var(--tx3)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 3,
                padding: 0,
                transition: 'color 0.13s, background 0.13s',
              }}
              onMouseEnter={e => {
                if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--tx1)'
              }}
              onMouseLeave={e => {
                if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--tx3)'
              }}
            >
              {tab.icon}
              <span style={{
                fontSize: 9,
                fontFamily: 'var(--font-ui)',
                letterSpacing: '0.04em',
                fontWeight: active ? 600 : 400,
                userSelect: 'none',
              }}>
                {tab.label}
              </span>
            </button>
          )
        })}
      </div>

      {/* ── Content panel ── */}
      {activeTab && (
        <div style={{
          width: panelWidth,
          background: 'var(--panel)',
          borderRight: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          position: 'relative',
        }}>
          {/* resize handle */}
          <div
            onMouseDown={startResize}
            style={{
              position: 'absolute',
              right: -2,
              top: 0,
              bottom: 0,
              width: 4,
              cursor: 'col-resize',
              zIndex: 5,
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          />

          {/* panel title */}
          <div style={{
            padding: '10px 14px 8px',
            borderBottom: '1px solid var(--line)',
            flexShrink: 0,
          }}>
            <span style={{
              fontSize: 11,
              fontWeight: 700,
              fontFamily: 'var(--font-ui)',
              letterSpacing: '0.09em',
              textTransform: 'uppercase',
              color: 'var(--tx2)',
            }}>
              {TABS.find(t => t.id === activeTab)?.label}
            </span>
          </div>

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
                          padding: '5px 14px 5px 26px',
                          color: 'var(--tx2)',
                          fontSize: 13,
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
                          padding: '5px 14px 5px 26px',
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
            )}

            {/* ── TEMPLATES ── */}
            {activeTab === 'templates' && (
              <div style={{ flex: 1, overflowY: 'auto' }}>
                <TemplateGallery />
              </div>
            )}

            {/* ── WORKFLOWS ── */}
            {activeTab === 'workflows' && <WorkflowManager />}

            {/* ── SCRIPT ── */}
            {activeTab === 'script' && (
              <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <ScriptEditor />
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  )
}
