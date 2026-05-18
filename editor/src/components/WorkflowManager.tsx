import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { useStore } from '../store'

interface WorkflowMeta {
  slug: string
  name: string
  saved_at: string
}

function fmtDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function WorkflowManager() {
  const {
    tabs, activeTabId, workflowRevision,
    openWorkflowAsTab, saveActiveWorkflow, insertSavedWorkflow, renameSavedWorkflow,
    duplicateSavedWorkflow, deleteWorkflow,
  } = useStore()
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const needsSave = Boolean(activeTab && (activeTab.dirty || !activeTab.slug))
  const openSlugs = new Set(tabs.map(tab => tab.slug).filter(Boolean))

  const [workflows, setWorkflows] = useState<WorkflowMeta[]>([])
  const [saveName,  setSaveName]  = useState('')
  const [filter,    setFilter]    = useState('')
  const [saving,    setSaving]    = useState(false)
  const [loading,   setLoading]   = useState<string | null>(null)
  const [inserting, setInserting] = useState<string | null>(null)
  const [deleting,  setDeleting]  = useState<string | null>(null)
  const [duplicating, setDuplicating] = useState<string | null>(null)
  const [saveOk,    setSaveOk]    = useState(false)
  const [workflowMenu, setWorkflowMenu] = useState<{ x: number; y: number; slug: string } | null>(null)
  const [renamingSlug, setRenamingSlug] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const menuWorkflow = workflowMenu ? workflows.find(w => w.slug === workflowMenu.slug) : null

  const refresh = useCallback(async () => {
    try { setWorkflows(await api.listWorkflows()) } catch {}
  }, [])

  useEffect(() => { refresh() }, [refresh, workflowRevision])
  useEffect(() => { setSaveName(activeTab?.name ?? '') }, [activeTabId, activeTab?.name])
  useEffect(() => {
    if (!workflowMenu) return
    const close = () => setWorkflowMenu(null)
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [workflowMenu])

  const filteredWorkflows = workflows.filter(w => {
    const query = filter.trim().toLowerCase()
    return !query || w.name.toLowerCase().includes(query) || w.slug.toLowerCase().includes(query)
  })

  const handleSave = async () => {
    const name = saveName.trim()
    if (!name) return
    setSaving(true)
    setSaveOk(false)
    try {
      const saved = await saveActiveWorkflow(name)
      setSaveOk(true)
      setSaveName(saved.name)
      await refresh()
      setTimeout(() => setSaveOk(false), 2000)
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const handleLoad = async (slug: string) => {
    setLoading(slug)
    try {
      const workflow = workflows.find(w => w.slug === slug)
      await openWorkflowAsTab(slug, workflow?.name ?? slug)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(null)
    }
  }

  const handleDelete = async (slug: string) => {
    setWorkflowMenu(null)
    setDeleting(slug)
    try {
      await deleteWorkflow(slug)
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setDeleting(null)
    }
  }

  const handleInsert = async (slug: string) => {
    setWorkflowMenu(null)
    setInserting(slug)
    try {
      await insertSavedWorkflow(slug)
    } catch (e) {
      console.error(e)
    } finally {
      setInserting(null)
    }
  }

  const startRename = (workflow: WorkflowMeta) => {
    setWorkflowMenu(null)
    setRenamingSlug(workflow.slug)
    setRenameDraft(workflow.name)
  }

  const commitRename = async () => {
    if (!renamingSlug) return
    const name = renameDraft.trim()
    if (!name) {
      setRenamingSlug(null)
      setRenameDraft('')
      return
    }
    try {
      await renameSavedWorkflow(renamingSlug, name)
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setRenamingSlug(null)
      setRenameDraft('')
    }
  }

  const handleDuplicate = async (slug: string) => {
    setWorkflowMenu(null)
    setDuplicating(slug)
    try {
      await duplicateSavedWorkflow(slug)
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setDuplicating(null)
    }
  }

  const openWorkflowMenu = useCallback((e: React.MouseEvent, slug: string) => {
    e.preventDefault()
    e.stopPropagation()
    setWorkflowMenu({ x: e.clientX, y: e.clientY, slug })
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* save row */}
      <div style={{
        padding: '10px 10px 8px',
        borderBottom: '1px solid var(--line)',
        display: 'flex',
        gap: 6,
      }}>
        <input
          value={saveName}
          onChange={e => setSaveName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
          placeholder="Workflow name…"
          style={{
            flex: 1,
            background: 'var(--lift)',
            border: `1px solid ${saveOk ? 'var(--ok)' : 'var(--line2)'}`,
            borderRadius: 6,
            color: 'var(--tx1)',
            fontFamily: 'var(--font-ui)',
            fontSize: 12,
            padding: '5px 8px',
            outline: 'none',
            transition: 'border-color 0.2s',
          }}
        />
        <button
          onClick={handleSave}
          disabled={!saveName.trim() || saving}
          style={{
            background: saveOk ? 'var(--ok)' : needsSave ? 'var(--save-pending)' : 'var(--accent)',
            border: 'none',
            borderRadius: 6,
            color: '#fff',
            cursor: saveName.trim() && !saving ? 'pointer' : 'default',
            fontFamily: 'var(--font-ui)',
            fontSize: 12,
            fontWeight: 600,
            padding: '5px 12px',
            opacity: saveName.trim() && !saving ? 1 : 0.45,
            transition: 'background 0.2s',
            flexShrink: 0,
          }}
        >
          {saveOk ? '✓ Saved' : saving ? '…' : 'Save'}
        </button>
      </div>

      <div style={{ padding: '8px 10px 4px', borderBottom: '1px solid var(--line)' }}>
        <input
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Find workflow…"
          style={{
            width: '100%',
            background: 'var(--lift)',
            border: '1px solid var(--line2)',
            borderRadius: 6,
            color: 'var(--tx1)',
            fontFamily: 'var(--font-ui)',
            fontSize: 12,
            padding: '5px 8px',
            outline: 'none',
          }}
        />
      </div>

      {/* list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px' }}
           onWheel={e => e.stopPropagation()}>

        {workflows.length === 0 && (
          <div style={{
            color: 'var(--tx3)',
            fontSize: 12,
            fontStyle: 'italic',
            padding: '12px 6px',
          }}>
            No saved workflows yet. Build something and click Save.
          </div>
        )}

        {workflows.length > 0 && filteredWorkflows.length === 0 && (
          <div style={{
            color: 'var(--tx3)',
            fontSize: 12,
            fontStyle: 'italic',
            padding: '12px 6px',
          }}>
            No matching workflows.
          </div>
        )}

        {filteredWorkflows.map(w => {
          const isOpen = openSlugs.has(w.slug)
          const isActive = activeTab?.slug === w.slug
          return (
          <div
            className="bn-workflow-row"
            key={w.slug}
            onClick={() => {
              if (loading !== w.slug && inserting !== w.slug && deleting !== w.slug && duplicating !== w.slug && renamingSlug !== w.slug) {
                void handleLoad(w.slug)
              }
            }}
            onMouseDown={e => { if (e.button === 2) openWorkflowMenu(e, w.slug) }}
            onContextMenu={e => openWorkflowMenu(e, w.slug)}
            style={{
              background: 'var(--lift)',
              border: '1px solid var(--line2)',
              borderRadius: 7,
              padding: '8px 10px',
              marginBottom: 6,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              cursor: loading === w.slug || inserting === w.slug || deleting === w.slug || duplicating === w.slug || renamingSlug === w.slug ? 'default' : 'pointer',
              opacity: loading === w.slug || inserting === w.slug || deleting === w.slug || duplicating === w.slug ? 0.65 : 1,
            }}
            title="Open workflow"
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
              <div style={{ minWidth: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
                {renamingSlug === w.slug ? (
                  <input
                    autoFocus
                    value={renameDraft}
                    onChange={e => setRenameDraft(e.target.value)}
                    onClick={e => e.stopPropagation()}
                    onMouseDown={e => e.stopPropagation()}
                    onFocus={e => e.currentTarget.select()}
                    onBlur={() => void commitRename()}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void commitRename()
                      }
                      if (e.key === 'Escape') {
                        e.preventDefault()
                        setRenamingSlug(null)
                        setRenameDraft('')
                      }
                    }}
                    style={{
                      width: '100%',
                      minWidth: 96,
                      background: 'var(--panel)',
                      border: '1px solid var(--accent)',
                      borderRadius: 5,
                      color: 'var(--tx1)',
                      fontFamily: 'var(--font-ui)',
                      fontSize: 13,
                      fontWeight: 600,
                      outline: 'none',
                      padding: '3px 6px',
                    }}
                  />
                ) : (
                  <span style={{
                    color: 'var(--tx1)',
                    fontSize: 13,
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {w.name}
                  </span>
                )}
                {(isActive || isOpen) && (
                  <span style={{
                    color: isActive ? 'var(--ok)' : 'var(--tx3)',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    flexShrink: 0,
                  }}>
                    {isActive ? 'Active' : 'Tab'}
                  </span>
                )}
              </div>
              {(loading === w.slug || inserting === w.slug || deleting === w.slug || duplicating === w.slug) && (
                <span style={{ color: 'var(--tx3)', fontSize: 11, flexShrink: 0 }}>
                  {deleting === w.slug ? 'Deleting…' : duplicating === w.slug ? 'Duplicating…' : inserting === w.slug ? 'Inserting…' : 'Opening…'}
                </span>
              )}
            </div>

            {w.saved_at && (
              <span style={{ color: 'var(--tx3)', fontSize: 11 }}>
                {fmtDate(w.saved_at)}
              </span>
            )}
          </div>
        )})}
      </div>

      {workflowMenu && menuWorkflow && (
        <div
          onMouseDown={e => e.stopPropagation()}
          onClick={e => e.stopPropagation()}
          onContextMenu={e => e.preventDefault()}
          style={{
            position: 'fixed',
            top: workflowMenu.y,
            left: workflowMenu.x,
            zIndex: 60,
            minWidth: 120,
            background: 'var(--panel)',
            border: '1px solid var(--line2)',
            borderRadius: 7,
            padding: 4,
            boxShadow: '0 8px 24px rgba(0,0,0,.28)',
          }}
        >
          <button
            className="bn-menu-item"
            style={workflowMenuItemStyle(inserting === menuWorkflow.slug)}
            disabled={inserting === menuWorkflow.slug}
            onClick={() => void handleInsert(menuWorkflow.slug)}
          >
            Insert
          </button>
          <button
            className="bn-menu-item"
            style={workflowMenuItemStyle()}
            onClick={() => startRename(menuWorkflow)}
          >
            Rename
          </button>
          <button
            className="bn-menu-item"
            style={workflowMenuItemStyle(duplicating === menuWorkflow.slug)}
            disabled={duplicating === menuWorkflow.slug}
            onClick={() => void handleDuplicate(menuWorkflow.slug)}
          >
            Duplicate
          </button>
          <button
            className="bn-menu-item"
            style={workflowMenuItemStyle(deleting === menuWorkflow.slug, 'var(--err)')}
            disabled={deleting === menuWorkflow.slug}
            onClick={() => void handleDelete(menuWorkflow.slug)}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

function workflowMenuItemStyle(disabled = false, color = 'var(--tx2)'): React.CSSProperties {
  return {
    width: '100%',
    background: 'transparent',
    border: 'none',
    borderRadius: 5,
    color: disabled ? 'var(--tx3)' : color,
    cursor: disabled ? 'default' : 'pointer',
    display: 'block',
    fontFamily: 'var(--font-ui)',
    fontSize: 12,
    padding: '6px 9px',
    textAlign: 'left',
  }
}
