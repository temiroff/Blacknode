import { useEffect, useMemo, useState } from 'react'

import { api, type TemplateMeta } from '../api'
import { useStore } from '../store'

export interface WorkflowShortcut {
  id: string
  label: string
  templateSlug: string
}

interface ShortcutDraft {
  id: string | null
  label: string
  templateSlug: string
}

export const WORKFLOW_SHORTCUTS_STORAGE_KEY = 'blacknode-workflow-shortcuts'
export const DEFAULT_WORKFLOW_SHORTCUTS: WorkflowShortcut[] = [
  {
    id: 'collect-episodes',
    label: 'Collect episodes',
    templateSlug: 'teleoperation-episode-recording',
  },
]

function readWorkflowShortcuts(): WorkflowShortcut[] {
  try {
    const stored = window.localStorage.getItem(WORKFLOW_SHORTCUTS_STORAGE_KEY)
    if (stored === null) return DEFAULT_WORKFLOW_SHORTCUTS.map(shortcut => ({ ...shortcut }))
    const parsed = JSON.parse(stored)
    if (!Array.isArray(parsed)) throw new Error('Workflow shortcuts must be an array')
    return parsed
      .filter(value => value && typeof value === 'object')
      .map((value, index) => ({
        id: String(value.id || `shortcut-${index + 1}`),
        label: String(value.label || '').trim(),
        templateSlug: String(value.templateSlug || '').trim(),
      }))
      .filter(shortcut => shortcut.label && shortcut.templateSlug)
  } catch {
    return DEFAULT_WORKFLOW_SHORTCUTS.map(shortcut => ({ ...shortcut }))
  }
}

function shortcutId(): string {
  return `shortcut-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export default function WorkflowShortcuts() {
  const { loadGraph, loadNodeTypes, openGraphAsTab, organizeNodes } = useStore()
  const [shortcuts, setShortcuts] = useState<WorkflowShortcut[]>(readWorkflowShortcuts)
  const [templates, setTemplates] = useState<TemplateMeta[]>([])
  const [customizing, setCustomizing] = useState(false)
  const [draft, setDraft] = useState<ShortcutDraft | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)

  useEffect(() => {
    try {
      window.localStorage.setItem(WORKFLOW_SHORTCUTS_STORAGE_KEY, JSON.stringify(shortcuts))
    } catch {
      // Browser privacy settings may disable local storage. Shortcuts still work
      // for the current editor session.
    }
  }, [shortcuts])

  useEffect(() => {
    void api.listTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]))
  }, [])

  const sortedTemplates = useMemo(
    () => [...templates].sort((left, right) => left.name.localeCompare(right.name)),
    [templates],
  )

  const beginAdd = () => {
    setDraft({
      id: null,
      label: '',
      templateSlug: sortedTemplates[0]?.slug ?? '',
    })
  }

  const beginEdit = (shortcut: WorkflowShortcut) => {
    setDraft({ ...shortcut })
  }

  const saveDraft = () => {
    if (!draft) return
    const label = draft.label.trim()
    const templateSlug = draft.templateSlug.trim()
    if (!label || !templateSlug) return
    if (draft.id) {
      setShortcuts(current => current.map(shortcut => (
        shortcut.id === draft.id ? { ...shortcut, label, templateSlug } : shortcut
      )))
    } else {
      setShortcuts(current => [...current, { id: shortcutId(), label, templateSlug }])
    }
    setDraft(null)
  }

  const loadShortcut = async (shortcut: WorkflowShortcut) => {
    if (loadingId) return
    setLoadingId(shortcut.id)
    const previousGraph = await api.getGraph().catch(() => null)
    let openedNewTab = false
    try {
      await api.loadTemplate(shortcut.templateSlug)
      const templateGraph = await api.getGraph()
      const template = templates.find(candidate => candidate.slug === shortcut.templateSlug)
      const tabName = shortcut.label || template?.name || 'Robot workflow'
      if (previousGraph) {
        await api.setGraph(
          previousGraph.nodes,
          previousGraph.edges,
          previousGraph.metadata,
          previousGraph.entrypoint,
        )
        await loadGraph()
        await openGraphAsTab(tabName, templateGraph)
        openedNewTab = true
      } else {
        await loadGraph(tabName)
      }
      await loadNodeTypes()
      await organizeNodes()
      window.dispatchEvent(new Event('blacknode:fit-view'))
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: `${tabName} opened`,
          message: 'Review the workflow configuration, then use its controls when you are ready.',
        },
      }))
    } catch (error) {
      if (previousGraph && !openedNewTab) {
        await api.setGraph(
          previousGraph.nodes,
          previousGraph.edges,
          previousGraph.metadata,
          previousGraph.entrypoint,
        ).catch(() => undefined)
        await loadGraph().catch(() => undefined)
      }
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: `Could not open ${shortcut.label}`,
          message: error instanceof Error ? error.message : String(error),
        },
      }))
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <section className="bn-workflow-shortcuts" aria-label="Robot workflow shortcuts">
      <span className="bn-workflow-shortcuts-label">Robot workflows</span>
      <div className="bn-workflow-shortcuts-list">
        {shortcuts.map(shortcut => (
          <div className="bn-workflow-shortcut-item" key={shortcut.id}>
            <button
              type="button"
              className="bn-workflow-shortcut"
              disabled={Boolean(loadingId)}
              onClick={() => void loadShortcut(shortcut)}
              title={`Open template: ${shortcut.templateSlug}`}
            >
              <span className="bn-workflow-shortcut-dot" aria-hidden="true" />
              {loadingId === shortcut.id ? 'Opening…' : shortcut.label}
            </button>
            {customizing && (
              <span className="bn-workflow-shortcut-actions">
                <button
                  type="button"
                  onClick={() => beginEdit(shortcut)}
                  aria-label={`Edit ${shortcut.label}`}
                  title={`Edit ${shortcut.label}`}
                >
                  ✎
                </button>
                <button
                  type="button"
                  onClick={() => setShortcuts(current => current.filter(item => item.id !== shortcut.id))}
                  aria-label={`Delete ${shortcut.label}`}
                  title={`Delete ${shortcut.label}`}
                >
                  ×
                </button>
              </span>
            )}
          </div>
        ))}
        {shortcuts.length === 0 && (
          <span className="bn-workflow-shortcuts-empty">Add a robot workflow shortcut</span>
        )}
        {customizing && (
          <button type="button" className="bn-workflow-shortcut-add" onClick={beginAdd}>
            + Add shortcut
          </button>
        )}
      </div>
      {customizing && (
        <button
          type="button"
          className="bn-workflow-shortcuts-reset"
          onClick={() => setShortcuts(DEFAULT_WORKFLOW_SHORTCUTS.map(shortcut => ({ ...shortcut })))}
        >
          Reset
        </button>
      )}
      <button
        type="button"
        className={`bn-workflow-shortcuts-customize${customizing ? ' is-active' : ''}`}
        onClick={() => { setCustomizing(value => !value); setDraft(null) }}
        aria-pressed={customizing}
      >
        {customizing ? 'Done' : 'Customize'}
      </button>

      {draft && (
        <div className="bn-workflow-shortcut-backdrop" role="presentation" onMouseDown={() => setDraft(null)}>
          <form
            className="bn-workflow-shortcut-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="bn-workflow-shortcut-dialog-title"
            onMouseDown={event => event.stopPropagation()}
            onSubmit={event => { event.preventDefault(); saveDraft() }}
          >
            <header>
              <strong id="bn-workflow-shortcut-dialog-title">
                {draft.id ? 'Edit workflow shortcut' : 'Add workflow shortcut'}
              </strong>
              <button type="button" onClick={() => setDraft(null)} aria-label="Close">×</button>
            </header>
            <label htmlFor="bn-workflow-shortcut-label">Button label</label>
            <input
              id="bn-workflow-shortcut-label"
              autoFocus
              value={draft.label}
              onChange={event => setDraft(current => current ? { ...current, label: event.target.value } : current)}
              placeholder="Collect episodes"
            />
            <label htmlFor="bn-workflow-shortcut-template">Workflow template</label>
            <input
              id="bn-workflow-shortcut-template"
              list="bn-workflow-shortcut-template-options"
              value={draft.templateSlug}
              onChange={event => setDraft(current => current ? { ...current, templateSlug: event.target.value } : current)}
              placeholder="Template slug"
            />
            <datalist id="bn-workflow-shortcut-template-options">
              {sortedTemplates.map(template => (
                <option key={template.slug} value={template.slug}>{template.name}</option>
              ))}
            </datalist>
            <small>Choose any template available in the Templates panel.</small>
            <footer>
              <button type="button" onClick={() => setDraft(null)}>Cancel</button>
              <button className="is-primary" type="submit" disabled={!draft.label.trim() || !draft.templateSlug.trim()}>
                {draft.id ? 'Save changes' : 'Add shortcut'}
              </button>
            </footer>
          </form>
        </div>
      )}
    </section>
  )
}
