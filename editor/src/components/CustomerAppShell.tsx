import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'

import { api, type AppDeploymentSummary } from '../api'
import { isWorkflowOperatorView } from '../operatorView'
import { useStore } from '../store'
import WorkflowOperatorView from './WorkflowOperatorView'


interface CustomerAppShellProps {
  deployment: AppDeploymentSummary
}

function requestedAppId(): string {
  const match = window.location.pathname.match(/^\/app\/([a-z][a-z0-9_-]{0,63})\/?$/)
  return match?.[1] ?? ''
}

function AppGlyph({ icon }: { icon: string }) {
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
      {icon === 'play' && (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="m10 8 6 4-6 4z" fill="currentColor" stroke="none" />
        </>
      )}
      {!['record', 'camera', 'robot', 'play'].includes(icon) && (
        <>
          <rect x="3" y="5" width="6" height="5" rx="1.5" />
          <rect x="15" y="14" width="6" height="5" rx="1.5" />
          <path d="M9 7.5h4a3 3 0 0 1 3 3V14M13.5 12l2.5 2 2.5-2" />
        </>
      )}
    </svg>
  )
}

function SettingsGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19 13.5v-3l-2.1-.7a7 7 0 0 0-.7-1.6l1-2-2.2-2.1-1.9 1a7 7 0 0 0-1.7-.7L10.6 2h-3l-.7 2.3a7 7 0 0 0-1.6.7l-2-1-2.1 2.1 1 2a7 7 0 0 0-.7 1.6L0 10.5v3l2.3.7a7 7 0 0 0 .7 1.6l-1 2L4.1 20l2-1a7 7 0 0 0 1.6.7l.8 2.3h3l.7-2.3a7 7 0 0 0 1.6-.7l2 1 2.1-2.1-1-2a7 7 0 0 0 .7-1.6z" transform="translate(1.2) scale(.9)" />
    </svg>
  )
}

export default function CustomerAppShell({ deployment }: CustomerAppShellProps) {
  const { workflowMetadata, loadGraph, loadRuntimeNodeOutputs, loadSpatialViewerNodeOutputs } = useStore()
  const [activeAppId, setActiveAppId] = useState('')
  const [loadingAppId, setLoadingAppId] = useState('')
  const [error, setError] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const activationRef = useRef('')
  const appsById = useMemo(() => new Map(deployment.apps.map(app => [app.id, app])), [deployment.apps])

  const activate = useCallback(async (appId: string, updateUrl = true) => {
    const selected = appsById.get(appId)
    if (!selected || activationRef.current === appId) return
    activationRef.current = appId
    setLoadingAppId(appId)
    setError('')
    setSettingsOpen(false)
    try {
      await api.activateDeploymentApp(appId)
      await loadGraph(selected.name)
      setActiveAppId(appId)
      if (updateUrl) {
        window.history.pushState(window.history.state, '', `/app/${appId}`)
      }
    } catch (cause) {
      activationRef.current = ''
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoadingAppId('')
    }
  }, [appsById, loadGraph])

  useEffect(() => {
    const requested = requestedAppId()
    const initialAppId = requested && appsById.has(requested)
      ? requested
      : appsById.has(deployment.start_app)
        ? deployment.start_app
        : deployment.apps[0]?.id
    if (initialAppId) void activate(initialAppId, false)
  }, [activate, appsById, deployment.apps, deployment.start_app])

  useEffect(() => {
    if (!activeAppId) return
    void loadRuntimeNodeOutputs()
    void loadSpatialViewerNodeOutputs()
    const runtimeId = window.setInterval(() => void loadRuntimeNodeOutputs(), 1000)
    const spatialId = window.setInterval(() => void loadSpatialViewerNodeOutputs(), 100)
    return () => {
      window.clearInterval(runtimeId)
      window.clearInterval(spatialId)
    }
  }, [activeAppId, loadRuntimeNodeOutputs, loadSpatialViewerNodeOutputs])

  const operatorView = isWorkflowOperatorView(workflowMetadata.operator_view)
    ? workflowMetadata.operator_view
    : null

  return (
    <main className="bn-customer-app-shell">
      <header className="bn-customer-app-bar">
        <div className="bn-customer-app-brand">
          <img src="/blacknode-logo.png" alt="" />
          <div>
            <strong>Blacknode</strong>
            <span>{deployment.name}</span>
          </div>
        </div>
        <nav aria-label="Deployed Apps">
          {deployment.apps.map(app => (
            <button
              type="button"
              className={`${activeAppId === app.id ? 'is-active' : ''}${loadingAppId === app.id ? ' is-loading' : ''}`}
              disabled={Boolean(loadingAppId)}
              onClick={() => void activate(app.id)}
              title={app.name}
              aria-label={app.name}
              aria-pressed={activeAppId === app.id}
              key={app.id}
              style={{ '--bn-customer-app-accent': app.accent || 'var(--accent)' } as CSSProperties}
            >
              <AppGlyph icon={app.icon || 'workflow'} />
            </button>
          ))}
        </nav>
        <button
          type="button"
          className="bn-customer-app-settings"
          disabled={Boolean(loadingAppId) || !operatorView?.settings?.groups.length}
          onClick={() => setSettingsOpen(true)}
          title={operatorView?.settings ? 'App settings' : 'This App has no configurable settings'}
          aria-label="App settings"
        >
          <SettingsGlyph />
        </button>
      </header>
      <div className="bn-customer-app-stage">
        {error && <p className="bn-customer-app-error">{error}</p>}
        {activeAppId && operatorView
          ? (
              <WorkflowOperatorView
                config={operatorView}
                settingsOpen={settingsOpen}
                onCloseSettings={() => setSettingsOpen(false)}
              />
            )
          : (
              <div className="bn-customer-app-opening" role="status">
                <img src="/blacknode-logo.png" alt="" />
                <span>{loadingAppId ? 'Opening App…' : 'Preparing Apps…'}</span>
              </div>
            )}
      </div>
    </main>
  )
}
