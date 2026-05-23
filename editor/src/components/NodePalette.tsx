import { useEffect, useState, useRef } from 'react'
import { useStore } from '../store'
import { CATEGORIES } from '../categories'
import { isPythonToolPreset, resolvePythonToolPreset } from '../pythonToolPresets'
import McpPanel from './McpPanel'
import RunsPanel from './RunsPanel'
import ScriptEditor from './ScriptEditor'
import TemplateGallery from './TemplateGallery'
import WorkflowManager from './WorkflowManager'

const ALL_CATEGORISED = Object.values(CATEGORIES).flatMap(c => c.nodes)

type Tab = 'nodes' | 'templates' | 'workflows' | 'script' | 'runs' | 'mcp'

const TOP_BAR_H = 44
const RAIL_W = 78
const PANEL_DEFAULT_W = 240
const PANEL_MIN_W = 188
const PANEL_MAX_W = 520

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
const ICON_RUNS = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M9 5v4l2.5 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
const ICON_MCP = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <rect x="3" y="6" width="12" height="7" rx="1.6" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M6 6V3.5M9 6V3.5M12 6V3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <path d="M7 13v2M11 13v2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
  </svg>
)

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'nodes',     label: 'Nodes',     icon: ICON_NODES     },
  { id: 'templates', label: 'Templates', icon: ICON_TEMPLATES },
  { id: 'workflows', label: 'Workflows', icon: ICON_WORKFLOWS },
  { id: 'script',    label: 'Script',    icon: ICON_SCRIPT    },
  { id: 'runs',      label: 'Runs',      icon: ICON_RUNS      },
  { id: 'mcp',       label: 'MCP',       icon: ICON_MCP       },
]

export default function NodePalette() {
  const { nodeTypes, nodeDefs, addNode, loadNodeTypes } = useStore()
  const [activeTab, setActiveTab] = useState<Tab | null>('nodes')
  const [panelWidth, setPanelWidth] = useState(PANEL_DEFAULT_W)
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set())
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  useEffect(() => {
    if (activeTab === 'nodes') loadNodeTypes()
  }, [activeTab, loadNodeTypes])

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: panelWidth }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPanelWidth(Math.max(PANEL_MIN_W, Math.min(PANEL_MAX_W, dragRef.current.startW + ev.clientX - dragRef.current.startX)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const nodeSpec = (type: string) => {
    const preset = resolvePythonToolPreset(type)
    return preset
      ? { type: preset.type, params: { ...preset.params } }
      : { type, params: {} }
  }

  const handleDragStart = (e: React.DragEvent, type: string) => {
    const spec = nodeSpec(type)
    e.dataTransfer.setData('application/blacknode-type', spec.type)
    e.dataTransfer.setData('application/blacknode-params', JSON.stringify(spec.params))
    e.dataTransfer.effectAllowed = 'move'
  }

  const groups = Object.entries(CATEGORIES).map(([group, { color, nodes }]) => ({
    group, color,
    types: nodes.filter(t => isPythonToolPreset(t) || nodeTypes.includes(t)),
  })).filter(g => g.types.length > 0)

  const ungrouped = nodeTypes.filter(t => !ALL_CATEGORISED.includes(t))
  for (const type of ungrouped) {
    const category = nodeDefs[type]?.category || 'Custom'
    const known = CATEGORIES[category]
    const color = known?.color || 'var(--tx3)'
    let group = groups.find(item => item.group === category)
    if (!group) {
      group = { group: category, color, types: [] }
      groups.push(group)
    }
    if (!group.types.includes(type)) group.types.push(type)
  }

  const toggleGroup = (group: string) => {
    setOpenGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const renderGroupHeader = (group: string, color: string, count: number) => {
    const open = openGroups.has(group)
    return (
      <button
        onClick={() => toggleGroup(group)}
        style={{
          width: '100%',
          background: open ? 'var(--menu-active)' : 'transparent',
          border: 'none',
          borderTop: '1px solid var(--line)',
          color,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          padding: '8px 12px',
          textAlign: 'left',
          fontFamily: 'var(--font-ui)',
        }}
        onMouseEnter={e => { if (!open) e.currentTarget.style.background = 'var(--hover)' }}
        onMouseLeave={e => { if (!open) e.currentTarget.style.background = 'transparent' }}
      >
        <span style={{ width: 10, color: 'var(--tx3)', fontSize: 12, lineHeight: 1 }}>
          {open ? '-' : '+'}
        </span>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: color, flexShrink: 0 }} />
        <span style={{
          flex: 1,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          {group}
        </span>
        <span style={{
          color: 'var(--tx3)',
          fontSize: 10,
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
        }}>
          {count}
        </span>
      </button>
    )
  }

  return (
    <div style={{ display: 'flex', flexShrink: 0, height: '100%' }}>

      {/* ── Icon rail ── */}
      <div style={{
        width: RAIL_W,
        background: 'var(--panel)',
        borderRight: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        flexShrink: 0,
      }}>
        <div style={{
          height: TOP_BAR_H,
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <span style={{
            width: 28,
            height: 24,
            border: '1px solid var(--line2)',
            borderRadius: 6,
            color: 'var(--tx2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-ui)',
            fontSize: 10,
            fontWeight: 800,
          }}>
            BN
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', padding: '4px 0' }}>
          {TABS.map(tab => {
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(active ? null : tab.id)}
                title={tab.label}
                style={{
                  width: '100%',
                  height: 50,
                  background: active ? 'var(--menu-active)' : 'transparent',
                  border: 'none',
                  borderRadius: 0,
                  color: active ? 'var(--tx1)' : 'var(--tx3)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 3,
                  padding: '0 4px',
                  boxShadow: active ? 'inset 3px 0 0 var(--accent)' : 'none',
                  transition: 'color 0.13s, background 0.13s',
                }}
                onMouseEnter={e => {
                  if (!active) {
                    e.currentTarget.style.background = 'var(--menu-hover)'
                    e.currentTarget.style.color = 'var(--tx1)'
                  }
                }}
                onMouseLeave={e => {
                  if (!active) {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.color = 'var(--tx3)'
                  }
                }}
              >
                {tab.icon}
                <span style={{
                  width: '100%',
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                  fontSize: 9,
                  fontFamily: 'var(--font-ui)',
                  letterSpacing: 0,
                  fontWeight: active ? 700 : 500,
                  lineHeight: 1.1,
                  userSelect: 'none',
                }}>
                  {tab.label}
                </span>
              </button>
            )
          })}
        </div>
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
            height: TOP_BAR_H,
            padding: '0 14px',
            borderBottom: '1px solid var(--line)',
            display: 'flex',
            alignItems: 'center',
            flexShrink: 0,
          }}>
            <span style={{
              fontSize: 11,
              fontWeight: 700,
              fontFamily: 'var(--font-ui)',
              letterSpacing: 0,
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

                {/* Structure — hardcoded, not from Python registry */}
                <div style={{ marginBottom: 4 }}>
                  {renderGroupHeader('Structure', '#6366f1', 1)}
                  {openGroups.has('Structure') && (
                    <div
                      draggable
                      onDragStart={e => handleDragStart(e, 'Subnet')}
                      onClick={() => addNode('Subnet', { x: 200 + Math.random() * 200, y: 80 + Math.random() * 200 })}
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
                        e.currentTarget.style.color = '#6366f1'
                        e.currentTarget.style.borderLeftColor = '#6366f1'
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background = 'transparent'
                        e.currentTarget.style.color = 'var(--tx2)'
                        e.currentTarget.style.borderLeftColor = 'transparent'
                      }}
                    >
                      Subnet
                    </div>
                  )}
                  </div>

                {groups.map(({ group, color, types }) => (
                  <div key={group} style={{ marginBottom: 4 }}>
                    {renderGroupHeader(group, color, types.length)}
                    {openGroups.has(group) && types.map(type => (
                        <div
                          key={type}
                          draggable
                          onDragStart={e => handleDragStart(e, type)}
                          onClick={() => {
                            const spec = nodeSpec(type)
                            addNode(spec.type, { x: 200 + Math.random() * 200, y: 80 + Math.random() * 200 }, spec.params)
                          }}
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

            {/* ── RUNS ── */}
            {activeTab === 'runs' && <RunsPanel />}

            {/* ── MCP ── */}
            {activeTab === 'mcp' && <McpPanel />}

          </div>
        </div>
      )}
    </div>
  )
}
