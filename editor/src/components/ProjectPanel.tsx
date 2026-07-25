import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type HardwareDevice,
  type Project,
  type ProjectArtifact,
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

type StarterStage = 'collect' | 'train' | 'simulate'

interface ProjectNextStep {
  detail: string
  label: string
  workflowSlug: string
  starterStage?: StarterStage
  panel?: 'devices' | 'deployments' | 'templates' | 'workflows'
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

const ARTIFACT_LABELS: Record<ProjectArtifact['artifact_type'], string> = {
  dataset: 'Dataset',
  training_run: 'Training run',
  checkpoint: 'Checkpoint',
  policy: 'Policy',
  simulation_run: 'Simulation run',
  evaluation: 'Evaluation',
}

function artifactDetail(artifact: ProjectArtifact): string {
  const metadata = artifact.metadata
  if (artifact.artifact_type === 'dataset') {
    const episodes = Number(metadata.episode_count ?? 0)
    return `${episodes} episode${episodes === 1 ? '' : 's'} · ${artifact.provider}`
  }
  if (artifact.artifact_type === 'training_run') {
    const step = Number(metadata.step ?? 0)
    const steps = Number(metadata.steps ?? 0)
    return steps > 0
      ? `${artifact.status} · step ${step} of ${steps}`
      : `${artifact.status} · ${artifact.provider}`
  }
  if (artifact.artifact_type === 'evaluation') {
    const frames = Number(metadata.frames ?? 0)
    return frames > 0
      ? `${frames} frame${frames === 1 ? '' : 's'} evaluated`
      : `${artifact.status} · ${artifact.provider}`
  }
  return `${artifact.status} · ${artifact.provider}`
}


export default function ProjectPanel() {
  const {
    tabs,
    activeTabId,
    activeProject,
    workflowRevision,
    projectRevision,
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
  const [newStarterKit, setNewStarterKit] = useState<'robot_learning' | ''>('')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [workflowToAdd, setWorkflowToAdd] = useState('')
  const [deviceToAdd, setDeviceToAdd] = useState('')
  const [artifactPath, setArtifactPath] = useState('')

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
  }, [refresh, workflowRevision, projectRevision])

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
        starter_kit: newStarterKit || null,
        active_workflow_slug: activeTab?.slug ?? null,
      })
      setProjects(current => [project, ...current])
      setSelectedId(project.id)
      setCreating(false)
      setNewName('')
      setNewDescription('')
      setNewStarterKit('')
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

  const enableRobotLearningStarter = async () => {
    await updateSelected(
      { starter_kit: 'robot_learning' },
      'starter:enable',
    )
  }

  const useCustomProjectSetup = async () => {
    await updateSelected(
      { starter_kit: null },
      'starter:disable',
    )
  }

  const addExistingArtifact = async () => {
    if (!selected || !artifactPath.trim()) return
    setBusy('artifact:add')
    setError('')
    try {
      const result = await api.inspectProjectArtifact(selected.id, {
        path: artifactPath.trim(),
        workflow_slug: selected.active_workflow_slug,
      })
      replaceProject(result.project)
      setArtifactPath('')
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setBusy('')
    }
  }

  const unlinkArtifact = async (artifactId: string) => {
    if (!selected) return
    await updateSelected({
      artifact_ids: selected.artifact_ids.filter(value => value !== artifactId),
    }, `artifact:${artifactId}`)
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
  const datasetArtifacts = selected?.artifacts.filter(
    artifact => artifact.artifact_type === 'dataset' && artifact.exists,
  ) ?? []
  const completedDatasets = datasetArtifacts.filter(
    artifact => Number(artifact.metadata.episode_count ?? 0) > 0,
  )
  const trainingArtifacts = selected?.artifacts.filter(
    artifact => ['training_run', 'checkpoint', 'policy'].includes(artifact.artifact_type),
  ) ?? []
  const policyArtifacts = trainingArtifacts.filter(
    artifact => artifact.artifact_type === 'policy' && artifact.exists,
  )
  const runningTraining = trainingArtifacts.filter(
    artifact => artifact.status === 'running',
  )
  const simulationArtifacts = selected?.artifacts.filter(
    artifact => ['simulation_run', 'evaluation'].includes(artifact.artifact_type),
  ) ?? []
  const completedSimulations = simulationArtifacts.filter(
    artifact => artifact.status === 'completed' && artifact.exists,
  )

  const lifecycle = useMemo<LifecycleItem[]>(() => {
    if (!selected) return []
    const existingWorkflows = selected.workflows.filter(workflow => workflow.exists)
    const existingDevices = selected.devices.filter(device => device.exists)
    const robotWorkflows = existingWorkflows.filter(workflow => workflow.requires_calibration)
    const calibratedWorkflows = robotWorkflows.filter(workflow => workflow.calibration)
    const hasStage = (stage: 'collect' | 'train' | 'simulate') => (
      existingWorkflows.some(workflow => workflow.stages.includes(stage))
    )
    const setupStages: LifecycleItem[] = [
      {
        id: 'connect',
        label: 'Connect',
        state: existingDevices.length ? 'complete' : 'waiting',
        detail: existingDevices.length
          ? `${existingDevices.length} paired device${existingDevices.length === 1 ? '' : 's'} linked`
          : 'Install the device runtime and pair a robot',
      },
      {
        id: 'build',
        label: 'Build',
        state: existingWorkflows.length
          ? 'complete'
          : selected.starter_kit
            ? 'available'
            : 'waiting',
        detail: existingWorkflows.length
          ? `${existingWorkflows.length} saved workflow${existingWorkflows.length === 1 ? '' : 's'} linked`
          : selected.starter_kit
            ? 'Starter is ready to create the first workflow'
            : 'Choose a template or link a saved workflow',
      },
      {
        id: 'calibrate',
        label: 'Configure',
        state: robotWorkflows.length === 0
          ? 'optional'
          : calibratedWorkflows.length === robotWorkflows.length
            ? 'complete'
            : 'waiting',
        detail: robotWorkflows.length === 0
          ? 'No linked robot workflow requires calibration'
          : calibratedWorkflows.length === robotWorkflows.length
            ? `Selected in ${calibratedWorkflows.length} robot workflow${calibratedWorkflows.length === 1 ? '' : 's'}`
            : `Click to select calibration in ${robotWorkflows.length - calibratedWorkflows.length} robot workflow${robotWorkflows.length - calibratedWorkflows.length === 1 ? '' : 's'}`,
      },
    ]
    const learningConfigured = Boolean(
      selected.starter_kit
      || hasStage('collect')
      || hasStage('train')
      || hasStage('simulate')
      || datasetArtifacts.length
      || trainingArtifacts.length
      || simulationArtifacts.length,
    )
    const learningStages: LifecycleItem[] = learningConfigured ? [
      {
        id: 'collect',
        label: 'Collect',
        state: completedDatasets.length
          ? 'complete'
          : selected.starter_kit || hasStage('collect') || datasetArtifacts.length
            ? 'available'
            : 'optional',
        detail: completedDatasets.length
          ? `${completedDatasets.reduce((sum, artifact) => sum + Number(artifact.metadata.episode_count ?? 0), 0)} recorded episode${completedDatasets.reduce((sum, artifact) => sum + Number(artifact.metadata.episode_count ?? 0), 0) === 1 ? '' : 's'}`
          : datasetArtifacts.length
            ? 'Dataset created; record the first episode'
            : hasStage('collect')
              ? 'Dataset recording workflow available'
              : selected.starter_kit
                ? 'Starter recording workflow ready'
              : 'Not configured for this project',
      },
      {
        id: 'train',
        label: 'Train',
        state: policyArtifacts.length
          ? 'complete'
          : selected.starter_kit || hasStage('train') || trainingArtifacts.length
            ? 'available'
            : 'optional',
        detail: policyArtifacts.length
          ? `${policyArtifacts.length} policy artifact${policyArtifacts.length === 1 ? '' : 's'} ready`
          : runningTraining.length
            ? `${runningTraining.length} training run${runningTraining.length === 1 ? '' : 's'} running`
            : trainingArtifacts.length
              ? 'Training evidence available; export a policy'
              : hasStage('train')
                ? 'Policy training workflow available'
                : selected.starter_kit
                  ? 'Starter training workflow ready'
                : 'Not configured for this project',
      },
      {
        id: 'simulate',
        label: 'Simulate',
        state: completedSimulations.length
          ? 'complete'
          : selected.starter_kit || hasStage('simulate') || simulationArtifacts.length
            ? 'available'
            : 'optional',
        detail: completedSimulations.length
          ? `${completedSimulations.length} completed simulation result${completedSimulations.length === 1 ? '' : 's'}`
          : simulationArtifacts.some(artifact => artifact.status === 'running')
            ? 'Simulation is running'
            : hasStage('simulate')
              ? 'Simulation workflow available'
              : selected.starter_kit
                ? 'Starter simulation workflow ready'
              : 'Not configured for this project',
      },
    ] : []
    return [
      ...setupStages,
      ...learningStages,
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
  }, [
    completedDatasets,
    completedSimulations,
    datasetArtifacts.length,
    policyArtifacts.length,
    runningDeployments.length,
    runningTraining.length,
    selected,
    simulationArtifacts,
    stagedDeployments.length,
    trainingArtifacts.length,
  ])

  const nextStep = useMemo<ProjectNextStep>(() => {
    if (!selected) return { detail: '', label: '', workflowSlug: '' }
    const workflowFor = (stage: StarterStage) => {
      const candidates = selected.workflows.filter(
        workflow => workflow.exists && workflow.stages.includes(stage),
      )
      return (
        candidates.find(workflow => !workflow.starter_stage)
        ?? candidates[0]
      )
    }
    const build = lifecycle.find(item => item.id === 'build')
    const connect = lifecycle.find(item => item.id === 'connect')
    const calibrate = lifecycle.find(item => item.id === 'calibrate')
    if (connect?.state === 'waiting') {
      return {
        detail: 'Install Blacknode on the robot computer, then pair and verify it.',
        label: 'Set up robot',
        workflowSlug: '',
        panel: 'devices',
      }
    }
    if (build?.state === 'waiting') {
      return {
        detail: 'Start from a tested template or link a workflow you already saved.',
        label: 'Choose workflow',
        workflowSlug: '',
        panel: 'templates',
      }
    }
    if (
      selected.starter_kit === 'robot_learning'
      && selected.workflows.every(workflow => !workflow.exists)
      && completedDatasets.length === 0
      && policyArtifacts.length === 0
    ) {
      return {
        detail: 'Start with a ready-made workflow for recording robot demonstrations.',
        label: 'Create recording workflow',
        workflowSlug: '',
        starterStage: 'collect',
      }
    }
    if (completedDatasets.length > 0 && policyArtifacts.length === 0) {
      const train = workflowFor('train')
      if (!train && selected.starter_kit === 'robot_learning') {
        return {
          detail: 'Your recorded data is ready. Create the predefined ACT training workflow.',
          label: 'Create training workflow',
          workflowSlug: '',
          starterStage: 'train',
        }
      }
      if (train) {
        return {
          detail: runningTraining.length
            ? 'Training is running. Open the workflow to monitor progress.'
            : 'Recorded data is ready. Start or resume policy training.',
          label: runningTraining.length ? 'Monitor training' : 'Open training workflow',
          workflowSlug: train.slug,
        }
      }
    }
    if (policyArtifacts.length > 0 && completedSimulations.length === 0) {
      const simulate = workflowFor('simulate')
      if (!simulate && selected.starter_kit === 'robot_learning') {
        return {
          detail: 'Your policy is ready. Create the predefined Isaac evaluation workflow.',
          label: 'Create simulation workflow',
          workflowSlug: '',
          starterStage: 'simulate',
        }
      }
      if (simulate) {
        return {
          detail: 'A policy is ready. Run it in simulation and capture the result.',
          label: 'Open simulation workflow',
          workflowSlug: simulate.slug,
        }
      }
    }
    if (calibrate?.state === 'waiting') {
      const workflow = selected.workflows.find(item => item.exists && item.requires_calibration)
      return {
        detail: 'Open the robot workflow and select its matching calibration.',
        label: 'Open calibration workflow',
        workflowSlug: workflow?.slug ?? '',
      }
    }
    if (completedDatasets.length === 0 && policyArtifacts.length === 0) {
      const collect = workflowFor('collect')
      if (!collect && selected.starter_kit === 'robot_learning') {
        return {
          detail: 'Create the ready-made recording workflow and save the first episode.',
          label: 'Create recording workflow',
          workflowSlug: '',
          starterStage: 'collect',
        }
      }
      if (collect) {
        return {
          detail: datasetArtifacts.length
            ? 'The dataset is ready. Record and save the first episode.'
            : 'Create the dataset and record the first episode.',
          label: 'Open recording workflow',
          workflowSlug: collect.slug,
        }
      }
    }
    if (runningDeployments.length) {
      return {
        detail: 'Monitor the running deployment and robot state.',
        label: 'Monitor deployment',
        workflowSlug: '',
        panel: 'deployments',
      }
    }
    return {
      detail: 'Open the project workflows, check setup, then deploy to a linked device.',
      label: 'Open project',
      workflowSlug: selected.active_workflow_slug ?? '',
    }
  }, [
    completedDatasets.length,
    completedSimulations.length,
    datasetArtifacts.length,
    lifecycle,
    policyArtifacts.length,
    runningDeployments.length,
    runningTraining.length,
    selected,
  ])

  const runProjectStep = async (step: ProjectNextStep) => {
    if (!selected) return
    if (step.panel) {
      setActiveProject({
        id: selected.id,
        name: selected.name,
        workflowSlugs: selected.workflow_slugs,
        deviceIds: selected.device_ids,
      })
      window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
        detail: { tab: step.panel },
      }))
      return
    }
    setBusy('next')
    setError('')
    try {
      let project = selected
      let workflow = step.workflowSlug
        ? selected.workflows.find(item => item.slug === step.workflowSlug)
        : null
      if (step.starterStage) {
        const result = await api.createProjectStarterWorkflow(
          selected.id,
          step.starterStage,
        )
        project = result.project
        workflow = result.workflow
        replaceProject(project)
        setWorkflows(current => (
          current.some(item => item.slug === result.workflow.slug)
            ? current
            : [{
                slug: result.workflow.slug,
                name: result.workflow.name,
                saved_at: result.workflow.saved_at ?? '',
              }, ...current]
        ))
      }
      if (!workflow) return
      setActiveProject({
        id: project.id,
        name: project.name,
        workflowSlugs: project.workflow_slugs,
        deviceIds: project.device_ids,
      })
      await openWorkflowAsTab(workflow.slug, workflow.name)
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setBusy('')
    }
  }

  const openLifecycleStage = async (stageId: string) => {
    if (!selected || busy) return
    if (stageId === 'connect') {
      setActiveProject({
        id: selected.id,
        name: selected.name,
        workflowSlugs: selected.workflow_slugs,
        deviceIds: selected.device_ids,
      })
      window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
        detail: { tab: 'devices' },
      }))
      return
    }
    if (stageId === 'deploy' || stageId === 'operate') {
      window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
        detail: { tab: 'deployments' },
      }))
      return
    }
    if (stageId === 'build') {
      if (selected.workflows.some(workflow => workflow.exists)) {
        await openProject()
      } else if (selected.starter_kit === 'robot_learning') {
        await runProjectStep({
          detail: '',
          label: '',
          workflowSlug: '',
          starterStage: 'collect',
        })
      } else {
        window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
          detail: { tab: 'workflows' },
        }))
      }
      return
    }
    if (stageId === 'calibrate') {
      const robotWorkflows = selected.workflows.filter(
        workflow => workflow.exists && workflow.requires_calibration,
      )
      const workflow = (
        robotWorkflows.find(item => !item.calibration)
        ?? robotWorkflows[0]
      )
      if (workflow) {
        await runProjectStep({
          detail: '',
          label: '',
          workflowSlug: workflow.slug,
        })
      } else if (selected.starter_kit === 'robot_learning') {
        await runProjectStep({
          detail: '',
          label: '',
          workflowSlug: '',
          starterStage: 'collect',
        })
      } else {
        window.dispatchEvent(new CustomEvent('blacknode:notice', {
          detail: {
            kind: 'info',
            title: 'No calibration needed',
            message: 'No linked workflow currently requires robot calibration.',
          },
        }))
      }
      return
    }
    if (['collect', 'train', 'simulate'].includes(stageId)) {
      const stage = stageId as StarterStage
      const candidates = selected.workflows.filter(
        workflow => workflow.exists && workflow.stages.includes(stage),
      )
      const workflow = (
        candidates.find(item => !item.starter_stage)
        ?? candidates[0]
      )
      if (workflow) {
        await runProjectStep({
          detail: '',
          label: '',
          workflowSlug: workflow.slug,
        })
      } else if (selected.starter_kit === 'robot_learning') {
        await runProjectStep({
          detail: '',
          label: '',
          workflowSlug: '',
          starterStage: stage,
        })
      } else {
        window.dispatchEvent(new CustomEvent('blacknode:notice', {
          detail: {
            kind: 'info',
            title: `${stageId[0].toUpperCase()}${stageId.slice(1)} is not configured`,
            message: 'Link a saved workflow for this stage or enable the robot learning starter.',
          },
        }))
      }
    }
  }

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
                {selected.starter_kit === 'robot_learning' && (
                  <div className="bn-project-starter-note">
                    Robot learning starter · Next creates the appropriate
                    predefined workflow when you have not linked your own.
                  </div>
                )}
                <div className="bn-project-actions">
                  <button className="primary" disabled={busy === 'open'} onClick={() => void openProject()}>
                    {busy === 'open' ? 'Opening…' : 'Open project'}
                  </button>
                  {!selected.starter_kit && (
                    <button
                      disabled={busy === 'starter:enable'}
                      onClick={() => void enableRobotLearningStarter()}
                    >
                      {busy === 'starter:enable'
                        ? 'Enabling…'
                        : 'Use robot learning starter'}
                    </button>
                  )}
                  {selected.starter_kit === 'robot_learning' && (
                    <button
                      disabled={busy === 'starter:disable'}
                      title="Keep linked workflows and stop suggesting predefined starter templates"
                      onClick={() => void useCustomProjectSetup()}
                    >
                      {busy === 'starter:disable'
                        ? 'Switching…'
                        : 'Use custom setup'}
                    </button>
                  )}
                  <button onClick={() => setEditing(true)}>Edit</button>
                  <button className="danger-text" disabled={busy === 'delete'} onClick={() => void removeProject()}>Remove</button>
                </div>
              </>
            )}
          </section>

          <section className="bn-project-next">
            <span>Next step</span>
            <strong>{nextStep.detail}</strong>
            {nextStep.label && (nextStep.workflowSlug || nextStep.starterStage || nextStep.panel) && (
              <button
                disabled={busy === 'next'}
                onClick={() => void runProjectStep(nextStep)}
              >
                {busy === 'next' ? 'Preparing…' : nextStep.label}
              </button>
            )}
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Lifecycle</h3>
              <span>Evidence from linked resources</span>
            </div>
            <div className="bn-project-lifecycle">
              {lifecycle.map((item, index) => (
                <button
                  type="button"
                  className={`bn-project-stage ${item.state}`}
                  key={item.id}
                  title={`Open ${item.label}`}
                  onClick={() => void openLifecycleStage(item.id)}
                >
                  <div className="bn-project-stage-marker">{item.state === 'complete' ? '✓' : index + 1}</div>
                  <div>
                    <strong>{item.label}</strong>
                    <span>{item.detail}</span>
                  </div>
                  <span className="bn-project-stage-open" aria-hidden="true">›</span>
                </button>
              ))}
            </div>
          </section>

          <section className="bn-project-section">
            <div className="bn-project-section-title">
              <h3>Artifacts</h3>
              <span>{selected.artifacts.length} linked</span>
            </div>
            <div className="bn-project-hint">
              Dataset, training, policy, and simulation outputs are captured
              automatically when linked workflows run.
            </div>
            <div className="bn-project-add-row">
              <input
                value={artifactPath}
                onChange={event => setArtifactPath(event.target.value)}
                onKeyDown={event => event.key === 'Enter' && void addExistingArtifact()}
                placeholder="Path to an existing artifact or manifest"
              />
              <button
                disabled={!artifactPath.trim() || busy === 'artifact:add'}
                onClick={() => void addExistingArtifact()}
              >
                {busy === 'artifact:add' ? 'Adding…' : 'Add'}
              </button>
            </div>
            <div className="bn-project-resource-list">
              {selected.artifacts.map(artifact => (
                <div
                  className={`bn-project-resource ${artifact.exists ? '' : 'missing'}`}
                  key={artifact.id}
                >
                  <div className="bn-project-resource-main">
                    <strong>
                      <span className="bn-project-artifact-kind">
                        {ARTIFACT_LABELS[artifact.artifact_type]}
                      </span>
                      {artifact.name}
                    </strong>
                    <span>{artifactDetail(artifact)}</span>
                    <em title={artifact.locator}>
                      {artifact.exists ? artifact.locator : `Source unavailable · ${artifact.locator}`}
                    </em>
                  </div>
                  <div className="bn-project-resource-actions">
                    <span className={`bn-project-artifact-state ${artifact.status}`}>
                      {artifact.status}
                    </span>
                    <button
                      className="danger-text"
                      disabled={busy === `artifact:${artifact.id}`}
                      title="Unlink from this project; the source artifact will not be deleted"
                      onClick={() => void unlinkArtifact(artifact.id)}
                    >
                      Unlink
                    </button>
                  </div>
                </div>
              ))}
              {selected.artifacts.length === 0 && (
                <div className="bn-project-empty">
                  No artifacts linked yet. Run a linked collect, train, or
                  simulation workflow, or add an existing artifact path.
                </div>
              )}
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
          <p>Group workflows, robots, artifacts, and deployments.</p>
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
          <label>
            Setup
            <select
              value={newStarterKit}
              onChange={event => setNewStarterKit(
                event.target.value as 'robot_learning' | '',
              )}
            >
              <option value="">Robot deployment — recommended</option>
              <option value="robot_learning">Robot learning</option>
            </select>
          </label>
          {newStarterKit === 'robot_learning' && (
            <div className="bn-project-starter-note">
              Next will prepare recording, ACT training, and Isaac evaluation
              workflows as you reach each stage. You can replace any stage
              with your own linked workflow.
            </div>
          )}
          {newStarterKit !== 'robot_learning' && (
            <div className="bn-project-starter-note">
              Follow a guided path from installing the device runtime and
              pairing the robot through workflow setup, deployment, and
              operation.
            </div>
          )}
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
            <h3>Set up your first robot project</h3>
            <p>Blacknode guides you through connecting the robot, choosing a workflow, checking its setup, and deploying it.</p>
            <div className="bn-project-onboarding-steps" aria-label="Project setup steps">
              <span><b>1</b> Connect</span>
              <span><b>2</b> Build</span>
              <span><b>3</b> Configure</span>
              <span><b>4</b> Deploy</span>
            </div>
            <button className="primary" onClick={() => setCreating(true)}>Create robot project</button>
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
              {project.starter_kit === 'robot_learning' && <span>Guided starter</span>}
              <span>{project.workflow_slugs.length} workflow{project.workflow_slugs.length === 1 ? '' : 's'}</span>
              <span>{project.device_ids.length} device{project.device_ids.length === 1 ? '' : 's'}</span>
              <span>{project.artifact_ids.length} artifact{project.artifact_ids.length === 1 ? '' : 's'}</span>
            </div>
            <em>Updated {formatUpdated(project.updated_at)}</em>
          </button>
        ))}
      </div>
    </div>
  )
}
