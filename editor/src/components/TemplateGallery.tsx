import { useEffect, useState } from 'react'
import { api, type TemplateMeta } from '../api'
import { useStore } from '../store'

export default function TemplateGallery() {
  const { loadGraph, loadNodeTypes, organizeNodes } = useStore()
  const [templates, setTemplates] = useState<TemplateMeta[]>([])
  const [loading, setLoading] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<string | null>(null)
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
    } catch (err) {
      console.error(err)
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
        return (
          <div
            key={template.slug}
            style={{
              background: 'var(--lift)',
              border: `1px solid ${wasLoaded ? template.color : 'var(--line2)'}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: isLoading ? 'default' : 'pointer',
              transition: 'border-color 0.2s',
            }}
            onMouseEnter={e => {
              if (!isLoading) (e.currentTarget as HTMLElement).style.borderColor = template.color
            }}
            onMouseLeave={e => {
              if (!wasLoaded) (e.currentTarget as HTMLElement).style.borderColor = 'var(--line2)'
            }}
            onClick={() => !isLoading && loadTemplate(template)}
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
                color: wasLoaded ? template.color : 'var(--tx3)',
                fontFamily: 'var(--font-ui)',
              }}>
                {isLoading ? 'loading...' : wasLoaded ? 'loaded' : `${template.node_count} nodes`}
              </span>
            </div>
            <div style={{ color: 'var(--tx2)', fontSize: 12, lineHeight: 1.4 }}>
              {template.description}
            </div>
          </div>
        )
      })}
    </div>
  )
}
