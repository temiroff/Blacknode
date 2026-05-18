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
  const { loadGraph, loadNodeTypes } = useStore()

  const [workflows, setWorkflows] = useState<WorkflowMeta[]>([])
  const [saveName,  setSaveName]  = useState('')
  const [saving,    setSaving]    = useState(false)
  const [loading,   setLoading]   = useState<string | null>(null)
  const [deleting,  setDeleting]  = useState<string | null>(null)
  const [saveOk,    setSaveOk]    = useState(false)

  const refresh = useCallback(async () => {
    try { setWorkflows(await api.listWorkflows()) } catch {}
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleSave = async () => {
    const name = saveName.trim()
    if (!name) return
    setSaving(true)
    setSaveOk(false)
    try {
      await api.saveWorkflow(name)
      setSaveOk(true)
      setSaveName('')
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
      await api.loadWorkflow(slug)
      await loadGraph()
      await loadNodeTypes()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(null)
    }
  }

  const handleDelete = async (slug: string) => {
    setDeleting(slug)
    try {
      await api.deleteWorkflow(slug)
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setDeleting(null)
    }
  }

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
            background: saveOk ? 'var(--ok)' : 'var(--accent)',
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

        {workflows.map(w => (
          <div
            key={w.slug}
            style={{
              background: 'var(--lift)',
              border: '1px solid var(--line2)',
              borderRadius: 7,
              padding: '8px 10px',
              marginBottom: 6,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
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
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                <button
                  onClick={() => handleLoad(w.slug)}
                  disabled={loading === w.slug}
                  style={{
                    background: 'var(--accent)',
                    border: 'none',
                    borderRadius: 5,
                    color: '#fff',
                    cursor: loading === w.slug ? 'default' : 'pointer',
                    fontFamily: 'var(--font-ui)',
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '3px 9px',
                    opacity: loading === w.slug ? 0.6 : 1,
                  }}
                >
                  {loading === w.slug ? '…' : '▶ Load'}
                </button>
                <button
                  onClick={() => handleDelete(w.slug)}
                  disabled={deleting === w.slug}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--line2)',
                    borderRadius: 5,
                    color: deleting === w.slug ? 'var(--tx3)' : 'var(--err)',
                    cursor: deleting === w.slug ? 'default' : 'pointer',
                    fontFamily: 'var(--font-ui)',
                    fontSize: 11,
                    padding: '3px 7px',
                  }}
                >
                  {deleting === w.slug ? '…' : '✕'}
                </button>
              </div>
            </div>

            {w.saved_at && (
              <span style={{ color: 'var(--tx3)', fontSize: 11 }}>
                {fmtDate(w.saved_at)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
