import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import {
  api,
  type ComputeDevice,
  type DeviceActionProgress,
  type DeviceInstallProgress,
  type DeviceRuntimeStatus,
  type HardwareDevice,
  type HardwareDeviceStatus,
  type ManagedServiceUpdateCheckResult,
  type ManagedServiceUpdateResult,
  type RemoteRos2Diagnostics,
  type RobotTelemetrySample,
  type SshDeviceProbe,
  type SshRuntimeInspection,
} from '../api'
import { useStore } from '../store'
import { RobotLiveMonitor } from './RobotMonitorNode'

type RobotState = {
  status?: HardwareDeviceStatus
  telemetry?: RobotTelemetrySample
  telemetryError?: string
  error?: string
  loading?: boolean
  checkedAt?: number
}

type DeviceState = {
  runtime?: DeviceRuntimeStatus
  loading?: boolean
  checkedAt?: number
}

type RosHealthState =
  | 'unchecked'
  | 'checking'
  | 'healthy'
  | 'warning'
  | 'error'
  | 'unavailable'

type RosHealth = {
  state: RosHealthState
  checking?: boolean
  summary: string
  issues: string[]
  checkedAt?: number
  diagnostics?: RemoteRos2Diagnostics
}

type DeviceCheckIssue = {
  id: string
  robotId?: string
  title: string
  detail: string
  action: string
}

type ServiceCheckState =
  | 'checking'
  | 'connected'
  | 'awaiting'
  | 'stopped'
  | 'disconnected'
  | 'unknown'
  | 'unreachable'
  | 'unchecked'

type RuntimeInstallAction =
  | 'install'
  | 'reuse'
  | 'replace'
  | 'side_by_side'
  | 'isolated_stack'

const DEFAULT_RUNTIME_URL = 'http://192.168.1.87:8766'
const LOCAL_RUNTIME_URL = 'http://127.0.0.1:8766'
const DEFAULT_SSH_HOST = '192.168.1.87'
const FIRST_HARDWARE_PORT = 8765
const RUNTIME_PORT = 8766

function suggestedHardwareUrl(device: ComputeDevice): string {
  try {
    const runtime = new URL(device.runtime_url)
    const runtimePort = Number(runtime.port || (runtime.protocol === 'https:' ? 443 : 80))
    const usedPorts = new Set(device.robots.flatMap(robot => {
      try {
        const parsed = new URL(robot.base_url)
        return parsed.port ? [Number(parsed.port)] : []
      } catch {
        return []
      }
    }))
    let port = FIRST_HARDWARE_PORT
    while (port === runtimePort || usedPorts.has(port)) port += 1
    const host = runtime.hostname.includes(':') ? `[${runtime.hostname}]` : runtime.hostname
    return `${runtime.protocol}//${host}:${port}`
  } catch {
    return 'http://192.168.1.87:8765'
  }
}

function hardwareUrlError(value: string, runtimeUrl = DEFAULT_RUNTIME_URL): string | null {
  let parsed: URL
  try {
    parsed = new URL(value.trim())
  } catch {
    return 'Enter the complete hardware URL printed by pair.sh.'
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    return 'Hardware URL must start with http:// or https://.'
  }
  if (!parsed.port) {
    return 'Include the hardware service port printed by pair.sh.'
  }
  let runtimePort = RUNTIME_PORT
  try {
    const runtime = new URL(runtimeUrl)
    runtimePort = Number(runtime.port || (runtime.protocol === 'https:' ? 443 : 80))
  } catch {
    // Keep the default runtime port in the validation message.
  }
  if (Number(parsed.port) === runtimePort) {
    return `Port ${runtimePort} is this device runtime. Choose a different robot hardware port.`
  }
  return null
}

function runtimeHostname(runtimeUrl: string): string {
  try {
    return new URL(runtimeUrl).hostname
  } catch {
    return ''
  }
}

function isLocalRuntimeUrl(runtimeUrl: string): boolean {
  try {
    const hostname = new URL(runtimeUrl).hostname.toLowerCase()
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]' || hostname === '::1'
  } catch {
    return false
  }
}

function urlPort(url: string): number | null {
  try {
    const parsed = new URL(url)
    const value = parsed.port || (parsed.protocol === 'https:' ? '443' : '80')
    const port = Number(value)
    return Number.isInteger(port) && port > 0 ? port : null
  } catch {
    return null
  }
}

function formatVersion(value?: string): string {
  const version = value?.trim()
  return version && version !== 'unknown' ? `v${version}` : 'version unavailable'
}

function rosEndpointCount(stdout: string, label: 'Publisher' | 'Subscription'): number | null {
  const match = stdout.match(new RegExp(`${label} count:\\s*(\\d+)`, 'i'))
  return match ? Number(match[1]) : null
}

function rosTopicName(topic: string): string {
  return topic.replace(/\s+\[[^\]]+\]\s*$/, '').trim()
}

function rosTopicType(topic: string): string {
  return topic.match(/\[([^\]]+)\]\s*$/)?.[1] ?? 'type unavailable'
}

function rosTopicEndpointSummary(
  detail: RemoteRos2Diagnostics['topic_details'][number] | undefined,
): string {
  if (!detail) return 'endpoint counts not sampled'
  if (!detail.ok) return detail.error || detail.stderr || 'endpoint inspection failed'
  const publishers = rosEndpointCount(detail.stdout || '', 'Publisher')
  const subscribers = rosEndpointCount(detail.stdout || '', 'Subscription')
  if (publishers === null && subscribers === null) return 'endpoint counts unavailable'
  return `${publishers ?? '?'} publisher${publishers === 1 ? '' : 's'} · ${
    subscribers ?? '?'
  } subscriber${subscribers === 1 ? '' : 's'}`
}

function rosTopicDetail(
  diagnostics: RemoteRos2Diagnostics,
  topic: string,
): RemoteRos2Diagnostics['topic_details'][number] | undefined {
  return diagnostics.topic_details.find(detail => detail.topic === topic)
}

function rosPathCounts(
  diagnostics: RemoteRos2Diagnostics,
  topic: string,
): { publishers: number | null; subscribers: number | null } {
  const detail = rosTopicDetail(diagnostics, topic)
  if (!detail?.ok) return { publishers: null, subscribers: null }
  return {
    publishers: rosEndpointCount(detail.stdout || '', 'Publisher'),
    subscribers: rosEndpointCount(detail.stdout || '', 'Subscription'),
  }
}

function rosNameCounts(names: string[]): Array<[string, number]> {
  const counts = new Map<string, number>()
  names.forEach(name => counts.set(name, (counts.get(name) ?? 0) + 1))
  return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right))
}

function RosRobotPathCard({
  diagnostics,
  role,
}: {
  diagnostics: RemoteRos2Diagnostics
  role: 'leader' | 'follower'
}) {
  const states = rosPathCounts(diagnostics, `/${role}/joint_states`)
  const commands = rosPathCounts(diagnostics, `/${role}/joint_commands`)
  const requiredCounts = role === 'leader'
    ? [states.publishers, states.subscribers]
    : [
        states.publishers,
        states.subscribers,
        commands.publishers,
        commands.subscribers,
      ]
  const countsAvailable = requiredCounts.every(value => value !== null)
  const ready = countsAvailable
    && (states.publishers ?? 0) > 0
    && (states.subscribers ?? 0) > 0
    && (
      role === 'leader'
      || (
        (commands.publishers ?? 0) > 0
        && (commands.subscribers ?? 0) > 0
      )
    )

  return (
    <div className={`bn-ros-robot-path${ready ? ' is-ready' : countsAvailable ? ' is-attention' : ''}`}>
      <div>
        <strong>{role === 'leader' ? 'Leader' : 'Follower'}</strong>
        <span>
          {ready
            ? 'Endpoints present'
            : countsAvailable
              ? 'Missing endpoint'
              : 'Endpoint counts unavailable'}
        </span>
      </div>
      <dl>
        <div>
          <dt>Position feedback</dt>
          <dd>
            {states.publishers ?? '?'} hardware source → {states.subscribers ?? '?'} workflow listener
          </dd>
        </div>
        <div>
          <dt>{role === 'leader' ? 'Motion commands' : 'Joint commands'}</dt>
          <dd>
            {role === 'leader'
              ? 'Read-only by design'
              : `${commands.publishers ?? '?'} workflow source → ${
                  commands.subscribers ?? '?'
                } hardware listener`}
          </dd>
        </div>
      </dl>
    </div>
  )
}

function summarizeRosHealth(
  diagnostics: RemoteRos2Diagnostics,
  expectController: boolean,
): RosHealth {
  if (!diagnostics.available) {
    return {
      state: 'unavailable',
      summary: diagnostics.summary || 'ROS 2 is unavailable.',
      issues: diagnostics.warnings ?? [],
      checking: false,
      checkedAt: Date.now(),
      diagnostics,
    }
  }

  const issues = [...(diagnostics.warnings ?? [])]
  const robotTopics = (diagnostics.topics ?? []).filter(topic => (
    topic.startsWith('/leader/')
    || topic.startsWith('/follower/')
    || topic.startsWith('/blacknode/leader_follower/')
  ))
  if (expectController && robotTopics.length === 0) {
    issues.push('No leader/follower ROS 2 topics are visible to the running deployment.')
  }
  if (expectController) {
    for (const detail of diagnostics.topic_details ?? []) {
      const publishers = rosEndpointCount(detail.stdout || '', 'Publisher')
      const subscribers = rosEndpointCount(detail.stdout || '', 'Subscription')
      if (detail.topic.endsWith('/joint_states') && publishers === 0) {
        issues.push(`${detail.topic} has no publisher.`)
      }
      if (detail.topic.endsWith('/joint_states') && subscribers === 0) {
        issues.push(`${detail.topic} is not reaching the controller.`)
      }
      if (
        detail.topic === '/follower/joint_commands'
        && (publishers === 0 || subscribers === 0)
      ) {
        issues.push('/follower/joint_commands is missing its controller or driver endpoint.')
      }
      if (
        detail.topic.startsWith('/blacknode/leader_follower/')
        && subscribers === 0
      ) {
        issues.push(`${detail.topic} has no armed-state listener.`)
      }
    }
  }

  const uniqueIssues = [...new Set(issues)]
  const state: RosHealthState = !diagnostics.ok || (
    expectController
    && uniqueIssues.some(issue => (
      issue.includes('No leader/follower')
      || issue.includes('no publisher')
      || issue.includes('not reaching')
      || issue.includes('missing its controller')
      || issue.includes('no armed-state listener')
    ))
  )
    ? 'error'
    : uniqueIssues.length
      ? 'warning'
      : 'healthy'
  return {
    state,
    checking: false,
    summary: state === 'healthy'
      ? 'ROS 2 endpoints connected'
      : state === 'warning'
        ? 'ROS 2 is running with warnings'
        : 'ROS 2 needs attention',
    issues: uniqueIssues,
    checkedAt: Date.now(),
    diagnostics,
  }
}

function deploymentForStatus(status?: HardwareDeviceStatus) {
  return status?.deployment_lease ?? status?.running_deployment
}

function diagnoseDeviceMotion(
  device: ComputeDevice,
  statuses: Array<HardwareDeviceStatus | undefined>,
  telemetry: Array<RobotTelemetrySample | undefined>,
  telemetryErrors: Array<string | undefined>,
): DeviceCheckIssue[] {
  const issues: DeviceCheckIssue[] = []
  let motionControllers = 0

  device.robots.forEach((robot, index) => {
    const status = statuses[index]
    const sample = telemetry[index]
    const sampleError = telemetryErrors[index]
    const deployment = deploymentForStatus(status)
    const controlsMotion = Number(deployment?.motion_control_count || 0) > 0
    if (controlsMotion) motionControllers += 1

    if (!status?.connected) {
      issues.push({
        id: `${robot.id}:connection`,
        robotId: robot.id,
        title: `${robot.name} is not connected`,
        detail: status?.error || 'Robot Hardware did not report a live hardware connection.',
        action: 'Check robot power, USB connection, and the configured serial device, then restart Robot Hardware.',
      })
      return
    }
    if (!deployment) {
      issues.push({
        id: `${robot.id}:deployment`,
        robotId: robot.id,
        title: `${robot.name} has no running deployment`,
        detail: 'The hardware service is connected, but no workflow currently controls this robot.',
        action: 'Start the intended deployment for this robot.',
      })
    }
    if (sampleError || !sample) {
      issues.push({
        id: `${robot.id}:telemetry`,
        robotId: robot.id,
        title: `${robot.name} telemetry check failed`,
        detail: sampleError || 'No telemetry sample was returned.',
        action: 'Open Monitor and restart the deployment if live joint data does not appear.',
      })
      return
    }
    if (!sample.available || sample.stale) {
      issues.push({
        id: `${robot.id}:telemetry-stale`,
        robotId: robot.id,
        title: `${robot.name} joint telemetry is not fresh`,
        detail: sample.message || 'The deployment is not producing a current robot-state sample.',
        action: 'Restart the deployment and verify that joint positions update in Monitor.',
      })
    }
    if (!sample.payload?.joints?.length) {
      issues.push({
        id: `${robot.id}:joints`,
        robotId: robot.id,
        title: `${robot.name} has no live joint positions`,
        detail: sample.message || 'The hardware driver returned no joint samples.',
        action: 'Check the serial bus and servo power, then restart Robot Hardware and the deployment.',
      })
    }

    if (!controlsMotion) return
    const driverError = sample.payload?.error?.trim()
    if (driverError) {
      const goalSeedFailure = driverError.match(
        /could not seed Goal_Position for (.+?) \(servo id (\d+)\)/i,
      )
      issues.push({
        id: `${robot.id}:driver`,
        robotId: robot.id,
        title: 'Follower torque could not enable',
        detail: driverError,
        action: goalSeedFailure
          ? `Check power and the bus cable at ${goalSeedFailure[1]} (servo ID ${goalSeedFailure[2]}), then press Arm follower again.`
          : 'Inspect the follower driver error, correct the hardware connection, then press Arm follower again.',
      })
    } else if (deployment?.motion_armed !== true) {
      issues.push({
        id: `${robot.id}:disarmed`,
        robotId: robot.id,
        title: 'Follower motion is disarmed',
        detail: 'The deployment is running but commands are intentionally blocked.',
        action: 'Support both arms, clear the workspace, then press Arm follower.',
      })
    } else if (sample.payload?.torque_enabled !== true) {
      issues.push({
        id: `${robot.id}:torque`,
        robotId: robot.id,
        title: 'Follower is armed but physical torque is off',
        detail: 'The logical arm command did not receive torque confirmation from the follower driver.',
        action: 'Check follower servo power and bus communication, then press Arm follower again.',
      })
    }
  })

  if (
    device.robots.some((_robot, index) => Boolean(deploymentForStatus(statuses[index])))
    && motionControllers === 0
  ) {
    issues.push({
      id: `${device.id}:motion-controller`,
      title: 'No follower motion controller is running',
      detail: 'Running deployments are connected, but none owns a motion-control path.',
      action: 'Start or redeploy the follower workflow that contains the leader-follower controller.',
    })
  }
  return issues
}

export default function DevicesPanel() {
  const activeProject = useStore(state => state.activeProject)
  const setActiveProject = useStore(state => state.setActiveProject)
  const openGraphAsTab = useStore(state => state.openGraphAsTab)
  const [devices, setDevices] = useState<ComputeDevice[]>([])
  const [deviceStates, setDeviceStates] = useState<Record<string, DeviceState>>({})
  const [robotStates, setRobotStates] = useState<Record<string, RobotState>>({})
  const [rosHealthByDevice, setRosHealthByDevice] = useState<Record<string, RosHealth>>({})
  const [checkIssuesByDevice, setCheckIssuesByDevice] = useState<
    Record<string, DeviceCheckIssue[]>
  >({})
  const [knownHardwareVersions, setKnownHardwareVersions] = useState<Record<string, string>>({})
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  const [showDeviceForm, setShowDeviceForm] = useState(false)
  const [setupMode, setSetupMode] = useState<'local' | 'automatic' | 'manual'>('local')
  const [deviceName, setDeviceName] = useState('Local computer')
  const [localInstallDir, setLocalInstallDir] = useState('')
  const [runtimeUrl, setRuntimeUrl] = useState(LOCAL_RUNTIME_URL)
  const [runtimeToken, setRuntimeToken] = useState('')
  const [sshHost, setSshHost] = useState(DEFAULT_SSH_HOST)
  const [sshPort, setSshPort] = useState(22)
  const [sshUsername, setSshUsername] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [sshProbe, setSshProbe] = useState<SshDeviceProbe | null>(null)
  const [sshInspection, setSshInspection] = useState<SshRuntimeInspection | null>(null)
  const [installAction, setInstallAction] = useState<RuntimeInstallAction>('install')
  const [installInstanceId, setInstallInstanceId] = useState('default')
  const [installProgress, setInstallProgress] = useState<DeviceInstallProgress | null>(null)
  const [actionProgress, setActionProgress] = useState<Record<string, DeviceActionProgress>>({})
  const [showRuntimeControl, setShowRuntimeControl] = useState(false)
  const [runtimeControlPassword, setRuntimeControlPassword] = useState('')
  const [showUpdateForm, setShowUpdateForm] = useState(false)
  const [showSoftwareDetails, setShowSoftwareDetails] = useState(false)
  const [showServiceDetails, setShowServiceDetails] = useState(false)
  const [showRosDetails, setShowRosDetails] = useState(false)
  const [showDeviceManagement, setShowDeviceManagement] = useState(false)
  const [updatePassword, setUpdatePassword] = useState('')
  const [updateCheckReport, setUpdateCheckReport] = useState<ManagedServiceUpdateCheckResult | null>(null)
  const [updateReport, setUpdateReport] = useState<ManagedServiceUpdateResult | null>(null)
  const [showDirtySourceHelp, setShowDirtySourceHelp] = useState(false)
  const showLegacyPackageManager = false as boolean
  const [showUninstallForm, setShowUninstallForm] = useState(false)
  const [uninstallPassword, setUninstallPassword] = useState('')
  const [showSshManagement, setShowSshManagement] = useState(false)
  const [managementHost, setManagementHost] = useState('')
  const [managementPort, setManagementPort] = useState(22)
  const [managementUsername, setManagementUsername] = useState('')
  const [managementPassword, setManagementPassword] = useState('')
  const [managementProbe, setManagementProbe] = useState<SshDeviceProbe | null>(null)
  const [showRobotForm, setShowRobotForm] = useState(false)
  const [robotName, setRobotName] = useState('')
  const [robotUrl, setRobotUrl] = useState('')
  const [robotToken, setRobotToken] = useState('')
  const [robotDiscoveryPassword, setRobotDiscoveryPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [linkedProjectName, setLinkedProjectName] = useState('')
  const rosChecksInFlight = useRef(new Set<string>())

  const selectedDevice = devices.find(device => device.id === selectedDeviceId) ?? null
  const selectedRosHealth = selectedDevice
    ? rosHealthByDevice[selectedDevice.id]
    : undefined
  const selectedCheckIssues = selectedDevice
    ? checkIssuesByDevice[selectedDevice.id] ?? []
    : []
  const selectedDeviceIsLocal = Boolean(
    selectedDevice && isLocalRuntimeUrl(selectedDevice.runtime_url),
  )
  const selectedDeviceManagedLocally = (
    selectedDevice?.managed_runtime?.management_mode === 'local'
  )
  const selectedStackIsIsolated = (
    selectedDevice?.managed_runtime?.stack_mode === 'isolated'
  )
  const selectedDeviceState = selectedDevice
    ? deviceStates[selectedDevice.id]
    : undefined
  const selectedRobotChecks = selectedDevice
    ? selectedDevice.robots.map(robot => ({
      robot,
      state: robotStates[robot.id],
    }))
    : []
  const selectedRunningDeployments = selectedRobotChecks.flatMap(({ state }) => {
    const deployment = state?.status?.deployment_lease
      ?? state?.status?.running_deployment
    return deployment ? [deployment] : []
  })
  const selectedMotionControllers = selectedRunningDeployments.filter(
    deployment => Number(deployment.motion_control_count || 0) > 0,
  )
  const selectedArmedMotionControllers = selectedMotionControllers.filter(
    deployment => deployment.motion_armed === true,
  )
  const selectedMotionDisarmed = (
    selectedMotionControllers.length > selectedArmedMotionControllers.length
  )
  const selectedHardwareSiblingDevices = (
    selectedDevice?.managed_runtime
    && !selectedDeviceManagedLocally
    && !selectedStackIsIsolated
  )
    ? devices.filter(device => {
      const selectedManagement = selectedDevice.managed_runtime
      const candidateManagement = device.managed_runtime
      if (
        !selectedManagement
        || !candidateManagement
        || candidateManagement.stack_mode === 'isolated'
      ) return false
      return (
        device.id !== selectedDevice.id
        && device.robots.length > 0
        && candidateManagement.ssh_host === selectedManagement.ssh_host
        && candidateManagement.ssh_port === selectedManagement.ssh_port
        && candidateManagement.ssh_username === selectedManagement.ssh_username
        && candidateManagement.host_fingerprint === selectedManagement.host_fingerprint
      )
    })
    : []
  const selectedDeviceChecking = Boolean(
    selectedDeviceState?.loading
    || selectedRobotChecks.some(item => item.state?.loading),
  )
  const selectedManagedHardwareInstalled = Boolean(
    selectedDevice?.managed_runtime?.hardware_dir,
  )
  const selectedManagedHardwareReady = (
    !selectedManagedHardwareInstalled
    || selectedDeviceState?.runtime?.hardware?.ok === true
  )
  const selectedHardwareReady = selectedRobotChecks.every(item => Boolean(
    item.state?.status
    && !item.state.error
    && item.state.status.connected,
  ))
  const selectedDeviceReady = Boolean(
    selectedDeviceState?.runtime?.ok
    && selectedManagedHardwareReady
    && selectedHardwareReady,
  )
  const selectedRuntimeVersionValue = (
    selectedDeviceState?.runtime?.manifest?.runtime_version
    || selectedDeviceState?.runtime?.installed_version
  )
  const selectedRuntimeVersion = (
    selectedRuntimeVersionValue
    && selectedRuntimeVersionValue !== 'unknown'
  )
    ? `v${selectedRuntimeVersionValue}`
    : 'version not reported'
  const selectedWorkflowPackages = (
    selectedDeviceState?.runtime?.manifest?.packages ?? []
  ).filter(item => (
    item.name.startsWith('blacknode-')
    && !['blacknode-runtime', 'blacknode-hardware'].includes(item.name)
  ))
  const selectedHardwareVersion = (
    selectedDeviceState?.runtime?.hardware?.status?.software_version
    || selectedDeviceState?.runtime?.hardware?.installed_version
    || selectedRobotChecks.find(item => item.state?.status?.software_version)
      ?.state?.status?.software_version
    || selectedDevice?.robots.find(robot => robot.software_version)?.software_version
  )
  const selectedHardwareVersionLabel = selectedHardwareVersion
    ? `v${selectedHardwareVersion}`
    : 'version not reported'
  const selectedHardwarePackageState = selectedDeviceState?.loading
    ? 'checking'
    : selectedDeviceManagedLocally
      ? selectedDeviceState?.runtime?.hardware?.state || 'unchecked'
      : selectedDevice?.managed_runtime?.hardware_state === 'stopped'
        ? 'stopped'
      : selectedDevice?.managed_runtime?.hardware_state === 'running'
        ? 'running'
      : selectedRobotChecks.some(item => item.state?.loading)
        ? 'checking'
        : selectedRobotChecks.some(item => item.state?.error)
          ? 'unreachable'
          : selectedRobotChecks.some(item => item.state?.status)
            ? 'running'
            : selectedDevice?.robots.length
              ? 'unchecked'
              : 'unavailable'
  const selectedRuntimePackageState = selectedDeviceState?.loading
    ? 'checking'
    : selectedDeviceState?.runtime?.state
      || (selectedDeviceState?.runtime?.paused || selectedDevice?.paused
        ? 'stopped'
        : selectedDeviceState?.runtime?.ok === true
          ? 'running'
          : selectedDeviceState?.runtime
            ? 'unreachable'
            : 'unchecked')
  const selectedAttachedHardwareServiceFailed = selectedRobotChecks.some(item => (
    Boolean(item.state?.error)
    || Boolean(item.state?.checkedAt && !item.state?.status)
  ))
  const selectedPackageCheckState: ServiceCheckState = selectedDeviceState?.loading
    ? 'checking'
    : selectedDeviceState?.runtime?.state === 'stopped'
      ? 'stopped'
    : selectedDeviceState?.runtime?.ok !== true
      ? selectedDeviceState?.runtime
        ? 'unreachable'
        : 'unchecked'
      : selectedManagedHardwareInstalled
        && selectedDeviceState.runtime.hardware?.state === 'stopped'
        ? 'stopped'
        : selectedManagedHardwareInstalled
        && selectedDeviceState.runtime.hardware?.ok !== true
        ? 'unreachable'
        : selectedAttachedHardwareServiceFailed
          ? 'unreachable'
          : 'connected'
  const selectedPackageCheckDetail = selectedDeviceState?.loading
    ? 'Checking Runtime and Hardware package services'
    : selectedDeviceState?.runtime?.state === 'stopped'
      ? `Runtime ${selectedRuntimeVersion} · service stopped · Hardware ${selectedHardwareVersionLabel}`
    : selectedDeviceState?.runtime?.ok !== true
      ? `Runtime service unreachable${
          selectedDeviceState?.runtime?.error
            ? ` · ${selectedDeviceState.runtime.error}`
            : ''
        }`
      : selectedManagedHardwareInstalled
        && selectedDeviceState.runtime.hardware?.state === 'stopped'
        ? `Runtime ${selectedRuntimeVersion} · Hardware ${selectedHardwareVersionLabel} · service stopped`
        : selectedManagedHardwareInstalled
        && selectedDeviceState.runtime.hardware?.ok !== true
        ? `Runtime ${selectedRuntimeVersion} · Hardware service unreachable${
            selectedDeviceState.runtime.hardware?.error
              ? ` · ${selectedDeviceState.runtime.hardware.error}`
              : ''
          }`
        : selectedAttachedHardwareServiceFailed
          ? `Runtime ${selectedRuntimeVersion} · Hardware service unreachable`
          : `Runtime ${selectedRuntimeVersion} · Hardware ${selectedHardwareVersionLabel}`
  const selectedServiceChecks: Array<{
    id: string
    name: string
    kind: 'Software package' | 'Robot hardware'
    state: ServiceCheckState
    detail: string
  }> = selectedDevice
    ? [
      {
        id: `packages:${selectedDevice.id}`,
        name: 'Software packages',
        kind: 'Software package',
        state: selectedPackageCheckState,
        detail: selectedPackageCheckDetail,
      },
      ...selectedRobotChecks.map(({ robot, state }) => {
        const checkState: ServiceCheckState = state?.loading
          ? 'checking'
          : state?.error || (!state?.status && state?.checkedAt)
            ? 'unreachable'
            : state?.status?.connected
              ? 'connected'
              : state?.status
                ? 'disconnected'
                : 'unchecked'
        const version = state?.status?.software_version
          ? `v${state.status.software_version}`
          : robot.software_version
            ? `v${robot.software_version} (last verified)`
            : 'version not reported'
        const detail = checkState === 'checking'
          ? `Contacting ${robot.base_url}`
          : checkState === 'connected'
            ? `Robot Hardware ${version}`
            : checkState === 'disconnected'
              ? state?.status?.error || `Robot Hardware ${version} · hardware provider reports disconnected`
              : checkState === 'unreachable'
                  ? state?.error || 'Robot Hardware service is unreachable.'
                  : 'Robot Hardware has not been checked yet.'
        return {
          id: `robot:${robot.id}`,
          name: robot.name,
          kind: 'Robot hardware' as const,
          state: checkState,
          detail,
        }
      }),
    ]
    : []
  const selectedCheckStarted = selectedServiceChecks.some(
    service => service.state !== 'unchecked',
  )
  const selectedCheckHasFailure = selectedServiceChecks.some(
    service => service.state === 'disconnected' || service.state === 'unreachable',
  )
  const selectedCheckHasStopped = selectedServiceChecks.some(
    service => service.state === 'stopped',
  )
  const selectedCheckHasUnknown = selectedServiceChecks.some(
    service => service.state === 'unknown',
  )
  const selectedReadyChecks = selectedServiceChecks.filter(
    service => service.state === 'connected' || service.state === 'awaiting',
  ).length
  const selectedLastChecked = Math.max(
    selectedDeviceState?.checkedAt ?? 0,
    ...selectedRobotChecks.map(item => item.state?.checkedAt ?? 0),
  )
  const checkedSoftwareComponents = updateCheckReport?.check.components ?? []
  const checkedHardwareComponents = checkedSoftwareComponents.filter(
    component => component.kind === 'hardware',
  )
  const checkedHardwareNeedsRepair = checkedHardwareComponents.some(component => (
    Boolean(component.error)
    || component.installed.version === 'unknown'
    || component.latest.version === 'unknown'
  ))
  const checkedHardwareHasUpdate = checkedHardwareComponents.some(
    component => component.update_available,
  )
  const checkedHardwareIsDirty = checkedHardwareComponents.some(
    component => component.dirty,
  )
  const checkedRuntimeComponents = checkedSoftwareComponents.filter(
    component => component.kind === 'runtime',
  )
  const checkedRuntimeInstallation = checkedRuntimeComponents.find(component => (
    component.installed.version !== 'unknown'
    && component.latest.version !== 'unknown'
  )) ?? checkedRuntimeComponents[0]
  const checkedHardwareInstallation = checkedHardwareComponents.find(component => (
    component.installed.version !== 'unknown'
    && component.latest.version !== 'unknown'
  )) ?? checkedHardwareComponents[0]
  const runtimeCurrentVersion = (
    checkedRuntimeInstallation?.installed.version
    && checkedRuntimeInstallation.installed.version !== 'unknown'
  )
    ? `v${checkedRuntimeInstallation.installed.version}`
    : selectedRuntimeVersion
  const runtimeLatestVersion = (
    checkedRuntimeInstallation?.latest.version
    && checkedRuntimeInstallation.latest.version !== 'unknown'
  )
    ? `v${checkedRuntimeInstallation.latest.version}`
    : null
  const hardwareCurrentVersion = (
    checkedHardwareInstallation?.installed.version
    && checkedHardwareInstallation.installed.version !== 'unknown'
  )
    ? `v${checkedHardwareInstallation.installed.version}`
    : selectedHardwareVersionLabel
  const hardwareLatestVersion = (
    checkedHardwareInstallation?.latest.version
    && checkedHardwareInstallation.latest.version !== 'unknown'
  )
    ? `v${checkedHardwareInstallation.latest.version}`
    : null
  const remoteHardwareServices = selectedDevice?.robots
    .map(robot => `${robot.name}: ${robot.base_url}`)
    .join('\n') || ''
  const updatedSoftwareComponents = updateReport?.update.components ?? []
  const updatedRuntimeComponents = updatedSoftwareComponents.filter(
    component => component.kind === 'runtime',
  )
  const updatedHardwareComponents = updatedSoftwareComponents.filter(
    component => component.kind === 'hardware',
  )
  const updatedHardwareInstallation = updatedHardwareComponents[0]
  const robotNameForPort = (port: number): string => (
    selectedDevice?.robots.find(robot => urlPort(robot.base_url) === port)?.name
    ?? `Robot on port ${port}`
  )
  const installedHardwareVersionForPort = (port: number | null): string => {
    if (port == null) return ''
    const checked = updateCheckReport?.check.components.find(component => (
      component.kind === 'hardware' && component.port === port
    ))
    if (checked?.installed.version && checked.installed.version !== 'unknown') {
      return checked.installed.version
    }
    const updated = updateReport?.update.components.find(component => (
      component.kind === 'hardware' && component.port === port
    ))
    if (updated?.after.version && updated.after.version !== 'unknown') {
      return updated.after.version
    }
    const robot = selectedDevice?.robots.find(
      item => urlPort(item.base_url) === port,
    )
    return robot
      ? knownHardwareVersions[robot.id] ?? robot.software_version ?? ''
      : ''
  }

  const refreshRobot = async (robot: HardwareDevice) => {
    setRobotStates(previous => ({
      ...previous,
      [robot.id]: { ...previous[robot.id], loading: true },
    }))
    try {
      const status = await api.deviceStatus(robot.id)
      const reportedVersion = status.software_version
      if (reportedVersion) {
        setKnownHardwareVersions(previous => ({
          ...previous,
          [robot.id]: reportedVersion,
        }))
      }
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: { status, loading: false, checkedAt: Date.now() },
      }))
      return status
    } catch (reason) {
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: {
          loading: false,
          checkedAt: Date.now(),
          error: reason instanceof Error ? reason.message : String(reason),
        },
      }))
      return undefined
    }
  }

  const checkRobotTelemetry = async (robot: HardwareDevice) => {
    try {
      const telemetry = await api.deviceMonitor(robot.id)
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: {
          ...previous[robot.id],
          telemetry,
          telemetryError: undefined,
        },
      }))
      return { telemetry, error: undefined }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: {
          ...previous[robot.id],
          telemetry: undefined,
          telemetryError: message,
        },
      }))
      return { telemetry: undefined, error: message }
    }
  }

  const checkRosHealth = async (
    device: ComputeDevice,
    expectController = device.robots.some(robot => Boolean(
      robotStates[robot.id]?.status?.deployment_lease
      || robotStates[robot.id]?.status?.running_deployment,
    )),
    reportProgress = true,
  ) => {
    if (device.robots.length === 0 || rosChecksInFlight.current.has(device.id)) {
      return undefined
    }
    rosChecksInFlight.current.add(device.id)
    if (reportProgress) {
      setActionProgress(previous => ({
        ...previous,
        [device.id]: {
          progress: 10,
          message: 'Checking live ROS 2 endpoints',
        },
      }))
    }
    setRosHealthByDevice(previous => ({
      ...previous,
      [device.id]: {
        ...previous[device.id],
        state: previous[device.id]?.state ?? 'checking',
        checking: true,
        summary: previous[device.id]?.summary ?? 'Checking ROS 2 graph…',
        issues: previous[device.id]?.issues ?? [],
      },
    }))
    try {
      const diagnostics = await api.remoteRos2Diagnostics(device.robots[0].id)
      const health = summarizeRosHealth(diagnostics, expectController)
      setRosHealthByDevice(previous => ({
        ...previous,
        [device.id]: health,
      }))
      if (reportProgress) {
        setActionProgress(previous => ({
          ...previous,
          [device.id]: {
            progress: 100,
            message: `${health.summary} · check complete`,
          },
        }))
      }
      return health
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setRosHealthByDevice(previous => ({
        ...previous,
        [device.id]: {
          state: 'error',
          checking: false,
          summary: 'ROS 2 diagnostics failed',
          issues: [message],
          checkedAt: Date.now(),
        },
      }))
      if (reportProgress) {
        setActionProgress(previous => ({
          ...previous,
          [device.id]: {
            progress: 0,
            message: `ROS 2 check failed: ${message}`,
          },
        }))
      }
      return undefined
    } finally {
      rosChecksInFlight.current.delete(device.id)
    }
  }

  const refreshDevice = async (device: ComputeDevice) => {
    setDeviceStates(previous => ({
      ...previous,
      [device.id]: { ...previous[device.id], loading: true },
    }))
    try {
      const runtime = await api.computeDeviceRuntimeStatus(device.id)
      setDeviceStates(previous => ({
        ...previous,
        [device.id]: { runtime, loading: false, checkedAt: Date.now() },
      }))
    } catch (reason) {
      setDeviceStates(previous => ({
        ...previous,
        [device.id]: {
          runtime: {
            ok: false,
            runtime_url: device.runtime_url,
            error: reason instanceof Error ? reason.message : String(reason),
          },
          loading: false,
          checkedAt: Date.now(),
        },
      }))
    }
  }

  const refresh = async () => {
    setError(null)
    try {
      const result = await api.listComputeDevices()
      setDevices(result.devices)
      setSelectedDeviceId(current => (
        current && result.devices.some(device => device.id === current)
          ? current
          : null
      ))
      await Promise.all(result.devices.map(async device => {
        await Promise.all([
          refreshDevice(device),
          Promise.all(device.robots.map(refreshRobot)),
        ])
      }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  useEffect(() => {
    if (!showDeviceForm || setupMode !== 'local' || localInstallDir) return
    void api.localComputeDeviceInstallDefaults()
      .then(result => setLocalInstallDir(result.install_dir))
      .catch(reason => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [showDeviceForm, setupMode, localInstallDir])

  useEffect(() => {
    const timers = Object.entries(actionProgress).flatMap(([id, value]) => {
      const failed = (
        value.progress <= 0
        && value.message.toLowerCase().includes('failed')
      )
      if (value.progress < 100 && !failed) return []
      return [window.setTimeout(() => {
        setActionProgress(previous => {
          if (previous[id] !== value) return previous
          const next = { ...previous }
          delete next[id]
          return next
        })
      }, failed ? 10000 : 3500)]
    })
    return () => timers.forEach(timer => window.clearTimeout(timer))
  }, [actionProgress])

  const resetDeviceForm = () => {
    setShowDeviceForm(false)
    setSetupMode('local')
    setDeviceName('Local computer')
    setRuntimeUrl(LOCAL_RUNTIME_URL)
    setRuntimeToken('')
    setSshPassword('')
    setSshProbe(null)
    setSshInspection(null)
    setInstallAction('install')
    setInstallInstanceId('default')
    setInstallProgress(null)
  }

  const selectSetupMode = (mode: 'local' | 'automatic' | 'manual') => {
    const previousMode = setupMode
    setSetupMode(mode)
    setError(null)
    setInstallProgress(null)
    if (mode === 'local') {
      setRuntimeUrl(LOCAL_RUNTIME_URL)
      if (!deviceName.trim() || deviceName === 'Local computer') {
        setDeviceName('Local computer')
      }
      return
    }
    if (previousMode === 'local') {
      if (runtimeUrl === LOCAL_RUNTIME_URL) setRuntimeUrl(DEFAULT_RUNTIME_URL)
      if (deviceName === 'Local computer') setDeviceName('')
    }
  }

  const manualPair = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result = await api.pairComputeDevice(
        deviceName.trim(),
        runtimeUrl.trim(),
        runtimeToken.trim(),
      )
      resetDeviceForm()
      setSelectedDeviceId(result.device.id)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const browseLocalInstallDir = async () => {
    setError(null)
    try {
      const result = await api.pickDirectory(
        localInstallDir,
        'Choose the Blacknode local stack installation folder',
      )
      if (!result.cancelled && result.selected) setLocalInstallDir(result.selected)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const installLocalComputer = async (event: FormEvent) => {
    event.preventDefault()
    if (!localInstallDir.trim()) {
      setError('Choose the local stack installation folder.')
      return
    }
    setBusy(true)
    setError(null)
    setInstallProgress({ progress: 1, message: 'Starting local robot stack installation' })
    try {
      const result = await api.installLocalComputeDevice(
        deviceName.trim() || 'Local computer',
        localInstallDir.trim(),
        setInstallProgress,
      )
      resetDeviceForm()
      setSelectedDeviceId(result.device.id)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const probeSsh = async () => {
    setBusy(true)
    setError(null)
    setSshProbe(null)
    setSshInspection(null)
    try {
      setSshProbe(await api.probeComputeDeviceSsh(
        sshHost.trim(),
        sshPort,
      ))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const automaticInstall = async (event: FormEvent) => {
    event.preventDefault()
    if (!sshProbe) {
      await probeSsh()
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (!sshInspection) {
        setInstallProgress(null)
        const inspection = await api.inspectComputeDeviceSsh(
          sshHost.trim(),
          sshPort,
          sshUsername.trim(),
          sshPassword,
          sshProbe.host_fingerprint,
        )
        setSshInspection(inspection)
        const reusable = inspection.instances.find(instance => instance.healthy)
        if (reusable) {
          setInstallAction('reuse')
          setInstallInstanceId(reusable.instance_id)
        } else if (inspection.instances.length) {
          setInstallAction('replace')
          setInstallInstanceId(inspection.instances[0].instance_id)
        } else {
          setInstallAction('install')
          setInstallInstanceId('default')
        }
        return
      }
      setInstallProgress({ progress: 1, message: 'Starting secure installation' })
      const result = await api.installComputeDevice(
        deviceName.trim(),
        sshHost.trim(),
        sshPort,
        sshUsername.trim(),
        sshPassword,
        sshProbe.host_fingerprint,
        installAction,
        installInstanceId,
        setInstallProgress,
      )
      resetDeviceForm()
      setSelectedDeviceId(result.device.id)
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      if (
        message.toLowerCase().includes('authentication failed')
        || message.toLowerCase().includes('ssh login was rejected')
      ) {
        setSshInspection(null)
        setInstallProgress(null)
        setError(
          `${message} The confirmed host key is still valid; correct the login and press Confirm and inspect again.`,
        )
      } else {
        setError(message)
      }
    } finally {
      setBusy(false)
    }
  }

  const openRobotForm = (device: ComputeDevice) => {
    setSelectedDeviceId(device.id)
    setRobotName('')
    setRobotUrl(suggestedHardwareUrl(device))
    setRobotToken('')
    setRobotDiscoveryPassword('')
    setError(null)
    setShowRobotForm(true)
  }

  const discoverAndAttachRobots = async () => {
    if (!selectedDevice) return
    if (!robotDiscoveryPassword) {
      setError('Enter the device SSH password to find installed robots.')
      return
    }
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [selectedDevice.id]: {
        progress: 10,
        message: 'Finding installed Robot Hardware services over verified SSH',
      },
    }))
    try {
      const result = await api.discoverAndPairRobots(
        selectedDevice.id,
        robotDiscoveryPassword,
      )
      setRobotDiscoveryPassword('')
      setShowRobotForm(false)
      setRobotToken('')
      setRobotStates(previous => {
        const next = { ...previous }
        result.robots.forEach(robot => {
          next[robot.id] = {
            status: result.statuses[robot.id],
            loading: false,
            checkedAt: Date.now(),
          }
        })
        return next
      })
      setActionProgress(previous => ({
        ...previous,
        [selectedDevice.id]: {
          progress: 100,
          message: result.errors.length
            ? `${result.summary} ${result.errors.join(' ')}`
            : result.summary,
        },
      }))
      await refresh()
      if (activeProject) {
        const discoveredIds = result.robots.map(robot => robot.id)
        const nextDeviceIds = Array.from(new Set([
          ...activeProject.deviceIds,
          ...discoveredIds,
        ]))
        if (nextDeviceIds.length !== activeProject.deviceIds.length) {
          try {
            const project = await api.updateProject(activeProject.id, {
              device_ids: nextDeviceIds,
            })
            setActiveProject({
              id: project.id,
              name: project.name,
              workflowSlugs: project.workflow_slugs,
              deviceIds: project.device_ids,
            })
            setLinkedProjectName(project.name)
          } catch (projectError) {
            setError(
              `The robots were attached, but they could not be linked to “${activeProject.name}”: ${
                projectError instanceof Error ? projectError.message : String(projectError)
              }`,
            )
          }
        }
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [selectedDevice.id]: {
          progress: 0,
          message: `Robot discovery failed: ${message}`,
        },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const installDeviceHardware = async () => {
    if (!selectedDevice) return
    if (!robotDiscoveryPassword) {
      setError('Enter the device SSH password to install Robot Hardware.')
      return
    }
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [selectedDevice.id]: {
        progress: 5,
        message: 'Preparing the managed Robot Hardware package',
      },
    }))
    try {
      const result = await api.installComputeDeviceHardware(
        selectedDevice.id,
        robotDiscoveryPassword,
        progress => setActionProgress(previous => ({
          ...previous,
          [selectedDevice.id]: progress,
        })),
      )
      setRobotDiscoveryPassword('')
      setActionProgress(previous => ({
        ...previous,
        [selectedDevice.id]: {
          progress: 100,
          message: result.summary,
        },
      }))
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [selectedDevice.id]: {
          progress: 0,
          message: `Robot Hardware installation failed: ${message}`,
        },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const addRobot = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedDevice) return
    const urlError = hardwareUrlError(robotUrl, selectedDevice.runtime_url)
    if (urlError) {
      setError(urlError)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api.pairRobot(
        selectedDevice.id,
        robotName.trim(),
        robotUrl.trim(),
        robotToken.trim(),
      )
      setShowRobotForm(false)
      setRobotToken('')
      setRobotStates(previous => ({
        ...previous,
        [result.robot.id]: {
          status: result.status,
          loading: false,
          checkedAt: Date.now(),
        },
      }))
      await refresh()
      if (activeProject && !activeProject.deviceIds.includes(result.robot.id)) {
        try {
          const project = await api.updateProject(activeProject.id, {
            device_ids: [...activeProject.deviceIds, result.robot.id],
          })
          setActiveProject({
            id: project.id,
            name: project.name,
            workflowSlugs: project.workflow_slugs,
            deviceIds: project.device_ids,
          })
          setLinkedProjectName(project.name)
        } catch (projectError) {
          setError(
            `The robot was added, but it could not be linked to “${activeProject.name}”: ${
              projectError instanceof Error ? projectError.message : String(projectError)
            }`,
          )
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const renameDevice = async (device: ComputeDevice) => {
    const nextName = window.prompt('Name this device', device.name)
    if (nextName === null || nextName.trim() === device.name) return
    setBusy(true)
    setError(null)
    try {
      await api.renameComputeDevice(device.id, nextName.trim())
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const removeDevice = async (device: ComputeDevice) => {
    if (device.robots.length) {
      setError('Remove the robots from this device first. Saved deployment targets stay intact until you choose to remove them.')
      return
    }
    if (!window.confirm(
      `Forget "${device.name}"? This removes only Blacknode's saved connection. Runtime and Hardware stay installed and running on the computer.`,
    )) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteComputeDevice(device.id)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const uninstallDevice = async (device: ComputeDevice) => {
    const managedLocally = device.managed_runtime?.management_mode === 'local'
    if (!managedLocally && !uninstallPassword) {
      setError('Enter the SSH password to delete this managed installation.')
      return
    }
    if (!window.confirm(
      managedLocally
        ? device.managed_runtime?.hardware_dir
          ? device.managed_runtime?.owned_install && device.managed_runtime?.hardware_owned_install
            ? `Delete and uninstall "${device.name}" from this computer? This stops Runtime and Robot Hardware, permanently deletes both editor-created installation folders and attached robot registrations, and removes this device card.`
            : `Uninstall "${device.name}" from this computer? This stops Runtime and Robot Hardware, removes their editor-managed configuration and attached robot registrations, preserves existing source checkouts, and removes this device card.`
          : device.managed_runtime?.owned_install
            ? `Delete and uninstall "${device.name}" from this computer? This stops its Runtime, permanently deletes the editor-created installation folder and attached robot registrations, and removes this device card.`
            : `Uninstall "${device.name}" from this computer? This stops its Runtime, removes its editor-managed configuration and attached robot registrations, preserves the existing source checkout, and removes this device card.`
        : `Delete device "${device.name}" from the remote computer? This stops its Runtime and deployments, then permanently deletes its Runtime files, workflow packages, token, service, firewall rule, attached Robot Hardware services and unused Hardware files, robot registrations, and this device card. System ROS 2, Docker, and other device stacks are preserved.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 1,
        message: 'Starting managed installation deletion',
      },
    }))
    try {
      const result = await api.uninstallComputeDevice(
        device.id,
        uninstallPassword,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 100, message: result.summary },
      }))
      setShowUninstallForm(false)
      setUninstallPassword('')
      setSelectedDeviceId(null)
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `Delete failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const checkDevice = async (device: ComputeDevice) => {
    setShowUpdateForm(false)
    setUpdatePassword('')
    setUpdateReport(null)
    setBusy(true)
    setError(null)
    setCheckIssuesByDevice(previous => ({
      ...previous,
      [device.id]: [],
    }))
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 10,
        message: 'Checking Runtime and robot services',
      },
    }))
    try {
      const [, statuses] = await Promise.all([
        refreshDevice(device),
        Promise.all(device.robots.map(refreshRobot)),
      ])
      setActionProgress(previous => ({
        ...previous,
        [device.id]: {
          progress: 45,
          message: 'Checking live joint telemetry and physical torque',
        },
      }))
      const telemetryResults = await Promise.all(
        device.robots.map(checkRobotTelemetry),
      )
      const motionIssues = diagnoseDeviceMotion(
        device,
        statuses,
        telemetryResults.map(result => result.telemetry),
        telemetryResults.map(result => result.error),
      )
      setCheckIssuesByDevice(previous => ({
        ...previous,
        [device.id]: motionIssues,
      }))
      setActionProgress(previous => ({
        ...previous,
        [device.id]: {
          progress: 75,
          message: 'Checking ROS 2 endpoints and motion path',
        },
      }))
      const rosHealth = await checkRosHealth(device, statuses.some(status => Boolean(
        status?.deployment_lease || status?.running_deployment,
      )), false)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: {
          progress: rosHealth ? 100 : 0,
          message: rosHealth
            ? motionIssues.length
              ? `Device check found ${motionIssues.length} motion blocker${
                motionIssues.length === 1 ? '' : 's'
              }`
              : 'Device check complete · no motion blockers found'
            : 'Device check failed: ROS 2 diagnostics did not complete',
        },
      }))
    } finally {
      setBusy(false)
    }
  }

  const openSshManagement = (device: ComputeDevice) => {
    setShowSshManagement(current => !current)
    setShowRuntimeControl(false)
    setShowUninstallForm(false)
    setManagementHost(runtimeHostname(device.runtime_url))
    setManagementPort(22)
    setManagementUsername('')
    setManagementPassword('')
    setManagementProbe(null)
    setError(null)
  }

  const configureSshManagement = async (
    event: FormEvent,
    device: ComputeDevice,
  ) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (!managementProbe) {
        const probe = await api.probeComputeDeviceSsh(
          managementHost.trim(),
          managementPort,
        )
        setManagementProbe(probe)
        return
      }
      const result = await api.configureComputeDeviceSsh(
        device.id,
        managementHost.trim(),
        managementPort,
        managementUsername.trim(),
        managementPassword,
        managementProbe.host_fingerprint,
      )
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 100, message: result.summary },
      }))
      setShowSshManagement(false)
      setManagementPassword('')
      setManagementProbe(null)
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      if (
        message.toLowerCase().includes('authentication failed')
        || message.toLowerCase().includes('ssh login was rejected')
      ) {
        setManagementPassword('')
      }
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const controlDevice = async (
    device: ComputeDevice,
    action: 'pause' | 'resume',
    passwordOverride?: string,
  ) => {
    const managedLocally = device.managed_runtime?.management_mode === 'local'
    const password = passwordOverride ?? runtimeControlPassword
    if (!managedLocally && !password) {
      setError(`Enter the SSH password to ${action} this managed device.`)
      return
    }
    if (action === 'pause' && !window.confirm(
      `Pause "${device.name}"? Running deployments will stop, attached robots will be stopped and disarmed, and the runtime service will stop.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 1,
        message: action === 'pause' ? 'Starting device pause' : 'Starting device restore',
      },
    }))
    try {
      const result = await api.controlComputeDevice(
        device.id,
        action,
        managedLocally ? '' : password,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setActionProgress(previous => ({
        ...previous,
        [device.id]: {
          progress: 100,
          message: result.warnings.length
            ? `${result.summary} ${result.warnings.join(' ')}`
            : result.summary,
        },
      }))
      setShowRuntimeControl(false)
      setRuntimeControlPassword('')
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `Device action failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const updateDevice = async (
    device: ComputeDevice,
    scope: 'all' | 'runtime' | 'hardware',
    requestedOperation: 'update' | 'reinstall' | null = null,
  ) => {
    const managedLocally = device.managed_runtime?.management_mode === 'local'
    if (!managedLocally && !updatePassword) {
      setError('Enter the SSH password to update this managed device.')
      return
    }
    const selectedComponents = checkedSoftwareComponents.filter(component => (
      scope === 'all' || component.kind === scope
    ))
    const selectedUpdatesAvailable = selectedComponents.some(
      component => component.update_available,
    )
    const operation = requestedOperation
      ?? (selectedUpdatesAvailable ? 'update' : 'reinstall')
    const operationLabel = operation === 'update' ? 'Update' : 'Reinstall'
    const hardwareServiceCount = device.robots.length
    const targetLabel = managedLocally
      ? scope === 'all'
        ? 'Runtime + Hardware packages'
        : scope === 'runtime'
          ? 'Runtime package'
          : 'Hardware package'
      : scope === 'all'
        ? 'Runtime + workflow packages + Robot Hardware'
        : scope === 'runtime'
          ? 'Runtime + installed workflow packages'
          : `${device.managed_runtime?.stack_mode === 'isolated' ? 'isolated' : 'shared'} Robot Hardware installation used by ${hardwareServiceCount} robot service${
            hardwareServiceCount === 1 ? '' : 's'
          }`
    if (!window.confirm(
      `${operationLabel} ${targetLabel} on "${device.name}"? Running deployments will stop and robots will return with Blacknode motion disarmed. This action does not switch off physical actuator power.`,
    )) return
    setBusy(true)
    setError(null)
    setUpdateReport(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 1,
        message: managedLocally
          ? `Preparing ${targetLabel}`
          : scope === 'runtime'
            ? 'Preparing Runtime + workflow package update'
            : scope === 'hardware'
              ? `Preparing shared Robot Hardware update for ${hardwareServiceCount} robot service${
                hardwareServiceCount === 1 ? '' : 's'
              }`
              : 'Preparing Runtime + workflow packages + Robot Hardware update',
      },
    }))
    try {
      const result = await api.updateComputeDevice(
        device.id,
        managedLocally ? '' : updatePassword,
        scope,
        operation,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setUpdateReport(result)
      setKnownHardwareVersions(previous => {
        const next = { ...previous }
        result.update.components.forEach(component => {
          if (component.kind !== 'hardware' || component.after.version === 'unknown') return
          const robot = device.robots.find(
            item => urlPort(item.base_url) === component.port,
          )
          if (robot) next[robot.id] = component.after.version
        })
        return next
      })
      await refresh()
      try {
        const refreshedCheck = await api.checkComputeDeviceUpdates(
          device.id,
          managedLocally ? '' : updatePassword,
          progress => setActionProgress(previous => ({
            ...previous,
            [device.id]: progress,
          })),
        )
        setUpdateCheckReport(refreshedCheck)
        setKnownHardwareVersions(previous => {
          const next = { ...previous }
          refreshedCheck.check.components.forEach(component => {
            if (component.kind !== 'hardware' || component.installed.version === 'unknown') return
            const robot = device.robots.find(
              item => urlPort(item.base_url) === component.port,
            )
            if (robot) next[robot.id] = component.installed.version
          })
          return next
        })
        setActionProgress(previous => ({
          ...previous,
          [device.id]: { progress: 100, message: result.summary },
        }))
      } catch (checkReason) {
        const checkMessage = checkReason instanceof Error
          ? checkReason.message
          : String(checkReason)
        setUpdateCheckReport(null)
        setActionProgress(previous => ({
          ...previous,
          [device.id]: {
            progress: 100,
            message: `${result.summary} Version report refresh failed: ${checkMessage}`,
          },
        }))
        setError(
          `The update completed, but the version report could not refresh: ${checkMessage}`,
        )
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `${targetLabel} update failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const checkDeviceSoftware = async (device: ComputeDevice) => {
    const managedLocally = device.managed_runtime?.management_mode === 'local'
    if (!managedLocally && !updatePassword) {
      setError('Enter the SSH password to compare installed and latest versions.')
      return
    }
    setBusy(true)
    setError(null)
    setUpdateReport(null)
    setShowDirtySourceHelp(false)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: { progress: 1, message: 'Checking Runtime + Robot Hardware versions' },
    }))
    try {
      const result = await api.checkComputeDeviceUpdates(
        device.id,
        managedLocally ? '' : updatePassword,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setUpdateCheckReport(result)
      setKnownHardwareVersions(previous => {
        const next = { ...previous }
        result.check.components.forEach(component => {
          if (component.kind !== 'hardware' || component.installed.version === 'unknown') return
          const robot = device.robots.find(
            item => urlPort(item.base_url) === component.port,
          )
          if (robot) next[robot.id] = component.installed.version
        })
        return next
      })
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 100, message: result.summary },
      }))
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `Version check failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const manageLocalPackage = async (
    device: ComputeDevice,
    kind: 'runtime' | 'hardware',
    action: 'run' | 'stop' | 'restart' | 'delete',
  ) => {
    const packageName = kind === 'runtime' ? 'Runtime package' : 'Hardware package'
    if (action === 'delete' && !window.confirm(
      `Delete the installed ${packageName} environment? Its service will stop. The source checkout and configuration are preserved so Reinstall can restore it.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 1,
        message: `${
          action === 'run'
            ? 'Starting'
            : action === 'stop'
              ? 'Stopping'
              : action === 'restart'
                ? 'Restarting'
                : 'Deleting'
        } ${packageName}`,
      },
    }))
    try {
      const result = await api.manageLocalPackage(
        device.id,
        kind,
        action,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setDeviceStates(previous => ({
        ...previous,
        [device.id]: {
          runtime: result.runtime,
          loading: false,
          checkedAt: Date.now(),
        },
      }))
      await refreshDevice(device)
      await checkDeviceSoftware(device)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `${packageName} action failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const manageRemoteHardwarePackage = async (
    device: ComputeDevice,
    action: 'run' | 'stop' | 'restart',
  ) => {
    if (!updatePassword) {
      setError(`Enter the SSH password to ${action} the Hardware package.`)
      return
    }
    if (device.robots.length === 0) {
      setError('Attach a robot before controlling the remote Hardware package.')
      return
    }
    if ((action === 'stop' || action === 'restart') && !window.confirm(
      `${action === 'stop' ? 'Stop' : 'Restart'} the remote Hardware package on "${device.name}"? Active deployments will stop and every robot will be disarmed first.`,
    )) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.manageRemoteHardwarePackage(
        device.id,
        action,
        updatePassword,
        progress => setActionProgress(previous => ({
          ...previous,
          [device.id]: progress,
        })),
      )
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 100, message: result.summary },
      }))
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `Hardware package action failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const restartRemotePackage = async (
    device: ComputeDevice,
    kind: 'runtime' | 'hardware',
  ) => {
    if (kind === 'hardware') {
      await manageRemoteHardwarePackage(device, 'restart')
      return
    }
    if (!updatePassword) {
      setError(`Enter the SSH password to restart the ${kind} package.`)
      return
    }
    const label = 'Runtime package'
    if (!window.confirm(
      `Restart the remote ${label} on "${device.name}"? Running deployments will stop and robots must return disarmed.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: { progress: 5, message: `Restarting remote ${label}` },
    }))
    try {
      await api.controlComputeDevice(
          device.id,
          'pause',
          updatePassword,
          progress => setActionProgress(previous => ({
            ...previous,
            [device.id]: {
              progress: Math.min(48, Math.max(5, Math.round(progress.progress * 0.48))),
              message: progress.message,
            },
          })),
      )
      await api.controlComputeDevice(
          device.id,
          'resume',
          updatePassword,
          progress => setActionProgress(previous => ({
            ...previous,
            [device.id]: {
              progress: 50 + Math.round(progress.progress * 0.5),
              message: progress.message,
            },
          })),
      )
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 100, message: `${label} restarted` },
      }))
      await refresh()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [device.id]: { progress: 0, message: `${label} restart failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const controlRobot = async (
    robot: HardwareDevice,
    action: 'pause' | 'resume' | 'restart',
    password = '',
  ): Promise<boolean> => {
    if (action === 'pause' && !window.confirm(
      `Pause "${robot.name}"? Its active deployment will stop and the robot will be stopped and disarmed.`,
    )) return false
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: {
        progress: 1,
        message: action === 'pause'
          ? 'Starting robot pause'
          : action === 'resume'
            ? 'Starting robot restore'
            : 'Starting robot service restart',
      },
    }))
    try {
      const result = await api.controlRobot(
        robot.id,
        action,
        progress => setActionProgress(previous => ({
          ...previous,
          [robot.id]: progress,
        })),
        password,
      )
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: {
          progress: 100,
          message: result.warnings.length
            ? `${result.summary} ${result.warnings.join(' ')}`
            : result.summary,
        },
      }))
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: {
          status: result.status,
          loading: false,
          checkedAt: Date.now(),
        },
      }))
      await refresh()
      return true
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 0, message: `Robot action failed: ${message}` },
      }))
      setError(message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const renameRobot = async (robot: HardwareDevice) => {
    const nextName = window.prompt('Name this robot', robot.name)
    if (nextName === null || nextName.trim() === robot.name) return
    setBusy(true)
    setError(null)
    try {
      await api.renameDevice(robot.id, nextName.trim())
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const removeRobot = async (robot: HardwareDevice) => {
    if (!window.confirm(`Remove robot "${robot.name}" from this device?`)) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteDevice(robot.id)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const stopDeployment = async (robot: HardwareDevice, deploymentId: string) => {
    if (!window.confirm(`Stop the deployment using "${robot.name}"?`)) return
    setBusy(true)
    setError(null)
    try {
      await api.stopRemoteDeployment(robot.id, deploymentId)
      await refreshRobot(robot)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const restartDeployment = async (
    robot: HardwareDevice,
    deploymentId: string,
    deploymentName: string,
  ) => {
    if (!window.confirm(
      `Restart deployment "${deploymentName}" on "${robot.name}"? Blacknode will recheck the robot safety state before starting it.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: { progress: 10, message: 'Restarting deployment' },
    }))
    try {
      await api.startRemoteDeployment(robot.id, deploymentId)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 100, message: `"${deploymentName}" restarted` },
      }))
      await refreshRobot(robot)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 0, message: `Deployment restart failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const waitForFollowerTorque = async (
    robot: HardwareDevice,
    expected: boolean,
  ): Promise<RobotTelemetrySample> => {
    let lastSample: RobotTelemetrySample | undefined
    for (let attempt = 0; attempt < 16; attempt += 1) {
      const result = await checkRobotTelemetry(robot)
      lastSample = result.telemetry
      const driverError = lastSample?.payload?.error?.trim()
      if (driverError) {
        throw new Error(`Follower driver blocked torque: ${driverError}`)
      }
      if (
        lastSample
        && lastSample.available
        && !lastSample.stale
        && lastSample.payload?.torque_enabled === expected
      ) {
        return lastSample
      }
      await new Promise(resolve => window.setTimeout(resolve, 500))
    }
    throw new Error(
      expected
        ? 'Follower did not confirm physical torque within 8 seconds.'
        : 'Follower did not confirm torque release within 8 seconds.',
    )
  }

  const setDeploymentMotion = async (
    robot: HardwareDevice,
    deploymentId: string,
    deploymentName: string,
    armed: boolean,
  ) => {
    const prompt = armed
      ? `ARM follower motion for "${deploymentName}" on "${robot.name}"? Keep the leader torque-released, support both arms, and clear the workspace.`
      : `Disarm follower motion for "${deploymentName}" on "${robot.name}" and release follower torque? Support the follower first.`
    if (!window.confirm(prompt)) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: {
        progress: 25,
        message: armed ? 'Arming follower deployment' : 'Disarming follower deployment',
      },
    }))
    try {
      await api.setRemoteDeploymentMotion(robot.id, deploymentId, armed)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: {
          progress: 60,
          message: armed
            ? 'Waiting for physical follower torque confirmation'
            : 'Waiting for follower torque release confirmation',
        },
      }))
      await waitForFollowerTorque(robot, armed)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: {
          progress: 100,
          message: armed
            ? `"${deploymentName}" armed · physical torque confirmed`
            : `"${deploymentName}" disarmed · torque released`,
        },
      }))
      await refreshRobot(robot)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      if (armed) {
        try {
          await api.setRemoteDeploymentMotion(robot.id, deploymentId, false)
        } catch {
          // Keep the original torque-confirmation failure visible.
        }
        await Promise.all([
          refreshRobot(robot),
          checkRobotTelemetry(robot),
        ])
      }
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 0, message: `Arm failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const openDeployedGraph = async (
    robot: HardwareDevice,
    deploymentId: string,
    deploymentName: string,
  ) => {
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: {
        progress: 25,
        message: `Loading deployed graph for "${deploymentName}"`,
      },
    }))
    try {
      const captured = await api.remoteDeploymentWorkflow(robot.id, deploymentId)
      const workflow = captured.workflow
      await openGraphAsTab(
        `${workflow.name || deploymentName} · deployed ${captured.revision.slice(0, 8)}`,
        {
          nodes: Object.values(workflow.node_meta ?? {}),
          edges: workflow.edges ?? [],
          metadata: workflow.metadata ?? {},
        },
      )
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: {
          progress: 100,
          message: `Opened deployed revision ${captured.revision.slice(0, 8)}`,
        },
      }))
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 0, message },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const releaseRobotTorque = async (robot: HardwareDevice) => {
    if (!window.confirm(
      `Release physical holding torque on "${robot.name}"? Support the robot first: its joints may move or drop as soon as torque is disabled.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: { progress: 10, message: 'Releasing physical servo torque' },
    }))
    try {
      const result = await api.releaseDeviceTorque(robot.id)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: {
          progress: 100,
          message: result.verification_warning
            ? `Torque-off command sent. ${result.verification_warning}`
            : result.already_released
              ? 'Physical servo torque was already off'
              : 'Physical servo torque released and verified off',
        },
      }))
      await refreshRobot(robot)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setActionProgress(previous => ({
        ...previous,
        [robot.id]: { progress: 0, message: `Torque release failed: ${message}` },
      }))
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bn-runs-panel bn-devices-panel">
      <div className="bn-runs-toolbar">
        <div>
          <div className="bn-runs-title">Devices</div>
          <div className="bn-runs-subtitle">
            {devices.length} {devices.length === 1 ? 'computer' : 'computers'} ·{' '}
            {devices.reduce((count, device) => count + device.robots.length, 0)} robots
          </div>
        </div>
        <div className="bn-runs-actions">
          <button onClick={refresh} disabled={busy} className="bn-device-action-button">
            Refresh
          </button>
          <button
            onClick={() => {
              setSelectedDeviceId(null)
              setShowDeviceForm(true)
              setShowRobotForm(false)
              setError(null)
            }}
            disabled={busy}
            className="bn-device-action-button is-primary"
          >
            Add device
          </button>
        </div>
      </div>

      {showDeviceForm && (
        <form
          className="bn-device-form"
          onSubmit={
            setupMode === 'automatic'
              ? automaticInstall
              : setupMode === 'local'
                ? installLocalComputer
                : manualPair
          }
        >
          <div className="bn-device-form-title">Add a compute device</div>
          <p className="bn-device-help">
            A device runs Blacknode Runtime. Add its robot hardware after the runtime is ready.
          </p>
          <div className="bn-device-mode-tabs" role="tablist" aria-label="Device setup method">
            <button
              type="button"
              className={setupMode === 'local' ? 'is-active' : ''}
              onClick={() => selectSetupMode('local')}
            >
              Local computer
            </button>
            <button
              type="button"
              className={setupMode === 'automatic' ? 'is-active' : ''}
              onClick={() => selectSetupMode('automatic')}
            >
              Remote SSH
            </button>
            <button
              type="button"
              className={setupMode === 'manual' ? 'is-active' : ''}
              onClick={() => selectSetupMode('manual')}
            >
              Remote Manual
            </button>
          </div>
          <label>
            <span>Device name</span>
            <input
              value={deviceName}
              onChange={event => setDeviceName(event.target.value)}
              placeholder="Jetson Orin"
              autoComplete="off"
            />
          </label>

          {setupMode === 'automatic' ? (
            <>
              <div className="bn-device-setup-step">
                <span className="bn-device-setup-number">1</span>
                <div>
                  <strong>Connect over SSH</strong>
                  <p>
                    Blacknode verifies the computer, checks existing runtimes and occupied
                    ports, then lets you reuse, replace, or install an independent instance.
                  </p>
                </div>
              </div>
              <div className="bn-device-ssh-grid">
                <label>
                  <span>IP address or hostname</span>
                  <input
                    value={sshHost}
                    onChange={event => {
                      setSshHost(event.target.value)
                      setSshProbe(null)
                      setSshInspection(null)
                    }}
                    required
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                  />
                </label>
                <label>
                  <span>SSH port</span>
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    value={sshPort}
                    onChange={event => {
                      setSshPort(Number(event.target.value))
                      setSshProbe(null)
                      setSshInspection(null)
                    }}
                    required
                  />
                </label>
                <label>
                  <span>Username</span>
                  <input
                    value={sshUsername}
                    onChange={event => {
                      setSshUsername(event.target.value)
                      setSshInspection(null)
                      setInstallProgress(null)
                    }}
                    required
                    autoComplete="username"
                  />
                </label>
                <label>
                  <span>Password</span>
                  <input
                    type="password"
                    value={sshPassword}
                    onChange={event => {
                      setSshPassword(event.target.value)
                      setSshInspection(null)
                      setInstallProgress(null)
                    }}
                    required
                    autoComplete="current-password"
                  />
                </label>
              </div>
              <div className="bn-device-help">
                The SSH password is used for this setup only. It is not saved by Blacknode.
              </div>
              {sshProbe && !sshInspection && (
                <div className="bn-device-fingerprint" role="status">
                  <strong>Confirm this device</strong>
                  <span>{sshProbe.hostname} · SSH host key</span>
                  <code>{sshProbe.host_fingerprint}</code>
                  <p>
                    Confirm this fingerprint belongs to your device before inspecting it.
                    A changed key is blocked automatically.
                  </p>
                </div>
              )}
              {sshInspection && (
                <div className="bn-runtime-install-review">
                  <div>
                    <strong>Runtime setup</strong>
                    <span>
                      {sshInspection.instances.length
                        ? `${sshInspection.instances.length} existing ${sshInspection.instances.length === 1 ? 'installation' : 'installations'} found`
                        : `No existing runtime found · port ${sshInspection.suggested_port} is available`}
                    </span>
                  </div>
                  {sshInspection.environment && (
                    <div className="bn-host-environment">
                      <div className="bn-host-environment-head">
                        <div>
                          <strong>Host environment</strong>
                          <span>Read-only inspection · existing system versions are preserved</span>
                        </div>
                        <span className="bn-preserved-badge">Preserved</span>
                      </div>
                      <div className="bn-host-environment-grid">
                        <article>
                          <span className="bn-host-environment-state is-available" aria-hidden="true" />
                          <div>
                            <strong>System</strong>
                            <span>
                              {sshInspection.environment.os.name}
                              {' · '}{sshInspection.environment.os.architecture}
                            </span>
                            <small>Python {sshInspection.environment.python.version}</small>
                          </div>
                        </article>
                        <article>
                          <span
                            className={`bn-host-environment-state${sshInspection.environment.nvidia.available ? ' is-available' : ''}`}
                            aria-hidden="true"
                          />
                          <div>
                            <strong>NVIDIA / CUDA</strong>
                            <span>
                              {sshInspection.environment.nvidia.available
                                ? sshInspection.environment.nvidia.gpus.join(', ') || 'NVIDIA software detected'
                                : 'Not detected'}
                            </span>
                            <small>
                              {sshInspection.environment.nvidia.available
                                ? [
                                    sshInspection.environment.nvidia.driver_version
                                      ? `Driver ${sshInspection.environment.nvidia.driver_version}`
                                      : '',
                                    sshInspection.environment.nvidia.driver_cuda_version
                                      ? `CUDA support ${sshInspection.environment.nvidia.driver_cuda_version}`
                                      : '',
                                    sshInspection.environment.nvidia.cuda_toolkit_version
                                      ? `Toolkit ${sshInspection.environment.nvidia.cuda_toolkit_version}`
                                      : 'Toolkit not detected',
                                  ].filter(Boolean).join(' · ')
                                : 'Runtime setup will not install it'}
                            </small>
                          </div>
                        </article>
                        <article>
                          <span
                            className={`bn-host-environment-state${sshInspection.environment.ros2.available ? ' is-available' : ''}`}
                            aria-hidden="true"
                          />
                          <div>
                            <strong>ROS 2</strong>
                            <span>
                              {sshInspection.environment.ros2.available
                                ? sshInspection.environment.ros2.distributions.join(', ') || 'ROS 2 command detected'
                                : 'Not detected'}
                            </span>
                            <small>
                              {sshInspection.environment.ros2.available
                                ? `${sshInspection.environment.ros2.selected_distribution || 'Installed distribution'} will be reused`
                                : 'Runtime setup will not install it'}
                            </small>
                          </div>
                        </article>
                        <article>
                          <span
                            className={`bn-host-environment-state${sshInspection.environment.docker.available ? ' is-available' : ''}`}
                            aria-hidden="true"
                          />
                          <div>
                            <strong>Docker</strong>
                            <span>
                              {sshInspection.environment.docker.available
                                ? `Docker ${sshInspection.environment.docker.server_version || sshInspection.environment.docker.client_version || 'installed'}`
                                : 'Not detected'}
                            </span>
                            <small>
                              {sshInspection.environment.docker.available
                                ? `Daemon ${sshInspection.environment.docker.daemon_running ? 'running' : 'stopped'} · service ${sshInspection.environment.docker.service_enabled ? 'enabled' : 'not enabled'}`
                                : 'Runtime setup will not install or start it'}
                            </small>
                          </div>
                        </article>
                      </div>
                      <p>
                        Runtime setup may install missing {sshInspection.environment.runtime_setup_packages.join(', ')}.
                        It does not replace NVIDIA drivers, CUDA, ROS 2, or Docker.
                      </p>
                    </div>
                  )}
                  <div className="bn-runtime-install-options">
                    {sshInspection.instances.flatMap(instance => [
                      <label
                        key={`reuse-${instance.instance_id}`}
                        className={installAction === 'reuse' && installInstanceId === instance.instance_id ? 'is-selected' : ''}
                        aria-disabled={!instance.healthy}
                      >
                        <input
                          type="radio"
                          name="runtime-install-action"
                          checked={installAction === 'reuse' && installInstanceId === instance.instance_id}
                          disabled={!instance.healthy}
                          onChange={() => {
                            setInstallAction('reuse')
                            setInstallInstanceId(instance.instance_id)
                          }}
                        />
                        <span>
                          <strong>Use existing {instance.instance_id === 'default' ? 'runtime' : instance.instance_id}</strong>
                          <small>
                            {instance.healthy
                              ? `Ready${instance.runtime_version ? ` · v${instance.runtime_version}` : ''} · port ${instance.port}`
                              : `Unavailable · ${instance.error || 'repair required'}`}
                          </small>
                        </span>
                      </label>,
                      <label
                        key={`replace-${instance.instance_id}`}
                        className={installAction === 'replace' && installInstanceId === instance.instance_id ? 'is-selected is-danger' : ''}
                      >
                        <input
                          type="radio"
                          name="runtime-install-action"
                          checked={installAction === 'replace' && installInstanceId === instance.instance_id}
                          onChange={() => {
                            setInstallAction('replace')
                            setInstallInstanceId(instance.instance_id)
                          }}
                        />
                        <span>
                          <strong>Reinstall {instance.instance_id === 'default' ? 'existing runtime' : instance.instance_id}</strong>
                          <small>Stops it and replaces its files, state, service, and token on port {instance.port}.</small>
                        </span>
                      </label>,
                    ])}
                    {sshInspection.instances.length === 0 && (
                      <label className={installAction === 'install' ? 'is-selected' : ''}>
                        <input
                          type="radio"
                          name="runtime-install-action"
                          checked={installAction === 'install'}
                          onChange={() => {
                            setInstallAction('install')
                            setInstallInstanceId('default')
                          }}
                        />
                        <span>
                          <strong>Install complete robot device</strong>
                          <small>
                            Installs Runtime and Robot Hardware in the default managed
                            stack on port {sshInspection.suggested_port}.
                          </small>
                        </span>
                      </label>
                    )}
                    {sshInspection.instances.length > 0 && (
                      <label className={installAction === 'side_by_side' ? 'is-selected' : ''}>
                        <input
                          type="radio"
                          name="runtime-install-action"
                          checked={installAction === 'side_by_side'}
                          onChange={() => {
                            setInstallAction('side_by_side')
                            setInstallInstanceId(sshInspection.suggested_instance_id)
                          }}
                        />
                        <span>
                          <strong>Install a separate runtime</strong>
                          <small>
                            Keeps every existing installation untouched. Creates {sshInspection.suggested_instance_id}
                            {' '}on available port {sshInspection.suggested_port}.
                          </small>
                        </span>
                      </label>
                    )}
                    {sshInspection.instances.length > 0 && (
                      <label className={installAction === 'isolated_stack' ? 'is-selected' : ''}>
                        <input
                          type="radio"
                          name="runtime-install-action"
                          checked={installAction === 'isolated_stack'}
                          onChange={() => {
                            setInstallAction('isolated_stack')
                            setInstallInstanceId(sshInspection.suggested_instance_id)
                          }}
                        />
                        <span>
                          <strong>Install a complete isolated robot stack</strong>
                          <small>
                            Creates {sshInspection.suggested_instance_id} with separate Runtime
                            and Robot Hardware directories, environments, tokens, state, services,
                            and ports. Existing stacks remain untouched.
                          </small>
                        </span>
                      </label>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : setupMode === 'local' ? (
            <>
              <div className="bn-device-setup-step">
                <span className="bn-device-setup-number">1</span>
                <div>
                  <strong>Install a local robot stack</strong>
                  <p>
                    Choose one folder. Blacknode installs the Runtime package and Hardware
                    package in separate subfolders and environments, configures
                    authentication, starts both services, and adds this computer.
                  </p>
                </div>
              </div>
              <div className="bn-device-local-capabilities" role="note">
                <strong>Same Blacknode workspace</strong>
                <span>
                  Deployments, logs, live monitoring, projects, and attached robots use the
                  same device APIs as a remote computer.
                </span>
                <small>
                  Robot Hardware starts authenticated, disconnected, and disarmed while it
                  waits for a physical robot configuration. Tokens stay on this computer.
                </small>
              </div>
              <label>
                <span>Local stack installation folder</span>
                <div className="bn-device-path-field">
                  <input
                    value={localInstallDir}
                    onChange={event => setLocalInstallDir(event.target.value)}
                    placeholder="Choose a folder for the Blacknode stack"
                    required
                    spellCheck={false}
                    disabled={busy}
                  />
                  <button
                    type="button"
                    onClick={() => void browseLocalInstallDir()}
                    disabled={busy}
                    style={miniButton}
                  >
                    Browse
                  </button>
                </div>
              </label>
            </>
          ) : (
            <>
              <div className="bn-device-setup-step">
                <span className="bn-device-setup-number">1</span>
                <div>
                  <strong>Install the runtime on the device</strong>
                  <p>
                    Run the Blacknode runtime installer on Ubuntu, Jetson, or Raspberry Pi,
                    then print its pairing details with <code>./service.sh pairing</code>.
                  </p>
                </div>
              </div>
              <label>
                <span>Runtime URL</span>
                <input
                  value={runtimeUrl}
                  onChange={event => setRuntimeUrl(event.target.value)}
                  placeholder={DEFAULT_RUNTIME_URL}
                  required
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                />
              </label>
              <label>
                <span>Runtime token</span>
                <input
                  type="password"
                  value={runtimeToken}
                  onChange={event => setRuntimeToken(event.target.value)}
                  placeholder="Paste token from service.sh pairing"
                  required
                  autoComplete="new-password"
                />
              </label>
            </>
          )}

          {installProgress && (setupMode === 'automatic' || setupMode === 'local') && (
            <div
              className="bn-device-install-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={installProgress.progress}
              aria-label={installProgress.message}
            >
              <div>
                <strong>{installProgress.message}</strong>
                <span>{installProgress.progress}%</span>
              </div>
              <span className="bn-device-install-progress-track" aria-hidden="true">
                <span style={{ width: `${installProgress.progress}%` }} />
              </span>
            </div>
          )}

          <div className="bn-device-form-actions">
            <button type="button" onClick={resetDeviceForm} style={miniButton}>Cancel</button>
            {setupMode === 'automatic' && !sshProbe ? (
              <button type="button" onClick={probeSsh} disabled={busy} style={primaryButton}>
                {busy ? 'Checking…' : 'Check connection'}
              </button>
            ) : (
              <button
                type="submit"
                disabled={busy || (setupMode === 'local' && !localInstallDir.trim())}
                style={primaryButton}
              >
                {busy
                  ? setupMode === 'automatic'
                    ? sshInspection ? installAction === 'reuse' ? 'Pairing…' : 'Installing…' : 'Inspecting…'
                    : setupMode === 'local' ? 'Installing…' : 'Pairing…'
                  : setupMode === 'automatic'
                    ? sshInspection
                      ? installAction === 'reuse'
                        ? 'Pair existing runtime'
                        : installAction === 'replace'
                          ? 'Reinstall runtime'
                          : installAction === 'isolated_stack'
                            ? 'Install isolated stack'
                            : installAction === 'install'
                              ? 'Install robot device'
                              : 'Install runtime'
                      : 'Confirm and inspect'
                    : setupMode === 'local' ? 'Add local computer' : 'Pair runtime'}
              </button>
            )}
          </div>
        </form>
      )}

      {error && <div className="bn-runs-error">{error}</div>}
      {linkedProjectName && (
        <div className="bn-device-continue" role="status">
          <div>
            <strong>Robot connected</strong>
            <span>It was linked to “{linkedProjectName}” and is ready for deployment setup.</span>
          </div>
          <button
            type="button"
            onClick={() => window.dispatchEvent(new CustomEvent('blacknode:open-panel', {
              detail: { tab: 'projects' },
            }))}
            style={primaryButton}
          >
            Continue project
          </button>
        </div>
      )}

      {!selectedDevice && (
        devices.length === 0 && !showDeviceForm && !error ? (
          <div className="bn-device-empty">
            <span className="bn-device-empty-icon">1</span>
            <strong>Add the computer that will run your robots</strong>
            <p>
              Install or pair Blacknode Runtime first. Then attach one or more robots
              and deploy a workflow to the robot you choose.
            </p>
            <button
              type="button"
              onClick={() => setShowDeviceForm(true)}
              className="bn-device-action-button is-primary"
            >
              Add first device
            </button>
          </div>
        ) : (
          <div className="bn-compute-device-grid">
            {devices.map(device => (
              <ComputeDeviceCard
                key={device.id}
                device={device}
                state={deviceStates[device.id]}
                selected={false}
                onSelect={() => {
                  setSelectedDeviceId(device.id)
                  setUpdateCheckReport(null)
                  setUpdateReport(null)
                  setShowSoftwareDetails(false)
                  setShowServiceDetails(false)
                  setShowRosDetails(false)
                  setShowDeviceManagement(false)
                  setShowDeviceForm(false)
                  setShowRobotForm(false)
                  setShowSshManagement(false)
                }}
              />
            ))}
          </div>
        )
      )}

      {selectedDevice && (
        <section className="bn-compute-device-detail">
          <div className="bn-compute-device-detail-nav">
            <button
              type="button"
              className="bn-device-back-button"
              onClick={() => {
                setSelectedDeviceId(null)
                setUpdateCheckReport(null)
                setUpdateReport(null)
                setShowRobotForm(false)
                setShowUninstallForm(false)
                setShowRuntimeControl(false)
                setShowUpdateForm(false)
                setUninstallPassword('')
                setRuntimeControlPassword('')
                setUpdatePassword('')
                setShowSoftwareDetails(false)
                setShowServiceDetails(false)
                setShowRosDetails(false)
                setShowDeviceManagement(false)
                setShowSshManagement(false)
                setManagementPassword('')
                setManagementProbe(null)
                setError(null)
              }}
            >
              <span className="bn-device-back-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M15 5 8 12l7 7" />
                </svg>
              </span>
              <span className="bn-device-back-label">Back to all devices</span>
            </button>
          </div>
          <div className="bn-compute-device-detail-head">
            <div className="bn-compute-device-identity">
              <strong>{selectedDevice.name}</strong>
              {selectedDeviceIsLocal
                ? <span>Local computer · loopback connection</span>
                : selectedStackIsIsolated
                  ? <span>Complete isolated robot stack</span>
                  : null}
              <code>{selectedDevice.runtime_url}</code>
            </div>
            <div className="bn-run-detail-actions bn-device-header-actions">
              <button
                onClick={() => setShowDeviceManagement(current => !current)}
                disabled={busy}
                className={`bn-device-action-button${showDeviceManagement ? ' is-primary' : ''}`}
                aria-expanded={showDeviceManagement}
              >
                {showDeviceManagement ? 'Close device settings' : 'Manage device'}
              </button>
              {showDeviceManagement && (
                <>
                  <button
                    onClick={() => renameDevice(selectedDevice)}
                    disabled={busy}
                    className="bn-device-action-button"
                  >
                    Rename
                  </button>
                  {!selectedDevice.managed_runtime && !selectedDeviceIsLocal && (
                <button
                  onClick={() => openSshManagement(selectedDevice)}
                  disabled={busy}
                  className={`bn-device-action-button bn-ssh-enable-button${showSshManagement ? ' is-active' : ''}`}
                  title="Verify this paired runtime over SSH to enable lifecycle controls"
                  aria-expanded={showSshManagement}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <rect x="3.5" y="5" width="17" height="14" rx="3" />
                    <path d="m7.5 9 2.5 2.5L7.5 14M12.5 14H16" />
                  </svg>
                  Enable SSH controls
                </button>
                  )}
                  {selectedDevice.managed_runtime && (
                    <>
                      <button
                        onClick={() => {
                          if (selectedDeviceManagedLocally) {
                            void controlDevice(
                              selectedDevice,
                              selectedDevice.paused ? 'resume' : 'pause',
                            )
                          } else {
                            setShowRuntimeControl(current => !current)
                            setShowUpdateForm(false)
                            setShowUninstallForm(false)
                            setRuntimeControlPassword('')
                            setError(null)
                          }
                        }}
                        disabled={busy}
                        className={`bn-device-action-button${selectedDevice.paused ? ' is-primary' : ''}`}
                      >
                        {selectedDevice.paused ? 'Resume device' : 'Pause device'}
                      </button>
                      <button
                        onClick={() => {
                          setShowUninstallForm(current => !current)
                          setShowRuntimeControl(false)
                          setShowUpdateForm(false)
                          setUninstallPassword('')
                          setError(null)
                        }}
                        disabled={busy}
                        className="bn-device-action-button is-danger"
                      >
                        {selectedDeviceManagedLocally
                          && !selectedDevice.managed_runtime?.owned_install
                          ? 'Uninstall local services'
                          : 'Delete device'}
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => removeDevice(selectedDevice)}
                    disabled={busy}
                    className="bn-device-action-button is-danger"
                    title="Remove only Blacknode's saved connection; do not uninstall Runtime or Hardware"
                  >
                    Forget device
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="bn-device-overview" role="status" aria-live="polite">
            <div className={`bn-device-overview-item${
              selectedDeviceChecking
                ? ' is-checking'
                : selectedDeviceReady
                  ? ' is-ready'
                  : ' is-attention'
            }`}>
              <span className="bn-device-overview-dot" aria-hidden="true" />
              <div>
                <small>System</small>
                <strong>
                  {selectedDeviceChecking
                    ? 'Checking'
                    : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                      ? 'Paused'
                      : selectedDeviceReady
                        ? 'Services online'
                        : 'Needs attention'}
                </strong>
                <span>Runtime {selectedRuntimeVersion}</span>
              </div>
            </div>
            <button
              type="button"
              className={`bn-device-overview-item bn-device-overview-toggle is-${
                selectedRosHealth?.state ?? 'unchecked'
              }${showRosDetails ? ' is-expanded' : ''}`}
              onClick={() => setShowRosDetails(current => !current)}
              aria-expanded={showRosDetails}
              aria-controls="bn-live-ros2-details"
              title="Show live ROS 2 nodes, topics, services, and endpoint counts"
            >
              <span className="bn-device-overview-dot" aria-hidden="true" />
              <div>
                <small>ROS 2</small>
                <strong>
                  {selectedRosHealth?.state === 'healthy'
                    ? 'Endpoints ready'
                    : selectedRosHealth?.state === 'warning'
                      ? 'Warning'
                      : selectedRosHealth?.state === 'error'
                        ? 'Needs attention'
                        : selectedRosHealth?.state === 'unavailable'
                        ? 'Unavailable'
                          : selectedRosHealth?.state === 'checking'
                            ? 'Checking'
                            : 'Not checked'}
                </strong>
                <span>
                  {selectedRosHealth?.checking && selectedRosHealth.state !== 'checking'
                    ? `Rechecking · ${selectedRosHealth.summary}`
                    : selectedRosHealth?.summary ?? 'Press Check device to inspect ROS 2'}
                </span>
              </div>
            </button>
            <div className={`bn-device-overview-item${
              selectedMotionDisarmed ? ' is-attention' : ''
            }`}>
              <span className="bn-device-overview-dot" aria-hidden="true" />
              <div>
                <small>Robots</small>
                <strong>
                  {selectedRobotChecks.filter(item => item.state?.status?.connected).length}
                  /{selectedDevice.robots.length} connected
                </strong>
                <span>
                  {selectedMotionControllers.length > 0
                    ? selectedMotionDisarmed
                      ? 'Follower motion disarmed'
                      : 'Follower motion armed'
                    : `${selectedRunningDeployments.length} running deployment${
                      selectedRunningDeployments.length === 1 ? '' : 's'
                    }`}
                </span>
              </div>
            </div>
            <div className="bn-device-overview-actions">
              <button
                type="button"
                onClick={() => void checkDevice(selectedDevice)}
                disabled={busy || selectedDeviceChecking || selectedRosHealth?.checking}
                className="bn-device-action-button is-primary"
              >
                {selectedDeviceChecking || selectedRosHealth?.checking
                  ? 'Checking…'
                  : 'Check device'}
              </button>
              {selectedDevice.managed_runtime && (
                <button
                  type="button"
                  onClick={() => setShowSoftwareDetails(current => !current)}
                  className="bn-device-action-button"
                  aria-expanded={showSoftwareDetails}
                >
                  {showSoftwareDetails ? 'Hide software' : 'Software'}
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowServiceDetails(current => !current)}
                className="bn-device-action-button"
                aria-expanded={showServiceDetails}
              >
                {showServiceDetails ? 'Hide details' : 'Details'}
              </button>
            </div>
          </div>

          {actionProgress[selectedDevice.id] && !showUninstallForm && (
            <div className="bn-device-check-progress">
              <LifecycleProgress value={actionProgress[selectedDevice.id]} />
            </div>
          )}

          {selectedCheckIssues.length > 0 && (
            <section className="bn-device-motion-diagnostics" role="alert">
              <div className="bn-device-motion-diagnostics-head">
                <span className="bn-device-overview-dot" aria-hidden="true" />
                <div>
                  <strong>Robot motion is blocked</strong>
                  <span>
                    Check device found {selectedCheckIssues.length} issue{
                      selectedCheckIssues.length === 1 ? '' : 's'
                    } that must be fixed before motion can work.
                  </span>
                </div>
              </div>
              <ol>
                {selectedCheckIssues.map(issue => (
                  <li key={issue.id}>
                    <strong>{issue.title}</strong>
                    <span>{issue.detail}</span>
                    <small>Fix: {issue.action}</small>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {selectedRosHealth
            && (selectedRosHealth.state === 'warning' || selectedRosHealth.state === 'error')
            && (
              <div
                className={`bn-device-health-alert is-${selectedRosHealth.state}`}
                role={selectedRosHealth.state === 'error' ? 'alert' : 'status'}
              >
                <span className="bn-device-overview-dot" aria-hidden="true" />
                <div>
                  <strong>{selectedRosHealth.summary}</strong>
                  <span>
                    {selectedRosHealth.issues[0]
                      || 'The ROS 2 graph did not pass its latest health check.'}
                  </span>
                </div>
                <div className="bn-run-detail-actions">
                  <button
                    type="button"
                    onClick={() => setShowRosDetails(current => !current)}
                    className="bn-device-action-button"
                  >
                    {showRosDetails ? 'Hide ROS details' : 'ROS details'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void checkRosHealth(selectedDevice)}
                    disabled={selectedRosHealth.checking}
                    className="bn-device-action-button"
                  >
                    {selectedRosHealth.checking ? 'Checking…' : 'Check ROS'}
                  </button>
                </div>
              </div>
            )}

          {showRosDetails && selectedRosHealth?.diagnostics && (
            <div id="bn-live-ros2-details" className="bn-device-ros-details">
              <div className="bn-device-ros-details-head">
                <div>
                  <strong>Live ROS 2 graph</strong>
                  <span>Last checked {formatCheckedAt(selectedRosHealth.checkedAt)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => void checkRosHealth(selectedDevice)}
                  disabled={selectedRosHealth.checking}
                  className="bn-device-action-button"
                >
                  {selectedRosHealth.checking ? 'Checking…' : 'Refresh ROS'}
                </button>
              </div>
              <div className="bn-ros-robot-paths">
                <RosRobotPathCard
                  diagnostics={selectedRosHealth.diagnostics}
                  role="leader"
                />
                <RosRobotPathCard
                  diagnostics={selectedRosHealth.diagnostics}
                  role="follower"
                />
              </div>
              <p className="bn-ros-internals-note">
                This check verifies ROS 2 endpoints. Robot motion also requires a running
                deployment, fresh data, and an explicitly armed follower.
              </p>
              <p className="bn-ros-internals-note">
                ROS internals: {selectedRosHealth.diagnostics.nodes.length} nodes,{' '}
                {selectedRosHealth.diagnostics.topics.length} topics, and{' '}
                {selectedRosHealth.diagnostics.services.length} services. Parameter and
                type-description services are generated automatically by ROS 2.
              </p>
              <details className="bn-ros-advanced">
                <summary>Advanced · raw ROS graph</summary>
                <section className="bn-ros-graph-section">
                  <h4>Nodes ({selectedRosHealth.diagnostics.nodes.length})</h4>
                  {selectedRosHealth.diagnostics.nodes.length > 0 ? (
                    <ul className="bn-ros-graph-list">
                      {rosNameCounts(selectedRosHealth.diagnostics.nodes).map(([node, count]) => (
                        <li key={node}>
                          <code>{node}</code>
                          {count > 1 && <span>{count} running instances</span>}
                        </li>
                      ))}
                    </ul>
                  ) : <span>No nodes discovered.</span>}
                </section>
                <section className="bn-ros-graph-section">
                  <h4>Topics ({selectedRosHealth.diagnostics.topics.length})</h4>
                  {selectedRosHealth.diagnostics.topics.length > 0 ? (
                    <ul className="bn-ros-graph-list is-topics">
                      {selectedRosHealth.diagnostics.topics.map(topic => {
                        const name = rosTopicName(topic)
                        const detail = rosTopicDetail(selectedRosHealth.diagnostics!, name)
                        return (
                          <li key={name}>
                            <code>{name}</code>
                            <span>{rosTopicType(topic)} · {rosTopicEndpointSummary(detail)}</span>
                          </li>
                        )
                      })}
                    </ul>
                  ) : <span>No topics discovered.</span>}
                </section>
                <section className="bn-ros-graph-section">
                  <h4>Services ({selectedRosHealth.diagnostics.services.length})</h4>
                  {selectedRosHealth.diagnostics.services.length > 0 ? (
                    <ul className="bn-ros-graph-list">
                      {selectedRosHealth.diagnostics.services.map(service => (
                        <li key={service}><code>{service}</code></li>
                      ))}
                    </ul>
                  ) : <span>No services discovered.</span>}
                </section>
              </details>
            </div>
          )}

          {selectedDevice.managed_runtime && showSoftwareDetails && (
            <div className="bn-device-local-note" role="note">
              <div className="bn-local-package-summary-head">
                <div>
                  <strong>Software packages</strong>
                  <span>
                    {selectedDeviceManagedLocally
                      ? 'Runtime and Hardware use independent package controls.'
                      : 'Updating Runtime also refreshes every installed workflow package.'}
                  </span>
                </div>
                <div className="bn-local-package-summary-actions">
                  {!selectedDeviceManagedLocally && (
                    <label className="bn-local-package-password">
                      <span>SSH password · never saved</span>
                      <input
                        type="password"
                        value={updatePassword}
                        onChange={event => setUpdatePassword(event.target.value)}
                        autoComplete="current-password"
                        placeholder="Required for package actions"
                      />
                    </label>
                  )}
                  <button
                    type="button"
                    className="bn-device-action-button"
                    disabled={busy}
                    onClick={() => void checkDeviceSoftware(selectedDevice)}
                  >
                    {busy ? 'Checking…' : 'Check updates'}
                  </button>
                  {!selectedDeviceManagedLocally && (
                    <button
                      type="button"
                      className="bn-device-action-button is-primary"
                      disabled={busy || !updatePassword}
                      title="Update Runtime, all installed workflow packages, and Hardware"
                      onClick={() => void updateDevice(
                        selectedDevice,
                        'all',
                        'update',
                      )}
                    >
                      Update all
                    </button>
                  )}
                </div>
              </div>
              {!selectedDeviceManagedLocally && (
                <div className="bn-local-package-check-help">
                  To check updates, enter the SSH password and press
                  {' '}
                  <strong>Check updates</strong>.
                </div>
              )}
              <div className="bn-local-package-summary">
                <SoftwarePackageSummaryCard
                  label={selectedDeviceManagedLocally
                    ? 'Runtime package'
                    : 'Runtime + workflow packages'}
                  path={selectedDevice.managed_runtime?.runtime_dir || selectedDevice.runtime_url}
                  detail={selectedDeviceManagedLocally
                    ? undefined
                    : `Packages: ${
                        selectedDevice.managed_runtime?.packages_dir
                        || `${selectedDevice.managed_runtime?.runtime_dir}/packages`
                      } · ${selectedWorkflowPackages.length
                        ? selectedWorkflowPackages
                          .map(item => `${item.name} v${item.version}`)
                          .join(', ')
                        : 'no workflow packages installed'}`}
                  state={selectedRuntimePackageState}
                  currentVersion={runtimeCurrentVersion}
                  latestVersion={runtimeLatestVersion}
                  installed={selectedDeviceState?.runtime?.installed !== false}
                  updateAvailable={checkedRuntimeComponents.some(
                    component => component.update_available,
                  )}
                  busy={busy}
                  onCheckLatest={() => void checkDeviceSoftware(selectedDevice)}
                  onRunStop={action => (
                    selectedDeviceManagedLocally
                      ? void manageLocalPackage(selectedDevice, 'runtime', action)
                      : void controlDevice(
                          selectedDevice,
                          action === 'run' ? 'resume' : 'pause',
                          updatePassword,
                        )
                  )}
                  onRestart={() => (
                    selectedDeviceManagedLocally
                      ? void manageLocalPackage(selectedDevice, 'runtime', 'restart')
                      : void restartRemotePackage(selectedDevice, 'runtime')
                  )}
                  onUpdate={() => void updateDevice(selectedDevice, 'runtime', 'update')}
                  onReinstall={() => void updateDevice(
                    selectedDevice,
                    'runtime',
                    'reinstall',
                  )}
                  deleteEnabled={selectedDeviceManagedLocally}
                  onDelete={() => {
                    if (selectedDeviceManagedLocally) {
                      void manageLocalPackage(selectedDevice, 'runtime', 'delete')
                    }
                  }}
                />
                {selectedDevice.managed_runtime?.hardware_dir
                  || !selectedDeviceManagedLocally ? (
                  <SoftwarePackageSummaryCard
                    label="Hardware package"
                    path={
                      selectedDevice.managed_runtime.hardware_dir
                      || remoteHardwareServices
                      || 'No Hardware services attached'
                    }
                    detail={selectedDeviceManagedLocally
                      ? `Port ${selectedDevice.managed_runtime.hardware_port || 8765}`
                      : `${selectedDevice.robots.length} Hardware service${
                          selectedDevice.robots.length === 1 ? '' : 's'
                        } on ${runtimeHostname(selectedDevice.runtime_url)}`}
                    state={selectedHardwarePackageState}
                    currentVersion={hardwareCurrentVersion}
                    latestVersion={hardwareLatestVersion}
                    installed={
                      selectedDeviceManagedLocally
                        ? selectedDeviceState?.runtime?.hardware?.installed !== false
                        : Boolean(
                            selectedDevice.managed_runtime.hardware_dir
                            || selectedDevice.robots.length,
                          )
                    }
                    updateAvailable={checkedHardwareHasUpdate}
                    busy={busy}
                    onCheckLatest={() => void checkDeviceSoftware(selectedDevice)}
                    runStopEnabled={
                      selectedDeviceManagedLocally || selectedDevice.robots.length > 0
                    }
                    onRunStop={action => (
                      selectedDeviceManagedLocally
                        ? void manageLocalPackage(selectedDevice, 'hardware', action)
                        : void manageRemoteHardwarePackage(selectedDevice, action)
                    )}
                    restartEnabled={
                      selectedDeviceManagedLocally || selectedDevice.robots.length > 0
                    }
                    onRestart={() => (
                      selectedDeviceManagedLocally
                        ? void manageLocalPackage(selectedDevice, 'hardware', 'restart')
                        : void restartRemotePackage(selectedDevice, 'hardware')
                    )}
                    onUpdate={() => void updateDevice(selectedDevice, 'hardware', 'update')}
                    onReinstall={() => void updateDevice(
                      selectedDevice,
                      'hardware',
                      'reinstall',
                    )}
                    deleteEnabled={selectedDeviceManagedLocally}
                    onDelete={() => {
                      if (selectedDeviceManagedLocally) {
                        void manageLocalPackage(selectedDevice, 'hardware', 'delete')
                      }
                    }}
                  />
                ) : (
                  <div className="bn-local-package-missing">
                    <strong>Hardware package</strong>
                    <span>Reinstall the local stack to add this package.</span>
                  </div>
                )}
              </div>
              <span>
                {selectedDeviceManagedLocally
                  ? 'Hardware remains disconnected and motion stays disarmed until a physical robot is configured. Device checks, deployments, logs, and monitoring use the loopback connection.'
                  : 'Remote package actions use the verified SSH identity. Hardware restarts require every attached robot to be stopped and disarmed.'}
              </span>
            </div>
          )}

          {showSshManagement && !selectedDevice.managed_runtime && !selectedDeviceIsLocal && (
            <form
              className="bn-runtime-uninstall bn-ssh-management-form"
              onSubmit={event => void configureSshManagement(event, selectedDevice)}
            >
              <div className="bn-ssh-management-head">
                <span className="bn-ssh-management-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <path d="M7 10V8a5 5 0 0 1 10 0v2" />
                    <rect x="4" y="10" width="16" height="11" rx="3" />
                    <path d="M12 14v3" />
                  </svg>
                </span>
                <div>
                  <strong>Enable SSH lifecycle controls</strong>
                  <span>
                    Securely connect this paired computer so Blacknode can pause,
                    resume, and maintain its runtime.
                  </span>
                </div>
                <span className="bn-ssh-private-badge">
                  <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                    <path d="M4.75 7V5.5a3.25 3.25 0 0 1 6.5 0V7" />
                    <rect x="3" y="7" width="10" height="7" rx="2" />
                  </svg>
                  Password not saved
                </span>
              </div>

              <div className="bn-ssh-management-progress" aria-label="SSH setup progress">
                <span className="is-active">
                  <i>1</i>
                  Connection
                </span>
                <b aria-hidden="true" />
                <span className={managementProbe ? 'is-active' : ''}>
                  <i>2</i>
                  Verify & enable
                </span>
              </div>

              <div className="bn-ssh-runtime-target">
                <div>
                  <span>Paired runtime</span>
                  <code>{selectedDevice.runtime_url}</code>
                </div>
                <span className={`bn-ssh-identity-state${selectedDevice.remote_device_id ? ' is-known' : ''}`}>
                  <i aria-hidden="true" />
                  {selectedDevice.remote_device_id
                    ? `Identity ${selectedDevice.remote_device_id}`
                    : 'Identity verified during setup'}
                </span>
              </div>

              <div className="bn-ssh-management-fields">
                <label>
                  <span>Device IP address or hostname</span>
                  <input
                    value={managementHost}
                    onChange={event => {
                      setManagementHost(event.target.value)
                      setManagementProbe(null)
                    }}
                    placeholder="192.168.1.87"
                    autoComplete="off"
                    required
                  />
                  <small>The address used to reach this computer from Blacknode.</small>
                </label>
                <label className="bn-ssh-port-field">
                  <span>SSH port</span>
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    value={managementPort}
                    onChange={event => {
                      setManagementPort(Number(event.target.value))
                      setManagementProbe(null)
                    }}
                    required
                  />
                  <small>Usually 22</small>
                </label>
              </div>

              {managementProbe && (
                <>
                  <div className="bn-device-fingerprint bn-ssh-host-card">
                    <div>
                      <span className="bn-ssh-host-check" aria-hidden="true">
                        <svg viewBox="0 0 16 16" focusable="false">
                          <path d="m3.5 8.5 3 3 6-7" />
                        </svg>
                      </span>
                      <div>
                        <strong>SSH connection verified</strong>
                        <p>{managementProbe.hostname} · {managementProbe.os} · {managementProbe.architecture}</p>
                      </div>
                      <span className="bn-ssh-verified-badge">Host verified</span>
                    </div>
                    <span>Confirm the host key before entering your credentials.</span>
                    <code>{managementProbe.host_fingerprint}</code>
                  </div>
                  <div className="bn-ssh-management-fields is-auth">
                    <label>
                      <span>SSH username</span>
                      <input
                        value={managementUsername}
                        onChange={event => setManagementUsername(event.target.value)}
                        autoComplete="username"
                        placeholder="robot"
                        required
                      />
                    </label>
                    <label>
                      <span>SSH password</span>
                      <input
                        type="password"
                        value={managementPassword}
                        onChange={event => setManagementPassword(event.target.value)}
                        autoComplete="current-password"
                        placeholder="Enter password"
                        required
                      />
                    </label>
                  </div>
                </>
              )}

              <div className="bn-device-form-actions bn-ssh-management-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowSshManagement(false)
                    setManagementPassword('')
                    setManagementProbe(null)
                  }}
                  disabled={busy}
                  className="bn-ssh-cancel-button"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={
                    busy
                    || !managementHost.trim()
                    || (Boolean(managementProbe)
                      && (!managementUsername.trim() || !managementPassword))
                  }
                  style={primaryButton}
                  className="bn-ssh-submit-button"
                >
                  {busy
                    ? managementProbe ? 'Verifying runtime…' : 'Checking SSH…'
                    : managementProbe ? 'Confirm and enable' : 'Check SSH connection'}
                </button>
              </div>
            </form>
          )}

          {showRuntimeControl && selectedDevice.managed_runtime && !selectedDeviceManagedLocally && (
            <form
              className="bn-runtime-uninstall"
              onSubmit={event => {
                event.preventDefault()
                void controlDevice(
                  selectedDevice,
                  selectedDevice.paused ? 'resume' : 'pause',
                )
              }}
            >
              <div>
                <strong>
                  {selectedDevice.paused ? 'Resume this device' : 'Pause this device safely'}
                </strong>
                <span>
                  {selectedDevice.paused
                    ? 'Starts this runtime and reconnects attached robot monitoring. Robots remain disarmed; previous deployments stay stopped until you start them again.'
                    : 'Stops deployments, stops and disarms attached robots, then stops the runtime service.'}
                </span>
              </div>
              <label>
                <span>SSH password for {selectedDevice.managed_runtime.ssh_username}</span>
                <input
                  type="password"
                  value={runtimeControlPassword}
                  onChange={event => setRuntimeControlPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowRuntimeControl(false)
                    setRuntimeControlPassword('')
                  }}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} style={primaryButton}>
                  {busy
                    ? selectedDevice.paused ? 'Resuming…' : 'Pausing…'
                    : selectedDevice.paused ? 'Resume device' : 'Pause device'}
                </button>
              </div>
            </form>
          )}

          {/* Superseded by the always-visible package cards above. */}
          {showUpdateForm && selectedDevice.managed_runtime && showLegacyPackageManager && (
            <form
              className="bn-runtime-uninstall bn-device-update-form"
              onSubmit={event => {
                event.preventDefault()
                void checkDeviceSoftware(selectedDevice)
              }}
            >
              <div>
                <strong>Software packages</strong>
                <span>
                  Shows the Runtime and Hardware packages separately with their installed
                  and latest versions. Each local package can be run, stopped, restarted,
                  updated, reinstalled, or deleted independently.
                </span>
              </div>
              {!selectedDeviceManagedLocally && (
                <label className="bn-device-update-password">
                  <span>
                    <strong>SSH password</strong>
                    <small>
                      {selectedDevice.managed_runtime.ssh_username} · verified device · never saved
                    </small>
                  </span>
                  <input
                    type="password"
                    value={updatePassword}
                    onChange={event => setUpdatePassword(event.target.value)}
                    autoComplete="current-password"
                    placeholder="Enter SSH password"
                    spellCheck={false}
                    required
                  />
                </label>
              )}
              <div className="bn-device-update-caution">
                Checking versions never starts a stopped package. Updating or reinstalling
                preserves that package's running or stopped state. Deleting removes its
                installed environment while preserving source and configuration.
              </div>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowUpdateForm(false)
                    setUpdatePassword('')
                  }}
                  className="bn-device-action-button"
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} className="bn-device-action-button">
                  {busy ? 'Checking versions…' : 'Check installed vs latest'}
                </button>
              </div>
            </form>
          )}

          {showUpdateForm && updateCheckReport && showLegacyPackageManager && (
            <section className="bn-device-update-report" aria-label="Runtime and Hardware package version report">
              <div className="bn-device-update-report-head">
                <div>
                  <strong>
                    {checkedHardwareComponents.length
                      ? 'Runtime + Hardware package version report'
                      : 'Runtime package version report'}
                  </strong>
                  <span>{updateCheckReport.summary}</span>
                </div>
                <span>
                  {updateCheckReport.check.components.length} service
                  {updateCheckReport.check.components.length === 1 ? '' : 's'} checked
                </span>
              </div>
              <div className="bn-device-update-components">
                {checkedRuntimeComponents.map(component => (
                  <div
                    className="bn-device-update-component"
                    key={`check-${component.kind}-${component.service_name}-${component.port}`}
                  >
                    <div>
                      <strong>Runtime package</strong>
                      <code>{component.service_name} · port {component.port}</code>
                    </div>
                    <div className="bn-device-update-version">
                      <span>Installed → latest</span>
                      <strong>
                        {component.installed.version}
                        <i aria-hidden="true">→</i>
                        {component.latest.version}
                      </strong>
                      <code>
                        {component.installed.commit || 'unknown'}
                        {' → '}
                        {component.latest.commit || 'unknown'}
                      </code>
                    </div>
                    <div className="bn-device-update-row-actions">
                      <span
                        className={`bn-device-update-state${
                          component.error
                            ? ' is-blocked'
                            : component.update_available
                              ? ' is-changed'
                              : ''
                        }`}
                      >
                        {component.error
                          ? 'ATTENTION'
                          : component.update_available
                            ? 'UPDATE AVAILABLE'
                            : 'CURRENT'}
                      </span>
                      <button
                        type="button"
                        className={`bn-device-action-button${
                          component.update_available ? ' is-primary' : ''
                        }`}
                        disabled={
                          busy
                          || (!component.dirty && !selectedDeviceManagedLocally && !updatePassword)
                        }
                        title={component.dirty
                          ? 'Show how to preserve or remove local source changes before updating'
                          : component.error
                            ? 'Attempt to repair and reinstall the Runtime package'
                            : component.update_available
                              ? 'Update Runtime package'
                              : 'Reinstall current Runtime package'}
                        onClick={() => {
                          if (component.dirty) {
                            setShowDirtySourceHelp(current => !current)
                          } else {
                            void updateDevice(
                              selectedDevice,
                              'runtime',
                              component.environment_installed === false
                                ? 'reinstall'
                                : component.update_available
                                  ? 'update'
                                  : 'reinstall',
                            )
                          }
                        }}
                      >
                        {busy
                          ? 'Working…'
                          : component.dirty
                            ? showDirtySourceHelp
                              ? 'Hide repair steps'
                              : 'Resolve local changes'
                          : component.error
                            || component.environment_installed === false
                            || component.installed.version === 'unknown'
                            || component.latest.version === 'unknown'
                            ? 'Repair Runtime package'
                            : component.update_available
                              ? 'Update Runtime package'
                              : 'Reinstall Runtime package'}
                      </button>
                      {selectedDeviceManagedLocally && (
                        <>
                          <button
                            type="button"
                            className="bn-device-action-button"
                            disabled={busy || (
                              component.state !== 'running'
                              && component.state !== 'unreachable'
                              && component.environment_installed === false
                            )}
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'runtime',
                              component.state === 'running' || component.state === 'unreachable'
                                ? 'stop'
                                : 'run',
                            )}
                          >
                            {component.state === 'running' || component.state === 'unreachable'
                              ? 'Stop'
                              : 'Run'}
                          </button>
                          <button
                            type="button"
                            className="bn-device-action-button"
                            disabled={
                              busy
                              || component.environment_installed === false
                              || (
                                component.state !== 'running'
                                && component.state !== 'unreachable'
                              )
                            }
                            title="Restart only the local Runtime package service"
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'runtime',
                              'restart',
                            )}
                          >
                            Restart
                          </button>
                          <button
                            type="button"
                            className="bn-device-action-button is-danger"
                            disabled={busy || component.environment_installed === false}
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'runtime',
                              'delete',
                            )}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                    <small>
                      Service {component.state}
                      {' · '}reports {component.reported_version || 'version unavailable'}
                    </small>
                    {component.error && (
                      <small className="bn-device-update-component-error">
                        {component.error}
                      </small>
                    )}
                    {component.dirty && showDirtySourceHelp && (
                      <div className="bn-device-update-dirty-help">
                        <strong>Preserve or remove the local edits first</strong>
                        <span>
                          Blacknode keeps checkout changes intact. Connect over SSH,
                          inspect the edits, then commit or stash work you need before
                          checking versions again.
                        </span>
                        <code>
                          ssh {selectedDevice.managed_runtime?.ssh_username}
                          @{selectedDevice.managed_runtime?.ssh_host}
                        </code>
                        <code>
                          cd {selectedDevice.managed_runtime?.runtime_dir}
                        </code>
                        <code>git status --short &amp;&amp; git diff</code>
                      </div>
                    )}
                  </div>
                ))}
                {checkedHardwareInstallation && (
                  <div className="bn-device-update-component" key="check-hardware-shared">
                    <div>
                      <strong>Hardware package</strong>
                      <code>
                        {selectedDeviceManagedLocally
                          ? `Local package · service ${checkedHardwareInstallation.state}`
                          : `${selectedStackIsIsolated ? 'Isolated' : 'Shared'} installation · ${
                            checkedHardwareComponents.length
                          } robot service${checkedHardwareComponents.length === 1 ? '' : 's'}`}
                      </code>
                    </div>
                    <div className="bn-device-update-version">
                      <span>Installed → latest</span>
                      <strong>
                        {checkedHardwareInstallation.installed.version}
                        <i aria-hidden="true">→</i>
                        {checkedHardwareInstallation.latest.version}
                      </strong>
                      <code>
                        {checkedHardwareInstallation.installed.commit || 'unknown'}
                        {' → '}
                        {checkedHardwareInstallation.latest.commit || 'unknown'}
                      </code>
                    </div>
                    <div className="bn-device-update-row-actions">
                      <span
                        className={`bn-device-update-state${
                          checkedHardwareNeedsRepair
                            ? ' is-blocked'
                            : checkedHardwareHasUpdate
                              ? ' is-changed'
                              : ''
                        }`}
                      >
                        {checkedHardwareNeedsRepair
                          ? 'ATTENTION'
                          : checkedHardwareHasUpdate
                            ? 'UPDATE AVAILABLE'
                            : 'CURRENT'}
                      </span>
                      <button
                        type="button"
                        className={`bn-device-action-button${
                          checkedHardwareHasUpdate ? ' is-primary' : ''
                        }`}
                        disabled={
                          busy
                          || checkedHardwareIsDirty
                          || (!selectedDeviceManagedLocally && !updatePassword)
                        }
                        title={selectedDeviceManagedLocally
                          ? 'Update or reinstall only the local Hardware package'
                          : `Updates the shared Robot Hardware installation and restarts ${
                            checkedHardwareComponents.length
                          } robot service${checkedHardwareComponents.length === 1 ? '' : 's'}`}
                        onClick={() => void updateDevice(
                          selectedDevice,
                          'hardware',
                          checkedHardwareInstallation.environment_installed === false
                            ? 'reinstall'
                            : checkedHardwareHasUpdate
                              ? 'update'
                              : 'reinstall',
                        )}
                      >
                        {busy
                          ? 'Working…'
                          : checkedHardwareNeedsRepair
                            || checkedHardwareInstallation.environment_installed === false
                            ? 'Repair Hardware package'
                            : checkedHardwareHasUpdate
                              ? 'Update Hardware package'
                              : 'Reinstall Hardware package'}
                      </button>
                      {selectedDeviceManagedLocally && (
                        <>
                          <button
                            type="button"
                            className="bn-device-action-button"
                            disabled={busy || (
                              checkedHardwareInstallation.state !== 'running'
                              && checkedHardwareInstallation.state !== 'unreachable'
                              && checkedHardwareInstallation.environment_installed === false
                            )}
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'hardware',
                              checkedHardwareInstallation.state === 'running'
                                || checkedHardwareInstallation.state === 'unreachable'
                                ? 'stop'
                                : 'run',
                            )}
                          >
                            {checkedHardwareInstallation.state === 'running'
                              || checkedHardwareInstallation.state === 'unreachable'
                              ? 'Stop'
                              : 'Run'}
                          </button>
                          <button
                            type="button"
                            className="bn-device-action-button"
                            disabled={
                              busy
                              || checkedHardwareInstallation.environment_installed === false
                              || (
                                checkedHardwareInstallation.state !== 'running'
                                && checkedHardwareInstallation.state !== 'unreachable'
                              )
                            }
                            title="Restart only the local Hardware package service"
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'hardware',
                              'restart',
                            )}
                          >
                            Restart
                          </button>
                          <button
                            type="button"
                            className="bn-device-action-button is-danger"
                            disabled={
                              busy
                              || checkedHardwareInstallation.environment_installed === false
                            }
                            onClick={() => void manageLocalPackage(
                              selectedDevice,
                              'hardware',
                              'delete',
                            )}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                    <small>
                      {selectedDeviceManagedLocally
                        ? `Service reports ${
                          checkedHardwareInstallation.reported_version || 'version unavailable'
                        }`
                        : `Robot services: ${checkedHardwareComponents.map(component => (
                          `${robotNameForPort(component.port)} (port ${component.port}) — ${
                            component.error
                              ? 'attention'
                              : formatVersion(
                                component.reported_version || component.installed.version,
                              )
                          }`
                        )).join(' · ')}`}
                    </small>
                    {checkedHardwareComponents
                      .filter(component => Boolean(component.error))
                      .map(component => (
                        <small
                          className="bn-device-update-component-error"
                          key={`hardware-error-${component.port}`}
                        >
                          {robotNameForPort(component.port)}: {component.error}
                        </small>
                      ))}
                  </div>
                )}
                {checkedHardwareComponents.length === 0 && (
                  <div className="bn-device-update-empty">
                    <div>
                      <strong>No physical robot is attached to this Runtime</strong>
                      <span>
                        {selectedHardwareSiblingDevices.length
                          ? `The Hardware package on this computer is managed under ${
                            selectedHardwareSiblingDevices.map(device => device.name).join(', ')
                          }. Open that Runtime card to check or repair its shared package installation.`
                          : 'Attach a robot before checking or repairing the Hardware package.'}
                      </span>
                    </div>
                    {selectedHardwareSiblingDevices.map(device => (
                      <button
                        type="button"
                        className="bn-device-action-button"
                        key={`open-hardware-${device.id}`}
                        onClick={() => {
                          setSelectedDeviceId(device.id)
                          setUpdateCheckReport(null)
                          setUpdateReport(null)
                          setShowDirtySourceHelp(false)
                          setUpdatePassword('')
                          setShowUpdateForm(true)
                        }}
                      >
                        Open {device.name} packages
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {updateCheckReport.warnings.length > 0 && (
                <div className="bn-device-update-warnings">
                  {updateCheckReport.warnings.map(warning => (
                    <span key={warning}>{warning}</span>
                  ))}
                </div>
              )}
            </section>
          )}

          {showUpdateForm && updateReport && showLegacyPackageManager && (
            <section className="bn-device-update-report" aria-label="Runtime and Hardware package update report">
              <div className="bn-device-update-report-head">
                <div>
                  <strong>Runtime + Hardware package update report</strong>
                  <span>{updateReport.summary}</span>
                </div>
                <span>{updateReport.update.components.length} services checked</span>
              </div>
              <div className="bn-device-update-components">
                {updatedRuntimeComponents.map(component => (
                  <div
                    className="bn-device-update-component"
                    key={`${component.kind}-${component.service_name}-${component.port}`}
                  >
                    <div>
                      <strong>Runtime package</strong>
                      <code>{component.service_name} · port {component.port}</code>
                    </div>
                    <div className="bn-device-update-version is-result">
                      <span>
                        {component.changed
                          ? 'Before update → Installed now'
                          : 'Reinstalled version'}
                      </span>
                      {component.changed ? (
                        <>
                          <strong>
                            <span>{component.before.version}</span>
                            <i aria-hidden="true">→</i>
                            <span className="is-current">{component.after.version}</span>
                          </strong>
                          <code>
                            {component.before.commit}
                            {' → '}
                            <b>{component.after.commit}</b>
                          </code>
                        </>
                      ) : (
                        <>
                          <strong>
                            <span className="is-current">{component.after.version}</span>
                          </strong>
                          <code><b>{component.after.commit}</b></code>
                        </>
                      )}
                    </div>
                    <span className={`bn-device-update-state${component.changed ? ' is-changed' : ''}`}>
                      {component.changed ? 'UPDATE COMPLETE' : 'REINSTALLED'}
                    </span>
                    <small>
                      Running service confirms{' '}
                      <strong>{component.reported_version || 'version unavailable'}</strong>
                    </small>
                  </div>
                ))}
                {updatedHardwareInstallation && (
                  <div className="bn-device-update-component" key="hardware-shared-result">
                    <div>
                      <strong>Hardware package</strong>
                      <code>
                        Shared installation · {updatedHardwareComponents.length} robot
                        {' '}service{updatedHardwareComponents.length === 1 ? '' : 's'}
                      </code>
                    </div>
                    <div className="bn-device-update-version is-result">
                      <span>
                        {updatedHardwareComponents.some(component => component.changed)
                          ? 'Before update → Installed now'
                          : 'Reinstalled version'}
                      </span>
                      {updatedHardwareComponents.some(component => component.changed) ? (
                        <>
                          <strong>
                            <span>{updatedHardwareInstallation.before.version}</span>
                            <i aria-hidden="true">→</i>
                            <span className="is-current">
                              {updatedHardwareInstallation.after.version}
                            </span>
                          </strong>
                          <code>
                            {updatedHardwareInstallation.before.commit}
                            {' → '}
                            <b>{updatedHardwareInstallation.after.commit}</b>
                          </code>
                        </>
                      ) : (
                        <>
                          <strong>
                            <span className="is-current">
                              {updatedHardwareInstallation.after.version}
                            </span>
                          </strong>
                          <code><b>{updatedHardwareInstallation.after.commit}</b></code>
                        </>
                      )}
                    </div>
                    <span className={`bn-device-update-state${
                      updatedHardwareComponents.some(component => component.changed)
                        ? ' is-changed'
                        : ''
                    }`}>
                      {updatedHardwareComponents.some(component => component.changed)
                        ? 'UPDATE COMPLETE'
                        : 'REINSTALLED'}
                    </span>
                    <small>
                      Robot services:{' '}
                      {updatedHardwareComponents.map(component => (
                        `${robotNameForPort(component.port)} (port ${component.port}) — ${
                          formatVersion(component.reported_version)
                        }`
                      )).join(' · ')}
                    </small>
                  </div>
                )}
              </div>
              {updateReport.warnings.length > 0 && (
                <div className="bn-device-update-warnings">
                  {updateReport.warnings.map(warning => (
                    <span key={warning}>{warning}</span>
                  ))}
                </div>
              )}
            </section>
          )}

          {showUninstallForm && selectedDevice.managed_runtime && (
            <form
              className="bn-runtime-uninstall"
              onSubmit={event => {
                event.preventDefault()
                void uninstallDevice(selectedDevice)
              }}
            >
              <div>
                <strong>
                  {
                    selectedDeviceManagedLocally
                      && !selectedDevice.managed_runtime?.owned_install
                      ? 'Uninstall this managed '
                      : 'Delete this '
                  }
                  {
                    selectedDeviceManagedLocally
                      ? 'robot stack'
                      : 'device'
                  }
                </strong>
                <span>
                  {selectedDeviceManagedLocally
                    ? selectedDevice.managed_runtime.hardware_dir
                      ? `Stops the local Runtime on port ${selectedDevice.managed_runtime.runtime_port} and Robot Hardware on port ${selectedDevice.managed_runtime.hardware_port}.`
                      : `Stops the local Runtime on port ${selectedDevice.managed_runtime.runtime_port}.`
                    : `Stops ${selectedDevice.managed_runtime.service_name} and its deployments; deletes ${selectedDevice.managed_runtime.runtime_dir}, its workflow packages, token, service and port ${selectedDevice.managed_runtime.runtime_port} firewall rule; and deletes this device's ${selectedDevice.robots.length} Robot Hardware service${selectedDevice.robots.length === 1 ? '' : 's'} plus Hardware files when no other device uses them.${selectedDevice.managed_runtime.install_root ? ` The empty ${selectedDevice.managed_runtime.install_root} stack folder is also removed.` : ''}`}
                  {selectedDeviceManagedLocally
                    ? selectedDevice.managed_runtime.hardware_dir
                      ? selectedDevice.managed_runtime.owned_install
                        && selectedDevice.managed_runtime.hardware_owned_install
                        ? ' Both editor-created installation folders are removed.'
                        : ' Existing source checkouts are preserved.'
                      : selectedDevice.managed_runtime.owned_install
                        ? ' The editor-created installation folder is removed.'
                        : ' The existing source checkout is preserved.'
                    : ' System ROS 2, Docker, and other device stacks on this computer stay untouched.'}
                </span>
              </div>
              {!selectedDeviceManagedLocally && (
                <label>
                  <span>SSH password for {selectedDevice.managed_runtime.ssh_username}</span>
                  <input
                    type="password"
                    value={uninstallPassword}
                    onChange={event => setUninstallPassword(event.target.value)}
                    autoComplete="current-password"
                    disabled={busy}
                    required
                  />
                </label>
              )}
              {actionProgress[selectedDevice.id] && (
                <LifecycleProgress value={actionProgress[selectedDevice.id]} />
              )}
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowUninstallForm(false)
                    setUninstallPassword('')
                  }}
                  disabled={busy}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} style={dangerButton}>
                  {busy
                    ? 'Deleting…'
                    : selectedDeviceManagedLocally
                      && !selectedDevice.managed_runtime?.owned_install
                      ? 'Uninstall services and forget device'
                      : 'Delete device'}
                </button>
              </div>
            </form>
          )}

          {(showServiceDetails
            || selectedCheckHasFailure
            || selectedCheckHasStopped
            || selectedCheckHasUnknown) && (
          <div
            className={`bn-runtime-check-result${
              selectedDeviceChecking
                ? ' is-checking'
                : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                  ? ' is-paused'
                : selectedDeviceReady
                  ? ' is-ready'
                  : selectedCheckHasFailure
                    ? ' is-error'
                    : selectedCheckHasUnknown
                      ? ' is-warning'
                      : ''
            }`}
            role="status"
            aria-live="polite"
          >
            <span className="bn-runtime-check-dot" aria-hidden="true" />
            <div>
              <strong>
                {selectedDeviceChecking
                  ? 'Checking device services…'
                  : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                    ? 'Device paused'
                  : selectedDeviceReady
                    ? 'Device services ready'
                    : selectedCheckHasStopped
                      ? 'Software package stopped'
                    : selectedCheckHasFailure
                      ? 'Device needs attention'
                      : selectedCheckHasUnknown
                        ? 'Connection status incomplete'
                        : 'Device not checked'}
              </strong>
              <span>
                {selectedDeviceChecking
                  ? `Checking installed package services and ${selectedDevice.robots.length} attached robot${selectedDevice.robots.length === 1 ? '' : 's'}`
                  : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                    ? 'Deployments are stopped and attached robots are disarmed.'
                    : selectedCheckStarted
                      ? `${selectedReadyChecks}/${selectedServiceChecks.length} checks ready · Last checked ${formatCheckedAt(selectedLastChecked)}`
                      : 'Run Check device to verify installed package services and attached robots.'}
              </span>
              <div className="bn-runtime-check-services">
                {selectedServiceChecks.map(service => (
                  <div
                    key={service.id}
                    className={`bn-runtime-check-service is-${service.state}`}
                  >
                    <span className="bn-runtime-check-service-dot" aria-hidden="true" />
                    <div>
                      <strong>{service.name}</strong>
                      <span>{service.kind} · {service.detail}</span>
                    </div>
                    <span className="bn-runtime-check-service-state">
                      {service.state === 'unchecked'
                        ? 'NOT CHECKED'
                        : service.id.startsWith('packages:')
                          && service.state === 'connected'
                          ? 'READY'
                        : service.state === 'stopped'
                          ? 'STOPPED'
                        : service.state === 'awaiting'
                          ? 'AWAITING ROBOT'
                          : service.state.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          )}

          <div className="bn-compute-robots-head">
            <div>
              <strong>Attached robots</strong>
              <span>
                {selectedDevice.robots.length
                  ? `${selectedDevice.robots.length} attached to this device`
                  : 'Attach the robot hardware physically connected to this device'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => openRobotForm(selectedDevice)}
              disabled={busy}
              className="bn-device-action-button is-primary"
            >
              Attach robot
            </button>
          </div>

          {showRobotForm && (
            <form className="bn-device-form bn-robot-form" onSubmit={addRobot}>
              <div className="bn-device-form-title">
                Attach existing robot to {selectedDevice.name}
              </div>
              {selectedDevice.managed_runtime && !selectedDeviceManagedLocally && (
                <div className="bn-device-local-note" role="note">
                  <strong>
                    {selectedDevice.managed_runtime.hardware_dir
                      ? 'Find installed robots automatically'
                      : 'Install the Robot Hardware package'}
                  </strong>
                  <span>
                    {selectedDevice.managed_runtime.hardware_dir
                      ? 'Blacknode reads each installed Hardware service URL and pairing token through this device’s verified SSH connection. Tokens remain hidden and the SSH password is never saved.'
                      : 'This Runtime-only device is missing its managed Hardware package. Install it beside Runtime before configuring and attaching a physical robot.'}
                  </span>
                  <label>
                    <span>Device SSH password</span>
                    <input
                      type="password"
                      value={robotDiscoveryPassword}
                      onChange={event => setRobotDiscoveryPassword(event.target.value)}
                      placeholder={`Password for ${
                        selectedDevice.managed_runtime.ssh_username || 'SSH user'
                      }`}
                      autoComplete="current-password"
                    />
                  </label>
                  <button
                    type="button"
                    className="bn-device-action-button is-primary"
                    disabled={busy || !robotDiscoveryPassword}
                    onClick={() => (
                      selectedDevice.managed_runtime?.hardware_dir
                        ? void discoverAndAttachRobots()
                        : void installDeviceHardware()
                    )}
                  >
                    {busy
                      ? selectedDevice.managed_runtime.hardware_dir
                        ? 'Finding robots…'
                        : 'Installing Hardware…'
                      : selectedDevice.managed_runtime.hardware_dir
                        ? 'Find and attach robots'
                        : 'Install Hardware package'}
                  </button>
                </div>
              )}
              {selectedDevice.managed_runtime && !selectedDeviceManagedLocally && (
                <div className="bn-device-help">
                  Or enter one Hardware service manually below.
                </div>
              )}
              <label>
                <span>Robot name</span>
                <input
                  value={robotName}
                  onChange={event => setRobotName(event.target.value)}
                  placeholder="Follower arm"
                  autoComplete="off"
                />
              </label>
              <label>
                <span>Robot Hardware service URL</span>
                <input
                  value={robotUrl}
                  onChange={event => setRobotUrl(event.target.value)}
                  required
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                />
              </label>
              {hardwareUrlError(robotUrl) && (
                <div className="bn-device-recovery-hint" role="alert">
                  {hardwareUrlError(robotUrl)}
                </div>
              )}
              <label>
                <span>Robot hardware token</span>
                <input
                  type="password"
                  value={robotToken}
                  onChange={event => setRobotToken(event.target.value)}
                  placeholder="Paste token from pair.sh"
                  required
                  autoComplete="new-password"
                />
              </label>
              <div className="bn-device-help">
                This registers existing hardware under {selectedDevice.name}. After
                attaching, expand the robot card and choose Deploy workflow.
              </div>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowRobotForm(false)
                    setRobotToken('')
                    setRobotDiscoveryPassword('')
                  }}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} style={primaryButton}>
                  {busy ? 'Attaching…' : 'Attach and verify robot'}
                </button>
              </div>
            </form>
          )}

          <div className="bn-device-robot-list">
            {selectedDevice.robots.length === 0 && !showRobotForm && (
              <div className="bn-device-robot-empty">
                {selectedStackIsIsolated && selectedDevice.managed_runtime ? (
                  <>
                    <strong>Isolated Hardware environment ready</strong>
                    <span>
                      Connect the new robot, install only that serial device into this
                      stack, then attach the pairing details here.
                    </span>
                    <code>
                      cd {selectedDevice.managed_runtime.hardware_dir}
                    </code>
                    <code>
                      BLACKNODE_HARDWARE_INSTANCE={selectedDevice.managed_runtime.instance_id}
                      {' '}BLACKNODE_RUNTIME_PORT={selectedDevice.managed_runtime.runtime_port}
                      {' '}./configure.sh --all --install
                      {' '}--serial-port /dev/serial/by-id/NEW_ROBOT
                    </code>
                  </>
                ) : (
                  'This compute device is ready. Attach its physical robot to create a deployment target.'
                )}
              </div>
            )}
            {selectedDevice.robots.map(robot => (
              <RobotRow
                key={robot.id}
                robot={robot}
                state={robotStates[robot.id]}
                rosHealth={selectedRosHealth}
                actionProgress={actionProgress[robot.id]}
                installedSoftwareVersion={installedHardwareVersionForPort(
                  urlPort(robot.base_url),
                )}
                canRestartService={Boolean(
                  selectedDevice.managed_runtime && !selectedDeviceManagedLocally,
                )}
                sshUsername={selectedDevice.managed_runtime?.ssh_username}
                busy={busy}
                onRefresh={() => {
                  void refreshRobot(robot)
                }}
                onRename={() => renameRobot(robot)}
                onRemove={() => removeRobot(robot)}
                onDeploy={() => window.dispatchEvent(new CustomEvent(
                  'blacknode:open-panel',
                  { detail: { tab: 'deployments', deviceId: robot.id } },
                ))}
                onStopDeployment={deploymentId => stopDeployment(robot, deploymentId)}
                onStartDeployment={(deploymentId, deploymentName) => (
                  restartDeployment(robot, deploymentId, deploymentName)
                )}
                onSetDeploymentMotion={(deploymentId, deploymentName, armed) => (
                  setDeploymentMotion(robot, deploymentId, deploymentName, armed)
                )}
                onOpenDeployedGraph={(deploymentId, deploymentName) => (
                  openDeployedGraph(robot, deploymentId, deploymentName)
                )}
                onReleaseTorque={() => releaseRobotTorque(robot)}
                onControl={action => controlRobot(robot, action)}
                onRestartService={password => controlRobot(robot, 'restart', password)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ComputeDeviceCard({
  device,
  state,
  selected,
  onSelect,
}: {
  device: ComputeDevice
  state?: DeviceState
  selected: boolean
  onSelect: () => void
}) {
  const paused = Boolean(device.paused || state?.runtime?.paused)
  const ready = !paused && state?.runtime?.ok === true
  const stopped = !paused && state?.runtime?.state === 'stopped'
  const local = isLocalRuntimeUrl(device.runtime_url)
  const isolated = device.managed_runtime?.stack_mode === 'isolated'
  const label = state?.loading
    ? 'CHECKING'
    : paused
      ? 'PAUSED'
      : stopped
        ? 'STOPPED'
        : ready
          ? 'READY'
          : 'ATTENTION'
  const color = paused || stopped
    ? 'var(--tx3)'
    : ready
      ? 'var(--ok)'
      : state?.runtime
        ? 'var(--warn)'
        : 'var(--tx3)'
  return (
    <button
      type="button"
      className={`bn-compute-device-card${selected ? ' is-selected' : ''}`}
      style={{ '--device-status': color } as CSSProperties}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="bn-compute-device-card-top">
        <span className="bn-compute-device-kind">
          {local ? 'LOCAL' : isolated ? 'REMOTE · ISOLATED' : 'REMOTE'}
        </span>
        <span className="bn-compute-device-status">{label}</span>
      </span>
      <span className="bn-compute-device-card-body">
        <strong>{device.name}</strong>
        <span>{device.robots.length} {device.robots.length === 1 ? 'robot' : 'robots'}</span>
      </span>
    </button>
  )
}

function SoftwarePackageSummaryCard({
  label,
  path,
  detail,
  state,
  currentVersion,
  latestVersion,
  installed,
  updateAvailable,
  busy,
  onCheckLatest,
  runStopEnabled = true,
  restartEnabled = true,
  deleteEnabled = true,
  onRunStop,
  onRestart,
  onUpdate,
  onReinstall,
  onDelete,
}: {
  label: string
  path: string
  detail?: string
  state: string
  currentVersion: string
  latestVersion: string | null
  installed: boolean
  updateAvailable: boolean
  busy: boolean
  onCheckLatest: () => void
  runStopEnabled?: boolean
  restartEnabled?: boolean
  deleteEnabled?: boolean
  onRunStop: (action: 'run' | 'stop') => void
  onRestart: () => void
  onUpdate: () => void
  onReinstall: () => void
  onDelete: () => void
}) {
  const normalizedState = String(state || 'unchecked').toLowerCase()
  const running = ['running', 'unreachable', 'awaiting_device', 'configured'].includes(
    normalizedState,
  )
  const statusLabel = normalizedState === 'checking'
    ? 'CHECKING'
    : running && normalizedState !== 'unreachable'
      ? 'RUNNING'
      : normalizedState === 'stopped'
        ? 'STOPPED'
        : normalizedState === 'unreachable'
          ? 'UNREACHABLE'
          : normalizedState === 'unavailable'
            ? 'NOT INSTALLED'
            : 'NOT CHECKED'
  const statusTone = normalizedState === 'checking'
    ? 'checking'
    : running && normalizedState !== 'unreachable'
      ? 'running'
      : normalizedState === 'stopped'
        ? 'stopped'
        : normalizedState === 'unavailable'
          ? 'missing'
          : 'attention'

  return (
    <article className="bn-local-package-card">
      <div className="bn-local-package-card-head">
        <div>
          <strong>{label}</strong>
          <div className="bn-local-package-versions">
            <span className="is-current">
              <small>Current</small>
              <b>{currentVersion}</b>
            </span>
            <span className={latestVersion ? 'is-latest' : 'is-latest is-not-checked'}>
              <small>Latest</small>
              <b>{latestVersion ?? 'Not checked'}</b>
            </span>
          </div>
        </div>
        <span className={`bn-local-package-state is-${statusTone}`}>
          <i aria-hidden="true" />
          {statusLabel}
        </span>
      </div>
      <code title={path}>{path}</code>
      {detail && <small>{detail}</small>}
      <div className="bn-local-package-version-action">
        {!latestVersion ? (
          <button
            type="button"
            className="bn-local-package-check-latest"
            disabled={busy}
            onClick={onCheckLatest}
          >
            {busy ? 'Checking versions…' : 'Check updates'}
          </button>
        ) : updateAvailable ? (
          <div className="bn-local-package-update-available">
            Update available · {latestVersion}
          </div>
        ) : (
          <div className="bn-local-package-version-current">
            Current version installed
          </div>
        )}
      </div>
      <div className="bn-local-package-actions">
        <button
          type="button"
          className="bn-device-action-button"
          disabled={busy || !installed || !runStopEnabled}
          onClick={() => onRunStop(running ? 'stop' : 'run')}
        >
          {running ? 'Stop' : 'Run'}
        </button>
        <button
          type="button"
          className="bn-device-action-button"
          disabled={busy || !installed || !running || !restartEnabled}
          onClick={onRestart}
        >
          Restart
        </button>
        <button
          type="button"
          className={`bn-device-action-button${updateAvailable ? ' is-primary' : ''}`}
          disabled={busy}
          onClick={onUpdate}
        >
          Update
        </button>
        <button
          type="button"
          className="bn-device-action-button"
          disabled={busy}
          onClick={onReinstall}
        >
          Reinstall
        </button>
        <button
          type="button"
          className="bn-device-action-button is-danger"
          disabled={busy || !installed || !deleteEnabled}
          onClick={onDelete}
        >
          Delete
        </button>
      </div>
    </article>
  )
}

function RobotRow({
  robot,
  state,
  rosHealth,
  actionProgress,
  installedSoftwareVersion,
  canRestartService,
  sshUsername,
  busy,
  onRefresh,
  onRename,
  onRemove,
  onDeploy,
  onStopDeployment,
  onStartDeployment,
  onSetDeploymentMotion,
  onOpenDeployedGraph,
  onReleaseTorque,
  onControl,
  onRestartService,
}: {
  robot: HardwareDevice
  state?: RobotState
  rosHealth?: RosHealth
  actionProgress?: DeviceActionProgress
  installedSoftwareVersion: string
  canRestartService: boolean
  sshUsername?: string
  busy: boolean
  onRefresh: () => void
  onRename: () => void
  onRemove: () => void
  onDeploy: () => void
  onStopDeployment: (deploymentId: string) => void
  onStartDeployment: (deploymentId: string, deploymentName: string) => void
  onSetDeploymentMotion: (
    deploymentId: string,
    deploymentName: string,
    armed: boolean,
  ) => void
  onOpenDeployedGraph: (
    deploymentId: string,
    deploymentName: string,
  ) => void
  onReleaseTorque: () => void
  onControl: (action: 'pause' | 'resume') => void
  onRestartService: (password: string) => Promise<boolean>
}) {
  const [expanded, setExpanded] = useState(false)
  const [showMonitor, setShowMonitor] = useState(false)
  const [showRestart, setShowRestart] = useState(false)
  const [showTorqueDetails, setShowTorqueDetails] = useState(false)
  const [restartPassword, setRestartPassword] = useState('')
  const status = state?.status
  const deploymentLease = status?.deployment_lease
  const runningDeployment = deploymentLease ?? status?.running_deployment
  const inactiveDeployment = runningDeployment
    ? undefined
    : status?.inactive_deployment ?? status?.stored_deployment
  const torqueReleaseSupported = Boolean(
    status?.service_features?.includes('torque_release_v1'),
  )
  const torqueUnknownReason = status?.torque_report_error
    || (runningDeployment
      ? 'The running deployment owns the robot connection, so the monitoring service cannot read the servo torque registers.'
      : 'Robot Hardware did not receive a valid torque-register reading from every configured servo.')
  const mqttTelemetry = status?.telemetry?.sinks.find(sink => sink.name === 'mqtt')
  const paused = Boolean(robot.paused || status?.paused)
  const connected = Boolean(status?.connected)
  const armed = Boolean(status?.armed)
  const connectionState = state?.loading
    ? 'checking'
    : !status
      ? 'unreachable'
      : connected
        ? 'connected'
        : 'disconnected'
  const connectionLabel = {
    checking: 'CHECKING',
    connected: 'CONNECTED',
    disconnected: 'DISCONNECTED',
    unreachable: 'UNREACHABLE',
  }[connectionState]
  const connectionColor = {
    checking: 'var(--accent)',
    connected: 'var(--ok)',
    disconnected: 'var(--err)',
    unreachable: 'var(--err)',
  }[connectionState]
  const deploymentState = runningDeployment ? 'running' : inactiveDeployment?.state
  const deploymentLabel = deploymentState === 'running'
    ? 'ACTIVE'
    : deploymentState === 'failed'
      ? 'FAILED'
      : deploymentState === 'exited'
        ? 'COMPLETED'
        : deploymentState
          ? 'INACTIVE'
          : 'NONE'
  const deploymentColor = deploymentState === 'running'
    ? 'var(--ok)'
    : deploymentState === 'failed'
      ? 'var(--err)'
      : deploymentState === 'exited'
        ? 'var(--tx2)'
      : 'var(--tx3)'
  const rosLabel = rosHealth?.state === 'healthy'
    ? 'ENDPOINTS'
    : rosHealth?.state === 'warning'
      ? 'WARNING'
      : rosHealth?.state === 'error'
        ? 'ATTENTION'
        : rosHealth?.state === 'unavailable'
          ? 'UNAVAILABLE'
          : rosHealth?.state === 'checking'
            ? 'CHECKING'
            : 'NOT CHECKED'
  const rosColor = rosHealth?.state === 'healthy'
    ? 'var(--ok)'
    : rosHealth?.state === 'warning'
      ? 'var(--warn)'
      : rosHealth?.state === 'error'
        ? 'var(--err)'
        : 'var(--tx3)'
  const summary = state?.loading
    ? 'Checking robot hardware…'
    : !status
      ? 'Robot Hardware service unreachable'
      : connected
        ? `Hardware connected · motion ${armed ? 'armed' : 'disarmed'}${paused ? ' · paused' : ''}`
        : status.connection_reported === false && status.notice
          ? status.notice
          : `Hardware disconnected${paused ? ' · robot paused and disarmed' : ''}`

  return (
    <div
      className={`bn-run-row bn-device-card${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': connectionColor } as CSSProperties}
    >
      <button
        type="button"
        className="bn-device-card-summary"
        aria-expanded={expanded}
        onClick={() => setExpanded(value => !value)}
      >
        <span className="bn-device-card-dot" aria-hidden="true" />
        <span className="bn-device-card-main">
          <strong>{robot.name}</strong>
          <span>{summary}</span>
        </span>
        <span className="bn-device-card-statuses">
          <span
            className="bn-device-card-state"
            style={{ '--device-status-color': connectionColor } as CSSProperties}
          >
            <small>Connection</small>
            {connectionLabel}
          </span>
          <span
            className="bn-device-card-state"
            style={{ '--device-status-color': deploymentColor } as CSSProperties}
          >
            <small>Deployment</small>
            {deploymentLabel}
          </span>
          <span
            className="bn-device-card-state"
            style={{ '--device-status-color': rosColor } as CSSProperties}
            title={rosHealth?.issues[0] || rosHealth?.summary}
          >
            <small>ROS 2</small>
            {rosLabel}
          </span>
        </span>
        <span className="bn-device-card-chevron" aria-hidden="true">›</span>
      </button>
      {!expanded && runningDeployment?.id && (
        <div className="bn-device-card-quick-actions">
          <span title={runningDeployment.name}>
            Running · {runningDeployment.name}
          </span>
          <button
            type="button"
            onClick={() => onOpenDeployedGraph(
              runningDeployment.id,
              runningDeployment.name,
            )}
            disabled={busy || state?.loading}
            className="bn-device-action-button"
          >
            Open graph
          </button>
          {Number(runningDeployment.motion_control_count || 0) === 1 && (
            <button
              type="button"
              onClick={() => onSetDeploymentMotion(
                runningDeployment.id,
                runningDeployment.name,
                !runningDeployment.motion_armed,
              )}
              disabled={busy || state?.loading || paused}
              className={`bn-device-action-button${
                runningDeployment.motion_armed ? ' is-danger' : ' is-primary'
              }`}
            >
              {runningDeployment.motion_armed ? 'Disarm' : 'Arm follower'}
            </button>
          )}
        </div>
      )}
      {expanded && (
        <div className="bn-run-detail bn-device-card-detail">
          <div className="bn-device-card-addresses">
            <span title={robot.base_url}>Hardware · {robot.base_url}</span>
            <span title={robot.runtime_url}>Deployment runtime · {robot.runtime_url}</span>
          </div>
          <div className="bn-run-badges">
            <span>{robot.remote_device_id}</span>
            <span>token {robot.token_fingerprint}</span>
            {status?.joint_names && <span>{status.joint_names.length} joints</span>}
          </div>
          {state?.error && (
            <div className="bn-run-error-line bn-device-error" role="alert">{state.error}</div>
          )}
          {actionProgress && <LifecycleProgress value={actionProgress} compact />}
          <div
            className={`bn-device-lease-notice${
              deploymentLease
                ? ' is-active'
                : runningDeployment
                  ? ' is-running'
                  : inactiveDeployment
                    ? ' is-inactive'
                    : ''
            }`}
            role="status"
          >
            <strong>Deployment</strong>
            <span>
              {deploymentLease
                ? status?.notice || `“${deploymentLease.name}” is running.`
                : runningDeployment
                  ? status?.notice || `“${runningDeployment.name}” is running without motion control.`
                : inactiveDeployment
                  ? status?.notice || `“${inactiveDeployment.name}” is ${inactiveDeployment.state} and can be restarted.`
                : 'No deployment currently controls this robot.'}
            </span>
          </div>
          <div className="bn-device-facts">
            <DeviceFact
              label="Motion"
              value={deploymentLease
                ? `Workflow · ${deploymentLease.name}`
                : runningDeployment
                  ? `Running · ${runningDeployment.name}`
                : status
                  ? status.armed ? 'Armed' : 'Disarmed'
                  : 'Unknown'}
              warn={!deploymentLease && Boolean(status?.armed)}
            />
            <DeviceFact
              label="Physical torque"
              value={status?.torque_enabled == null ? 'Unknown' : status.torque_enabled ? 'On' : 'Off'}
              warn={Boolean(status && status.torque_enabled !== false)}
              title={status?.torque_enabled == null
                ? `${showTorqueDetails ? 'Hide' : 'Show'} why physical torque is unknown`
                : undefined}
              onClick={status && status.torque_enabled == null
                ? () => setShowTorqueDetails(value => !value)
                : undefined}
              expanded={showTorqueDetails}
            />
            <DeviceFact
              label="Calibrated"
              value={status?.calibrated == null ? '—' : status.calibrated ? 'Yes' : 'No'}
            />
            <DeviceFact
              label="Robot Hardware version"
              value={status?.software_version
                ? `v${status.software_version}${
                  status.software_version_cached ? ' (last verified)' : ''
                }`
                : installedSoftwareVersion
                  ? `v${installedSoftwareVersion} (installed)`
                  : 'Not reported'}
            />
            <DeviceFact label="Connection" value={connectionLabel} warn={!connected} />
            {mqttTelemetry && (
              <DeviceFact
                label="MQTT telemetry"
                value={mqttTelemetry.connected
                  ? 'Connected'
                  : mqttTelemetry.error
                    ? 'Attention'
                    : 'Connecting'}
                warn={!mqttTelemetry.connected}
                title={
                  mqttTelemetry.error
                  || `${mqttTelemetry.broker || 'MQTT broker'} · ${
                    mqttTelemetry.published ?? 0
                  } samples published`
                }
              />
            )}
            <DeviceFact label="Last check" value={formatCheckedAt(state?.checkedAt)} />
          </div>
          {status
            && status.torque_enabled !== false
            && (status.torque_enabled === true || showTorqueDetails)
            && (
            <div
              className={`bn-device-torque-warning${
                status.torque_enabled == null ? ' is-unknown' : ''
              }`}
              role={status.torque_enabled === true ? 'alert' : 'status'}
            >
              <div>
                <strong>
                  {status.torque_enabled === true
                    ? 'Physical torque is on'
                    : 'Physical torque state is unknown'}
                </strong>
                <span>
                  {status.torque_enabled === true
                    ? 'Motion is disarmed, but the servos are still holding.'
                    : torqueUnknownReason}
                  {' '}Treat the servos as possibly holding torque. Support the robot
                  before releasing it because its joints may move or drop.
                  {!runningDeployment && !torqueReleaseSupported
                    ? ' Update Robot Hardware to enable the remote torque-off action.'
                    : ''}
                </span>
              </div>
              {!runningDeployment && (
                <button
                  type="button"
                  onClick={onReleaseTorque}
                  disabled={busy || state?.loading || paused || !torqueReleaseSupported}
                  title={torqueReleaseSupported
                    ? 'Send torque-off to every configured servo, then verify when register reads are available'
                    : 'Update Robot Hardware before releasing torque remotely'}
                  className="bn-device-action-button is-danger"
                >
                  Release torque
                </button>
              )}
            </div>
          )}
          <div className="bn-run-detail-actions bn-robot-card-actions is-primary">
            {runningDeployment?.id
              && Number(runningDeployment.motion_control_count || 0) === 1
              && (
                <button
                  type="button"
                  onClick={() => onSetDeploymentMotion(
                    runningDeployment.id,
                    runningDeployment.name,
                    !runningDeployment.motion_armed,
                  )}
                  disabled={busy || state?.loading || paused}
                  className={`bn-device-action-button${
                    runningDeployment.motion_armed ? ' is-danger' : ' is-primary'
                  }`}
                  title={runningDeployment.motion_armed
                    ? 'Disarm the follower controller and request torque release'
                    : 'Explicitly arm the follower controller after safety confirmation'}
                >
                  {runningDeployment.motion_armed ? 'Disarm follower' : 'Arm follower'}
                </button>
              )}
            <button
              onClick={() => {
                if (inactiveDeployment?.id) {
                  onStartDeployment(inactiveDeployment.id, inactiveDeployment.name)
                } else {
                  onDeploy()
                }
              }}
              disabled={busy || state?.loading || paused}
              className="bn-device-action-button is-primary"
              title={paused
                ? `Resume this robot before ${
                  inactiveDeployment ? 'restarting its deployment' : 'deploying a workflow'
                }`
                : inactiveDeployment
                  ? `Start the ${inactiveDeployment.state} deployment`
                  : 'Open deployment setup and history for this robot'}
            >
              {inactiveDeployment ? 'Restart deployment' : 'Deploy workflow'}
            </button>
            <button
              type="button"
              onClick={() => setShowMonitor(current => !current)}
              className="bn-device-action-button"
              aria-expanded={showMonitor}
              title="Show live telemetry inside this robot card"
            >
              {showMonitor ? 'Hide monitor' : 'Monitor'}
            </button>
            {runningDeployment?.id && (
              <button
                type="button"
                onClick={() => onOpenDeployedGraph(
                  runningDeployment.id,
                  runningDeployment.name,
                )}
                disabled={busy || state?.loading}
                className="bn-device-action-button"
                title="Open the exact active deployment revision in a new editable graph tab"
              >
                Open deployed graph
              </button>
            )}
            <button
              onClick={() => onControl(paused ? 'resume' : 'pause')}
              disabled={busy || state?.loading}
              className={`bn-device-action-button${paused ? ' is-primary' : ''}`}
            >
              {paused ? 'Resume robot' : 'Pause robot'}
            </button>
            <button
              onClick={() => {
                if (runningDeployment?.id) {
                  onStopDeployment(runningDeployment.id)
                } else if (inactiveDeployment) {
                  onDeploy()
                }
              }}
              disabled={busy || state?.loading || (!runningDeployment?.id && !inactiveDeployment)}
              title={runningDeployment?.id
                ? 'Stop the workflow running on this robot'
                : inactiveDeployment
                  ? 'Open this robot’s deployment and revision history'
                  : 'No deployment exists for this robot'}
              className="bn-device-action-button"
            >
              {inactiveDeployment ? 'Deployment details' : 'Stop deployment'}
            </button>
          </div>
          {showMonitor && (
            <div className="bn-device-inline-monitor">
              <RobotLiveMonitor
                robotId={robot.id}
                robotName={robot.name}
                emptyMessage=""
              />
            </div>
          )}
          <div className="bn-run-detail-actions bn-robot-card-actions is-secondary">
            <button
              onClick={onRefresh}
              disabled={busy || state?.loading}
              className="bn-device-action-button"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={() => {
                setShowRestart(value => !value)
                setRestartPassword('')
              }}
              disabled={busy || state?.loading || !canRestartService}
              title={canRestartService
                ? 'Restart the exact remote blacknode-hardware systemd service for this port'
                : 'Open the compute device and choose Enable SSH controls first'}
              className="bn-device-action-button"
            >
              Restart Robot Hardware
            </button>
            <button onClick={onRename} disabled={busy} className="bn-device-action-button">
              Rename
            </button>
            <button onClick={onRemove} disabled={busy} className="bn-device-action-button is-danger">
              Remove
            </button>
          </div>
          {showRestart && canRestartService && (
            <form
              className="bn-runtime-uninstall bn-robot-restart-form"
              onSubmit={event => {
                event.preventDefault()
                if (!window.confirm(
                  `Restart the hardware service for "${robot.name}"? The service will return with Blacknode motion disarmed.`,
                )) return
                void onRestartService(restartPassword).then(restarted => {
                  if (restarted) {
                    setShowRestart(false)
                    setRestartPassword('')
                  }
                })
              }}
            >
              <div>
                  <strong>Restart Robot Hardware for this robot</strong>
                <span>
                  Blacknode resolves the exact systemd unit from hardware port
                  {' '}{new URL(robot.base_url).port}, restarts only that unit, and verifies
                  the same authenticated robot returns.
                </span>
              </div>
              <label>
                <span>SSH password for {sshUsername || 'the compute device user'}</span>
                <input
                  type="password"
                  value={restartPassword}
                  onChange={event => setRestartPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowRestart(false)
                    setRestartPassword('')
                  }}
                  disabled={busy}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy || !restartPassword} style={primaryButton}>
                  {busy ? 'Restarting…' : 'Restart service'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  )
}

function LifecycleProgress({
  value,
  compact = false,
}: {
  value: DeviceActionProgress
  compact?: boolean
}) {
  const failed = value.progress <= 0 && value.message.toLowerCase().includes('failed')
  return (
    <div
      className={`bn-device-install-progress bn-device-action-progress${compact ? ' is-compact' : ''}${failed ? ' is-error' : ''}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value.progress}
      aria-label={value.message}
    >
      <div>
        <strong>{value.message}</strong>
        <span>{value.progress}%</span>
      </div>
      <span className="bn-device-install-progress-track" aria-hidden="true">
        <span style={{ width: `${value.progress}%` }} />
      </span>
    </div>
  )
}

function formatCheckedAt(checkedAt?: number): string {
  return checkedAt ? new Date(checkedAt).toLocaleTimeString() : '—'
}

function DeviceFact({
  label,
  value,
  warn = false,
  title,
  onClick,
  expanded = false,
}: {
  label: string
  value: string
  warn?: boolean
  title?: string
  onClick?: () => void
  expanded?: boolean
}) {
  const content = (
    <>
      <span>
        {label}
        {onClick && <i aria-hidden="true">›</i>}
      </span>
      <strong style={warn ? { color: 'var(--warn)' } : undefined}>{value}</strong>
    </>
  )
  return onClick ? (
    <button
      type="button"
      className="bn-device-fact is-interactive"
      title={title}
      onClick={onClick}
      aria-expanded={expanded}
    >
      {content}
    </button>
  ) : (
    <div className="bn-device-fact" title={title}>{content}</div>
  )
}

const miniButton: CSSProperties = {
  background: 'var(--lift)',
  border: '1px solid var(--line2)',
  color: 'var(--tx2)',
  padding: '3px 8px',
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

const dangerButton: CSSProperties = {
  ...miniButton,
  borderColor: 'var(--err)',
  color: 'var(--err)',
}
