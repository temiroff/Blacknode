import { useEffect, useState } from 'react'
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

      {templates.map(template => {
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
              border: `1px solid ${dependencyError ? 'var(--warn)' : wasLoaded ? template.color : 'var(--line2)'}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: isBusy ? 'default' : 'pointer',
              transition: 'border-color 0.2s',
            }}
            onMouseEnter={e => {
              if (!isBusy && !dependencyError) (e.currentTarget as HTMLElement).style.borderColor = template.color
            }}
            onMouseLeave={e => {
              if (!wasLoaded) {
                (e.currentTarget as HTMLElement).style.borderColor = dependencyError ? 'var(--warn)' : 'var(--line2)'
              }
            }}
            onClick={() => !isBusy && loadTemplate(template)}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
              <span style={{
                color: template.color,
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
                color: dependencyError ? 'var(--warn)' : wasLoaded ? template.color : 'var(--tx3)',
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
    </div>
  )
}
