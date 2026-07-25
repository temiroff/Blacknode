import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import {
  api,
  type DeviceCalibrationCandidate,
  type DeviceRobotProfile,
  type Deployment,
  type DeploymentPreflight,
  type DeploymentPreflightStatus,
  type DeploymentState,
  type HardwareDevice,
  type HardwareDeviceStatus,
  type RemoteDeployment,
  type RemoteDeploymentState,
} from '../api'
import { useStore } from '../store'

const REFRESH_INTERVAL_MS = 3000
const DEFAULT_DEPLOYMENT_NAME = 'Deployed graph'
const ROBOT_NODE_TYPES = new Set(['Robot', 'RobotProfileLoad'])
const JOINT_MOTION_NODE_TYPES = new Set([
  'ROS2SetJoint',
  'ROS2ManualMove',
  'ROS2JointSliders',
  'ROS2LeaderFollower',
  'ROS2NativeFollowDetectionJoint',
  'ROS2FollowDetectionJoint',
  'RobotFollow',
  'PolicyRuntime',
  'IsaacPolicyRuntime',
])

function normalizedHardwareIdentity(value: unknown): string {
  return String(value ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '')
}

function deploymentNameFromTab(name: string | undefined): string {
  const cleanName = name?.trim() ?? ''
  return !cleanName || cleanName.toLocaleLowerCase() === 'untitled'
    ? DEFAULT_DEPLOYMENT_NAME
    : cleanName
}

function deviceForHardwareIdentity(
  devices: HardwareDevice[],
  hardwareId: string,
): HardwareDevice | null {
  const hardwareToken = normalizedHardwareIdentity(hardwareId)
  if (hardwareToken.length < 6) return null
  const matches = devices.filter(device => (
    normalizedHardwareIdentity(device.remote_device_id).includes(hardwareToken)
  ))
  return matches.length === 1 ? matches[0] : null
}

const STATE_COLOR: Record<DeploymentState, string> = {
  running: 'var(--ok)',
  stopped: 'var(--tx3)',
  exited: 'var(--tx2)',
  failed: 'var(--err)',
}

const STATE_LABEL: Record<DeploymentState, string> = {
  running: 'LIVE',
  stopped: 'OFF',
  exited: 'DONE',
  failed: 'FAIL',
}

const REMOTE_STATE_COLOR: Record<RemoteDeploymentState, string> = {
  staged: 'var(--accent)',
  running: 'var(--ok)',
  stopped: 'var(--tx3)',
  exited: 'var(--tx2)',
  failed: 'var(--err)',
}

const REMOTE_STATE_LABEL: Record<RemoteDeploymentState, string> = {
  staged: 'STAGED',
  running: 'LIVE',
  stopped: 'OFF',
  exited: 'DONE',
  failed: 'FAIL',
}

interface DeploymentsPanelProps {
  onOpenTemplates: (query: string) => void
}

export default function DeploymentsPanel({ onOpenTemplates }: DeploymentsPanelProps) {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [logs, setLogs] = useState<Record<string, string>>({})
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  const [preflight, setPreflight] = useState<DeploymentPreflight | null>(null)
  const [remoteDeployments, setRemoteDeployments] = useState<RemoteDeployment[]>([])
  const [remoteOpenId, setRemoteOpenId] = useState<string | null>(null)
  const [remoteLogs, setRemoteLogs] = useState<Record<string, string>>({})
  const [remoteDeploymentName, setRemoteDeploymentName] = useState('')
  const [remoteAction, setRemoteAction] = useState<'send' | 'send-run' | null>(null)
  const [remoteNotice, setRemoteNotice] = useState<string | null>(null)
  const stopRuntimeServices = useStore(s => s.stopRuntimeServices)
  const tabs = useStore(s => s.tabs)
  const activeTabId = useStore(s => s.activeTabId)
  const activeTab = tabs.find(tab => tab.id === activeTabId)
  const activeDeploymentName = deploymentNameFromTab(activeTab?.name)
  const activeProject = useStore(s => s.activeProject)
  const deploymentProject = (
    activeProject
    && activeTab?.slug
    && activeProject.workflowSlugs.includes(activeTab.slug)
  )
    ? {
        id: activeProject.id,
        name: activeProject.name,
        workflowSlug: activeTab.slug,
        workflowName: activeTab.name,
        deviceIds: activeProject.deviceIds,
      }
    : null
  const switchTab = useStore(s => s.switchTab)
  const workflowRevision = useStore(s => s.workflowRevision)
  const workflowMetadata = useStore(s => s.workflowMetadata)
  const setWorkflowRequirements = useStore(s => s.setWorkflowRequirements)
  const nodes = useStore(s => s.nodes)
  const nodeDefs = useStore(s => s.nodeDefs)
  const updateParam = useStore(s => s.updateParam)
  const selectNode = useStore(s => s.selectNode)
  const [robotProfiles, setRobotProfiles] = useState<DeviceRobotProfile[]>([])
  const [calibrations, setCalibrations] = useState<DeviceCalibrationCandidate[]>([])
  const [targetStatus, setTargetStatus] = useState<HardwareDeviceStatus | null>(null)
  const [requirementsBusy, setRequirementsBusy] = useState(false)
  const [profileBusyId, setProfileBusyId] = useState<string | null>(null)

  const requiredCapabilities = Array.isArray(workflowMetadata.required_capabilities)
    ? workflowMetadata.required_capabilities.map(String)
    : []
  const selectedCalibration = (
    workflowMetadata.device_calibration
    && typeof workflowMetadata.device_calibration === 'object'
  )
    ? workflowMetadata.device_calibration
    : null
  const robotNodes = useMemo(
    () => nodes.filter(node => ROBOT_NODE_TYPES.has(node.data.type)),
    [nodes],
  )
  const isCalibrationWorkflow = nodes.some(
    node => node.data.type === 'RobotCalibrationRecorder',
  )
  const calibrationNode = nodes.find(
    node => node.data.type === 'RobotCalibrationRecorder',
  )
  const deploymentWorkflowTab = tabs.find(tab => {
    if (tab.id === activeTabId || !tab.graph) return false
    const graphNodes = Array.isArray(tab.graph.nodes) ? tab.graph.nodes : []
    const nodeTypes = graphNodes.map(node => String(node?.type ?? node?.data?.type ?? ''))
    return (
      nodeTypes.some(type => ROBOT_NODE_TYPES.has(type))
      && !nodeTypes.includes('RobotCalibrationRecorder')
    )
  })
  const hasJointMotion = nodes.some(
    node => JOINT_MOTION_NODE_TYPES.has(node.data.type),
  )
  const inferredCapabilities = robotNodes.length > 0
    ? [
        ...(hasJointMotion && !isCalibrationWorkflow ? ['joint_group'] : []),
        'position_feedback',
        'servo_bus',
      ].sort()
    : requiredCapabilities
  const activeCalibration = targetStatus?.calibration
  const selectedCalibrationCandidate = calibrations.find(
    calibration => (
      calibration.profile_id === selectedCalibration?.profile_id
      && calibration.hardware_id === selectedCalibration?.hardware_id
    ),
  )
  const calibrationIsActive = Boolean(
    selectedCalibration
    && targetStatus?.calibrated
    && activeCalibration?.profile_id === selectedCalibration.profile_id
    && activeCalibration?.hardware_id === selectedCalibration.hardware_id
  )
  const calibrationMatchedDevice = useMemo(
    () => deviceForHardwareIdentity(
      devices,
      String(selectedCalibration?.hardware_id ?? ''),
    ),
    [devices, selectedCalibration?.hardware_id],
  )

  const refresh = async () => {
    try {
      const result = await api.listDeployments()
      setDeployments(result.deployments)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    setRemoteDeploymentName(activeDeploymentName)
  }, [activeDeploymentName, activeTabId])

  useEffect(() => {
    setPreflight(null)
    setRemoteNotice(null)
  }, [activeTabId])

  useEffect(() => {
    let cancelled = false
    const loadRequirements = async () => {
      try {
        const calibrationResult = await api.listGraphCalibrations()
        if (cancelled) return
        setRobotProfiles(calibrationResult.profiles ?? [])
        setCalibrations(calibrationResult.calibrations)
        if (!selectedDeviceId) {
          setTargetStatus(null)
          return
        }
        try {
          const status = await api.deviceStatus(selectedDeviceId)
          if (!cancelled) setTargetStatus(status)
        } catch {
          if (!cancelled) setTargetStatus(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void loadRequirements()
    return () => { cancelled = true }
  }, [activeTabId, selectedDeviceId, workflowRevision])

  const updateRequirements = async (
    capabilities: string[],
    calibration: { profile_id: string; hardware_id: string } | null,
  ) => {
    setRequirementsBusy(true)
    setError(null)
    try {
      await setWorkflowRequirements(capabilities, calibration)
      setPreflight(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRequirementsBusy(false)
    }
  }

  const selectCalibration = (value: string) => {
    const calibration = calibrations.find(
      item => `${item.profile_id}\u0000${item.hardware_id}` === value,
    )
    void updateRequirements(
      inferredCapabilities,
      calibration
        ? { profile_id: calibration.profile_id, hardware_id: calibration.hardware_id }
        : null,
    )
  }

  const changeRobotProfile = async (nodeId: string, profileId: string) => {
    setProfileBusyId(nodeId)
    setError(null)
    try {
      await updateParam(nodeId, 'profile_id', profileId)
      await setWorkflowRequirements(inferredCapabilities, null)
      const calibrationResult = await api.listGraphCalibrations()
      setRobotProfiles(calibrationResult.profiles ?? [])
      setCalibrations(calibrationResult.calibrations)
      setPreflight(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setProfileBusyId(null)
    }
  }

  useEffect(() => {
    if (
      robotNodes.length !== 1
      || calibrations.length !== 1
      || selectedCalibration
      || requirementsBusy
      || profileBusyId
      || isCalibrationWorkflow
    ) return
    const calibration = calibrations[0]
    void updateRequirements(inferredCapabilities, {
      profile_id: calibration.profile_id,
      hardware_id: calibration.hardware_id,
    })
  }, [
    calibrations,
    inferredCapabilities.join('|'),
    isCalibrationWorkflow,
    profileBusyId,
    requirementsBusy,
    robotNodes.length,
    selectedCalibration,
  ])

  useEffect(() => {
    if (!selectedDeviceId) {
      setRemoteDeployments([])
      return
    }
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.listRemoteDeployments(selectedDeviceId)
        if (!cancelled) setRemoteDeployments(result.deployments)
      } catch {
        if (!cancelled) setRemoteDeployments([])
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [selectedDeviceId])

  useEffect(() => {
    api.listDevices()
      .then(result => {
        setDevices(result.devices)
        setSelectedDeviceId(current => (
          current && result.devices.some(device => device.id === current)
            ? current
            : result.devices[0]?.id ?? ''
        ))
      })
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  useEffect(() => {
    if (!calibrationMatchedDevice) return
    setSelectedDeviceId(current => (
      current === calibrationMatchedDevice.id
        ? current
        : calibrationMatchedDevice.id
    ))
    setPreflight(null)
    setRemoteNotice(null)
  }, [activeTabId, calibrationMatchedDevice?.id, selectedCalibration?.hardware_id])

  // Only the open row's log is fetched, and only while it is open, so a long
  // list of deployments does not turn into a log-tail storm every 3s.
  useEffect(() => {
    if (!openId) return
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.deploymentLogs(openId)
        if (!cancelled) setLogs(prev => ({ ...prev, [openId]: result.logs }))
      } catch {
        /* the row itself already shows state; a failed tail is not worth an error banner */
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [openId])

  useEffect(() => {
    if (!selectedDeviceId || !remoteOpenId) return
    let cancelled = false
    const pull = async () => {
      try {
        const result = await api.remoteDeploymentLogs(selectedDeviceId, remoteOpenId)
        if (!cancelled) {
          setRemoteLogs(prev => ({ ...prev, [remoteOpenId]: result.logs }))
        }
      } catch {
        /* deployment state remains visible when a log tail is temporarily unavailable */
      }
    }
    pull()
    const id = window.setInterval(pull, REFRESH_INTERVAL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [selectedDeviceId, remoteOpenId])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeploy = async (autostart: boolean) => {
    const name = window.prompt('Name this deployment', activeDeploymentName)
    if (name === null) return
    const finalName = name.trim() || activeDeploymentName
    await act(async () => {
      // Only a running deployment competes for the hardware, so stop the
      // editor's live graph first in that case. Save-only just writes the
      // files and runs nothing, so it leaves the live graph alone.
      if (autostart) {
        try { await stopRuntimeServices() } catch { /* deploy stops it too */ }
      }
      return api.deployGraph(finalName, autostart)
    })
  }

  const handleExport = async (deployment: Deployment) => {
    setBusy(true); setError(null)
    try {
      const res = await api.exportDeployment(deployment.id)
      // Not an error, but the message row is the one visible surface for a path.
      setError(`Saved runnable script to ${res.path}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (deployment: Deployment) => {
    if (!window.confirm(`Delete "${deployment.name}"? This stops it and removes its snapshot.`)) return
    await act(() => api.deleteDeployment(deployment.id))
    setOpenId(prev => (prev === deployment.id ? null : prev))
  }

  const validateRemoteDeployment = async () => {
    if (!selectedDeviceId) return
    setBusy(true)
    setError(null)
    setRemoteNotice(null)
    setPreflight(null)
    try {
      await setWorkflowRequirements(inferredCapabilities, selectedCalibration)
      let result = await api.validateDeviceDeployment(selectedDeviceId)
      const calibrationCheck = result.checks.find(check => check.id === 'calibration')
      const safetyReady = result.checks.some(
        check => check.id === 'safety' && check.status === 'pass',
      )
      if (calibrationCheck?.action === 'activate_calibration' && safetyReady) {
        const activation = await api.activateDeviceCalibration(selectedDeviceId)
        setTargetStatus(activation.status)
        result = await api.validateDeviceDeployment(selectedDeviceId)
      } else {
        setTargetStatus(result.status)
      }
      setPreflight(result)
      setRemoteDeploymentName(current => current.trim() || activeDeploymentName)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const refreshRemote = async () => {
    if (!selectedDeviceId) return
    const result = await api.listRemoteDeployments(selectedDeviceId)
    setRemoteDeployments(result.deployments)
  }

  const actRemote = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refreshRemote()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const stageRemote = async (
    start: boolean,
    existing?: RemoteDeployment,
  ) => {
    if (!selectedDeviceId || !preflight?.ready) return
    if (
      existing?.project_id
      && (
        !deploymentProject
        || deploymentProject.id !== existing.project_id
        || deploymentProject.workflowSlug !== existing.workflow_slug
      )
    ) {
      setError(
        `Deployment "${existing.name}" belongs to project `
        + `"${existing.project_id}" / "${existing.workflow_slug}". Open that `
        + 'workflow from its Project before staging an update.',
      )
      return
    }
    if (
      deploymentProject
      && !deploymentProject.deviceIds.includes(selectedDeviceId)
    ) {
      setError(
        `The selected device is not linked to project "${deploymentProject.name}". `
        + 'Link it in Projects before staging this workflow.',
      )
      return
    }
    const name = (
      existing?.name
      || remoteDeploymentName.trim()
      || activeDeploymentName
      || preflight.workflow.name
      || DEFAULT_DEPLOYMENT_NAME
    )
    setBusy(true)
    setRemoteAction(start ? 'send-run' : 'send')
    setRemoteNotice(null)
    setError(null)
    try {
      const result = await api.stageRemoteDeployment(
        selectedDeviceId,
        name,
        preflight.workflow.hash,
        start,
        existing?.id,
        deploymentProject?.id,
        deploymentProject?.workflowSlug,
      )
      setRemoteOpenId(result.deployment.id)
      await refreshRemote()
      setRemoteNotice(
        start
          ? `"${name}" was sent to the device and started.`
          : `"${name}" was sent to the device and is ready to start.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRemoteAction(null)
      setBusy(false)
    }
  }

  const deleteRemote = async (deployment: RemoteDeployment) => {
    if (!selectedDeviceId) return
    if (!window.confirm(`Delete remote deployment "${deployment.name}"?`)) return
    await actRemote(() => api.deleteRemoteDeployment(selectedDeviceId, deployment.id))
    setRemoteOpenId(current => current === deployment.id ? null : current)
  }

  const running = deployments.filter(d => d.state === 'running').length
  const remoteRunning = remoteDeployments.filter(d => d.state === 'running').length

  return (
    <div className="bn-runs-panel bn-deploy-panel">
      <div className="bn-runs-toolbar">
        <div>
          <div className="bn-runs-title">Deployments</div>
          <div className="bn-runs-subtitle">
            {deployments.length} total · {running} running
          </div>
        </div>
        <div className="bn-runs-actions">
          <button onClick={refresh} style={miniButton}>Refresh</button>
          <button onClick={() => handleDeploy(false)} disabled={busy} style={miniButton} title="Save the runnable script on this computer without running it">Save local</button>
          <button onClick={() => handleDeploy(true)} disabled={busy} style={primaryButton} title="Stop the live graph, then run it on this computer">Run local</button>
        </div>
      </div>

      {error && <div className="bn-runs-error">{error}</div>}

      <div className="bn-deploy-target">
        <div className="bn-deploy-target-head">
          <div>
            <div className="bn-deploy-target-title">Deploy one robot</div>
            <div className="bn-runs-subtitle">
              Choose the computer physically connected to this robot. Use a separate
              deployment workflow for each additional robot.
            </div>
          </div>
        </div>
        {devices.length > 0 ? (
          <select
            className="bn-deploy-device-select"
            value={selectedDeviceId}
            onChange={event => {
              setSelectedDeviceId(event.target.value)
              setPreflight(null)
              setRemoteNotice(null)
            }}
          >
            {devices.map(device => (
              <option key={device.id} value={device.id}>
                {device.name} · {device.base_url}
              </option>
            ))}
          </select>
        ) : (
          <div className="bn-device-help">Pair a Raspberry Pi in the Devices tab first.</div>
        )}
        <div className={`bn-robot-step-status ${deploymentProject ? 'is-success' : ''}`}>
          <strong>Deployment ownership:</strong>{' '}
          {deploymentProject
            ? `${deploymentProject.name} / ${deploymentProject.workflowName}`
            : 'Unassigned. Open this workflow from a Project to attach deployment history.'}
        </div>
        {calibrationMatchedDevice && selectedDeviceId === calibrationMatchedDevice.id && (
          <div className="bn-robot-step-status is-success">
            <strong>Matched to the graph calibration:</strong>
            {' '}
            {calibrationMatchedDevice.name} · {selectedCalibration?.hardware_id}
          </div>
        )}

        <div className="bn-robot-deploy-steps">
          <section className={`bn-robot-deploy-step${robotNodes.length > 0 ? ' is-complete' : ' is-needed'}`}>
            <div className="bn-robot-step-number">1</div>
            <div className="bn-robot-step-content">
              <div className="bn-robot-step-title">Choose one robot profile</div>
              <div className="bn-robot-step-help">
                The profile describes this robot’s model, joints, servo IDs, and driver.
              </div>

              {robotNodes.length === 0 ? (
                <div className="bn-robot-step-empty">
                  <strong>No Robot node is in this workflow.</strong>
                  <span>Start with a robot workflow, then return here to deploy it.</span>
                  <button
                    type="button"
                    onClick={() => onOpenTemplates('SO-ARM101 Motion Test')}
                    style={primaryButton}
                  >
                    Open robot starter
                  </button>
                </div>
              ) : (
                <div className="bn-robot-profile-list">
                  {robotNodes.length > 1 && (
                    <div className="bn-robot-step-status is-warning">
                      This workflow contains {robotNodes.length} robot connections. Keep one
                      Robot node in each deployable workflow, then deploy the robots one at a time.
                    </div>
                  )}
                  {robotNodes.map((node, index) => {
                    const definition = nodeDefs[node.data.type]
                    const currentProfile = String(
                      node.data.params?.profile_id
                      ?? definition?.input_defaults?.profile_id
                      ?? 'so_arm101',
                    )
                    const choices = Array.from(new Set([
                      currentProfile,
                      ...robotProfiles.map(profile => profile.id),
                      ...(definition?.input_choices?.profile_id ?? []),
                    ])).filter(Boolean)
                    const fallbackName = node.data.type === 'RobotProfileLoad'
                      ? 'Legacy Robot'
                      : 'Robot'
                    const nodeName = String(
                      node.data.params?.label
                      || (robotNodes.length === 1 ? fallbackName : `${fallbackName} ${index + 1}`),
                    )
                    return (
                      <div className="bn-robot-profile-row" key={node.id}>
                        <label>
                          <span>{nodeName}</span>
                          <select
                            className="bn-deploy-device-select"
                            value={currentProfile}
                            disabled={profileBusyId === node.id}
                            onChange={event => {
                              void changeRobotProfile(node.id, event.target.value)
                            }}
                          >
                            {choices.map(profileId => {
                              const profile = robotProfiles.find(item => item.id === profileId)
                              const calibrationLabel = profile?.calibration_count
                                ? ` · ${profile.calibration_count} calibration${profile.calibration_count === 1 ? '' : 's'}`
                                : ''
                              return (
                                <option value={profileId} key={profileId}>
                                  {profile?.name || profileId}{calibrationLabel}
                                </option>
                              )
                            })}
                          </select>
                        </label>
                        <button
                          type="button"
                          onClick={() => selectNode(node.id)}
                          style={miniButton}
                        >
                          Show node
                        </button>
                      </div>
                    )
                  })}
                  <button
                    type="button"
                    className="bn-robot-setup-action"
                    onClick={() => onOpenTemplates('Editable SO-ARM101 Robot Profile')}
                    style={miniButton}
                  >
                    Create or edit robot profile
                  </button>
                </div>
              )}
            </div>
          </section>

          <section className={`bn-robot-deploy-step${
            isCalibrationWorkflow || !hasJointMotion || calibrationIsActive
              ? ' is-complete'
              : calibrations.length > 0
              ? ' is-pending'
              : ' is-needed'
          }`}>
            <div className="bn-robot-step-number">2</div>
            <div className="bn-robot-step-content">
              <div className="bn-robot-step-title">Prepare the safety calibration</div>
              <div className="bn-robot-step-help">
                Calibration saves this physical robot’s neutral Home position and safe joint ranges.
              </div>

              {isCalibrationWorkflow ? (
                <>
                  <div className="bn-robot-step-status is-info">
                    <strong>This tab creates calibrations; it does not choose one for deployment.</strong>
                    {' '}
                    Name and record the calibration here, then return to the robot workflow.
                    Its Step 2 contains the calibration picker.
                  </div>
                  {calibrationNode && (
                    <button
                      type="button"
                      className="bn-robot-setup-action"
                      onClick={() => selectNode(calibrationNode.id)}
                      style={primaryButton}
                    >
                      Open calibration controls
                    </button>
                  )}
                  {deploymentWorkflowTab ? (
                    <button
                      type="button"
                      className="bn-robot-setup-action"
                      onClick={() => void switchTab(deploymentWorkflowTab.id)}
                      style={primaryButton}
                    >
                      Return to {deploymentWorkflowTab.name} and choose calibration
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="bn-robot-setup-action"
                      onClick={() => onOpenTemplates('SO-ARM101 Motion Test')}
                      style={miniButton}
                    >
                      Open robot deployment workflow
                    </button>
                  )}
                  {calibrations.length > 0 && (
                    <div className="bn-robot-step-status">
                      {calibrations.length} saved calibration{calibrations.length === 1 ? '' : 's'}
                      {' '}
                      match this profile. You will choose one after returning to the deployment
                      workflow.
                    </div>
                  )}
                </>
              ) : robotNodes.length === 0 ? (
                <div className="bn-robot-step-status">
                  A robot calibration will appear here after the workflow has a Robot node.
                </div>
              ) : robotNodes.length > 1 ? (
                <div className="bn-robot-step-status is-warning">
                  Calibration is selected per deployment. Split this graph so it contains one
                  Robot node, then choose that physical robot’s calibration below.
                </div>
              ) : (
                <>
                  {!hasJointMotion && (
                    <div className="bn-robot-step-status is-info">
                      This workflow only reads robot state, so calibration is optional. Its
                      open-graph selection is still shown below and will become required if
                      motion controls are added.
                    </div>
                  )}

                  {calibrations.length === 0 ? (
                    <>
                      {selectedCalibration && (
                        <div className="bn-robot-step-status is-warning">
                          <strong>Open graph calibration:</strong>
                          {' '}
                          {selectedCalibration.profile_id} · {selectedCalibration.hardware_id}.
                          The saved calibration record is not currently available.
                        </div>
                      )}
                      <div className="bn-robot-step-empty">
                        <strong>No saved calibration matches this profile.</strong>
                        <span>
                          Open the guided workflow, calibrate this connected robot locally, then
                          return here and select the saved calibration.
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <label className="bn-robot-calibration-choice">
                        <span>Calibration from the open graph</span>
                        <select
                          className="bn-deploy-device-select"
                          value={selectedCalibration
                            ? `${selectedCalibration.profile_id}\u0000${selectedCalibration.hardware_id}`
                            : ''}
                          disabled={requirementsBusy}
                          onChange={event => selectCalibration(event.target.value)}
                        >
                          {(!selectedCalibration || calibrations.length > 1) && (
                            <option value="">
                              {calibrations.length > 1
                                ? `Choose one of ${calibrations.length} saved calibrations…`
                                : 'Choose the saved calibration…'}
                            </option>
                          )}
                          {selectedCalibration && !selectedCalibrationCandidate && (
                            <option
                              value={`${selectedCalibration.profile_id}\u0000${selectedCalibration.hardware_id}`}
                            >
                              Selected: {selectedCalibration.profile_id} · {selectedCalibration.hardware_id} (not found)
                            </option>
                          )}
                          {calibrations.map(calibration => (
                            <option
                              key={`${calibration.profile_id}\u0000${calibration.hardware_id}`}
                              value={`${calibration.profile_id}\u0000${calibration.hardware_id}`}
                            >
                              {calibration.name} · {calibration.profile_name}
                              {' · '}
                              {calibration.hardware_id}
                              {' · '}
                              {formatCalibrationTime(calibration.recorded_at)}
                              {' · '}
                              {calibration.joint_count} joints
                            </option>
                          ))}
                        </select>
                      </label>

                      <div className={`bn-robot-calibration-summary${
                        selectedCalibrationCandidate
                          ? calibrationIsActive
                            ? ' is-success'
                            : ''
                          : ' is-warning'
                      }`}>
                        {selectedCalibrationCandidate ? (
                          <>
                            Selected:
                            {' '}
                            {selectedCalibrationCandidate.name}
                            {' · '}
                            {selectedCalibrationCandidate.hardware_id}.
                            {' '}
                            {hasJointMotion && (
                              calibrationIsActive
                                ? 'Active on this device.'
                                : 'Check setup will verify the robot and prepare it automatically.'
                            )}
                          </>
                        ) : (
                          <>
                            Choose the named calibration for the physical robot connected to
                            this device.
                          </>
                        )}
                      </div>
                    </>
                  )}
                </>
              )}
              {!isCalibrationWorkflow && robotNodes.length === 1 && (
                <button
                  type="button"
                  className="bn-robot-setup-action"
                  onClick={() => onOpenTemplates('Guided Calibration')}
                  style={calibrations.length === 0 ? primaryButton : miniButton}
                >
                  {calibrations.length === 0
                    ? 'Create calibration'
                    : 'Create another calibration'}
                </button>
              )}
            </div>
          </section>

          <section className={`bn-robot-deploy-step${preflight?.ready ? ' is-complete' : ''}`}>
            <div className="bn-robot-step-number">3</div>
            <div className="bn-robot-step-content">
              <div className="bn-robot-step-title">Check and deploy</div>
              <div className="bn-robot-step-help">
                Blacknode selected the workflow requirements automatically:
                {' '}
                {inferredCapabilities.length > 0
                  ? inferredCapabilities.join(', ')
                  : 'no device-specific capabilities'}.
              </div>
              {preflight?.ready && (
                <label className="bn-robot-deployment-name">
                  <span>Deployment name</span>
                  <input
                    value={remoteDeploymentName}
                    onChange={event => setRemoteDeploymentName(event.target.value)}
                    placeholder={activeDeploymentName}
                    disabled={busy}
                  />
                </label>
              )}
              <div className="bn-robot-step-actions">
                <button
                  onClick={validateRemoteDeployment}
                  disabled={
                    busy
                    || requirementsBusy
                    || Boolean(profileBusyId)
                    || !selectedDeviceId
                    || robotNodes.length > 1
                  }
                  style={preflight?.ready ? miniButton : primaryButton}
                >
                  Check setup
                </button>
                {preflight?.ready && (
                  <>
                    <button onClick={() => stageRemote(false)} disabled={busy} style={miniButton}>
                      {remoteAction === 'send' ? 'Sending…' : 'Send to device'}
                    </button>
                    <button onClick={() => stageRemote(true)} disabled={busy} style={primaryButton}>
                      {remoteAction === 'send-run' ? 'Sending & starting…' : 'Send & run'}
                    </button>
                  </>
                )}
              </div>
              {remoteAction && (
                <div className="bn-robot-step-status is-info">
                  Synchronizing required packages and sending the workflow. This can take a few
                  minutes the first time.
                </div>
              )}
              {remoteNotice && !remoteAction && (
                <div className="bn-robot-step-status is-success">{remoteNotice}</div>
              )}
            </div>
          </section>
        </div>
      </div>

      {preflight && <PreflightResult result={preflight} />}

      <div className="bn-deployment-section-head">
        <div>
          <strong>Remote deployments</strong>
          <span>{remoteDeployments.length} total · {remoteRunning} running</span>
        </div>
        <button onClick={() => actRemote(refreshRemote)} disabled={busy || !selectedDeviceId} style={miniButton}>
          Refresh
        </button>
      </div>
      <div className="bn-runs-list bn-card-list bn-remote-deployment-list">
        {selectedDeviceId && remoteDeployments.length === 0 && (
          <div className="bn-runs-empty">
            No deployment has been sent to this device. Check the setup, then choose
            <strong> Send to device</strong> or <strong>Send &amp; run</strong>.
          </div>
        )}
        {remoteDeployments.map(deployment => (
          <RemoteDeploymentRow
            key={deployment.id}
            deployment={deployment}
            busy={busy}
            canStage={Boolean(preflight?.ready)}
            expanded={remoteOpenId === deployment.id}
            log={remoteLogs[deployment.id] ?? ''}
            onToggle={() => setRemoteOpenId(current => (
              current === deployment.id ? null : deployment.id
            ))}
            onStage={() => stageRemote(false, deployment)}
            onStart={() => actRemote(() => (
              api.startRemoteDeployment(selectedDeviceId, deployment.id)
            ))}
            onStop={() => actRemote(() => (
              api.stopRemoteDeployment(selectedDeviceId, deployment.id)
            ))}
            onRollback={() => {
              if (!window.confirm(`Roll back "${deployment.name}" to its previous revision?`)) return
              actRemote(() => api.rollbackRemoteDeployment(
                selectedDeviceId,
                deployment.id,
              ))
            }}
            onDelete={() => deleteRemote(deployment)}
          />
        ))}
      </div>

      <div className="bn-deployment-section-head">
        <div>
          <strong>Local deployments</strong>
          <span>Run by this editor computer</span>
        </div>
      </div>
      <div className="bn-runs-list">
        {deployments.length === 0 && !error && (
          <div className="bn-runs-empty">
            Nothing deployed. <strong>Deploy graph</strong> snapshots the current graph and runs
            it in the background, so it keeps running while you edit something else.
          </div>
        )}
        {deployments.map(deployment => (
          <DeploymentRow
            key={deployment.id}
            deployment={deployment}
            busy={busy}
            expanded={openId === deployment.id}
            log={logs[deployment.id] ?? ''}
            onToggle={() => setOpenId(prev => (prev === deployment.id ? null : deployment.id))}
            onStart={() => act(() => api.startDeployment(deployment.id))}
            onStop={() => act(() => api.stopDeployment(deployment.id))}
            onExport={() => handleExport(deployment)}
            onDelete={() => handleDelete(deployment)}
          />
        ))}
      </div>
    </div>
  )
}

const PREFLIGHT_LABEL: Record<DeploymentPreflightStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  warning: 'WARN',
  pending: 'WAIT',
}

function PreflightResult({ result }: { result: DeploymentPreflight }) {
  return (
    <div className="bn-preflight">
      <div className={`bn-preflight-summary ${result.ready ? 'is-ready' : 'is-blocked'}`}>
        <strong>{result.ready ? 'Ready' : 'Not ready'}</strong>
        <span>{result.summary}</span>
      </div>
      <div className="bn-preflight-checks">
        {result.checks.map(check => (
          <div className="bn-preflight-check" key={check.id}>
            <span className={`bn-preflight-pill is-${check.status}`}>
              {PREFLIGHT_LABEL[check.status]}
            </span>
            <div>
              <strong>{check.label}</strong>
              <span>{check.message}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RemoteDeploymentRow({
  deployment,
  busy,
  canStage,
  expanded,
  log,
  onToggle,
  onStage,
  onStart,
  onStop,
  onRollback,
  onDelete,
}: {
  deployment: RemoteDeployment
  busy: boolean
  canStage: boolean
  expanded: boolean
  log: string
  onToggle: () => void
  onStage: () => void
  onStart: () => void
  onStop: () => void
  onRollback: () => void
  onDelete: () => void
}) {
  const isRunning = deployment.state === 'running'
  const canRollback = deployment.revisions.length > 1
  const badges = [
    deployment.project_id
      ? `project ${deployment.project_id} / ${deployment.workflow_slug || 'workflow'}`
      : 'unassigned',
    `${deployment.revisions.length} revision${deployment.revisions.length === 1 ? '' : 's'}`,
    `staged ${deployment.staged_revision}`,
    deployment.active_revision ? `active ${deployment.active_revision}` : null,
    deployment.pid ? `pid ${deployment.pid}` : null,
  ].filter(Boolean) as string[]

  return (
    <div
      className={`bn-run-row${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': REMOTE_STATE_COLOR[deployment.state] } as CSSProperties}
    >
      <button onClick={onToggle} className="bn-run-summary" type="button" aria-expanded={expanded}>
        <div className="bn-run-timeline-mark"><span /></div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-title" title={deployment.name}>{deployment.name}</span>
            <span className="bn-run-age">{formatTime(deployment.updated_at)}</span>
          </div>
          <div className="bn-run-node" title={deployment.id}>{deployment.id}</div>
          <div className="bn-run-badges">
            {badges.map(badge => <span key={badge}>{badge}</span>)}
          </div>
          {deployment.error && <div className="bn-run-error-line">{deployment.error}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{REMOTE_STATE_LABEL[deployment.state]}</span>
          <span>{describeRemoteState(deployment)}</span>
        </div>
      </button>

      {expanded && (
        <div className="bn-run-detail">
          <pre style={logStyle}>{log.trim() || 'No remote output captured yet.'}</pre>
          <div className="bn-run-detail-actions">
            {isRunning
              ? <button onClick={onStop} disabled={busy} style={miniButton}>Stop</button>
              : <button onClick={onStart} disabled={busy} style={primaryButton}>Run</button>}
            <button
              onClick={onStage}
              disabled={busy || !canStage || isRunning}
              style={miniButton}
              title={canStage ? 'Stage the validated graph as a new revision' : 'Validate the graph first'}
            >
              Stage update
            </button>
            <button
              onClick={onRollback}
              disabled={busy || !canRollback}
              style={miniButton}
              title={canRollback ? 'Stage the previous revision' : 'No previous revision exists'}
            >
              Rollback
            </button>
            <button onClick={onDelete} disabled={busy || isRunning} style={miniButton}>
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function DeploymentRow({ deployment, busy, expanded, log, onToggle, onStart, onStop, onExport, onDelete }: {
  deployment: Deployment
  busy: boolean
  expanded: boolean
  log: string
  onToggle: () => void
  onStart: () => void
  onStop: () => void
  onExport: () => void
  onDelete: () => void
}) {
  const color = STATE_COLOR[deployment.state]
  const isRunning = deployment.state === 'running'
  const badges = [
    deployment.kind,
    `${deployment.node_count} ${deployment.node_count === 1 ? 'node' : 'nodes'}`,
    deployment.snapshot_hash,
    deployment.pid ? `pid ${deployment.pid}` : null,
  ].filter(Boolean) as string[]

  return (
    <div
      className={`bn-run-row${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': color } as CSSProperties}
    >
      <button onClick={onToggle} className="bn-run-summary" type="button" aria-expanded={expanded}>
        <div className="bn-run-timeline-mark"><span /></div>
        <div className="bn-run-main">
          <div className="bn-run-line">
            <span className="bn-run-title" title={deployment.name}>{deployment.name}</span>
            <span className="bn-run-age">{formatTime(deployment.started_at)}</span>
          </div>
          <div className="bn-run-node" title={deployment.id}>{deployment.id}</div>
          <div className="bn-run-badges">
            {badges.map(badge => <span key={badge}>{badge}</span>)}
          </div>
          {deployment.error && <div className="bn-run-error-line">{deployment.error}</div>}
        </div>
        <div className="bn-run-status">
          <span className="bn-run-status-pill">{STATE_LABEL[deployment.state]}</span>
          <span>{describeState(deployment)}</span>
        </div>
      </button>

      {expanded && (
        <div className="bn-run-detail">
          <div className="bn-run-node">
            entrypoint {deployment.entrypoint?.node_id ?? '?'}.{deployment.entrypoint?.port ?? '?'}
            {deployment.live_node_types.length > 0 && ` · live: ${deployment.live_node_types.join(', ')}`}
          </div>

          <pre style={logStyle}>{log.trim() || 'No output captured yet.'}</pre>

          <div className="bn-run-detail-actions">
            {isRunning
              ? <button onClick={onStop} disabled={busy} style={miniButton}>Stop</button>
              : <button onClick={onStart} disabled={busy} style={miniButton}>Start</button>}
            <button onClick={onExport} disabled={busy} style={miniButton} title="Copy the runnable script to a folder Delete never touches">Export .py</button>
            <button onClick={onDelete} disabled={busy} style={miniButton}>Delete</button>
          </div>
        </div>
      )}
    </div>
  )
}

function describeRemoteState(deployment: RemoteDeployment): string {
  switch (deployment.state) {
    case 'staged':
      return 'Ready to run'
    case 'running':
      return 'Running on device'
    case 'stopped':
      return 'Stopped'
    case 'exited':
      return deployment.exit_code == null ? 'Finished' : `Finished (exit ${deployment.exit_code})`
    case 'failed':
      return deployment.exit_code == null ? 'Failed' : `Failed (exit ${deployment.exit_code})`
  }
}

function describeState(deployment: Deployment): string {
  switch (deployment.state) {
    case 'running':
      return deployment.kind === 'service' ? 'Running' : 'Running (one-off)'
    case 'stopped':
      return 'Stopped by you'
    case 'exited':
      return 'Finished'
    case 'failed':
      return deployment.exit_code == null ? 'Failed' : `Failed (exit ${deployment.exit_code})`
    default:
      return deployment.state
  }
}

function formatTime(value: string | null): string {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString()
}

function formatCalibrationTime(value: string): string {
  if (!value) return 'date unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const miniButton: CSSProperties = {
  background: 'var(--lift)',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '2px 8px',
  fontSize: 12,
  fontFamily: 'var(--font-ui)',
  borderRadius: 4,
  cursor: 'pointer',
}

const primaryButton: CSSProperties = {
  ...miniButton,
  background: 'var(--action)',
  borderColor: 'var(--action)',
  color: 'var(--action-ink)',
  fontWeight: 700,
}

const logStyle: CSSProperties = {
  margin: '8px 0 0',
  padding: 8,
  maxHeight: 220,
  overflow: 'auto',
  background: 'var(--panel)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  color: 'var(--tx2)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  lineHeight: 1.5,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}
