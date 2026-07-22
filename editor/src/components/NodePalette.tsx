import { useEffect, useMemo, useState, useRef } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { CATEGORIES } from '../categories'
import { CORE_GROUP, componentDisplayName, groupForPackage, packageGroupIndex } from '../packageGroups'
import { PYTHON_TOOL_TYPES, resolvePythonToolPreset } from '../pythonToolPresets'
import McpPanel from './McpPanel'
import LearnedNodesPanel from './LearnedNodesPanel'
import PackagesPanel from './PackagesPanel'
import RunsPanel from './RunsPanel'
import ScriptEditor from './ScriptEditor'
import TemplateGallery from './TemplateGallery'
import WorkflowManager from './WorkflowManager'

// Curated ordering for the built-in categories; anything else sorts by name.
const CATEGORY_ORDER = Object.keys(CATEGORIES)

// The Nodes tab groups by package (like the Templates tab), then by category
// inside each package, so a long node list stays scannable.
interface PaletteSubGroup { name: string; color: string; types: string[] }
interface PaletteGroup { name: string; color: string; subgroups: PaletteSubGroup[]; count: number }

type Tab = 'nodes' | 'templates' | 'workflows' | 'script' | 'runs' | 'learned' | 'mcp' | 'packages'

const TOP_BAR_H = 44
const RAIL_W = 78
const PANEL_DEFAULT_W = 240
const PANEL_MIN_W = 188
const PANEL_MAX_W = 520
const welcomeButtonStyle: React.CSSProperties = {
  border: '1px solid var(--line2)',
  borderRadius: 6,
  background: 'transparent',
  color: 'var(--tx2)',
  cursor: 'pointer',
  fontFamily: 'var(--font-ui)',
  fontSize: 12,
  padding: '7px 12px',
}

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
const ICON_LEARNED = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M2.5 6.5L9 3.5l6.5 3-6.5 3-6.5-3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
    <path d="M5 8v3.2c0 1.2 1.8 2.1 4 2.1s4-.9 4-2.1V8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <path d="M15.5 6.5v4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
  </svg>
)
const ICON_PACKAGES = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M9 2l6 3v8l-6 3-6-3V5l6-3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
    <path d="M3 5l6 3 6-3M9 8v8" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
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
  { id: 'learned',   label: 'Learned',   icon: ICON_LEARNED   },
  { id: 'packages',  label: 'Packages',  icon: ICON_PACKAGES  },
  { id: 'mcp',       label: 'MCP',       icon: ICON_MCP       },
]

export default function NodePalette() {
  const { nodeTypes, nodeDefs, packages, addNode, loadNodeTypes, learnedNodeHighlight } = useStore()
  const [activeTab, setActiveTab] = useState<Tab | null>('templates')
  const [showPackageWelcome, setShowPackageWelcome] = useState(false)
  const [panelWidth, setPanelWidth] = useState(PANEL_DEFAULT_W)
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set())
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  useEffect(() => {
    if (activeTab === 'nodes') loadNodeTypes()
  }, [activeTab, loadNodeTypes])

  useEffect(() => {
    let active = true
    api.getOnboarding()
      .then(state => {
        if (active && !state.package_welcome_seen) {
          setActiveTab('packages')
          setShowPackageWelcome(true)
        }
      })
      .catch(() => {
        if (active) {
          setActiveTab('packages')
          setShowPackageWelcome(true)
        }
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!learnedNodeHighlight) return
    setActiveTab('nodes')
    setOpenGroups(prev => new Set(prev).add(CORE_GROUP.name).add(`${CORE_GROUP.name}/Learned`))
  }, [learnedNodeHighlight])

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

  const paletteGroups = useMemo<PaletteGroup[]>(() => {
    const index = packageGroupIndex(packages)
    const tops = new Map<string, { color: string; subs: Map<string, PaletteSubGroup> }>()

    // `type` is undefined when declaring a component that has no nodes yet.
    const place = (top: { name: string; color: string }, subName: string, subColor: string, type?: string) => {
      let entry = tops.get(top.name)
      if (!entry) {
        entry = { color: top.color, subs: new Map() }
        tops.set(top.name, entry)
      }
      let sub = entry.subs.get(subName)
      if (!sub) {
        sub = { name: subName, color: subColor, types: [] }
        entry.subs.set(subName, sub)
      }
      if (type && !sub.types.includes(type)) sub.types.push(type)
    }

    // Subnet and the Python tool presets are editor-side, not registry nodes.
    place(CORE_GROUP, 'Structure', CATEGORIES.Subnet.color, 'Subnet')
    for (const type of PYTHON_TOOL_TYPES) {
      place(CORE_GROUP, 'PythonTools', CATEGORIES.PythonTools.color, type)
    }

    // Colors declared by package manifests, keyed by category name.
    const declaredColors: Record<string, string> = {}
    for (const pkg of packages) Object.assign(declaredColors, pkg.categories ?? {})

    for (const type of nodeTypes) {
      const def = nodeDefs[type]
      if (def?.hidden) continue
      const top = groupForPackage(def?.package ?? '', index)
      // Packages organise their nodes into components, which say what a node
      // does far better than a category does. Uncomponentised packages and
      // built-ins keep falling back to the declared category.
      const sub = def?.component ? componentDisplayName(def.component) : (def?.category || 'Custom')
      // Resolve the color from the subgroup's own name so every node in it
      // agrees, rather than from whichever node happened to be placed first.
      const color = CATEGORIES[sub]?.color || declaredColors[sub] || top.color
      place(top, sub, color, type)
    }

    // Components a package declares but has not implemented yet still show, so
    // the palette reads as the package roadmap rather than only what exists.
    for (const pkg of packages) {
      if (!pkg.ok) continue
      const top = groupForPackage(pkg.name, index)
      for (const [name, component] of Object.entries(pkg.components ?? {})) {
        // A component that declares node types but shows none of its own is the
        // package's legacy loading shim — its nodes are attributed to the
        // roadmap components they declare, so listing it as empty is noise.
        if ((component.node_types ?? []).length > 0) continue
        const entry = tops.get(top.name)
        const label = componentDisplayName(name)
        if (entry?.subs.has(label)) continue
        place(top, label, top.color, undefined)
      }
    }

    return Array.from(tops.entries())
      .map(([name, { color, subs }]) => {
        // A package leads with the category it is named after; built-in
        // categories keep their curated order.
        const rank = (sub: PaletteSubGroup) => {
          if (sub.name === name) return -1
          const i = CATEGORY_ORDER.indexOf(sub.name)
          return i === -1 ? CATEGORY_ORDER.length : i
        }
        // Implemented components first; not-yet-built ones sink to the bottom.
        const subgroups = Array.from(subs.values())
          .sort((a, b) =>
            Number(a.types.length === 0) - Number(b.types.length === 0)
            || rank(a) - rank(b)
            || a.name.localeCompare(b.name))
        return { name, color, subgroups, count: subgroups.reduce((n, s) => n + s.types.length, 0) }
      })
      .sort((a, b) =>
        Number(a.name !== CORE_GROUP.name) - Number(b.name !== CORE_GROUP.name)
        || a.name.localeCompare(b.name))
  }, [nodeTypes, nodeDefs, packages])

  const toggleGroup = (group: string) => {
    setOpenGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const finishPackageWelcome = async (tab: Tab) => {
    try {
      await api.setOnboarding(true)
    } catch {
      // Keep the editor usable; an unavailable server will cause the prompt
      // to return on the next launch instead of losing the acknowledgement.
    }
    setShowPackageWelcome(false)
    setActiveTab(tab)
  }

  // `key` is the accordion path ('Core', 'Core/Flow') so a category name reused
  // by two packages still expands independently.
  const renderGroupHeader = (key: string, label: string, color: string, count: number, nested = false) => {
    const open = openGroups.has(key)
    // A declared component with no nodes yet: shown so the palette reads as the
    // package roadmap, but dimmed and inert since there is nothing to expand.
    if (nested && count === 0) {
      return (
        <div
          title="Declared by the package but not implemented yet"
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '4px 12px 4px 24px', color: 'var(--tx3)',
            fontFamily: 'var(--font-ui)', opacity: 0.5, cursor: 'default',
          }}
        >
          <span style={{ width: 10 }} />
          <span style={{
            width: 5, height: 5, borderRadius: 2, flexShrink: 0,
            border: `1px solid ${color}`, background: 'transparent',
          }} />
          <span style={{
            flex: 1, fontSize: 10, fontWeight: 600,
            letterSpacing: '0.03em', textTransform: 'uppercase',
          }}>
            {label}
          </span>
          <span style={{ fontSize: 10, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>0</span>
        </div>
      )
    }
    return (
      <button
        onClick={() => toggleGroup(key)}
        style={{
          width: '100%',
          background: open && !nested ? 'var(--menu-active)' : 'transparent',
          border: 'none',
          borderTop: nested ? 'none' : '1px solid var(--line)',
          color,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          padding: nested ? '4px 12px 4px 24px' : '8px 12px',
          textAlign: 'left',
          fontFamily: 'var(--font-ui)',
        }}
        onMouseEnter={e => { if (!open || nested) e.currentTarget.style.background = 'var(--hover)' }}
        onMouseLeave={e => { if (!open || nested) e.currentTarget.style.background = 'transparent' }}
      >
        <span style={{ width: 10, color: 'var(--tx3)', fontSize: 12, lineHeight: 1 }}>
          {open ? '-' : '+'}
        </span>
        <span style={{
          width: nested ? 5 : 6,
          height: nested ? 5 : 6,
          borderRadius: 2,
          background: color,
          flexShrink: 0,
        }} />
        <span style={{
          flex: 1,
          fontSize: nested ? 10 : 11,
          fontWeight: nested ? 600 : 700,
          letterSpacing: nested ? '0.03em' : '0.06em',
          textTransform: 'uppercase',
          opacity: nested ? 0.85 : 1,
        }}>
          {label}
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

  const renderNodeItem = (type: string, color: string) => (
    <div
      key={type}
      className={type === learnedNodeHighlight ? 'bn-node-palette-item bn-learned-node-pulse' : 'bn-node-palette-item'}
      draggable
      onDragStart={e => handleDragStart(e, type)}
      onClick={() => {
        const spec = nodeSpec(type)
        addNode(spec.type, { x: 200 + Math.random() * 200, y: 80 + Math.random() * 200 }, spec.params)
      }}
      style={{
        padding: '5px 14px 5px 38px',
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
  )

  return (
    <div style={{ display: 'flex', flexShrink: 0, height: '100%' }}>

      {showPackageWelcome && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="package-welcome-title"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1000,
            background: 'rgba(4, 8, 18, 0.72)',
            display: 'grid',
            placeItems: 'center',
            padding: 24,
          }}
        >
          <div style={{
            width: 'min(520px, calc(100vw - 48px))',
            background: 'var(--panel)',
            border: '1px solid var(--line2)',
            borderRadius: 12,
            boxShadow: '0 24px 80px rgba(0,0,0,.5)',
            padding: 24,
            color: 'var(--tx1)',
            fontFamily: 'var(--font-ui)',
          }}>
            <div style={{ color: 'var(--accent)', fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Welcome to Blacknode
            </div>
            <h1 id="package-welcome-title" style={{ margin: '8px 0 10px', fontSize: 22, lineHeight: 1.2 }}>
              Prepare your robotics workspace
            </h1>
            <p style={{ margin: 0, color: 'var(--tx2)', fontSize: 13, lineHeight: 1.6 }}>
              Start in Packages and install the official Blacknode capabilities for robot hardware, ROS 2, vision, CUDA, datasets, and training. Package-backed templates need their listed packages before they can run.
            </p>
            <p style={{ margin: '10px 0 0', color: 'var(--tx3)', fontSize: 12, lineHeight: 1.5 }}>
              Core graph workflows are ready immediately. You can return to Packages at any time from the left sidebar.
            </p>
            <div style={{ marginTop: 20, display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => finishPackageWelcome('templates')}
                style={welcomeButtonStyle}
              >
                Explore core templates
              </button>
              <button
                type="button"
                onClick={() => finishPackageWelcome('packages')}
                style={{ ...welcomeButtonStyle, padding: '7px 14px', color: '#fff', background: 'var(--accent)', borderColor: 'var(--accent)', fontWeight: 700 }}
              >
                Explore essential packages
              </button>
            </div>
          </div>
        </div>
      )}

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
                {paletteGroups.map(group => (
                  <div key={group.name} style={{ marginBottom: 4 }}>
                    {renderGroupHeader(group.name, group.name, group.color, group.count)}
                    {openGroups.has(group.name) && <>
                      {/* The category a package is named after gets no header of
                          its own — that row would just repeat the package. Its
                          nodes sit directly under it, above the real subgroups. */}
                      {group.subgroups
                        .filter(sub => sub.name === group.name)
                        .flatMap(sub => sub.types.map(type => renderNodeItem(type, sub.color)))}
                      {group.subgroups.filter(sub => sub.name !== group.name).map(sub => {
                        const subKey = `${group.name}/${sub.name}`
                        return (
                          <div key={subKey}>
                            {renderGroupHeader(subKey, sub.name, sub.color, sub.types.length, true)}
                            {openGroups.has(subKey) && sub.types.map(type => renderNodeItem(type, sub.color))}
                          </div>
                        )
                      })}
                    </>}
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

            {/* ── LEARNED ── */}
            {activeTab === 'learned' && <LearnedNodesPanel />}

            {/* ── PACKAGES ── */}
            {activeTab === 'packages' && <PackagesPanel />}

            {/* ── MCP ── */}
            {activeTab === 'mcp' && <McpPanel />}

          </div>
        </div>
      )}
    </div>
  )
}
