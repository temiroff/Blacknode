import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import {
  api,
  type ComputeDevice,
  type DeviceActionProgress,
  type DeviceInstallProgress,
  type DeviceRuntimeStatus,
  type HardwareDevice,
  type HardwareDeviceStatus,
  type SshDeviceProbe,
  type SshRuntimeInspection,
} from '../api'
import { useStore } from '../store'

type RobotState = {
  status?: HardwareDeviceStatus
  error?: string
  loading?: boolean
  checkedAt?: number
}

type DeviceState = {
  runtime?: DeviceRuntimeStatus
  loading?: boolean
  checkedAt?: number
}

type RuntimeInstallAction = 'install' | 'reuse' | 'replace' | 'side_by_side'

const DEFAULT_RUNTIME_URL = 'http://192.168.1.87:8766'
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

export default function DevicesPanel() {
  const activeProject = useStore(state => state.activeProject)
  const setActiveProject = useStore(state => state.setActiveProject)
  const [devices, setDevices] = useState<ComputeDevice[]>([])
  const [deviceStates, setDeviceStates] = useState<Record<string, DeviceState>>({})
  const [robotStates, setRobotStates] = useState<Record<string, RobotState>>({})
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  const [showDeviceForm, setShowDeviceForm] = useState(false)
  const [setupMode, setSetupMode] = useState<'automatic' | 'manual'>('automatic')
  const [deviceName, setDeviceName] = useState('')
  const [runtimeUrl, setRuntimeUrl] = useState(DEFAULT_RUNTIME_URL)
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
  const [showUninstallForm, setShowUninstallForm] = useState(false)
  const [uninstallPassword, setUninstallPassword] = useState('')
  const [showRobotForm, setShowRobotForm] = useState(false)
  const [robotName, setRobotName] = useState('')
  const [robotUrl, setRobotUrl] = useState('')
  const [robotToken, setRobotToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [linkedProjectName, setLinkedProjectName] = useState('')

  const selectedDevice = devices.find(device => device.id === selectedDeviceId) ?? null
  const selectedDeviceState = selectedDevice
    ? deviceStates[selectedDevice.id]
    : undefined

  const refreshRobot = async (robot: HardwareDevice) => {
    setRobotStates(previous => ({
      ...previous,
      [robot.id]: { ...previous[robot.id], loading: true },
    }))
    try {
      const status = await api.deviceStatus(robot.id)
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: { status, loading: false, checkedAt: Date.now() },
      }))
    } catch (reason) {
      setRobotStates(previous => ({
        ...previous,
        [robot.id]: {
          loading: false,
          checkedAt: Date.now(),
          error: reason instanceof Error ? reason.message : String(reason),
        },
      }))
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
      await Promise.all([
        ...result.devices.map(refreshDevice),
        ...result.devices.flatMap(device => device.robots.map(refreshRobot)),
      ])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const resetDeviceForm = () => {
    setShowDeviceForm(false)
    setDeviceName('')
    setRuntimeToken('')
    setSshPassword('')
    setSshProbe(null)
    setSshInspection(null)
    setInstallAction('install')
    setInstallInstanceId('default')
    setInstallProgress(null)
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
    setError(null)
    setShowRobotForm(true)
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
    if (!window.confirm(`Remove "${device.name}" from this Blacknode editor?`)) return
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
    if (!uninstallPassword) {
      setError('Enter the SSH password to uninstall this managed runtime.')
      return
    }
    if (!window.confirm(
      `Uninstall "${device.name}" from the remote computer? This stops its runtime, removes its service, files, token, firewall rule, attached robot registrations, and this device card.`,
    )) return
    setBusy(true)
    setError(null)
    try {
      await api.uninstallComputeDevice(device.id, uninstallPassword)
      setShowUninstallForm(false)
      setUninstallPassword('')
      setSelectedDeviceId(null)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const controlDevice = async (device: ComputeDevice, action: 'pause' | 'resume') => {
    if (!runtimeControlPassword) {
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
        runtimeControlPassword,
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
          <button onClick={refresh} disabled={busy} style={miniButton}>Refresh</button>
          <button
            onClick={() => {
              setSelectedDeviceId(null)
              setShowDeviceForm(true)
              setShowRobotForm(false)
              setError(null)
            }}
            disabled={busy}
            style={primaryButton}
          >
            Add device
          </button>
        </div>
      </div>

      {showDeviceForm && (
        <form
          className="bn-device-form"
          onSubmit={setupMode === 'automatic' ? automaticInstall : manualPair}
        >
          <div className="bn-device-form-title">Add a compute device</div>
          <p className="bn-device-help">
            A device runs Blacknode Runtime. Add its robot hardware after the runtime is ready.
          </p>
          <div className="bn-device-mode-tabs" role="tablist" aria-label="Device setup method">
            <button
              type="button"
              className={setupMode === 'automatic' ? 'is-active' : ''}
              onClick={() => {
                setSetupMode('automatic')
                setError(null)
              }}
            >
              Automatic SSH
            </button>
            <button
              type="button"
              className={setupMode === 'manual' ? 'is-active' : ''}
              onClick={() => {
                setSetupMode('manual')
                setError(null)
              }}
            >
              Pair manually
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
                          <strong>Install Blacknode Runtime</strong>
                          <small>Creates the default isolated service on port {sshInspection.suggested_port}.</small>
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
                  </div>
                </div>
              )}
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

          {installProgress && setupMode === 'automatic' && (
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
              <button type="submit" disabled={busy} style={primaryButton}>
                {busy
                  ? setupMode === 'automatic'
                    ? sshInspection ? installAction === 'reuse' ? 'Pairing…' : 'Installing…' : 'Inspecting…'
                    : 'Pairing…'
                  : setupMode === 'automatic'
                    ? sshInspection
                      ? installAction === 'reuse' ? 'Pair existing runtime' : installAction === 'replace' ? 'Reinstall runtime' : 'Install runtime'
                      : 'Confirm and inspect'
                    : 'Pair runtime'}
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
            <button type="button" onClick={() => setShowDeviceForm(true)} style={primaryButton}>
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
                  setShowDeviceForm(false)
                  setShowRobotForm(false)
                }}
              />
            ))}
          </div>
        )
      )}

      {selectedDevice && (
        <section className="bn-compute-device-detail">
          <div className="bn-compute-device-detail-head">
            <div>
              <button
                type="button"
                className="bn-device-back-button"
                onClick={() => {
                  setSelectedDeviceId(null)
                  setShowRobotForm(false)
                  setShowUninstallForm(false)
                  setShowRuntimeControl(false)
                  setUninstallPassword('')
                  setRuntimeControlPassword('')
                  setError(null)
                }}
              >
                <span className="bn-device-back-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <path d="M15 5 8 12l7 7" />
                  </svg>
                </span>
                Back to all devices
              </button>
              <span>Compute device</span>
              <strong>{selectedDevice.name}</strong>
              <code>{selectedDevice.runtime_url}</code>
            </div>
            <div className="bn-run-detail-actions">
              <button
                onClick={() => refreshDevice(selectedDevice)}
                disabled={busy || selectedDeviceState?.loading}
                className={`bn-runtime-check-button${selectedDeviceState?.loading ? ' is-checking' : ''}`}
              >
                {selectedDeviceState?.loading ? 'Checking runtime…' : 'Check runtime'}
              </button>
              <button onClick={() => renameDevice(selectedDevice)} disabled={busy} style={miniButton}>
                Rename
              </button>
              {selectedDevice.managed_runtime && (
                <>
                  <button
                    onClick={() => {
                      setShowRuntimeControl(current => !current)
                      setShowUninstallForm(false)
                      setRuntimeControlPassword('')
                      setError(null)
                    }}
                    disabled={busy}
                    style={selectedDevice.paused ? primaryButton : miniButton}
                  >
                    {selectedDevice.paused ? 'Resume device' : 'Pause device'}
                  </button>
                  <button
                    onClick={() => {
                      setShowUninstallForm(current => !current)
                      setShowRuntimeControl(false)
                      setUninstallPassword('')
                      setError(null)
                    }}
                    disabled={busy}
                    style={dangerButton}
                  >
                    Uninstall runtime
                  </button>
                </>
              )}
              <button onClick={() => removeDevice(selectedDevice)} disabled={busy} style={dangerButton}>
                Remove from editor
              </button>
            </div>
          </div>

          {showRuntimeControl && selectedDevice.managed_runtime && (
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

          {actionProgress[selectedDevice.id] && (
            <LifecycleProgress value={actionProgress[selectedDevice.id]} />
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
                <strong>Uninstall this managed runtime</strong>
                <span>
                  Stops {selectedDevice.managed_runtime.service_name}, removes only
                  {' '}{selectedDevice.managed_runtime.runtime_dir}, its token and port
                  {' '}{selectedDevice.managed_runtime.runtime_port} firewall rule. Other runtime
                  instances on this computer stay untouched.
                </span>
              </div>
              <label>
                <span>SSH password for {selectedDevice.managed_runtime.ssh_username}</span>
                <input
                  type="password"
                  value={uninstallPassword}
                  onChange={event => setUninstallPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowUninstallForm(false)
                    setUninstallPassword('')
                  }}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} style={dangerButton}>
                  {busy ? 'Uninstalling…' : 'Uninstall and remove device'}
                </button>
              </div>
            </form>
          )}

          <div
            className={`bn-runtime-check-result${
              selectedDeviceState?.loading
                ? ' is-checking'
                : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                  ? ' is-paused'
                : selectedDeviceState?.runtime?.ok
                  ? ' is-ready'
                  : ' is-error'
            }`}
            role="status"
            aria-live="polite"
          >
            <span className="bn-runtime-check-dot" aria-hidden="true" />
            <div>
              <strong>
                {selectedDeviceState?.loading
                  ? 'Checking runtime…'
                  : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                    ? 'Runtime paused'
                  : selectedDeviceState?.runtime?.ok
                    ? 'Runtime connected'
                    : 'Runtime unavailable'}
              </strong>
              <span>
                {selectedDeviceState?.loading
                  ? `Contacting ${selectedDevice.runtime_url}`
                  : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                    ? 'Deployments are stopped and attached robots are disarmed.'
                  : selectedDeviceState?.runtime?.ok
                    ? `Last checked ${formatCheckedAt(selectedDeviceState.checkedAt)}`
                    : selectedDeviceState?.runtime?.error || 'The runtime has not been checked yet.'}
              </span>
            </div>
          </div>

          <div className="bn-compute-robots-head">
            <div>
              <strong>Robots</strong>
              <span>
                {selectedDevice.robots.length
                  ? `${selectedDevice.robots.length} attached to this device`
                  : 'Add the robot hardware connected to this device'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => openRobotForm(selectedDevice)}
              disabled={busy}
              style={primaryButton}
            >
              Add robot
            </button>
          </div>

          {showRobotForm && (
            <form className="bn-device-form bn-robot-form" onSubmit={addRobot}>
              <div className="bn-device-form-title">Add robot to {selectedDevice.name}</div>
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
                <span>Hardware service URL</span>
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
                This pairs hardware only. Deployments automatically use the runtime on{' '}
                {selectedDevice.name}.
              </div>
              <div className="bn-device-form-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowRobotForm(false)
                    setRobotToken('')
                  }}
                  style={miniButton}
                >
                  Cancel
                </button>
                <button type="submit" disabled={busy} style={primaryButton}>
                  {busy ? 'Adding…' : 'Add and verify robot'}
                </button>
              </div>
            </form>
          )}

          <div className="bn-device-robot-list">
            {selectedDevice.robots.length === 0 && !showRobotForm && (
              <div className="bn-device-robot-empty">
                This device is ready. Add a robot to create a deployment target.
              </div>
            )}
            {selectedDevice.robots.map(robot => (
              <RobotRow
                key={robot.id}
                robot={robot}
                state={robotStates[robot.id]}
                runtimeReady={deviceStates[selectedDevice.id]?.runtime?.ok === true}
                actionProgress={actionProgress[robot.id]}
                canRestartService={Boolean(selectedDevice.managed_runtime)}
                sshUsername={selectedDevice.managed_runtime?.ssh_username}
                busy={busy}
                onRefresh={() => refreshRobot(robot)}
                onRename={() => renameRobot(robot)}
                onRemove={() => removeRobot(robot)}
                onStopDeployment={deploymentId => stopDeployment(robot, deploymentId)}
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
  const label = state?.loading ? 'CHECKING' : paused ? 'PAUSED' : ready ? 'READY' : 'ATTENTION'
  const color = paused ? 'var(--tx3)' : ready ? 'var(--ok)' : state?.runtime ? 'var(--warn)' : 'var(--tx3)'
  return (
    <button
      type="button"
      className={`bn-compute-device-card${selected ? ' is-selected' : ''}`}
      style={{ '--device-status': color } as CSSProperties}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="bn-compute-device-card-top">
        <span className="bn-compute-device-status">{label}</span>
      </span>
      <span className="bn-compute-device-card-body">
        <strong>{device.name}</strong>
        <span>{device.robots.length} {device.robots.length === 1 ? 'robot' : 'robots'}</span>
      </span>
    </button>
  )
}

function RobotRow({
  robot,
  state,
  runtimeReady,
  actionProgress,
  canRestartService,
  sshUsername,
  busy,
  onRefresh,
  onRename,
  onRemove,
  onStopDeployment,
  onControl,
  onRestartService,
}: {
  robot: HardwareDevice
  state?: RobotState
  runtimeReady: boolean
  actionProgress?: DeviceActionProgress
  canRestartService: boolean
  sshUsername?: string
  busy: boolean
  onRefresh: () => void
  onRename: () => void
  onRemove: () => void
  onStopDeployment: (deploymentId: string) => void
  onControl: (action: 'pause' | 'resume') => void
  onRestartService: (password: string) => Promise<boolean>
}) {
  const [expanded, setExpanded] = useState(false)
  const [showRestart, setShowRestart] = useState(false)
  const [restartPassword, setRestartPassword] = useState('')
  const status = state?.status
  const deploymentLease = status?.deployment_lease
  const paused = Boolean(robot.paused || status?.paused)
  const leased = Boolean(status?.leased_to_deployment || deploymentLease)
  const connected = Boolean(status?.connected)
  const armed = Boolean(status?.armed)
  const ready = !paused && !armed && runtimeReady && (connected || leased)
  const color = paused
    ? 'var(--tx3)'
    : armed
      ? 'var(--warn)'
      : ready
        ? 'var(--ok)'
        : status
          ? 'var(--warn)'
          : 'var(--err)'
  const label = state?.loading
    ? 'CHECK'
    : paused
      ? 'PAUSED'
    : deploymentLease
      ? 'ACTIVE'
      : armed
        ? 'ARMED'
      : ready
        ? 'CONNECTED'
        : 'OFF'
  const summary = state?.loading
    ? 'Checking robot hardware…'
    : paused
      ? 'Stopped and disarmed'
    : deploymentLease
      ? `Deployment “${deploymentLease.name}” is running`
      : armed
        ? 'Robot motion is armed'
      : ready
        ? 'Hardware monitoring connected · Blacknode motion disarmed'
        : status
          ? 'Robot needs attention'
          : 'Hardware service unavailable'

  return (
    <div
      className={`bn-run-row bn-device-card${expanded ? ' is-expanded' : ''}`}
      style={{ '--run-status': color } as CSSProperties}
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
        <span className="bn-device-card-state">{label}</span>
        <span className="bn-device-card-chevron" aria-hidden="true">›</span>
      </button>
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
          {deploymentLease && (
            <div className="bn-device-lease-notice" role="status">
              <strong>Deployment controls this robot</strong>
              <span>{status?.notice || `“${deploymentLease.name}” is running.`}</span>
            </div>
          )}
          <div className="bn-device-facts">
            <DeviceFact
              label={deploymentLease ? 'Motion control' : 'Armed'}
              value={deploymentLease ? `Deployment · ${deploymentLease.name}` : status ? (status.armed ? 'Yes' : 'No') : '—'}
              warn={!deploymentLease && Boolean(status?.armed)}
            />
            <DeviceFact
              label="Torque"
              value={status?.torque_enabled == null ? 'Not reported' : status.torque_enabled ? 'On' : 'Off'}
              warn={status?.torque_enabled === true}
            />
            <DeviceFact
              label="Calibrated"
              value={status?.calibrated == null ? '—' : status.calibrated ? 'Yes' : 'No'}
            />
            <DeviceFact label="Hardware" value={connected || leased ? 'Connected' : 'Unavailable'} />
            <DeviceFact label="Last check" value={formatCheckedAt(state?.checkedAt)} />
          </div>
          <div className="bn-run-detail-actions">
            <button
              onClick={() => onControl(paused ? 'resume' : 'pause')}
              disabled={busy || state?.loading}
              style={paused ? primaryButton : miniButton}
            >
              {paused ? 'Resume robot' : 'Pause robot'}
            </button>
            {deploymentLease?.id && (
              <button
                onClick={() => onStopDeployment(deploymentLease.id)}
                disabled={busy || state?.loading}
                style={miniButton}
              >
                Stop deployment
              </button>
            )}
            <button onClick={onRefresh} disabled={busy || state?.loading} style={miniButton}>
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
                : 'Automatic restart requires a compute device installed through SSH'}
              style={miniButton}
            >
              Restart robot service
            </button>
            <button onClick={onRename} disabled={busy} style={miniButton}>Rename</button>
            <button onClick={onRemove} disabled={busy} style={dangerButton}>Remove</button>
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
                <strong>Restart this robot service</strong>
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

function DeviceFact({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="bn-device-fact">
      <span>{label}</span>
      <strong style={warn ? { color: 'var(--warn)' } : undefined}>{value}</strong>
    </div>
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
