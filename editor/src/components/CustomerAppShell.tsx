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

export default function CustomerAppShell({ deployment }: CustomerAppShellProps) {
  const { workflowMetadata, loadGraph, loadRuntimeNodeOutputs, loadSpatialViewerNodeOutputs } = useStore()
  const [activeAppId, setActiveAppId] = useState('')
  const [loadingAppId, setLoadingAppId] = useState('')
  const [error, setError] = useState('')
  const activationRef = useRef('')
  const appsById = useMemo(() => new Map(deployment.apps.map(app => [app.id, app])), [deployment.apps])

  const activate = useCallback(async (appId: string, updateUrl = true) => {
    const selected = appsById.get(appId)
    if (!selected || activationRef.current === appId) return
    activationRef.current = appId
    setLoadingAppId(appId)
    setError('')
    try {
      await api.activateDeploymentApp(appId)
      await loadGraph(selected.name)
      setActiveAppId(appId)
      if (updateUrl && deployment.apps.length > 1) {
        window.history.pushState(window.history.state, '', `/app/${appId}`)
      }
    } catch (cause) {
      activationRef.current = ''
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoadingAppId('')
    }
  }, [appsById, deployment.apps.length, loadGraph])

  useEffect(() => {
    const requested = requestedAppId()
    if (requested && appsById.has(requested)) {
      void activate(requested, false)
      return
    }
    if (deployment.apps.length === 1) void activate(deployment.apps[0].id, false)
  }, [activate, appsById, deployment.apps])

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

  const openLauncher = () => {
    activationRef.current = ''
    setActiveAppId('')
    window.history.pushState(window.history.state, '', '/')
  }

  if (activeAppId && operatorView) {
    return (
      <div className="bn-customer-app-shell">
        <WorkflowOperatorView
          config={operatorView}
          onOpenLauncher={deployment.apps.length > 1 ? openLauncher : undefined}
        />
      </div>
    )
  }

  return (
    <main className="bn-customer-launcher">
      <header>
        <img src="/blacknode-logo.png" alt="" />
        <div>
          <span>Blacknode Apps</span>
          <h1>{deployment.name}</h1>
        </div>
      </header>
      {error && <p className="bn-customer-launcher-error">{error}</p>}
      <section aria-label="Available apps">
        {deployment.apps.map(app => (
          <button
            type="button"
            key={app.id}
            disabled={Boolean(loadingAppId)}
            onClick={() => void activate(app.id)}
            style={{ '--bn-customer-app-accent': app.accent || 'var(--accent)' } as CSSProperties}
          >
            <i aria-hidden="true" />
            <strong>{app.name}</strong>
            {app.description && <span>{app.description}</span>}
            <small>{loadingAppId === app.id ? 'Opening…' : 'Open app'}</small>
          </button>
        ))}
      </section>
    </main>
  )
}
