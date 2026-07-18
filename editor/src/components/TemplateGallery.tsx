import { useEffect, useMemo, useState } from 'react'
import {
  api,
  templateDependencyError,
  type MissingTemplatePackage,
  type TemplateDependencyError,
  type TemplateMeta,
} from '../api'
import { useStore } from '../store'

export default function TemplateGallery() {
  const { loadGraph, loadNodeTypes, organizeNodes } = useStore()
  const [templates, setTemplates] = useState<TemplateMeta[]>([])
  const [loading, setLoading] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<string | null>(null)
  const [installing, setInstalling] = useState<{ slug: string; packageName: string } | null>(null)
  const [missing, setMissing] = useState<Record<string, TemplateDependencyError>>({})
  const [error, setError] = useState<string | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set())
  const [query, setQuery] = useState('')

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

  const loadTemplate = async (template: TemplateMeta) => {
    setLoading(template.slug)
    setLoaded(null)
    const previousGraph = await api.getGraph().catch(() => null)
    try {
      await api.loadTemplate(template.slug)
      await loadGraph()
      await loadNodeTypes()
      await organizeNodes()
      window.dispatchEvent(new Event('blacknode:fit-view'))
      setLoaded(template.slug)
      setMissing(current => {
        const next = { ...current }
        delete next[template.slug]
        return next
      })
    } catch (err) {
      console.error(err)
      const dependencyError = templateDependencyError(err)
      if (dependencyError) {
        setMissing(current => ({ ...current, [template.slug]: dependencyError }))
        return
      }
      if (previousGraph) {
        await api.setGraph(previousGraph.nodes, previousGraph.edges).catch(console.error)
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

  return (
    <div style={{ padding: '10px 10px', display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
      <div style={{
        color: 'var(--tx2)',
        fontSize: 12,
        padding: '2px 4px 8px',
        lineHeight: 1.5,
      }}>
        One-click starter graphs. Loads into the canvas.
      </div>

      <input
        type="search"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="Search templates or categories..."
        aria-label="Search templates"
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
          fontSize: 12,
        }}
      />

      {error && (
        <div style={{
          color: 'var(--danger)',
          border: '1px solid var(--danger)',
          borderRadius: 8,
          padding: '10px 12px',
          fontSize: 12,
          lineHeight: 1.4,
        }}>
          {error}
        </div>
      )}

      {!error && templates.length === 0 && (
        <div style={{ color: 'var(--tx3)', fontSize: 12, padding: '8px 4px' }}>
          No templates found.
        </div>
      )}

      {!error && templates.length > 0 && query.trim() && filteredTemplateGroups.length === 0 && (
        <div style={{ color: 'var(--tx3)', fontSize: 12, padding: '8px 4px' }}>
          No templates match “{query.trim()}”.
        </div>
      )}

      {filteredTemplateGroups.map(group => {
        const isExpanded = Boolean(query.trim()) || expandedGroups.has(group.name)
        return (
          <section key={group.name} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
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
              <span style={{ color: group.color, fontSize: 12, width: 12 }}>
                {isExpanded ? '▾' : '▸'}
              </span>
              <span style={{ flex: 1, fontSize: 12, fontWeight: 650 }}>{group.name}</span>
              <span style={{ color: 'var(--tx3)', fontSize: 11 }}>{group.templates.length}</span>
            </button>
            {isExpanded && group.templates.map(template => {
        const isLoading = loading === template.slug
        const wasLoaded = loaded === template.slug
        const dependencyError = missing[template.slug]
        const isInstalling = installing?.slug === template.slug
        const isBusy = isLoading || isInstalling
        return (
          <div
            key={template.slug}
            style={{
              background: 'var(--lift)',
              border: `1px solid ${dependencyError ? 'var(--warn)' : group.color}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: isBusy ? 'default' : 'pointer',
              transition: 'border-color 0.2s',
            }}
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
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
              <span style={{
                color: group.color,
                fontSize: 13,
                fontWeight: 600,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {template.name}
              </span>
              <span style={{
                flex: '0 0 auto',
                fontSize: 11,
                color: dependencyError ? 'var(--warn)' : wasLoaded ? group.color : 'var(--tx3)',
                fontFamily: 'var(--font-ui)',
              }}>
                {isLoading
                  ? 'loading...'
                  : isInstalling
                    ? 'installing...'
                    : dependencyError
                      ? 'missing nodes'
                      : wasLoaded
                        ? 'loaded'
                        : `${template.node_count} nodes`}
              </span>
            </div>
            <div style={{ color: 'var(--tx2)', fontSize: 12, lineHeight: 1.4 }}>
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
                      <div style={{ flex: 1, minWidth: 0, color: 'var(--warn)', fontSize: 11, lineHeight: 1.35 }}>
                        {pkg.installed
                          ? pkg.load_error ? 'Package failed to load: ' : 'Installed package is missing nodes: '
                          : 'Missing package: '}
                        <strong>{pkg.name}</strong>
                        {pkg.node_types.length > 0 && (
                          <div style={{ color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                            {pkg.node_types.join(', ')}
                          </div>
                        )}
                        {pkg.load_error && (
                          <div style={{ color: 'var(--err)', fontSize: 10 }}>
                            {pkg.load_error.trim().split('\n').slice(-1)[0]}
                          </div>
                        )}
                        {!pkg.installed && !pkg.git_url && (
                          <div style={{ color: 'var(--err)', fontSize: 10 }}>
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
                            fontSize: 11,
                            padding: '3px 9px',
                          }}
                        >
                          {packageInstalling ? 'Installing...' : 'Install'}
                        </button>
                      )}
                    </div>
                  )
                })}
                {dependencyError.unresolved_node_types.length > 0 && (
                  <div style={{ color: 'var(--err)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
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
