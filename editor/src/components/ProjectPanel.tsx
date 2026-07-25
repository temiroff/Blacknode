import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type HardwareDevice,
  type Project,
  type RemoteDeployment,
} from '../api'
import { useStore } from '../store'
import './ProjectPanel.css'


interface SavedWorkflow {
  slug: string
  name: string
  saved_at: string
}

interface DeviceDeployment {
  deviceId: string
  deviceName: string
  deployment: RemoteDeployment
}

interface LifecycleItem {
  id: string
  label: string
  state: 'complete' | 'available' | 'waiting' | 'optional'
  detail: string
}


function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatUpdated(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
}


export default function ProjectPanel() {
  const {
    tabs,
    activeTabId,
    activeProject,
    workflowRevision,
    openWorkflowAsTab,
    setActiveProject,
  } = useStore()
  const activeTab = tabs.find(tab => tab.id === activeTabId)

  const [projects, setProjects] = useState<Project[]>([])
  const [workflows, setWorkflows] = useState<SavedWorkflow[]>([])
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deployments, setDeployments] = useState<DeviceDeployment[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [workflowToAdd, setWorkflowToAdd] = useState('')
  const [deviceToAdd, setDeviceToAdd] = useState('')

  const selected = projects.find(project => project.id === selectedId) ?? null

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [nextProjects, nextWorkflows, deviceResult] = await Promise.all([
        api.listProjects(),
        api.listWorkflows(),
        api.listDevices(),
      ])
      setProjects(nextProjects)
      setWorkflows(nextWorkflows)
      setDevices(deviceResult.devices)
      setSelectedId(current => (
        current && nextProjects.some(project => project.id === current)
          ? current
          : null
      ))
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh, workflowRevision])

  const deploymentDeviceKey = selected?.device_ids.join('|') ?? ''
  useEffect(() => {
    let cancelled = false
    if (!selected) {
      setDeployments([])
      return
    }
    const availableDevices = selected.devices.filter(device => device.exists)
    if (availableDevices.length === 0) {
      setDeployments([])
      return
    }
    void Promise.all(availableDevices.map(async device => {
      try {
        const result = await api.listRemoteDeployments(device.id)
        return result.deployments
          .filter(deployment => deployment.project_id === selected.id)
          .map(deployment => ({
            deviceId: device.id,
            deviceName: device.name,
            deployment,
          }))
      } catch {
        return []
      }
    })).then(groups => {
      if (!cancelled) setDeployments(groups.flat())
    })
    return () => {
      cancelled = true
    }
  }, [selectedId, deploymentDeviceKey])

  useEffect(() => {
    if (!selected) return
    setEditName(selected.name)
    setEditDescription(selected.description)
  }, [selected?.id, selected?.name, selected?.description])

  const replaceProject = useCallback((project: Project) => {
    setProjects(current => current.map(item => item.id === project.id ? project : item))
    if (activeProject?.id === project.id) {
      setActiveProject({
        id: project.id,
        name: project.name,
        workflowSlugs: project.workflow_slugs,
        deviceIds: project.device_ids,
      })
    }
  }, [activeProject?.id, setActiveProject])

  const updateSelected = useCallback(async (
    patch: Parameters<typeof api.updateProject>[1],
    action: string,
  ) => {
    if (!selected) return
    setBusy(action)
    setError('')
    try {
      replaceProject(await api.updateProject(selected.id, patch))
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setBusy('')
    }
  }, [replaceProject, selected])

  const createProject = async () => {
    const name = newName.trim()
    if (!name) return
    setBusy('create')
    setError('')
    try {
      const project = await api.createProject({
        name,
        description: newDescription.trim(),
        workflow_slugs: activeTab?.slug ? [activeTab.slug] : [],
        active_workflow_slug: activeTab?.slug ?? null,
      })
      setProjects(current => [project, ...current])
      setSelectedId(project.id)
      setCreating(false)
      setNewName('')
      setNewDescription('')
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setBusy('')
    }
  }

  const saveProjectDetails = async () => {
    if (!editName.trim()) return
    await updateSelected({
      name: editName.trim(),
      description: editDescription.trim(),
    }, 'edit')
    setEditing(false)
  }

  const removeProject = async () => {
    if (!selected) return
    if (!window.confirm(`Remove project “${selected.name}”? Linked workflows and devices will not be deleted.`)) {
      return
    }
    setBusy('delete')
    setError('')
    try {
      await api.deleteProject(selected.id)
      setProjects(current => current.filter(project => project.id !== selected.id))
      if (activeProject?.id === selected.id) setActiveProject(null)
      setSelectedId(null)
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setBusy('')
    }
  }

  const openProject = async () => {
    if (!selected) return
    const available = selected.workflows.filter(workflow => workflow.exists)
    if (available.length === 0) {
      setError('This project has no available saved workflows to open.')
      return
    }
    setBusy('open')
    setError('')
    const failed: string[] = []
    setActiveProject({
      id: selected.id,
      name: selected.name,
      workflowSlugs: selected.workflow_slugs,
      deviceIds: selected.device_ids,
    })
    for (const workflow of available) {
      try {
        await openWorkflowAsTab(workflow.slug, workflow.name)
      } catch {
        failed.push(workflow.name)
      }
    }
    const preferred = available.find(
      workflow => workflow.slug === selected.active_workflow_slug,
    )
    if (preferred && preferred.slug !== available[available.length - 1]?.slug) {
      try {
        await openWorkflowAsTab(preferred.slug, preferred.name)
      } catch {
        if (!failed.includes(preferred.name)) failed.push(preferred.name)
      }
    }
    if (failed.length > 0) {
      setError(`Could not open: ${failed.join(', ')}.`)
    }
    setBusy('')
  }

  const addWorkflow = async (slug: string) => {
    if (!selected || !slug || selected.workflow_slugs.includes(slug)) return
    await updateSelected({
      workflow_slugs: [...selected.workflow_slugs, slug],
      active_workflow_slug: selected.active_workflow_slug ?? slug,
    }, `workflow:${slug}`)
    setWorkflowToAdd('')
  }

  const removeWorkflow = async (slug: string) => {
    if (!selected) return
    await updateSelected({
      workflow_slugs: selected.workflow_slugs.filter(value => value !== slug),
    }, `workflow:${slug}`)
  }

  const addDevice = async (deviceId: string) => {
    if (!selected || !deviceId || selected.device_ids.includes(deviceId)) return
    await updateSelected({
      device_ids: [...selected.device_ids, deviceId],
    }, `device:${deviceId}`)
    setDeviceToAdd('')
  }

  const removeDevice = async (deviceId: string) => {
    if (!selected) return
    await updateSelected({
      device_ids: selected.device_ids.filter(value => value !== deviceId),
    }, `device:${deviceId}`)
  }

  const availableWorkflows = workflows.filter(
    workflow => !selected?.workflow_slugs.includes(workflow.slug),
  )
  const availableDevices = devices.filter(
    device => !selected?.device_ids.includes(device.id),
  )
  const runningDeployments = deployments.filter(item => item.deployment.state === 'running')
  const stagedDeployments = deployments.filter(item => (
    item.deployment.state === 'staged'
    || item.deployment.active_revision
  ))

  const lifecycle = useMemo<LifecycleItem[]>(() => {
    if (!selected) return []
    const existingWorkflows = selected.workflows.filter(workflow => workflow.exists)
    const existingDevices = selected.devices.filter(device => device.exists)
    const robotWorkflows = existingWorkflows.filter(workflow => workflow.requires_calibration)
    const calibratedWorkflows = robotWorkflows.filter(workflow => workflow.calibration)
    const hasStage = (stage: 'collect' | 'train' | 'simulate') => (
      existingWorkflows.some(workflow => workflow.stages.includes(stage))
    )
    return [
      {
        id: 'build',
        label: 'Build',
        state: existingWorkflows.length ? 'complete' : 'waiting',
        detail: existingWorkflows.length
          ? `${existingWorkflows.length} saved workflow${existingWorkflows.length === 1 ? '' : 's'} linked`
          : 'Link a saved workflow',
      },
      {
        id: 'connect',
        label: 'Connect',
        state: existingDevices.length ? 'complete' : 'waiting',
        detail: existingDevices.length
          ? `${existingDevices.length} paired device${existingDevices.length === 1 ? '' : 's'} linked`
          : 'Link a paired device',
      },
      {
        id: 'calibrate',
        label: 'Calibrate',
        state: robotWorkflows.length === 0
          ? 'optional'
          : calibratedWorkflows.length === robotWorkflows.length
            ? 'complete'
            : 'waiting',
        detail: robotWorkflows.length === 0
          ? 'No linked robot workflow requires calibration'
          : calibratedWorkflows.length === robotWorkflows.length
            ? `Selected in ${calibratedWorkflows.length} robot workflow${calibratedWorkflows.length === 1 ? '' : 's'}`
            : `Select calibration in ${robotWorkflows.length - calibratedWorkflows.length} robot workflow${robotWorkflows.length - calibratedWorkflows.length === 1 ? '' : 's'}`,
      },
      {
        id: 'collect',
        label: 'Collect',
        state: hasStage('collect') ? 'available' : 'optional',
        detail: hasStage('collect') ? 'Dataset recording workflow available' : 'Not configured for this project',
      },
      {
        id: 'train',
        label: 'Train',
        state: hasStage('train') ? 'available' : 'optional',
        detail: hasStage('train') ? 'Policy training workflow available' : 'Not configured for this project',
      },
      {
        id: 'simulate',
        label: 'Simulate',
        state: hasStage('simulate') ? 'available' : 'optional',
        detail: hasStage('simulate') ? 'Simulation workflow available' : 'Not configured for this project',
      },
      {
        id: 'deploy',
        label: 'Deploy',
        state: runningDeployments.length
          ? 'complete'
          : stagedDeployments.length
            ? 'available'
            : existingDevices.length && existingWorkflows.length
              ? 'available'
              : 'waiting',
        detail: runningDeployments.length
          ? `${runningDeployments.length} deployment${runningDeployments.length === 1 ? '' : 's'} running`
          : stagedDeployments.length
            ? `${stagedDeployments.length} deployment${stagedDeployments.length === 1 ? '' : 's'} staged or active`
            : 'Open a workflow and deploy it',
      },
      {
        id: 'operate',
        label: 'Operate',
        state: runningDeployments.length ? 'complete' : 'waiting',
        detail: runningDeployments.length ? 'Monitor the running robot deployment' : 'Waiting for a running deployment',
      },
    ]
  }, [selected, runningDeployments.length, stagedDeployments.length])

  const nextStep = useMemo(() => {
    if (!selected) return ''
    const build = lifecycle.find(item => item.id === 'build')
    const connect = lifecycle.find(item => item.id === 'connect')
    const calibrate = lifecycle.find(item => item.id === 'calibrate')
    if (build?.state === 'waiting') return 'Save a workflow, then link it to this project.'
    if (connect?.state === 'waiting') return 'Pair a device in Devices, then link it here.'
    if (calibrate?.state === 'waiting') return 'Open the robot workflow and select its matching calibration.'
    if (runningDeployments.length) return 'Monitor the running deployment and robot state.'
    return 'Open the project workflows, check setup, then deploy to a linked device.'
  }, [lifecycle, runningDeployments.length, selected])

  if (selected) {
    return (
      <div className="bn-project-panel">
        <div className="bn-project-toolbar">
          <button className="bn-project-link-button" onClick={() => setSelectedId(null)}>← Projects</button>
          <button className="bn-project-refresh" onClick={() => void refresh()} title="Refresh projects">↻</button>
        </div>

        <div className="bn-project-scroll">
          {error && <div className="bn-project-error">{error}</div>}

          <section className="bn-project-hero">
            {editing ? (
              <div className="bn-project-edit-form">
                <label>
                  Project name
                  <input value={editName} onChange={event => setEditName(event.target.value)} />
                </label>
                <label>
                  Description
                  <textarea value={editDescription} onChange={event => setEditDescription(event.target.value)} rows={3} />
                </label>
                <div className="bn-project-actions">
                  <button className="primary" disabled={!editName.trim() || busy === 'edit'} onClick={() => void saveProjectDetails()}>
                    {busy === 'edit' ? 'Saving…' : 'Save details'}
                  </button>
                  <button onClick={() => setEditing(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="bn-project-title-row">
                  <div>
                    <div className="bn-project-eyebrow">Project</div>
                    <h2>{selected.name}</h2>
                  </div>
                  <span className={activeProject?.id === selected.id ? 'bn-project-active' : 'bn-project-local'}>
                    {activeProject?.id === selected.id ? 'Active' : 'Local'}
                  </span>
                </div>
                {selected.description && <p>{selected.description}</p>}
                <div className="bn-project-actions">
                  <button className="primary" disabled={busy === 'open'} onClick={() => void openProject()}>
                    {busy === 'open' ? 'Opening…' : 'Open project'}
                  </button>
                  <button onClick={() => setEditing(true)}>Edit</button>
                  <button className="danger-text" disabled={busy === 'delete'} onClick={() => void removeProject()}>Remove</button>
                </div>
              </>
            )}
          </section>

          <section className="bn-project-next">
            <span>Next step</span>
            <strong>{nextStep}</strong>
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Lifecycle</h3>
              <span>Evidence from linked resources</span>
            </div>
            <div className="bn-project-lifecycle">
              {lifecycle.map((item, index) => (
                <div className={`bn-project-stage ${item.state}`} key={item.id}>
                  <div className="bn-project-stage-marker">{item.state === 'complete' ? '✓' : index + 1}</div>
                  <div>
                    <strong>{item.label}</strong>
                    <span>{item.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Workflows</h3>
              <span>{selected.workflow_slugs.length} linked</span>
            </div>
            <div className="bn-project-add-row">
              <select value={workflowToAdd} onChange={event => setWorkflowToAdd(event.target.value)}>
                <option value="">Choose saved workflow…</option>
                {availableWorkflows.map(workflow => (
                  <option value={workflow.slug} key={workflow.slug}>{workflow.name}</option>
                ))}
              </select>
              <button disabled={!workflowToAdd} onClick={() => void addWorkflow(workflowToAdd)}>Add</button>
            </div>
            {activeTab?.slug && !selected.workflow_slugs.includes(activeTab.slug) && (
              <button className="bn-project-wide-button" onClick={() => void addWorkflow(activeTab.slug!)}>
                + Add current workflow: {activeTab.name}
              </button>
            )}
            {!activeTab?.slug && (
              <div className="bn-project-hint">Save the current workflow before linking it.</div>
            )}
            <div className="bn-project-resource-list">
              {selected.workflows.map(workflow => (
                <div className={`bn-project-resource ${workflow.exists ? '' : 'missing'}`} key={workflow.slug}>
                  <div className="bn-project-resource-main">
                    <strong>{workflow.name}</strong>
                    <span>{workflow.exists ? workflow.slug : `Missing · ${workflow.slug}`}</span>
                    {workflow.calibration && (
                      <em>
                        Calibration: {workflow.calibration.profile_id ?? 'profile'} · {workflow.calibration.hardware_id ?? 'hardware'}
                      </em>
                    )}
                  </div>
                  <div className="bn-project-resource-actions">
                    {workflow.exists && (
                      <button onClick={() => void openWorkflowAsTab(workflow.slug, workflow.name)}>Open</button>
                    )}
                    {workflow.exists && selected.active_workflow_slug !== workflow.slug && (
                      <button
                        title="Select this tab after opening the project"
                        onClick={() => void updateSelected({ active_workflow_slug: workflow.slug }, `workflow:${workflow.slug}`)}
                      >
                        Start here
                      </button>
                    )}
                    {selected.active_workflow_slug === workflow.slug && <span className="bn-project-starts-here">Starts here</span>}
                    <button className="danger-text" onClick={() => void removeWorkflow(workflow.slug)}>Remove</button>
                  </div>
                </div>
              ))}
              {selected.workflows.length === 0 && <div className="bn-project-empty">No workflows linked yet.</div>}
            </div>
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Devices</h3>
              <span>{selected.device_ids.length} linked</span>
            </div>
            <div className="bn-project-add-row">
              <select value={deviceToAdd} onChange={event => setDeviceToAdd(event.target.value)}>
                <option value="">Choose paired device…</option>
                {availableDevices.map(device => (
                  <option value={device.id} key={device.id}>{device.name} · {device.id}</option>
                ))}
              </select>
              <button disabled={!deviceToAdd} onClick={() => void addDevice(deviceToAdd)}>Add</button>
            </div>
            <div className="bn-project-resource-list">
              {selected.devices.map(device => (
                <div className={`bn-project-resource ${device.exists ? '' : 'missing'}`} key={device.id}>
                  <div className="bn-project-resource-main">
                    <strong>{device.name}</strong>
                    <span>{device.exists ? device.id : `Missing · ${device.id}`}</span>
                    {device.exists && device.base_url && <em>{device.base_url}</em>}
                  </div>
                  <div className="bn-project-resource-actions">
                    <button className="danger-text" onClick={() => void removeDevice(device.id)}>Remove</button>
                  </div>
                </div>
              ))}
              {selected.devices.length === 0 && <div className="bn-project-empty">No devices linked yet.</div>}
            </div>
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Deployments</h3>
              <span>Owned by this project</span>
            </div>
            <div className="bn-project-resource-list">
              {deployments.map(item => (
                <div className="bn-project-resource" key={`${item.deviceId}:${item.deployment.id}`}>
                  <div className="bn-project-resource-main">
                    <strong>{item.deployment.name}</strong>
                    <span>
                      {item.deviceName}
                      {item.deployment.workflow_slug ? ` · ${item.deployment.workflow_slug}` : ''}
                    </span>
                  </div>
                  <span className={`bn-project-deployment-state ${item.deployment.state}`}>
                    {item.deployment.state}
                  </span>
                </div>
              ))}
              {deployments.length === 0 && (
                <div className="bn-project-empty">
                  No deployments are assigned to this project. Older unassigned
                  deployments remain available in Deployments.
                </div>
              )}
            </div>
          </section>

          <div className="bn-project-updated">Updated {formatUpdated(selected.updated_at)}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="bn-project-panel">
      <div className="bn-project-list-header">
        <div>
          <h2>Projects</h2>
          <p>Group workflows, robots, and deployments.</p>
        </div>
        <button className="primary" onClick={() => setCreating(value => !value)}>
          {creating ? 'Cancel' : '+ New'}
        </button>
      </div>

      {creating && (
        <div className="bn-project-create">
          <label>
            Project name
            <input
              autoFocus
              value={newName}
              onChange={event => setNewName(event.target.value)}
              onKeyDown={event => event.key === 'Enter' && void createProject()}
              placeholder="Leader Follower Demo"
            />
          </label>
          <label>
            Description <span>optional</span>
            <textarea
              value={newDescription}
              onChange={event => setNewDescription(event.target.value)}
              rows={2}
              placeholder="What are you building?"
            />
          </label>
          <div className="bn-project-hint">
            {activeTab?.slug
              ? `The current saved workflow “${activeTab.name}” will be linked.`
              : 'You can link saved workflows after creating the project.'}
          </div>
          <button className="primary bn-project-wide-button" disabled={!newName.trim() || busy === 'create'} onClick={() => void createProject()}>
            {busy === 'create' ? 'Creating…' : 'Create project'}
          </button>
        </div>
      )}

      {error && <div className="bn-project-error">{error}</div>}

      <div className="bn-project-list" onWheel={event => event.stopPropagation()}>
        {loading && <div className="bn-project-empty">Loading projects…</div>}
        {!loading && projects.length === 0 && (
          <div className="bn-project-onboarding">
            <div className="bn-project-onboarding-icon">◇</div>
            <h3>One place for the whole robot application</h3>
            <p>Create a project, link its workflows and devices, then follow the next step from setup to operation.</p>
            <button className="primary" onClick={() => setCreating(true)}>Create first project</button>
          </div>
        )}
        {projects.map(project => (
          <button
            className="bn-project-card"
            key={project.id}
            onClick={() => setSelectedId(project.id)}
          >
            <div className="bn-project-card-title">
              <strong>{project.name}</strong>
              {activeProject?.id === project.id && <span>Active</span>}
            </div>
            {project.description && <p>{project.description}</p>}
            <div className="bn-project-card-stats">
              <span>{project.workflow_slugs.length} workflow{project.workflow_slugs.length === 1 ? '' : 's'}</span>
              <span>{project.device_ids.length} device{project.device_ids.length === 1 ? '' : 's'}</span>
            </div>
            <em>Updated {formatUpdated(project.updated_at)}</em>
          </button>
        ))}
      </div>
    </div>
  )
}
