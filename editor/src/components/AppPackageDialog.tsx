import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react'

import { api, type PackageableAppWorkflow } from '../api'


interface AppPackageDialogProps {
  open: boolean
  currentAppId?: string
  onClose: () => void
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function cleanDeploymentId(value: string): string {
  const clean = value.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
  return /^[a-z]/.test(clean) ? clean.slice(0, 64) : `app-${clean || 'package'}`.slice(0, 64)
}

function PackageGlyph({ icon }: { icon: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      {icon === 'record' ? (
        <>
          <rect x="3.5" y="4" width="17" height="16" rx="3" />
          <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
        </>
      ) : icon === 'camera' ? (
        <>
          <path d="M4 8.5h3l1.5-2h7l1.5 2h3v10H4z" />
          <circle cx="12" cy="13.5" r="3.3" />
        </>
      ) : (
        <>
          <rect x="4" y="4" width="16" height="16" rx="4" />
          <path d="M8 9h8M8 12h5M8 15h7" />
        </>
      )}
    </svg>
  )
}

export default function AppPackageDialog({ open, currentAppId, onClose }: AppPackageDialogProps) {
  const [workflows, setWorkflows] = useState<PackageableAppWorkflow[]>([])
  const [selectedSlugs, setSelectedSlugs] = useState<string[]>([])
  const [deploymentId, setDeploymentId] = useState('blacknode-app')
  const [deploymentName, setDeploymentName] = useState('')
  const [startApp, setStartApp] = useState('')
  const [loading, setLoading] = useState(false)
  const [packaging, setPackaging] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError('')
    api.listPackageableAppWorkflows()
      .then(items => {
        if (cancelled) return
        setWorkflows(items)
        const initial = items.find(item => item.app_id === currentAppId) ?? items[0]
        setSelectedSlugs(initial ? [initial.slug] : [])
        setStartApp(initial?.app_id ?? '')
        setDeploymentId(cleanDeploymentId(initial?.app_id ?? 'blacknode-app'))
        setDeploymentName(initial?.title ?? '')
      })
      .catch(cause => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentAppId, open])

  const selected = useMemo(
    () => workflows.filter(item => selectedSlugs.includes(item.slug)),
    [selectedSlugs, workflows],
  )
  const duplicateAppIds = useMemo(() => {
    const counts = new Map<string, number>()
    selected.forEach(item => counts.set(item.app_id, (counts.get(item.app_id) ?? 0) + 1))
    return [...counts.entries()].filter(([, count]) => count > 1).map(([id]) => id)
  }, [selected])

  if (!open) return null

  const toggleWorkflow = (workflow: PackageableAppWorkflow) => {
    setSelectedSlugs(current => {
      const included = current.includes(workflow.slug)
      const next = included ? current.filter(slug => slug !== workflow.slug) : [...current, workflow.slug]
      const nextApps = workflows.filter(item => next.includes(item.slug))
      if (!nextApps.some(item => item.app_id === startApp)) setStartApp(nextApps[0]?.app_id ?? '')
      if (!included && current.length === 0) {
        setDeploymentId(cleanDeploymentId(workflow.app_id))
        setDeploymentName(workflow.title)
      }
      return next
    })
    setError('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!selected.length || packaging || duplicateAppIds.length) return
    setPackaging(true)
    setError('')
    try {
      const result = await api.packageApps({
        workflow_slugs: selected.map(item => item.slug),
        deployment_id: cleanDeploymentId(deploymentId),
        name: deploymentName.trim(),
        start_app: startApp,
      })
      downloadBlob(result.filename, result.blob)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'info',
          title: 'App package ready',
          message: `${result.filename} contains ${selected.length} Workflow App${selected.length === 1 ? '' : 's'}.`,
        },
      }))
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setPackaging(false)
    }
  }

  return (
    <div
      className="bn-app-package-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bn-app-package-title"
      onMouseDown={event => {
        if (event.target === event.currentTarget && !packaging) onClose()
      }}
    >
      <form className="bn-app-package-dialog" onSubmit={submit}>
        <header>
          <div>
            <span>Distribute</span>
            <h2 id="bn-app-package-title">Package Workflow Apps</h2>
          </div>
          <button type="button" onClick={onClose} disabled={packaging} aria-label="Close">×</button>
        </header>
        <p>
          Select saved Workflow Apps. Blacknode builds the customer UI and downloads one installable ZIP.
        </p>

        <div className="bn-app-package-fields">
          <label>
            <span>Package ID</span>
            <input
              value={deploymentId}
              onChange={event => setDeploymentId(event.target.value)}
              onBlur={() => setDeploymentId(cleanDeploymentId(deploymentId))}
              disabled={packaging}
              required
            />
          </label>
          <label>
            <span>Package name</span>
            <input
              value={deploymentName}
              onChange={event => setDeploymentName(event.target.value)}
              disabled={packaging}
              placeholder="Optional"
            />
          </label>
        </div>

        <section className="bn-app-package-workflows" aria-label="Saved Workflow Apps">
          <div className="bn-app-package-section-title">
            <strong>Apps</strong>
            <span>{selected.length} selected</span>
          </div>
          {loading ? (
            <div className="bn-app-package-empty">Loading saved Apps…</div>
          ) : workflows.length ? workflows.map(workflow => {
            const checked = selectedSlugs.includes(workflow.slug)
            return (
              <label className={checked ? 'is-selected' : ''} key={workflow.slug}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleWorkflow(workflow)}
                  disabled={packaging}
                />
                <i style={{ '--bn-app-package-accent': workflow.accent || 'var(--accent)' } as CSSProperties}>
                  <PackageGlyph icon={workflow.icon} />
                </i>
                <span>
                  <strong>{workflow.title}</strong>
                  <small>{workflow.name}</small>
                </span>
              </label>
            )
          }) : (
            <div className="bn-app-package-empty">
              No saved Workflow Apps found. Open an App workflow, press Save, then reopen this dialog.
            </div>
          )}
        </section>

        {selected.length > 1 && (
          <label className="bn-app-package-start">
            <span>Open first</span>
            <select value={startApp} onChange={event => setStartApp(event.target.value)} disabled={packaging}>
              {selected.map(item => <option value={item.app_id} key={item.slug}>{item.title}</option>)}
            </select>
          </label>
        )}

        {duplicateAppIds.length > 0 && (
          <p className="bn-app-package-error">App IDs must be unique: {duplicateAppIds.join(', ')}</p>
        )}
        {error && <p className="bn-app-package-error">{error}</p>}

        <footer>
          <span>Includes Windows and Linux installers.</span>
          <div>
            <button type="button" onClick={onClose} disabled={packaging}>Cancel</button>
            <button
              type="submit"
              className="is-primary"
              disabled={loading || packaging || !selected.length || duplicateAppIds.length > 0}
            >
              {packaging ? 'Building ZIP…' : 'Package ZIP'}
            </button>
          </div>
        </footer>
      </form>
    </div>
  )
}
