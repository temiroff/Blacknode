import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import {
  api,
  deviceMonitorSocketUrl,
  type ComputeDevice,
  type DeviceActionProgress,
  type DeviceInstallProgress,
  type DeviceRuntimeStatus,
  type HardwareDevice,
  type HardwareDeviceStatus,
  type ManagedServiceUpdateCheckResult,
  type ManagedServiceUpdateResult,
  type RobotTelemetryJoint,
  type RobotTelemetrySample,
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

function runtimeHostname(runtimeUrl: string): string {
  try {
    return new URL(runtimeUrl).hostname
  } catch {
    return ''
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

export default function DevicesPanel() {
  const activeProject = useStore(state => state.activeProject)
  const setActiveProject = useStore(state => state.setActiveProject)
  const [devices, setDevices] = useState<ComputeDevice[]>([])
  const [deviceStates, setDeviceStates] = useState<Record<string, DeviceState>>({})
  const [robotStates, setRobotStates] = useState<Record<string, RobotState>>({})
  const [knownHardwareVersions, setKnownHardwareVersions] = useState<Record<string, string>>({})
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
  const [showUpdateForm, setShowUpdateForm] = useState(false)
  const [updatePassword, setUpdatePassword] = useState('')
  const [updateCheckReport, setUpdateCheckReport] = useState<ManagedServiceUpdateCheckResult | null>(null)
  const [updateReport, setUpdateReport] = useState<ManagedServiceUpdateResult | null>(null)
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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [linkedProjectName, setLinkedProjectName] = useState('')

  const selectedDevice = devices.find(device => device.id === selectedDeviceId) ?? null
  const selectedDeviceState = selectedDevice
    ? deviceStates[selectedDevice.id]
    : undefined
  const selectedRobotChecks = selectedDevice
    ? selectedDevice.robots.map(robot => ({
      robot,
      state: robotStates[robot.id],
    }))
    : []
  const selectedDeviceChecking = Boolean(
    selectedDeviceState?.loading
    || selectedRobotChecks.some(item => item.state?.loading),
  )
  const selectedHardwareReady = selectedRobotChecks.every(item => Boolean(
    item.state?.status
    && !item.state.error
    && (
      item.state.status.connected
      || item.state.status.leased_to_deployment
      || item.state.status.deployment_lease
    ),
  ))
  const selectedDeviceReady = Boolean(
    selectedDeviceState?.runtime?.ok
    && selectedHardwareReady,
  )
  const selectedServiceVersions = selectedDevice
    ? [
      `Runtime ${
        selectedDeviceState?.runtime?.manifest?.runtime_version
          ? `v${selectedDeviceState.runtime.manifest.runtime_version}`
          : 'version not reported'
      }`,
      ...selectedRobotChecks.map(({ robot, state }) => (
        `${robot.name} Hardware ${
          state?.status?.software_version
            ? `v${state.status.software_version}`
            : robot.software_version
              ? `v${robot.software_version} (last verified)`
            : 'version not reported'
        }`
      )),
    ]
    : []
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
  const checkedHardwareInstallation = checkedHardwareComponents.find(component => (
    component.installed.version !== 'unknown'
    && component.latest.version !== 'unknown'
  )) ?? checkedHardwareComponents[0]
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

  const checkDevice = async (device: ComputeDevice) => {
    setShowUpdateForm(false)
    setUpdatePassword('')
    setUpdateCheckReport(null)
    setUpdateReport(null)
    setBusy(true)
    setError(null)
    try {
      await Promise.all([
        refreshDevice(device),
        ...device.robots.map(refreshRobot),
      ])
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

  const updateDevice = async (
    device: ComputeDevice,
    scope: 'all' | 'runtime' | 'hardware',
  ) => {
    if (!updatePassword) {
      setError('Enter the SSH password to update this managed device.')
      return
    }
    const selectedComponents = checkedSoftwareComponents.filter(component => (
      scope === 'all' || component.kind === scope
    ))
    const selectedUpdatesAvailable = selectedComponents.some(
      component => component.update_available,
    )
    const operation = selectedUpdatesAvailable ? 'Update' : 'Reinstall'
    const hardwareServiceCount = device.robots.length
    const targetLabel = scope === 'all'
      ? 'Runtime + Robot Hardware'
      : scope === 'runtime'
        ? 'Runtime'
        : `shared Robot Hardware installation used by ${hardwareServiceCount} robot service${
          hardwareServiceCount === 1 ? '' : 's'
        }`
    if (!window.confirm(
      `${operation} ${targetLabel} on "${device.name}"? Running deployments will stop and robots will return with Blacknode motion disarmed. This action does not switch off physical actuator power.`,
    )) return
    setBusy(true)
    setError(null)
    setUpdateReport(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: {
        progress: 1,
        message: scope === 'runtime'
          ? 'Preparing Runtime update'
          : scope === 'hardware'
            ? `Preparing shared Robot Hardware update for ${hardwareServiceCount} robot service${
              hardwareServiceCount === 1 ? '' : 's'
            }`
            : 'Preparing Runtime + Robot Hardware update',
      },
    }))
    try {
      const result = await api.updateComputeDevice(
        device.id,
        updatePassword,
        scope,
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
          updatePassword,
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
    if (!updatePassword) {
      setError('Enter the SSH password to compare installed and latest versions.')
      return
    }
    setBusy(true)
    setError(null)
    setUpdateReport(null)
    setUpdateCheckReport(null)
    setActionProgress(previous => ({
      ...previous,
      [device.id]: { progress: 1, message: 'Checking Runtime + Robot Hardware versions' },
    }))
    try {
      const result = await api.checkComputeDeviceUpdates(
        device.id,
        updatePassword,
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

  const restartStoredDeployment = async (
    robot: HardwareDevice,
    deploymentId: string,
    deploymentName: string,
  ) => {
    if (!window.confirm(
      `Restart stored deployment "${deploymentName}" on "${robot.name}"? Blacknode will recheck the robot safety state before starting it.`,
    )) return
    setBusy(true)
    setError(null)
    setActionProgress(previous => ({
      ...previous,
      [robot.id]: { progress: 10, message: 'Restarting stored deployment' },
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
              <code>{selectedDevice.runtime_url}</code>
            </div>
            <div className="bn-run-detail-actions bn-device-header-actions">
              <button
                onClick={() => void checkDevice(selectedDevice)}
                disabled={busy || selectedDeviceState?.loading}
                className={`bn-device-action-button bn-runtime-check-button${selectedDeviceState?.loading ? ' is-checking' : ''}`}
                title="Check the runtime and every attached robot hardware service"
              >
                {selectedDeviceState?.loading ? 'Checking device…' : 'Check device'}
              </button>
              <button
                onClick={() => renameDevice(selectedDevice)}
                disabled={busy}
                className="bn-device-action-button"
              >
                Rename
              </button>
              {!selectedDevice.managed_runtime && (
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
                      setShowRuntimeControl(current => !current)
                      setShowUpdateForm(false)
                      setShowUninstallForm(false)
                      setRuntimeControlPassword('')
                      setError(null)
                    }}
                    disabled={busy}
                    className={`bn-device-action-button${selectedDevice.paused ? ' is-primary' : ''}`}
                  >
                    {selectedDevice.paused ? 'Resume device' : 'Pause device'}
                  </button>
                  <button
                    onClick={() => {
                      setShowUpdateForm(current => !current)
                      setShowRuntimeControl(false)
                      setShowUninstallForm(false)
                      setUpdatePassword('')
                      setError(null)
                    }}
                    disabled={busy}
                    className={`bn-device-action-button${showUpdateForm ? ' is-active' : ''}`}
                  >
                    Runtime + Robot Hardware
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
                    Uninstall runtime
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
            </div>
          </div>

          {showSshManagement && !selectedDevice.managed_runtime && (
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

          {showUpdateForm && selectedDevice.managed_runtime && (
            <form
              className="bn-runtime-uninstall bn-device-update-form"
              onSubmit={event => {
                event.preventDefault()
                void checkDeviceSoftware(selectedDevice)
              }}
            >
              <div>
                <strong>Runtime + Robot Hardware</strong>
                <span>
                  Checks the Blacknode Runtime repository and every Blacknode Hardware
                  repository used by this device. Installed, latest, and live-reported
                  versions are shown together first. Current versions can also be
                  reinstalled when you want to repair the environments and restart services.
                </span>
              </div>
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
              <div className="bn-device-update-caution">
                Checking versions is read-only. Updating stops deployments and restarts
                robot monitoring disarmed. Physical servo torque may remain enabled.
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

          {updateCheckReport && (
            <section className="bn-device-update-report" aria-label="Runtime and Robot Hardware version report">
              <div className="bn-device-update-report-head">
                <div>
                  <strong>Runtime + Robot Hardware version report</strong>
                  <span>{updateCheckReport.summary}</span>
                </div>
                <span>{updateCheckReport.check.components.length} services checked</span>
              </div>
              <div className="bn-device-update-components">
                {checkedRuntimeComponents.map(component => (
                  <div
                    className="bn-device-update-component"
                    key={`check-${component.kind}-${component.service_name}-${component.port}`}
                  >
                    <div>
                      <strong>Runtime</strong>
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
                        disabled={busy || component.dirty || !updatePassword}
                        title={component.dirty
                          ? 'Local source changes must be resolved before reinstalling'
                          : component.error
                            ? 'Attempt to repair and reinstall Runtime'
                            : component.update_available
                              ? 'Update Runtime'
                              : 'Reinstall current Runtime'}
                        onClick={() => void updateDevice(selectedDevice, 'runtime')}
                      >
                        {busy
                          ? 'Working…'
                          : component.error
                            || component.installed.version === 'unknown'
                            || component.latest.version === 'unknown'
                            ? 'Repair Runtime'
                            : component.update_available
                              ? 'Update Runtime'
                              : 'Reinstall Runtime'}
                      </button>
                    </div>
                    <small>
                      Live service reports {component.reported_version || 'version unavailable'}
                    </small>
                    {component.error && (
                      <small className="bn-device-update-component-error">
                        {component.error}
                      </small>
                    )}
                  </div>
                ))}
                {checkedHardwareInstallation && (
                  <div className="bn-device-update-component" key="check-hardware-shared">
                    <div>
                      <strong>Robot Hardware</strong>
                      <code>
                        Shared installation · {checkedHardwareComponents.length} robot
                        {' '}service{checkedHardwareComponents.length === 1 ? '' : 's'}
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
                        disabled={busy || !updatePassword || checkedHardwareIsDirty}
                        title={`Updates the shared Robot Hardware installation and restarts ${
                          checkedHardwareComponents.length
                        } robot service${checkedHardwareComponents.length === 1 ? '' : 's'}`}
                        onClick={() => void updateDevice(selectedDevice, 'hardware')}
                      >
                        {busy
                          ? 'Working…'
                          : checkedHardwareNeedsRepair
                            ? 'Repair Robot Hardware'
                            : checkedHardwareHasUpdate
                              ? 'Update Robot Hardware'
                              : 'Reinstall Robot Hardware'}
                      </button>
                    </div>
                    <small>
                      Robot services:{' '}
                      {checkedHardwareComponents.map(component => (
                        `${robotNameForPort(component.port)} (port ${component.port}) — ${
                          component.error
                            ? 'attention'
                            : formatVersion(
                              component.reported_version || component.installed.version,
                            )
                        }`
                      )).join(' · ')}
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
              </div>
              {updateCheckReport.warnings.length > 0 && (
                <div className="bn-device-update-warnings">
                  {updateCheckReport.warnings.map(warning => (
                    <span key={warning}>{warning}</span>
                  ))}
                </div>
              )}
              <div className="bn-device-update-report-actions">
                <button
                  type="button"
                  className="bn-device-action-button"
                  disabled={
                    busy
                    || !updatePassword
                    || checkedSoftwareComponents.some(
                      component => component.dirty || Boolean(component.error),
                    )
                  }
                  title="Update or reinstall Runtime and the shared Robot Hardware installation together"
                  onClick={() => void updateDevice(selectedDevice, 'all')}
                >
                  {checkedSoftwareComponents.some(component => component.update_available)
                    ? 'Update all'
                    : 'Reinstall all'}
                </button>
              </div>
            </section>
          )}

          {updateReport && (
            <section className="bn-device-update-report" aria-label="Runtime and Hardware update report">
              <div className="bn-device-update-report-head">
                <div>
                  <strong>Runtime + Robot Hardware update report</strong>
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
                      <strong>Runtime</strong>
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
                      <strong>Robot Hardware</strong>
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
              selectedDeviceChecking
                ? ' is-checking'
                : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                  ? ' is-paused'
                : selectedDeviceReady
                  ? ' is-ready'
                  : ' is-error'
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
                    ? 'Device services connected'
                    : 'Device needs attention'}
              </strong>
              <span>
                {selectedDeviceChecking
                  ? `Checking Runtime and ${selectedDevice.robots.length} Robot Hardware service${selectedDevice.robots.length === 1 ? '' : 's'}`
                  : selectedDevice.paused || selectedDeviceState?.runtime?.paused
                    ? 'Deployments are stopped and attached robots are disarmed.'
                  : selectedDeviceReady
                    ? `${selectedServiceVersions.join(' · ')} · Last checked ${formatCheckedAt(selectedLastChecked)}`
                    : selectedDeviceState?.runtime?.error
                      || selectedRobotChecks.find(item => item.state?.error)?.state?.error
                      || 'Run Check device to verify Runtime and attached Robot Hardware services.'}
              </span>
            </div>
          </div>

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
                This compute device is ready. Attach its physical robot to create a
                deployment target.
              </div>
            )}
            {selectedDevice.robots.map(robot => (
              <RobotRow
                key={robot.id}
                robot={robot}
                state={robotStates[robot.id]}
                runtimeReady={deviceStates[selectedDevice.id]?.runtime?.ok === true}
                actionProgress={actionProgress[robot.id]}
                installedSoftwareVersion={installedHardwareVersionForPort(
                  urlPort(robot.base_url),
                )}
                canRestartService={Boolean(selectedDevice.managed_runtime)}
                sshUsername={selectedDevice.managed_runtime?.ssh_username}
                busy={busy}
                onRefresh={() => refreshRobot(robot)}
                onRename={() => renameRobot(robot)}
                onRemove={() => removeRobot(robot)}
                onDeploy={() => window.dispatchEvent(new CustomEvent(
                  'blacknode:open-panel',
                  { detail: { tab: 'deployments', deviceId: robot.id } },
                ))}
                onStopDeployment={deploymentId => stopDeployment(robot, deploymentId)}
                onStartDeployment={(deploymentId, deploymentName) => (
                  restartStoredDeployment(robot, deploymentId, deploymentName)
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
  onReleaseTorque,
  onControl,
  onRestartService,
}: {
  robot: HardwareDevice
  state?: RobotState
  runtimeReady: boolean
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
  onReleaseTorque: () => void
  onControl: (action: 'pause' | 'resume') => void
  onRestartService: (password: string) => Promise<boolean>
}) {
  const [expanded, setExpanded] = useState(false)
  const [showRestart, setShowRestart] = useState(false)
  const [showMonitor, setShowMonitor] = useState(false)
  const [showTorqueDetails, setShowTorqueDetails] = useState(false)
  const [restartPassword, setRestartPassword] = useState('')
  const status = state?.status
  const deploymentLease = status?.deployment_lease
  const runningDeployment = deploymentLease ?? status?.running_deployment
  const storedDeployment = runningDeployment ? undefined : status?.stored_deployment
  const torqueReleaseSupported = Boolean(
    status?.service_features?.includes('torque_release_v1'),
  )
  const torqueUnknownReason = status?.torque_report_error
    || (runningDeployment
      ? 'The running deployment owns the robot connection, so the monitoring service cannot read the servo torque registers.'
      : 'Robot Hardware did not receive a valid torque-register reading from every configured servo.')
  const mqttTelemetry = status?.telemetry?.sinks.find(sink => sink.name === 'mqtt')
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
      : runningDeployment
        ? 'RUNNING'
      : armed
        ? 'ARMED'
      : storedDeployment
        ? 'STORED'
      : ready
        ? 'CONNECTED'
        : 'OFF'
  const summary = state?.loading
    ? 'Checking robot hardware…'
    : paused
      ? 'Stopped and disarmed'
    : deploymentLease
      ? `Deployment “${deploymentLease.name}” is running`
      : runningDeployment
        ? `Deployment “${runningDeployment.name}” is running · motion control not held`
      : armed
        ? 'Robot motion is armed'
      : storedDeployment
        ? `Deployment “${storedDeployment.name}” is stored · ${storedDeployment.state}`
      : ready
        ? 'Hardware monitoring connected · Blacknode motion disarmed'
        : status
          ? 'Robot needs attention'
          : 'Robot Hardware service unavailable'

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
          <div
            className={`bn-device-lease-notice${
              deploymentLease
                ? ' is-active'
                : runningDeployment
                  ? ' is-running'
                  : storedDeployment
                    ? ' is-stored'
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
                : storedDeployment
                  ? status?.notice || `“${storedDeployment.name}” remains stored on the Runtime and can be restarted.`
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
            <DeviceFact label="Connection" value={connected || leased ? 'Connected' : 'Unavailable'} />
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
            <button
              onClick={() => {
                if (storedDeployment?.id) {
                  onStartDeployment(storedDeployment.id, storedDeployment.name)
                } else {
                  onDeploy()
                }
              }}
              disabled={busy || state?.loading || paused}
              className="bn-device-action-button is-primary"
              title={paused
                ? `Resume this robot before ${
                  storedDeployment ? 'restarting its stored deployment' : 'deploying a workflow'
                }`
                : storedDeployment
                  ? `Start the stored ${storedDeployment.state} deployment`
                  : 'Open deployment setup and history for this robot'}
            >
              {storedDeployment ? 'Restart deployment' : 'Deploy workflow'}
            </button>
            <button
              type="button"
              onClick={() => setShowMonitor(value => !value)}
              className={`bn-device-action-button${showMonitor ? ' is-primary' : ''}`}
              aria-pressed={showMonitor}
            >
              {showMonitor ? 'Close monitor' : 'Monitor live'}
            </button>
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
                } else if (storedDeployment) {
                  onDeploy()
                }
              }}
              disabled={busy || state?.loading || (!runningDeployment?.id && !storedDeployment)}
              title={runningDeployment?.id
                ? 'Stop the workflow running on this robot'
                : storedDeployment
                  ? 'Open this robot’s stored deployment and revision history'
                  : 'No deployment is stored on this robot'}
              className="bn-device-action-button"
            >
              {storedDeployment ? 'Deployment details' : 'Stop deployment'}
            </button>
          </div>
          {showMonitor && <RobotMonitor robot={robot} />}
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

type JointTrace = {
  position: number[]
  velocity: number[]
}

function RobotMonitor({ robot }: { robot: HardwareDevice }) {
  const [sample, setSample] = useState<RobotTelemetrySample | null>(null)
  const [connection, setConnection] = useState<'connecting' | 'live' | 'offline'>('connecting')
  const [traces, setTraces] = useState<Record<string, JointTrace>>({})
  const previous = useRef<Record<string, { position: number; at: number }>>({})
  const activeSource = useRef('')

  useEffect(() => {
    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined

    const connect = () => {
      if (stopped) return
      setConnection('connecting')
      socket = new WebSocket(deviceMonitorSocketUrl(robot.id))
      socket.onopen = () => setConnection('live')
      socket.onmessage = event => {
        let next: RobotTelemetrySample
        try {
          next = JSON.parse(String(event.data)) as RobotTelemetrySample
        } catch {
          return
        }
        const sourceKey = `${next.source || 'unknown'}:${next.source_label || ''}`
        if (activeSource.current && activeSource.current !== sourceKey) {
          previous.current = {}
          setTraces({})
        }
        activeSource.current = sourceKey
        const receivedAt = Date.now()
        if (next.available && next.payload?.joints) {
          const normalized = next.payload.joints.map(joint => {
            const prior = previous.current[joint.name]
            const elapsed = prior ? (receivedAt - prior.at) / 1000 : 0
            const derivedVelocity = elapsed > 0
              ? (joint.position - prior.position) / elapsed
              : 0
            previous.current[joint.name] = {
              position: joint.position,
              at: receivedAt,
            }
            return {
              ...joint,
              velocity: next.source === 'hardware'
                ? derivedVelocity
                : Number.isFinite(joint.velocity) ? joint.velocity : derivedVelocity,
            }
          })
          next = {
            ...next,
            payload: {
              ...next.payload,
              joints: normalized,
            },
          }
          setTraces(current => {
            const updated = { ...current }
            for (const joint of normalized) {
              const trace = updated[joint.name] || { position: [], velocity: [] }
              updated[joint.name] = {
                position: [...trace.position, joint.position].slice(-80),
                velocity: [...trace.velocity, joint.velocity].slice(-80),
              }
            }
            return updated
          })
        }
        setSample(next)
      }
      socket.onerror = () => socket?.close()
      socket.onclose = () => {
        if (stopped) return
        setConnection('offline')
        reconnectTimer = window.setTimeout(connect, 1200)
      }
    }

    connect()
    return () => {
      stopped = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [robot.id])

  const joints = sample?.payload?.joints || []
  const sourceLabel = sample?.source === 'deployment'
    ? `Deployed · ${sample.source_label || 'workflow'}`
    : 'Local · Robot Hardware'
  const torque = sample?.payload?.torque_enabled
  const stateLabel = connection !== 'live'
    ? connection
    : sample?.stale
      ? 'stale'
      : sample?.available
        ? 'live'
        : 'waiting'

  return (
    <section className="bn-robot-monitor" aria-label={`Live monitoring for ${robot.name}`}>
      <div className="bn-robot-monitor-head">
        <div>
          <span className={`bn-robot-monitor-pulse is-${stateLabel}`} aria-hidden="true" />
          <div>
            <strong>Live robot state</strong>
            <span>{sourceLabel}</span>
          </div>
        </div>
        <div className="bn-robot-monitor-status">
          <span className={`is-${stateLabel}`}>{stateLabel.toUpperCase()}</span>
          <span>
            Torque {torque == null ? 'unknown' : torque ? 'on' : 'off'}
          </span>
        </div>
      </div>

      {!sample?.available || joints.length === 0 ? (
        <div className="bn-robot-monitor-empty" role="status">
          <strong>
            {connection === 'connecting'
              ? 'Connecting to robot…'
              : connection === 'offline'
                ? 'Reconnecting…'
                : 'Waiting for joint state'}
          </strong>
          <span>
            {sample?.message
              || 'The monitor will start as soon as this robot reports joint positions.'}
          </span>
        </div>
      ) : (
        <>
          <div className="bn-robot-monitor-meta">
            <span>{joints.length} joints</span>
            <span>{sample.payload?.position_unit || 'degree'}</span>
            <span>
              Updated {sample.received_at
                ? new Date(sample.received_at).toLocaleTimeString()
                : 'now'}
            </span>
          </div>
          <div className="bn-robot-monitor-grid">
            {joints.map(joint => (
              <JointMonitorCard
                key={joint.name}
                joint={joint}
                trace={traces[joint.name]}
                positionUnit={sample.payload?.position_unit || 'degree'}
                velocityUnit={sample.payload?.velocity_unit || 'degree/s'}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}

function JointMonitorCard({
  joint,
  trace,
  positionUnit,
  velocityUnit,
}: {
  joint: RobotTelemetryJoint
  trace?: JointTrace
  positionUnit: string
  velocityUnit: string
}) {
  return (
    <article className="bn-joint-monitor-card">
      <div className="bn-joint-monitor-title">
        <strong title={joint.name}>{joint.name.replace(/_/g, ' ')}</strong>
        <span>{joint.position.toFixed(2)} {shortUnit(positionUnit)}</span>
      </div>
      <TelemetrySparkline values={trace?.position || []} />
      <div className="bn-joint-monitor-speed">
        <span>Speed</span>
        <strong>{joint.velocity.toFixed(2)} {shortUnit(velocityUnit)}</strong>
      </div>
    </article>
  )
}

function TelemetrySparkline({ values }: { values: number[] }) {
  const width = 180
  const height = 44
  const finite = values.filter(Number.isFinite)
  const minimum = finite.length ? Math.min(...finite) : 0
  const maximum = finite.length ? Math.max(...finite) : 0
  const range = Math.max(maximum - minimum, 0.001)
  const points = finite.map((value, index) => {
    const x = finite.length <= 1 ? width : index * width / (finite.length - 1)
    const y = height - 4 - ((value - minimum) / range) * (height - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg
      className="bn-joint-monitor-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Recent joint position"
    >
      <line x1="0" y1={height / 2} x2={width} y2={height / 2} />
      {points && <polyline points={points} />}
    </svg>
  )
}

function shortUnit(unit: string): string {
  return unit
    .replace('degree', '°')
    .replace('/s', '/s')
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
