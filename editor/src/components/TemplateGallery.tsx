import { useEffect, useMemo, useState } from 'react'
import {
  api,
  templateDependencyError,
  type MissingTemplateAdapter,
  type MissingTemplateComponent,
  type MissingTemplatePackage,
  type TemplateDependencyError,
  type TemplateMeta,
} from '../api'
import { useStore } from '../store'
import { familyColor, packageFamilyName } from '../categories'
import NodeGlyph from './NodeGlyph'

interface TemplateGalleryProps {
  initialQuery?: string
  openInNewTab?: boolean
}

function normalizedEnableTarget(
  target: { package: string; component: string; adapter?: string },
): { package: string; component: string; adapter?: string } {
  const separator = target.component.indexOf('@')
  if (separator < 0) return target
  const component = target.component.slice(0, separator)
  const compactAdapter = target.component.slice(separator + 1)
  return {
    ...target,
    component,
    adapter: target.adapter || compactAdapter || undefined,
  }
}

function templateTags(template: TemplateMeta): string[] {
  const tags = [
    ...(template.categories ?? []).filter(category => category !== 'Custom'),
    ...(template.required_packages ?? []).map(packageFamilyName),
  ]
  if (tags.length === 0 && template.group) tags.push(template.group)
  return tags.filter((tag, index) => (
    tag
    && tags.findIndex(candidate => candidate.toLowerCase() === tag.toLowerCase()) === index
  ))
}

export default function TemplateGallery({
  initialQuery = '',
  openInNewTab = true,
}: TemplateGalleryProps) {
  const { loadGraph, loadNodeTypes, openGraphAsTab, organizeNodes } = useStore()
  const [templates, setTemplates] = useState<TemplateMeta[]>([])
  const [loading, setLoading] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<string | null>(null)
  const [installing, setInstalling] = useState<{ slug: string; packageName: string } | null>(null)
  const [enabling, setEnabling] = useState<{ slug: string; label: string } | null>(null)
  const [missing, setMissing] = useState<Record<string, TemplateDependencyError>>({})
  const [error, setError] = useState<string | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set())
  const [query, setQuery] = useState(initialQuery)

  useEffect(() => {
    setQuery(initialQuery)
  }, [initialQuery])

  const templateGroups = useMemo(() => {
    const groups = new Map<string, { name: string; color: string; templates: TemplateMeta[] }>()
    templates.forEach(template => {
      const name = template.group || 'Core'
      const current = groups.get(name)
      if (current) current.templates.push(template)
      else groups.set(name, {
        name,
        color: template.group_color || '#6366f1',
        templates: [template],
      })
    })
    return Array.from(groups.values())
  }, [templates])

  const filteredTemplateGroups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return templateGroups
    return templateGroups
      .map(group => ({
        ...group,
        templates: group.templates.filter(template =>
          [template.name, template.description, template.slug, group.name]
            .some(value => value.toLowerCase().includes(needle))
        ),
      }))
      .filter(group => group.templates.length > 0)
  }, [query, templateGroups])

  const toggleGroup = (name: string) => {
    setExpandedGroups(current => {
      const next = new Set(current)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const refreshTemplates = async () => {
    try {
      setError(null)
      setTemplates(await api.listTemplates())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    refreshTemplates()
  }, [])

  useEffect(() => {
    const handlePackagesReloaded = () => setMissing({})
    window.addEventListener('blacknode:packages-reloaded', handlePackagesReloaded)
    return () => window.removeEventListener('blacknode:packages-reloaded', handlePackagesReloaded)
  }, [])

  const loadTemplate = async (template: TemplateMeta) => {
    setLoading(template.slug)
    setLoaded(null)
    const previousGraph = await api.getGraph().catch(() => null)
    let openedNewTab = false
    try {
      await api.loadTemplate(template.slug)
      if (openInNewTab && previousGraph) {
        const templateGraph = await api.getGraph()
        await api.setGraph(previousGraph.nodes, previousGraph.edges, previousGraph.metadata)
        await loadGraph()
        await openGraphAsTab(template.name, templateGraph)
        openedNewTab = true
      } else {
        await loadGraph(template.name)
      }
      await loadNodeTypes()
      await organizeNodes()
      window.dispatchEvent(new Event('blacknode:fit-view'))
      setLoaded(template.slug)
      setMissing(current => {
        const next = { ...current }
        delete next[template.slug]
        return next
      })
      if (openedNewTab) {
        window.dispatchEvent(new CustomEvent('blacknode:notice', {
          detail: {
            kind: 'info',
            title: `${template.name} opened`,
            message: 'The deployment workflow remains available in its original tab.',
          },
        }))
      }
    } catch (err) {
      console.error(err)
      const dependencyError = templateDependencyError(err)
      if (dependencyError) {
        setMissing(current => ({ ...current, [template.slug]: dependencyError }))
        return
      }
      if (previousGraph && !openedNewTab) {
        await api.setGraph(previousGraph.nodes, previousGraph.edges, previousGraph.metadata).catch(console.error)
        await loadGraph().catch(console.error)
      }
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: `Could not load ${template.name}`,
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setLoading(null)
    }
  }

  const installPackage = async (
    event: React.MouseEvent,
    template: TemplateMeta,
    pkg: MissingTemplatePackage,
  ) => {
    event.stopPropagation()
    if (!pkg.git_url || installing) return
    setInstalling({ slug: template.slug, packageName: pkg.name })
    try {
      const result = await api.installPackage(pkg.git_url)
      if (!result.ok) throw new Error(result.error || `Could not install ${pkg.name}`)
      await loadNodeTypes()
      await refreshTemplates()
      await loadTemplate(template)
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: `Could not install ${pkg.name}`,
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setInstalling(null)
    }
  }

  // Enable a disabled component (and, for an adapter requirement, its parent
  // component too), then retry the load. The backend pulls in any required
  // dependency packages when enabling.
  const enableTarget = async (
    event: React.MouseEvent,
    template: TemplateMeta,
    target: { package: string; component: string; adapter?: string },
  ) => {
    event.stopPropagation()
    if (enabling || installing) return
    const normalized = normalizedEnableTarget(target)
    const label = normalized.adapter
      ? `${normalized.package}/${normalized.component}@${normalized.adapter}`
      : `${normalized.package}/${normalized.component}`
    setEnabling({ slug: template.slug, label })
    try {
      if (normalized.adapter) {
        // Adapter activation transactionally enables its parent component and
        // dependency graph, so a separate component request is unnecessary.
        await api.setPackageAdapter(
          normalized.package,
          normalized.component,
          normalized.adapter,
          true,
        )
      } else {
        await api.setPackageComponent(normalized.package, normalized.component, true)
      }
      await loadNodeTypes()
      await refreshTemplates()
      await loadTemplate(template)
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: `Could not enable ${label}`,
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setEnabling(null)
    }
  }

  return (
    <div className="bn-template-gallery" style={{ padding: '10px 10px', display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
      <div className="bn-template-intro" style={{
        color: 'var(--tx2)',
        fontSize: 14,
        padding: '2px 4px 8px',
        lineHeight: 1.5,
      }}>
        {openInNewTab
          ? 'Browse reusable workflow setups. Each one opens in its own workflow tab.'
          : 'Reusable workflow components, organized by capability.'}
      </div>

      <div className="bn-template-search">
        <svg className="bn-template-search-icon" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="8.5" cy="8.5" r="5.25" />
          <path d="m12.4 12.4 4.1 4.1" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Search templates or categories..."
          aria-label="Search templates or categories"
          style={{
            width: '100%',
            minHeight: 38,
            padding: '8px 10px',
            color: 'var(--tx1)',
            background: 'var(--lift)',
            border: '1px solid var(--line2)',
            borderRadius: 8,
            outline: 'none',
            fontFamily: 'var(--font-ui)',
            fontSize: 14,
          }}
        />
      </div>

      {error && (
        <div style={{
          color: 'var(--danger)',
          border: '1px solid var(--danger)',
          borderRadius: 8,
          padding: '10px 12px',
          fontSize: 14,
          lineHeight: 1.4,
        }}>
          {error}
        </div>
      )}

      {!error && templates.length === 0 && (
        <div style={{ color: 'var(--tx3)', fontSize: 14, padding: '8px 4px' }}>
          No templates found.
        </div>
      )}

      {!error && templates.length > 0 && query.trim() && filteredTemplateGroups.length === 0 && (
        <div style={{ color: 'var(--tx3)', fontSize: 14, padding: '8px 4px' }}>
          No templates match “{query.trim()}”.
        </div>
      )}

      {filteredTemplateGroups.map(group => {
        const isExpanded = Boolean(query.trim()) || expandedGroups.has(group.name)
        const visualColor = familyColor(group.name, group.color)
        return (
          <section
            className={`bn-template-group${isExpanded ? ' is-expanded' : ''}`}
            key={group.name}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              '--bn-template-accent': visualColor,
            } as React.CSSProperties}
          >
            <button
              className="bn-template-group-button"
              type="button"
              aria-expanded={isExpanded}
              onClick={() => toggleGroup(group.name)}
              style={{
                width: '100%',
                minHeight: 42,
                padding: '8px 10px',
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                background: 'var(--lift)',
                border: '1px solid var(--line2)',
                borderRadius: 8,
                color: 'var(--tx1)',
                cursor: 'pointer',
                fontFamily: 'var(--font-ui)',
                textAlign: 'left',
              }}
            >
              <span className="bn-template-group-accent" style={{ color: group.color, fontSize: 14, width: 12 }}>
                {isExpanded ? '▾' : '▸'}
              </span>
              <NodeGlyph type={group.name} category={group.name} className="bn-template-group-glyph" />
              <span className="bn-template-group-name" style={{ flex: 1, fontSize: 14, fontWeight: 650 }}>{group.name}</span>
              <span className="bn-template-group-count" style={{ color: 'var(--tx3)', fontSize: 13 }}>
                ({group.templates.length})
              </span>
            </button>
            {isExpanded && group.templates.map(template => {
        const isLoading = loading === template.slug
        const wasLoaded = loaded === template.slug
        const dependencyError = missing[template.slug]
        const isInstalling = installing?.slug === template.slug
        const isEnabling = enabling?.slug === template.slug
        const isBusy = isLoading || isInstalling || isEnabling
        const tags = templateTags(template)
        return (
          <div
            className={`bn-template-card${wasLoaded ? ' is-loaded' : ''}${dependencyError ? ' has-dependency-error' : ''}`}
            key={template.slug}
            style={{
              background: 'var(--lift)',
              border: `1px solid ${dependencyError ? 'var(--warn)' : group.color}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: isBusy ? 'default' : 'pointer',
              transition: 'border-color 0.2s',
              '--bn-template-accent': visualColor,
            } as React.CSSProperties}
            onMouseEnter={e => {
              if (!isBusy && !dependencyError) (e.currentTarget as HTMLElement).style.borderColor = group.color
            }}
            onMouseLeave={e => {
              if (!wasLoaded) {
                (e.currentTarget as HTMLElement).style.borderColor = dependencyError ? 'var(--warn)' : group.color
              }
            }}
            onClick={() => !isBusy && loadTemplate(template)}
          >
            <div className="bn-template-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
              <NodeGlyph type={template.name} category={group.name} className="bn-template-card-glyph" />
              <span className="bn-template-card-title" style={{
                color: group.color,
                fontSize: 15,
                fontWeight: 600,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {template.name}
              </span>
              <span className="bn-template-card-status" style={{
                flex: '0 0 auto',
                fontSize: 13,
                color: dependencyError ? 'var(--warn)' : wasLoaded ? group.color : 'var(--tx3)',
                fontFamily: 'var(--font-ui)',
              }}>
                {isLoading
                  ? 'loading...'
                  : isInstalling
                    ? 'installing...'
                    : isEnabling
                      ? 'enabling...'
                      : dependencyError
                        ? 'needs setup'
                        : wasLoaded
                          ? 'loaded'
                          : ''}
              </span>
            </div>
            <div className="bn-template-card-meta" title={[
              ...(template.required_packages ?? []),
              ...(template.required_capabilities ?? []),
            ].join(' · ')}>
              <span className="bn-template-node-count">{template.node_count} nodes</span>
              {tags.slice(0, 3).map(tag => (
                <span
                  className="bn-template-tag"
                  key={tag}
                  style={{
                    '--bn-tag-color': familyColor(tag, visualColor),
                  } as React.CSSProperties}
                >
                  {tag}
                </span>
              ))}
              {tags.length > 3 && <span className="bn-template-tag-more">+{tags.length - 3}</span>}
            </div>
            <div className="bn-template-card-description" style={{ color: 'var(--tx2)', fontSize: 14, lineHeight: 1.4 }}>
              {template.description}
            </div>
            {dependencyError && (
              <div
                onClick={event => event.stopPropagation()}
                style={{
                  marginTop: 9,
                  paddingTop: 8,
                  borderTop: '1px solid color-mix(in srgb, var(--warn) 45%, transparent)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 7,
                }}
              >
                {dependencyError.missing_packages.map(pkg => {
                  const packageInstalling = installing?.packageName === pkg.name
                  return (
                    <div key={pkg.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, minWidth: 0, color: 'var(--warn)', fontSize: 13, lineHeight: 1.35 }}>
                        {pkg.installed
                          ? pkg.load_error ? 'Package failed to load: ' : 'Installed package is missing nodes: '
                          : 'Missing package: '}
                        <strong>{pkg.name}</strong>
                        {pkg.node_types.length > 0 && (
                          <div style={{ color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                            {pkg.node_types.join(', ')}
                          </div>
                        )}
                        {pkg.load_error && (
                          <div style={{ color: 'var(--err)', fontSize: 12 }}>
                            {pkg.load_error.trim().split('\n').slice(-1)[0]}
                          </div>
                        )}
                        {!pkg.installed && !pkg.git_url && (
                          <div style={{ color: 'var(--err)', fontSize: 12 }}>
                            No install URL was provided.
                          </div>
                        )}
                      </div>
                      {!pkg.installed && pkg.git_url && (
                        <button
                          onClick={event => installPackage(event, template, pkg)}
                          disabled={Boolean(installing)}
                          style={{
                            background: 'transparent',
                            border: '1px solid var(--warn)',
                            borderRadius: 5,
                            color: 'var(--warn)',
                            cursor: installing ? 'wait' : 'pointer',
                            fontFamily: 'var(--font-ui)',
                            fontSize: 13,
                            padding: '3px 9px',
                          }}
                        >
                          {packageInstalling ? 'Installing...' : 'Install'}
                        </button>
                      )}
                    </div>
                  )
                })}
                {dependencyError.missing_components.map((comp: MissingTemplateComponent) => (
                  <div key={`${comp.package}/${comp.component}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 0, color: 'var(--warn)', fontSize: 13, lineHeight: 1.35 }}>
                      Component <strong>{comp.package}/{comp.component}</strong>
                      <div style={{ color: 'var(--tx3)', fontSize: 12 }}>{comp.reason}</div>
                    </div>
                    <button
                      onClick={event => enableTarget(event, template, comp)}
                      disabled={Boolean(installing || enabling)}
                      style={{
                        background: 'transparent', border: '1px solid var(--warn)', borderRadius: 5,
                        color: 'var(--warn)', cursor: installing || enabling ? 'wait' : 'pointer',
                        fontFamily: 'var(--font-ui)', fontSize: 13, padding: '3px 9px',
                      }}
                    >
                      {enabling?.label === `${comp.package}/${comp.component}` ? 'Enabling...' : 'Enable'}
                    </button>
                  </div>
                ))}
                {dependencyError.missing_adapters.map((ad: MissingTemplateAdapter) => {
                  const label = `${ad.package}/${ad.component}@${ad.adapter}`
                  const notInstalled = /not installed/i.test(ad.reason)
                  return (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, minWidth: 0, color: 'var(--warn)', fontSize: 13, lineHeight: 1.35 }}>
                        Adapter <strong>{label}</strong>
                        <div style={{ color: 'var(--tx3)', fontSize: 12 }}>{ad.reason}</div>
                      </div>
                      {notInstalled ? (
                        <span style={{ color: 'var(--tx3)', fontSize: 12 }}>install package first</span>
                      ) : (
                        <button
                          onClick={event => enableTarget(event, template, ad)}
                          disabled={Boolean(installing || enabling)}
                          style={{
                            background: 'transparent', border: '1px solid var(--warn)', borderRadius: 5,
                            color: 'var(--warn)', cursor: installing || enabling ? 'wait' : 'pointer',
                            fontFamily: 'var(--font-ui)', fontSize: 13, padding: '3px 9px',
                          }}
                        >
                          {enabling?.label === label ? 'Enabling...' : 'Enable'}
                        </button>
                      )}
                    </div>
                  )
                })}
                {dependencyError.unresolved_node_types.length > 0 && (
                  <div style={{ color: 'var(--err)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                    No package mapping: {dependencyError.unresolved_node_types.join(', ')}
                  </div>
                )}
              </div>
            )}
          </div>
        )
            })}
          </section>
        )
      })}
    </div>
  )
}
