import { useEffect, useMemo, useState } from 'react'

import { api, type TemplateMeta } from '../api'
import { useStore } from '../store'

export interface WorkflowShortcut {
  id: string
  label: string
  templateSlug: string
  icon: WorkflowShortcutIcon
}

type WorkflowShortcutIcon = 'record' | 'camera' | 'robot' | 'workflow' | 'play'

interface ShortcutDraft {
  id: string | null
  label: string
  templateSlug: string
  icon: WorkflowShortcutIcon
}

const WORKFLOW_SHORTCUT_ICON_OPTIONS: Array<{ id: WorkflowShortcutIcon; label: string }> = [
  { id: 'record', label: 'Record' },
  { id: 'camera', label: 'Camera' },
  { id: 'robot', label: 'Robot' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'play', label: 'Run' },
]

export const WORKFLOW_SHORTCUTS_STORAGE_KEY = 'blacknode-workflow-shortcuts'
export const DEFAULT_WORKFLOW_SHORTCUTS: WorkflowShortcut[] = [
  {
    id: 'collect-episodes',
    label: 'Collect episodes',
    templateSlug: 'teleoperation-episode-recording',
    icon: 'record',
  },
]

function normalizedShortcutIcon(value: unknown, templateSlug: string): WorkflowShortcutIcon {
  const icon = String(value || '') as WorkflowShortcutIcon
  if (WORKFLOW_SHORTCUT_ICON_OPTIONS.some(option => option.id === icon)) return icon
  return /episode|record|dataset/i.test(templateSlug) ? 'record' : 'workflow'
}

function ShortcutGlyph({ icon }: { icon: WorkflowShortcutIcon }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      {icon === 'record' && (
        <>
          <rect x="3.5" y="4" width="17" height="16" rx="3" />
          <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
          <path d="M7 7.5h2" />
        </>
      )}
      {icon === 'camera' && (
        <>
          <path d="M4 8.5h3l1.5-2h7l1.5 2h3v10H4z" />
          <circle cx="12" cy="13.5" r="3.3" />
        </>
      )}
      {icon === 'robot' && (
        <>
          <rect x="5" y="7" width="14" height="11" rx="3" />
          <path d="M12 4v3M8.5 12h.01M15.5 12h.01M9 15h6" />
        </>
      )}
      {icon === 'workflow' && (
        <>
          <rect x="3" y="5" width="6" height="5" rx="1.5" />
          <rect x="15" y="14" width="6" height="5" rx="1.5" />
          <path d="M9 7.5h4a3 3 0 0 1 3 3V14M13.5 12l2.5 2 2.5-2" />
        </>
      )}
      {icon === 'play' && (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="m10 8 6 4-6 4z" fill="currentColor" stroke="none" />
        </>
      )}
    </svg>
  )
}

function readWorkflowShortcuts(): WorkflowShortcut[] {
  try {
    const stored = window.localStorage.getItem(WORKFLOW_SHORTCUTS_STORAGE_KEY)
    if (stored === null) return DEFAULT_WORKFLOW_SHORTCUTS.map(shortcut => ({ ...shortcut }))
    const parsed = JSON.parse(stored)
    if (!Array.isArray(parsed)) throw new Error('Workflow shortcuts must be an array')
    return parsed
      .filter(value => value && typeof value === 'object')
      .map((value, index) => {
        const templateSlug = String(value.templateSlug || '').trim()
        return {
          id: String(value.id || `shortcut-${index + 1}`),
          label: String(value.label || '').trim(),
          templateSlug,
          icon: normalizedShortcutIcon(value.icon, templateSlug),
        }
      })
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
      icon: 'workflow',
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
        shortcut.id === draft.id ? { ...shortcut, label, templateSlug, icon: draft.icon } : shortcut
      )))
    } else {
      setShortcuts(current => [...current, { id: shortcutId(), label, templateSlug, icon: draft.icon }])
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
      const tabName = shortcut.label || template?.name || 'Workflow template'
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
    <section className="bn-workflow-shortcuts" aria-label="Workflow shortcuts">
      <div className="bn-workflow-shortcuts-list">
        {shortcuts.map(shortcut => (
          <div className="bn-workflow-shortcut-item" key={shortcut.id}>
            <button
              type="button"
              className="bn-workflow-shortcut"
              disabled={Boolean(loadingId)}
              onClick={() => void loadShortcut(shortcut)}
              title={shortcut.label}
              aria-label={shortcut.label}
            >
              <span className={loadingId === shortcut.id ? 'is-loading' : ''}>
                <ShortcutGlyph icon={shortcut.icon} />
              </span>
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
        {customizing && (
          <button
            type="button"
            className="bn-workflow-shortcut-add"
            onClick={beginAdd}
            aria-label="Add shortcut"
            title="Add shortcut"
          >
            +
          </button>
        )}
      </div>
      {customizing && (
        <button
          type="button"
          className="bn-workflow-shortcuts-reset"
          onClick={() => setShortcuts(DEFAULT_WORKFLOW_SHORTCUTS.map(shortcut => ({ ...shortcut })))}
          aria-label="Reset shortcuts"
          title="Reset shortcuts"
        >
          ↺
        </button>
      )}
      <button
        type="button"
        className={`bn-workflow-shortcuts-customize${customizing ? ' is-active' : ''}`}
        onClick={() => { setCustomizing(value => !value); setDraft(null) }}
        aria-pressed={customizing}
        aria-label={customizing ? 'Finish customizing shortcuts' : 'Customize shortcuts'}
        title={customizing ? 'Finish customizing shortcuts' : 'Customize shortcuts'}
      >
        {customizing ? '✓' : '⚙'}
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
            <label htmlFor="bn-workflow-shortcut-icon">Icon</label>
            <select
              id="bn-workflow-shortcut-icon"
              value={draft.icon}
              onChange={event => setDraft(current => current ? {
                ...current,
                icon: event.target.value as WorkflowShortcutIcon,
              } : current)}
            >
              {WORKFLOW_SHORTCUT_ICON_OPTIONS.map(option => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
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
