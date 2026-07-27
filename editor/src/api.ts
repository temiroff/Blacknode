import type { BnNodeDef, BnNodeMeta, BnPackage, BnPackageIndex } from './types'
import type { GraphRunTarget } from './graphRun'

const BASE = (import.meta.env.VITE_BLACKNODE_API_BASE ?? '/api').replace(/\/$/, '')

export type CookEvent =
  | { type: 'start'; node_id: string; port: string; node_type?: string }
  | { type: 'success'; node_id: string; port: string; value: unknown; cached?: boolean; outputs?: Record<string, unknown>; node_type?: string }
  | { type: 'error'; node_id: string; port: string; error: string; node_type?: string }
  | { type: 'done'; port: string; value?: unknown; error?: string }
  | { type: 'model_call'; node_id: string; model: string; action?: string; provider?: string; tool_count?: number; node_type?: string }
  | { type: 'tool_call'; node_id: string; name: string; arguments?: Record<string, unknown>; node_type?: string }
  | { type: 'log'; node_id: string; stream: 'stdout' | 'stderr'; text: string; node_type?: string }

export interface TemplateMeta {
  slug: string
  name: string
  description: string
  color: string
  group: string
  group_color: string
  saved_at: string
  node_count: number
}

export interface MissingTemplatePackage {
  name: string
  git_url: string
  node_types: string[]
  source: 'core_index' | 'template'
  installed: boolean
  load_error: string
}

export interface MissingTemplateComponent {
  package: string
  component: string
  git_url: string
  reason: string
}

export interface MissingTemplateAdapter {
  package: string
  component: string
  adapter: string
  git_url: string
  reason: string
}

export interface TemplateDependencyError {
  ok: false
  code: 'missing_packages' | 'missing_node_types' | 'missing_components' | 'missing_adapters'
  message: string
  missing_node_types: string[]
  missing_packages: MissingTemplatePackage[]
  missing_components: MissingTemplateComponent[]
  missing_adapters: MissingTemplateAdapter[]
  unresolved_node_types: string[]
}

export interface DriverStatus {
  name: string
  workflow: string
  label: string        // connected bot identity, e.g. '@BlacknodeAgentBot'
  state: string        // 'listening' | 'processing' | 'starting' | 'stopped'
  processed: number
  live: boolean        // computed server-side from heartbeat freshness
}

export interface DriverInfo {
  name: string
  description: string
  status: string       // 'ready' | 'needs env' | 'needs install'
  extra: string        // e.g. 'blacknode[telegram]'
  packages_installed: boolean
  required_packages: string[]
  env: Record<string, boolean>
  missing_env: string[]
}

export interface DriverInstallResult {
  ok: boolean
  returncode: number
  log: string
  status: DriverInfo
}

export interface ApiKeyStatus {
  configured: boolean
  source: 'saved' | 'environment' | 'missing' | 'local'
  env_var: string
}

export interface HardwareDevice {
  id: string
  name: string
  base_url: string
  host_id?: string
  runtime_url: string
  remote_device_id: string
  token_fingerprint: string
  runtime_token_fingerprint?: string
  runtime_token_configured?: boolean
  software_version?: string
  paused?: boolean
  created_at: string
  updated_at: string
}

export interface ComputeDevice {
  id: string
  name: string
  runtime_url: string
  runtime_token_fingerprint: string
  remote_device_id?: string
  paused?: boolean
  created_at: string
  updated_at: string
  robots: HardwareDevice[]
  managed_runtime?: {
    management_mode?: 'ssh' | 'local'
    ssh_host?: string
    ssh_port?: number
    ssh_username?: string
    host_fingerprint?: string
    instance_id: string
    runtime_port: number
    service_name: string
    runtime_dir: string
    stack_mode?: 'runtime_only' | 'isolated'
    hardware_dir?: string
    hardware_port?: number
    hardware_service_name?: string
    hardware_state?: 'awaiting_device' | 'configured' | 'running' | 'stopped'
    hardware_configured?: boolean
    hardware_pid_file?: string
    hardware_token_file?: string
    hardware_log_path?: string
    hardware_owned_install?: boolean
    config_path?: string
    pid_file?: string
    log_path?: string
    owned_install?: boolean
  }
}

export interface SshDeviceProbe {
  ok: boolean
  host_fingerprint: string
  os: string
  architecture: string
  hostname: string
}

export interface SshRuntimeInstance {
  instance_id: string
  runtime_dir: string
  service_name: string
  port: number
  repository: boolean
  configured: boolean
  service_installed: boolean
  running: boolean
  healthy: boolean
  token_available: boolean
  runtime_version: string
  device_id: string
  error: string
}

export interface SshHostEnvironment {
  policy: 'preserve'
  os: {
    name: string
    version: string
    architecture: string
  }
  python: {
    version: string
    executable: string
  }
  nvidia: {
    available: boolean
    gpus: string[]
    driver_version: string
    driver_cuda_version: string
    cuda_toolkit_version: string
    nvidia_smi: boolean
    nvcc: boolean
    preserved: boolean
  }
  ros2: {
    available: boolean
    distributions: string[]
    selected_distribution: string
    ros2_on_path: boolean
    preserved: boolean
  }
  docker: {
    available: boolean
    client_version: string
    server_version: string
    daemon_running: boolean
    service_enabled: boolean
    preserved: boolean
  }
  runtime_setup_packages: string[]
}

export interface SshRuntimeInspection {
  ok: boolean
  host_fingerprint: string
  instances: SshRuntimeInstance[]
  environment: SshHostEnvironment
  suggested_port: number
  suggested_instance_id: string
}

export interface DeviceRuntimeStatus {
  ok: boolean
  paused?: boolean
  state?: 'running' | 'stopped' | 'unreachable' | 'unavailable' | string
  installed?: boolean
  installed_version?: string
  runtime_url: string
  manifest?: {
    service?: string
    protocol_version?: number
    runtime_version?: string
    device_id?: string
    [key: string]: unknown
  }
  hardware?: {
    ok: boolean
    service_url: string
    service_name: string
    state: 'awaiting_device' | 'configured' | string
    installed?: boolean
    installed_version?: string
    status?: HardwareDeviceStatus
    error?: string
  }
  error?: string
}

export interface HardwareDeviceStatus {
  device_id: string
  software_version?: string
  software_version_cached?: boolean
  service_features?: string[]
  connected: boolean
  connection_state?: 'connected' | 'disconnected'
  connection_reported?: boolean
  connection_present?: boolean
  connection_source?: 'device_path' | 'deployment_telemetry' | string
  armed: boolean
  torque_enabled?: boolean
  torque_report_error?: string
  telemetry?: {
    enabled: boolean
    streams: string[]
    sinks: Array<{
      name: string
      configured?: boolean
      connected?: boolean
      broker?: string
      tls?: boolean
      topic_prefix?: string
      qos?: number
      published?: number
      last_published_at?: number | null
      error?: string
    }>
  }
  calibrated?: boolean
  leased_to_deployment?: boolean
  paused?: boolean
  deployment_lease?: {
    id: string
    name: string
    state: string
    motion_armed?: boolean
    motion_control_count?: number
  }
  running_deployment?: {
    id: string
    name: string
    state: string
    motion_armed?: boolean
    motion_control_count?: number
  }
  stored_deployment?: {
    id: string
    name: string
    state: string
  }
  inactive_deployment?: {
    id: string
    name: string
    state: string
  }
  capabilities: string[]
  joint_names?: string[]
  positions?: Record<string, number>
  raw_positions?: Record<string, number>
  error?: string
  notice?: string
  updated_at?: number
  calibration?: {
    name?: string
    profile_id?: string
    hardware_id?: string
    activated_at?: string
    joint_count?: number
    digest?: string
  }
}

export interface RobotTelemetryJoint {
  name: string
  position: number
  velocity: number
}

export interface RobotTelemetrySample {
  type: 'robot_telemetry'
  robot_id: string
  robot_name?: string
  source?: 'hardware' | 'deployment'
  source_label?: string
  deployment?: {
    id: string
    name: string
    state: string
  }
  available: boolean
  stale: boolean
  sequence?: number
  sent_at?: string
  received_at?: string
  age_seconds?: number
  payload?: {
    connected: boolean
    armed?: boolean
    torque_enabled?: boolean | null
    position_unit: string
    velocity_unit: string
    joints: RobotTelemetryJoint[]
    error?: string
    battery?: {
      level?: number
      voltage?: number
      charging?: boolean
    }
    camera_streams?: Array<{
      id: string
      label?: string
      url?: string
    }>
  } | null
  message?: string
}

export function deviceMonitorSocketUrl(id: string): string {
  const path = `${BASE}/devices/${encodeURIComponent(id)}/monitor/ws`
  const url = new URL(path, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export interface DeviceInstallProgress {
  progress: number
  message: string
}

export type DeviceActionProgress = DeviceInstallProgress

export interface ComputeDeviceLifecycleResult {
  ok: boolean
  action: 'pause' | 'resume'
  device: ComputeDevice
  stopped_deployments: string[]
  controlled_robots: string[]
  warnings: string[]
  summary: string
}

export interface ManagedServiceUpdateResult {
  ok: boolean
  scope: 'all' | 'runtime' | 'hardware'
  device: ComputeDevice
  update: {
    ok: boolean
    host_fingerprint?: string
    components: Array<{
      kind: 'runtime' | 'hardware'
      service_name: string
      port: number
      before: { version: string; commit: string }
      after: { version: string; commit: string }
      reported_version?: string
      changed: boolean
      state: string
    }>
  }
  runtime: {
    runtime_version?: string
    [key: string]: unknown
  }
  robots: Array<{
    id: string
    name: string
    port: number
    software_version: string
    status: HardwareDeviceStatus
  }>
  stopped_deployments: string[]
  controlled_robots: string[]
  warnings: string[]
  summary: string
}

export interface ManagedServiceUpdateCheckResult {
  ok: boolean
  check: {
    ok: boolean
    host_fingerprint: string
    components: Array<{
      kind: 'runtime' | 'hardware'
      service_name: string
      port: number
      installed: { version: string; commit: string }
      latest: { version: string; commit: string }
      reported_version?: string
      update_available: boolean
      can_update: boolean
      dirty: boolean
      state: string
      error: string
      environment_installed?: boolean
    }>
  }
  warnings: string[]
  summary: string
}

export interface RobotLifecycleResult {
  ok: boolean
  action: 'pause' | 'resume' | 'restart'
  status: HardwareDeviceStatus
  service?: {
    service_name: string
    hardware_port: number
    state: string
  }
  warnings: string[]
  summary: string
}

export interface InstallComputeDeviceResult {
  device: ComputeDevice
  runtime: DeviceRuntimeStatus
  install: {
    ok: boolean
    host_fingerprint?: string
    elapsed_seconds: number
    action?: string
    instance_id: string
    runtime_port: number
    service_name: string
    runtime_dir: string
    stack_mode?: 'runtime_only' | 'isolated'
    hardware_dir?: string
    management_mode?: 'ssh' | 'local'
    config_path?: string
    pid_file?: string
    log_path?: string
    owned_install?: boolean
  }
}

export interface WorkflowMetadata extends Record<string, unknown> {
  required_capabilities?: string[]
  device_calibration?: {
    profile_id: string
    hardware_id: string
  }
}

export interface ProjectWorkflow {
  slug: string
  name: string
  saved_at?: string
  exists: boolean
  node_types: string[]
  stages: Array<'collect' | 'train' | 'simulate'>
  requires_calibration: boolean
  calibration: {
    profile_id?: string
    hardware_id?: string
  } | null
  starter_kit?: 'robot_learning' | null
  starter_stage?: 'collect' | 'train' | 'simulate' | null
  source_template?: string | null
}

export interface ProjectDevice extends Partial<HardwareDevice> {
  id: string
  name: string
  exists: boolean
}

export type ProjectArtifactType =
  | 'dataset'
  | 'training_run'
  | 'checkpoint'
  | 'policy'
  | 'simulation_run'
  | 'evaluation'

export interface ProjectArtifact {
  id: string
  artifact_type: ProjectArtifactType
  kind: string
  provider: string
  name: string
  locator: string
  status: 'available' | 'running' | 'completed' | 'failed'
  workflow_slugs?: string[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  exists: boolean
}

export interface Project {
  id: string
  name: string
  description: string
  workflow_slugs: string[]
  device_ids: string[]
  artifact_ids: string[]
  starter_kit: 'robot_learning' | null
  active_workflow_slug: string | null
  created_at: string
  updated_at: string
  workflows: ProjectWorkflow[]
  devices: ProjectDevice[]
  artifacts: ProjectArtifact[]
}

export interface GraphSnapshot {
  nodes: any[]
  edges: any[]
  metadata: WorkflowMetadata
}

export interface DeviceCalibrationCandidate {
  profile_id: string
  profile_name: string
  name: string
  hardware_id: string
  recorded_at: string
  joint_count: number
}

export interface DeviceRobotProfile {
  id: string
  name: string
  saved: boolean
  calibration_count: number
}

export type DeploymentPreflightStatus = 'pass' | 'fail' | 'warning' | 'pending'

export interface DeploymentPreflightCheck {
  id: string
  label: string
  status: DeploymentPreflightStatus
  message: string
  blocking: boolean
  action?: 'activate_calibration' | 'select_calibration' | 'choose_matching_hardware'
}

export interface DeploymentPreflight {
  ready: boolean
  summary: string
  device: HardwareDevice
  workflow: {
    name: string
    node_count: number
    required_capabilities: string[]
    hash: string
  }
  status: HardwareDeviceStatus | null
  runtime: Record<string, unknown> | null
  checks: DeploymentPreflightCheck[]
  checked_at: string
}

export type RunStatus = 'success' | 'error' | 'running'

export interface RunSummary {
  run_id: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  status: RunStatus
  node_id: string
  port: string
  node_type: string
  node_count: number
  model_calls: number
  tool_calls: number
  cached_nodes: number
  has_workflow?: boolean
  error?: string
}

export type DeploymentState = 'running' | 'stopped' | 'exited' | 'failed'
export type DeploymentKind = 'service' | 'job'

export interface Deployment {
  id: string
  name: string
  kind: DeploymentKind
  target: string
  state: DeploymentState
  snapshot_hash: string
  entrypoint: { node_id: string; port: string }
  node_count: number
  live_node_types: string[]
  created_at: string
  started_at: string | null
  stopped_at: string | null
  pid: number | null
  exit_code: number | null
  error: string
}

export type RemoteDeploymentState = 'staged' | 'running' | 'stopped' | 'exited' | 'failed'

export interface RemoteDeployment {
  id: string
  name: string
  target_device_id?: string
  project_id?: string
  workflow_slug?: string
  state: RemoteDeploymentState
  staged_revision: string
  active_revision: string | null
  revisions: string[]
  pid: number | null
  exit_code: number | null
  error: string
  motion_armed?: boolean
  motion_control_count?: number
  created_at: string
  updated_at: string
}

export interface WorkflowSnapshot {
  kind?: string
  schema_version?: number
  name?: string
  saved_at?: string
  entrypoint?: { node_id: string; port: string }
  metadata?: Record<string, unknown>
  node_meta?: Record<string, BnNodeMeta>
  edges?: Array<Record<string, unknown>>
}

export interface RunRecord extends RunSummary {
  events: Array<Record<string, unknown> & { type: string; ts?: string | number }>
  workflow?: WorkflowSnapshot
  value?: unknown
}

export interface EditorAction {
  id: string
  type: string
  created_at: string
  payload?: Record<string, unknown>
}

export interface FrameworkExportTarget {
  id: string
  label: string
  description: string
  extension: string
}

export interface FrameworkExportResult {
  target: string
  label: string
  description: string
  filename: string
  code: string
  warnings: string[]
}

export interface LearnedNodeSummary {
  name: string
  description: string
  category: string
  inputs: string[]
  outputs: string[]
  permissions: { network: boolean }
  created_at: string
}

export interface LearnedNodeSource {
  status: string
  node_type: string
  path: string
  source: string
}

export interface WorkflowValidation {
  ok: boolean
  errors: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
}

export interface RuntimeStatus {
  ok: boolean
  active?: boolean
  streams?: Array<Record<string, unknown>>
  cv2_streams?: Array<Record<string, unknown>>
  reasoning_streams?: Array<Record<string, unknown>>
  managed_runs?: Array<Record<string, unknown>>
  modules?: Record<string, Record<string, unknown>>
  detached_count?: number
  report?: string
  error?: string
}

export interface ConsoleEntry {
  id: number
  command: string
  backend: string
  source: string
  status: 'running' | 'ok' | 'failed'
  started_at: number
  duration_ms: number | null
  stdout: string
  stderr: string
  error: string
  exit_code: number | null
}

export interface ConsoleLog {
  entries: ConsoleEntry[]
  active: number
  diagnostics: Array<{ id: string; label: string }>
}

export interface RuntimeStopResult {
  ok: boolean
  stopped?: {
    streams?: number
    cv2_streams?: number
    reasoning_streams?: number
    managed_runs?: number
    detached?: number
  }
  runtime?: RuntimeStopResult
  report?: string
  error?: string
}

export interface PythonImportResult {
  workflow: WorkflowSnapshot
  validation: WorkflowValidation
}

function bodyPreview(text: string): string {
  return text.replace(/[^\x20-\x7E]+/g, ' ').trim().slice(0, 180)
}

function backendRequestError(path: string, err: unknown): Error {
  const message = err instanceof Error ? err.message : String(err)
  return new Error(
    `Backend disconnected while calling ${path}. Start or restart the Blacknode backend, then try again. ${message}`,
  )
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function templateDependencyError(err: unknown): TemplateDependencyError | null {
  if (!(err instanceof ApiError) || err.status !== 409 || !err.detail || typeof err.detail !== 'object') {
    return null
  }
  const detail = err.detail as Partial<TemplateDependencyError>
  const known = new Set(['missing_packages', 'missing_node_types', 'missing_components', 'missing_adapters'])
  if (!detail.code || !known.has(detail.code)) return null
  // Older/other error shapes may omit some arrays; default them so consumers can
  // map over each without guarding.
  return {
    missing_packages: [],
    missing_node_types: [],
    missing_components: [],
    missing_adapters: [],
    unresolved_node_types: [],
    ...detail,
  } as TemplateDependencyError
}

async function fetchBackend(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BASE}${path}`, init)
  } catch (err) {
    if ((err as { name?: string } | null)?.name === 'AbortError') throw err
    throw backendRequestError(path, err)
  }
}

async function responseJson<T>(res: Response, path: string): Promise<T> {
  const text = await res.text().catch(err => {
    throw backendRequestError(path, err)
  })

  if (!res.ok) {
    let detail: unknown = res.statusText
    if (text.trim()) {
      try {
        const payload = JSON.parse(text)
        detail = payload.detail ?? payload
      } catch {
        detail = bodyPreview(text) || res.statusText
      }
    }
    const message = typeof detail === 'string'
      ? detail
      : (
          detail
          && typeof detail === 'object'
          && typeof (detail as { message?: unknown }).message === 'string'
        )
        ? String((detail as { message: string }).message)
        : JSON.stringify(detail)
    throw new ApiError(message, res.status, detail)
  }

  if (!text.trim()) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(
      `Backend returned invalid JSON for ${path}. This usually means the backend errored or sent binary data instead of an API response. Response preview: ${bodyPreview(text) || '(binary data)'}`,
    )
  }
}

function parseCookEventLine(line: string, label: string): CookEvent {
  try {
    return JSON.parse(line) as CookEvent
  } catch {
    throw new Error(
      `Backend stream returned invalid JSON while cooking ${label}. The backend may have errored or disconnected. Response preview: ${bodyPreview(line) || '(binary data)'}`,
    )
  }
}

async function req<T>(method: string, path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null
  const timeout = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null
  try {
    const res = await fetchBackend(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller?.signal,
    })
    return responseJson<T>(res, path)
  } finally {
    if (timeout !== null) window.clearTimeout(timeout)
  }
}

async function streamCook(
  path: string,
  body: unknown,
  label: string,
  onEvent: (event: CookEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetchBackend(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) await responseJson<never>(res, path)
  if (!res.body) return

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      onEvent(parseCookEventLine(line, label))
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) onEvent(parseCookEventLine(buffer, label))
}

async function streamDeviceInstall(
  body: unknown,
  onProgress: (progress: DeviceInstallProgress) => void,
): Promise<InstallComputeDeviceResult> {
  const path = '/device-hosts/install-stream'
  const res = await fetchBackend(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) await responseJson<never>(res, path)
  if (!res.body) throw new Error('The device installer returned no progress stream.')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: InstallComputeDeviceResult | null = null

  const consume = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line) as {
      type: 'progress' | 'done' | 'error'
      progress?: number
      message?: string
      error?: string
      result?: InstallComputeDeviceResult
    }
    if (event.type === 'progress') {
      onProgress({
        progress: Math.max(0, Math.min(100, Number(event.progress) || 0)),
        message: String(event.message || 'Installing Blacknode Runtime'),
      })
    } else if (event.type === 'error') {
      throw new Error(event.error || 'Device installation failed.')
    } else if (event.type === 'done' && event.result) {
      result = event.result
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    lines.forEach(consume)
  }
  buffer += decoder.decode()
  if (buffer.trim()) consume(buffer)
  if (!result) throw new Error('The device installation ended before pairing completed.')
  return result
}

async function streamDeviceAction<T>(
  path: string,
  body: unknown,
  onProgress: (progress: DeviceActionProgress) => void,
): Promise<T> {
  const res = await fetchBackend(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) await responseJson<never>(res, path)
  if (!res.body) throw new Error('The lifecycle action returned no progress stream.')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: T | null = null

  const consume = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line) as {
      type: 'progress' | 'done' | 'error'
      progress?: number
      message?: string
      error?: string
      result?: T
    }
    if (event.type === 'progress') {
      onProgress({
        progress: Math.max(0, Math.min(100, Number(event.progress) || 0)),
        message: String(event.message || 'Applying lifecycle action'),
      })
    } else if (event.type === 'error') {
      throw new Error(event.error || 'Lifecycle action failed.')
    } else if (event.type === 'done' && event.result) {
      result = event.result
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    lines.forEach(consume)
  }
  buffer += decoder.decode()
  if (buffer.trim()) consume(buffer)
  if (!result) throw new Error('The lifecycle action ended before it completed.')
  return result
}

export const api = {
  nodeTypes: ()                              => req<string[]>('GET', '/node-types'),
  nodeDefs:  ()                              => req<Record<string, BnNodeDef>>('GET', '/node-defs'),
  // withGit runs per-package git status (branch/ahead/behind), which the
  // Packages panel shows. Leave it off for the frequent node-grouping refresh so
  // switching tabs or saving a script doesn't fire a burst of git commands.
  packages:  (withGit = false)               => req<{ packages: BnPackage[] }>('GET', withGit ? '/packages?git=true' : '/packages'),
  packageIndex: ()                           => req<BnPackageIndex>('GET', '/packages/index'),
  reloadPackages: ()                         => req<{ ok: boolean }>('POST', '/packages/reload'),
  installPackage: (url: string)              => req<{ ok: boolean; package: BnPackage | null; error: string; log: string[] }>('POST', '/packages/install', { url }),
  setupPackage: (name: string)               => req<{ ok: boolean; package: BnPackage | null; log: string[] }>('POST', `/packages/${encodeURIComponent(name)}/setup`),
  setPackageComponent: (name: string, component: string, enabled: boolean) =>
    req<{ ok: boolean; package: BnPackage }>(
      'POST',
      `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/${enabled ? 'enable' : 'disable'}`,
    ),
  resetPackageComponent: (name: string, component: string) =>
    req<{ ok: boolean; package: BnPackage }>(
      'POST',
      `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/reset`,
    ),
  setPackageAdapter: (name: string, component: string, adapter: string, enabled: boolean) =>
    req<{ ok: boolean; package: BnPackage }>(
      'POST',
      `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/adapters/${encodeURIComponent(adapter)}/${enabled ? 'enable' : 'disable'}`,
    ),
  resetPackageAdapter: (name: string, component: string, adapter: string) =>
    req<{ ok: boolean; package: BnPackage }>(
      'POST',
      `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/adapters/${encodeURIComponent(adapter)}/reset`,
    ),
  packageComponentDependencies: (name: string, component: string) =>
    req<{
      target: { package: string; component: string }
      plan: Array<{ package: string; component: string; version: string; enabled: boolean }>
      changes: Array<{ package: string; component: string; version: string; enabled: boolean }>
    }>('GET', `/packages/${encodeURIComponent(name)}/components/${encodeURIComponent(component)}/dependencies`),
  deletePackage: (name: string)              => req<{ ok: boolean }>('DELETE', `/packages/${encodeURIComponent(name)}`),
  getGraph:  ()                              => req<GraphSnapshot>('GET', '/graph'),
  setGraph:  (nodes: any[], edges: any[], metadata: WorkflowMetadata = {}) =>
    req<GraphSnapshot>('POST', '/graph', { nodes, edges, metadata }),
  updateWorkflowRequirements: (
    requiredCapabilities: string[],
    deviceCalibration: { profile_id: string; hardware_id: string } | null,
  ) => req<{ metadata: WorkflowMetadata }>('PATCH', '/graph/requirements', {
    required_capabilities: requiredCapabilities,
    device_calibration: deviceCalibration,
  }, 10000),
  listGraphCalibrations: () =>
    req<{
      profiles: DeviceRobotProfile[]
      calibrations: DeviceCalibrationCandidate[]
      selected: { profile_id: string; hardware_id: string } | null
    }>('GET', '/graph/calibrations', undefined, 10000),
  addNode:   (type_name: string, pos: [number,number], params = {}) =>
    req<BnNodeMeta>('POST', '/nodes', { type_name, pos, params }),
  removeNode: (id: string)                  => req('DELETE', `/nodes/${id}`),
  updateParam:(id: string, key: string, value: unknown) =>
    req('PATCH', `/nodes/${id}/params`, { key, value }, 10000),
  controlNode:(id: string, action: string) =>
    req<{ ok: boolean; node_id: string; outputs: Record<string, unknown> }>('POST', `/nodes/${id}/control`, { action }),
  pickDirectory:(initialPath = '', title = '') =>
    req<{ selected: string; cancelled: boolean }>(
      'POST',
      '/filesystem/pick-directory',
      { initial_path: initialPath, title },
    ),
  datasetFrame:(token: string, index: number) =>
    req<Record<string, unknown>>('GET', `/dataset/frame/${encodeURIComponent(token)}?index=${Math.max(0, Math.floor(index))}`),
  trimDatasetEpisode:(token: string, frameIndex: number, side: 'before' | 'after') =>
    req<Record<string, unknown>>('POST', '/dataset/trim', { token, frame_index: Math.max(0, Math.floor(frameIndex)), side }, 120000),
  publishDatasetReplayFrame:(token: string, frameIndex: number, event: 'play' | 'seek') =>
    req<Record<string, unknown>>('POST', '/dataset/replay-event', {
      token, frame_index: Math.max(0, Math.floor(frameIndex)), event,
    }),
  updatePorts:(id: string, patch: Partial<Pick<BnNodeMeta, 'inputs' | 'outputs' | 'input_types' | 'output_types' | 'input_defaults' | 'multi_input_ports'>>) =>
    req<BnNodeMeta>('PATCH', `/nodes/${id}/ports`, patch),
  updatePortVisibility:(id: string, patch: Pick<BnNodeMeta, 'promoted_inputs' | 'promoted_outputs'>) =>
    req<BnNodeMeta>('PATCH', `/nodes/${id}/presentation`, patch),
  updatePos:  (id: string, pos: [number,number]) =>
    req('PATCH', `/nodes/${id}/pos`, pos),
  connect:    (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('POST', '/edges', { from_id, from_port, to_id, to_port }),
  disconnect: (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('DELETE', `/edges?from_id=${from_id}&from_port=${from_port}&to_id=${to_id}&to_port=${to_port}`),
  cook:       (node_id: string, port = 'output') =>
    req<{ value: unknown; port: string }>('POST', '/cook', { node_id, port }),
  stopCook:   () => req<RuntimeStopResult>('POST', '/cook/stop'),
  runtimeStatus: () => req<RuntimeStatus>('GET', '/runtime/status'),
  consoleLog: (limit = 100) => req<ConsoleLog>('GET', `/console?limit=${limit}`),
  consoleClear: () => req<{ ok: boolean }>('POST', '/console/clear'),
  consoleRun: (id: string) => req<Record<string, unknown>>('POST', `/console/run/${encodeURIComponent(id)}`),
  consoleExec: (command: string, timeout = 20) =>
    req<Record<string, unknown>>('POST', '/console/exec', { command, timeout }),
  ollamaModels: (endpointUrl: string) =>
    req<{ ok: boolean; models: string[]; error?: string }>('GET', `/ollama/models?endpoint_url=${encodeURIComponent(endpointUrl)}`),
  stopRuntime: () => req<RuntimeStopResult>('POST', '/runtime/stop'),
  cookStream: (node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-stream', { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookGraphStream: (targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-graph-stream', { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} terminal nodes`, onEvent, signal),
  cookSubgraphStream: (subnet_id: string, node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-stream`, { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookSubgraphGraphStream: (subnet_id: string, targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-graph-stream`, { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} subnet terminal nodes`, onEvent, signal),
  reset:      ()                             => req('POST', '/reset'),
  execNode:   (code: string)                 => req<{ ok: boolean; new_types: string[] }>('POST', '/exec-node', { code }),
  saveCustomNode: (filename: string, code: string) =>
    req<{ ok: boolean; path: string; new_types: string[] }>('POST', '/custom-nodes', { filename, code }),
  reloadCustomNodes: () =>
    req<{ ok: boolean; loaded: Array<Record<string, unknown>>; failed: Array<Record<string, unknown>> }>('POST', '/custom-nodes/reload'),
  listCustomNodes: () =>
    req<{ directory: string; files: string[]; registered: BnNodeDef[] }>('GET', '/custom-nodes'),
  getDriverStatus:  () => req<Record<string, DriverStatus>>('GET', '/drivers/status', undefined, 3000),
  listDrivers:      () => req<DriverInfo[]>('GET', '/drivers'),
  installDriver:    (name: string) => req<DriverInstallResult>('POST', `/drivers/${name}/install`),
  startDriver:      (name: string) => req<{ ok: boolean; pid?: number }>('POST', `/drivers/${name}/start`),
  stopDriver:       (name: string) => req<{ ok: boolean }>('POST', `/drivers/${name}/stop`, undefined, 8000),
  getDriverLogs:    (name: string) => req<{ running: boolean; lines: string[] }>('GET', `/drivers/${name}/logs`),
  getApiKeys:       () => req<Record<string, string>>('GET', '/settings/api-keys'),
  getApiKeyStatus:  () => req<Record<string, ApiKeyStatus>>('GET', '/settings/api-key-status'),
  setApiKey:        (provider: string, key: string) =>
    req<{ ok: boolean; restarted?: string | null; credential?: ApiKeyStatus }>('POST', '/settings/api-key', { provider, key }),
  listComputeDevices: () =>
    req<{ devices: ComputeDevice[] }>('GET', '/device-hosts'),
  pairComputeDevice: (name: string, runtimeUrl: string, runtimeToken: string) =>
    req<{ device: ComputeDevice; runtime: DeviceRuntimeStatus }>(
      'POST',
      '/device-hosts',
      { name, runtime_url: runtimeUrl, runtime_token: runtimeToken },
      10000,
    ),
  localComputeDeviceInstallDefaults: () =>
    req<{ install_dir: string }>('GET', '/device-hosts/local-install-defaults'),
  installLocalComputeDevice: (
    name: string,
    installDir: string,
    onProgress: (progress: DeviceInstallProgress) => void = () => {},
  ) =>
    streamDeviceAction<InstallComputeDeviceResult>(
      '/device-hosts/local-install-stream',
      { name, install_dir: installDir },
      onProgress,
    ),
  probeComputeDeviceSsh: (
    host: string,
    port: number,
  ) =>
    req<SshDeviceProbe>(
      'POST',
      '/device-hosts/ssh-probe',
      { host, port },
      20000,
    ),
  inspectComputeDeviceSsh: (
    host: string,
    port: number,
    username: string,
    password: string,
    hostFingerprint: string,
  ) =>
    req<SshRuntimeInspection>(
      'POST',
      '/device-hosts/inspect',
      {
        host,
        port,
        username,
        password,
        host_fingerprint: hostFingerprint,
      },
      60000,
    ),
  configureComputeDeviceSsh: (
    id: string,
    host: string,
    port: number,
    username: string,
    password: string,
    hostFingerprint: string,
  ) =>
    req<{
      ok: boolean
      device: ComputeDevice
      instance: SshRuntimeInstance
      summary: string
    }>(
      'POST',
      `/device-hosts/${encodeURIComponent(id)}/management`,
      {
        host,
        port,
        username,
        password,
        host_fingerprint: hostFingerprint,
      },
      60000,
    ),
  installComputeDevice: (
    name: string,
    host: string,
    port: number,
    username: string,
    password: string,
    hostFingerprint: string,
    action: 'install' | 'reuse' | 'replace' | 'side_by_side' | 'isolated_stack',
    instanceId: string,
    onProgress: (progress: DeviceInstallProgress) => void = () => {},
  ) =>
    streamDeviceInstall(
      {
        name,
        host,
        port,
        username,
        password,
        host_fingerprint: hostFingerprint,
        action,
        instance_id: instanceId,
      },
      onProgress,
    ),
  computeDeviceRuntimeStatus: (id: string) =>
    req<DeviceRuntimeStatus>(
      'GET',
      `/device-hosts/${encodeURIComponent(id)}/runtime-status`,
      undefined,
      7000,
    ),
  pairRobot: (hostId: string, name: string, baseUrl: string, token: string) =>
    req<{
      robot: HardwareDevice
      status: HardwareDeviceStatus
      runtime: DeviceRuntimeStatus
    }>(
      'POST',
      `/device-hosts/${encodeURIComponent(hostId)}/robots`,
      { name, base_url: baseUrl, token },
      10000,
    ),
  renameComputeDevice: (id: string, name: string) =>
    req<{ device: ComputeDevice }>(
      'PATCH',
      `/device-hosts/${encodeURIComponent(id)}`,
      { name },
    ),
  deleteComputeDevice: (id: string) =>
    req<{ ok: boolean; id: string }>(
      'DELETE',
      `/device-hosts/${encodeURIComponent(id)}`,
    ),
  uninstallComputeDevice: (
    id: string,
    password: string,
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<{
      ok: boolean
      id: string
      uninstall: { instance_id: string; runtime_port: number }
      summary: string
    }>(
      `/device-hosts/${encodeURIComponent(id)}/uninstall-stream`,
      { password },
      onProgress,
    ),
  controlComputeDevice: (
    id: string,
    action: 'pause' | 'resume',
    password: string,
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<ComputeDeviceLifecycleResult>(
      `/device-hosts/${encodeURIComponent(id)}/lifecycle-stream`,
      { action, password },
      onProgress,
    ),
  updateComputeDevice: (
    id: string,
    password: string,
    scope: 'all' | 'runtime' | 'hardware',
    operation: 'auto' | 'update' | 'reinstall',
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<ManagedServiceUpdateResult>(
      `/device-hosts/${encodeURIComponent(id)}/update-stream`,
      { password, scope, operation },
      onProgress,
    ),
  manageLocalPackage: (
    id: string,
    kind: 'runtime' | 'hardware',
    action: 'run' | 'stop' | 'restart' | 'delete',
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<{
      ok: boolean
      kind: 'runtime' | 'hardware'
      action: 'run' | 'stop' | 'restart' | 'delete'
      package: Record<string, unknown>
      runtime: DeviceRuntimeStatus
    }>(
      `/device-hosts/${encodeURIComponent(id)}/local-packages/${kind}/action-stream`,
      { action },
      onProgress,
    ),
  manageRemoteHardwarePackage: (
    id: string,
    action: 'run' | 'stop' | 'restart',
    password: string,
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<{
      ok: boolean
      action: 'run' | 'stop' | 'restart'
      state: 'running' | 'stopped'
      services: Array<Record<string, unknown>>
      device: ComputeDevice
      warnings: string[]
      summary: string
    }>(
      `/device-hosts/${encodeURIComponent(id)}/hardware-package/action-stream`,
      { action, password },
      onProgress,
    ),
  checkComputeDeviceUpdates: (
    id: string,
    password: string,
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<ManagedServiceUpdateCheckResult>(
      `/device-hosts/${encodeURIComponent(id)}/update-check-stream`,
      { password },
      onProgress,
    ),
  listDevices:      () => req<{ devices: HardwareDevice[] }>('GET', '/devices'),
  pairDevice:       (name: string, baseUrl: string, token: string, runtimeToken = '') =>
    req<{
      device: HardwareDevice
      status: HardwareDeviceStatus
      runtime: DeviceRuntimeStatus
    }>(
      'POST',
      '/devices',
      { name, base_url: baseUrl, token, runtime_token: runtimeToken || null },
      10000,
    ),
  renameDevice:     (id: string, name: string) =>
    req<{ device: HardwareDevice }>(
      'PATCH',
      `/devices/${encodeURIComponent(id)}`,
      { name },
    ),
  deviceStatus:     (id: string) =>
    req<HardwareDeviceStatus>('GET', `/devices/${encodeURIComponent(id)}/status`, undefined, 7000),
  controlRobot: (
    id: string,
    action: 'pause' | 'resume' | 'restart',
    onProgress: (progress: DeviceActionProgress) => void,
    password = '',
  ) =>
    streamDeviceAction<RobotLifecycleResult>(
      `/devices/${encodeURIComponent(id)}/lifecycle-stream`,
      { action, password },
      onProgress,
    ),
  deviceRuntimeStatus: (id: string) =>
    req<DeviceRuntimeStatus>(
      'GET',
      `/devices/${encodeURIComponent(id)}/runtime-status`,
      undefined,
      7000,
    ),
  deviceCapabilities: (id: string) =>
    req<{ device_id: string; connected: boolean; capabilities: string[] }>(
      'GET',
      `/devices/${encodeURIComponent(id)}/capabilities`,
      undefined,
      7000,
    ),
  activateDeviceCalibration: (id: string) =>
    req<{ ok: boolean; activation: Record<string, unknown>; status: HardwareDeviceStatus }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/calibration`,
      {},
      10000,
    ),
  validateDeviceDeployment: (id: string) =>
    req<DeploymentPreflight>(
      'POST',
      `/devices/${encodeURIComponent(id)}/deployment-preflight`,
      {},
      10000,
    ),
  listRemoteDeployments: (deviceId: string) =>
    req<{ deployments: RemoteDeployment[] }>(
      'GET',
      `/devices/${encodeURIComponent(deviceId)}/deployments`,
      undefined,
      10000,
    ),
  stageRemoteDeployment: (
    deviceId: string,
    name: string,
    workflowHash: string,
    start = false,
    deploymentId?: string,
    projectId?: string,
    workflowSlug?: string,
  ) =>
    req<{
      deployment: RemoteDeployment
      workflow_hash: string
      started: boolean
      superseded_deployments: string[]
      cleanup_warnings: string[]
    }>(
      'POST',
      `/devices/${encodeURIComponent(deviceId)}/deployments`,
      {
        name,
        workflow_hash: workflowHash,
        start,
        deployment_id: deploymentId ?? null,
        project_id: projectId ?? null,
        workflow_slug: workflowSlug ?? null,
      },
      600000,
    ),
  startRemoteDeployment: (deviceId: string, deploymentId: string) =>
    req<RemoteDeployment>(
      'POST',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/start`,
      {},
      15000,
    ),
  stopRemoteDeployment: (deviceId: string, deploymentId: string) =>
    req<RemoteDeployment>(
      'POST',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/stop`,
      {},
      15000,
    ),
  rollbackRemoteDeployment: (deviceId: string, deploymentId: string, start = false) =>
    req<RemoteDeployment>(
      'POST',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/rollback`,
      { start },
      15000,
    ),
  remoteDeploymentLogs: (deviceId: string, deploymentId: string) =>
    req<{ id: string; logs: string }>(
      'GET',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/logs`,
      undefined,
      10000,
    ),
  remoteDeploymentWorkflow: (deviceId: string, deploymentId: string, revision = '') =>
    req<{
      id: string
      revision: string
      source: 'snapshot' | 'generated_script'
      workflow: {
        kind: 'blacknode.workflow'
        schema_version: number
        name?: string
        node_meta: Record<string, any>
        edges: any[]
        metadata?: WorkflowMetadata
      }
    }>(
      'GET',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/workflow${
        revision ? `?revision=${encodeURIComponent(revision)}` : ''
      }`,
      undefined,
      15000,
    ),
  setRemoteDeploymentMotion: (
    deviceId: string,
    deploymentId: string,
    armed: boolean,
  ) =>
    req<{
      ok: boolean
      id: string
      armed: boolean
      topic: string
      node_id: string
      deployment: RemoteDeployment
    }>(
      'POST',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}/motion`,
      { armed },
      20000,
    ),
  remoteRos2Diagnostics: (deviceId: string) =>
    req<{
      ok: boolean
      available: boolean
      checked_at: string
      summary: string
      nodes: string[]
      topics: string[]
      services: string[]
      topic_details: Array<{
        topic: string
        ok: boolean
        stdout: string
        stderr: string
        error: string
      }>
      warnings: string[]
    }>(
      'GET',
      `/devices/${encodeURIComponent(deviceId)}/ros2-diagnostics`,
      undefined,
      90000,
    ),
  deleteRemoteDeployment: (deviceId: string, deploymentId: string) =>
    req<{ ok: boolean; id: string }>(
      'DELETE',
      `/devices/${encodeURIComponent(deviceId)}/deployments/${encodeURIComponent(deploymentId)}`,
      undefined,
      15000,
    ),
  deviceRpc: (id: string, method: string, params: Record<string, unknown> = {}, requestId: string | number | null = null) =>
    req<Record<string, unknown>>(
      'POST',
      `/devices/${encodeURIComponent(id)}/rpc`,
      { jsonrpc: '2.0', id: requestId, method, params },
      10000,
    ),
  releaseDeviceTorque: (id: string) =>
    req<{
      ok: boolean
      status: HardwareDeviceStatus
      already_released: boolean
      verification_warning?: string
    }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/release-torque`,
      {},
      15000,
    ),
  deleteDevice:     (id: string) =>
    req<{ ok: boolean; id: string }>('DELETE', `/devices/${encodeURIComponent(id)}`),
  getOnboarding:    () => req<{ package_welcome_seen: boolean }>('GET', '/settings/onboarding'),
  setOnboarding:    (packageWelcomeSeen: boolean) =>
    req<{ ok: boolean; package_welcome_seen: boolean }>('POST', '/settings/onboarding', { package_welcome_seen: packageWelcomeSeen }),
  getCustomModels:  () => req<string[]>('GET', '/settings/custom-models'),
  addCustomModel:   (value: string) => req('POST', '/settings/custom-models', { value }),
  removeCustomModel:(value: string) => req('DELETE', `/settings/custom-models?value=${encodeURIComponent(value)}`),

  listWorkflows: () =>
    req<{ slug: string; name: string; saved_at: string }[]>('GET', '/workflows'),
  saveWorkflow: (name: string, previousSlug?: string | null) =>
    req<{ ok: boolean; slug: string }>('POST', '/workflows', { name, previous_slug: previousSlug ?? null }),
  loadWorkflow: (slug: string) =>
    req<GraphSnapshot>('POST', `/workflows/${encodeURIComponent(slug)}/load`),
  insertWorkflow: (slug: string) =>
    req<GraphSnapshot>('POST', `/workflows/${encodeURIComponent(slug)}/insert`),
  renameWorkflow: (slug: string, name: string) =>
    req<{ slug: string; name: string; saved_at: string }>('PATCH', `/workflows/${encodeURIComponent(slug)}`, { name }),
  duplicateWorkflow: (slug: string) =>
    req<{ slug: string; name: string; saved_at: string }>('POST', `/workflows/${encodeURIComponent(slug)}/duplicate`),
  deleteWorkflow: (slug: string) =>
    req('DELETE', `/workflows/${encodeURIComponent(slug)}`),

  listProjects: () =>
    req<Project[]>('GET', '/projects'),
  getProject: (projectId: string) =>
    req<Project>('GET', `/projects/${encodeURIComponent(projectId)}`),
  createProject: (payload: {
    name: string
    description?: string
    workflow_slugs?: string[]
    device_ids?: string[]
    artifact_ids?: string[]
    starter_kit?: 'robot_learning' | null
    active_workflow_slug?: string | null
  }) =>
    req<Project>('POST', '/projects', payload),
  updateProject: (
    projectId: string,
    payload: Partial<Pick<
      Project,
      'name' | 'description' | 'workflow_slugs' | 'device_ids' | 'artifact_ids' | 'starter_kit' | 'active_workflow_slug'
    >>,
  ) =>
    req<Project>('PATCH', `/projects/${encodeURIComponent(projectId)}`, payload),
  deleteProject: (projectId: string) =>
    req<{ ok: boolean }>('DELETE', `/projects/${encodeURIComponent(projectId)}`),
  importProjectArtifacts: (
    projectId: string,
    payload: {
      workflow_slug?: string | null
      node_type?: string
      value: unknown
    },
  ) =>
    req<{ artifacts: ProjectArtifact[]; project: Project }>(
      'POST',
      `/projects/${encodeURIComponent(projectId)}/artifacts/import`,
      payload,
    ),
  inspectProjectArtifact: (
    projectId: string,
    payload: { path: string; workflow_slug?: string | null },
  ) =>
    req<{ artifacts: ProjectArtifact[]; project: Project }>(
      'POST',
      `/projects/${encodeURIComponent(projectId)}/artifacts/inspect`,
      payload,
    ),
  createProjectStarterWorkflow: (
    projectId: string,
    stage: 'collect' | 'train' | 'simulate',
  ) =>
    req<{
      created: boolean
      workflow: ProjectWorkflow
      project: Project
    }>(
      'POST',
      `/projects/${encodeURIComponent(projectId)}/starter-workflows/${stage}`,
    ),

  listTemplates: () =>
    req<TemplateMeta[]>('GET', '/templates'),
  loadTemplate: (slug: string) =>
    req<GraphSnapshot>('POST', `/templates/${encodeURIComponent(slug)}/load`),

  listFrameworkExportTargets: () =>
    req<{ targets: FrameworkExportTarget[] }>('GET', '/export/frameworks'),
  exportFramework: (target: string, workflow?: WorkflowSnapshot) =>
    req<FrameworkExportResult>('POST', '/export/framework', { target, workflow }),
  importPython: (code: string, name = 'Imported Python Workflow') =>
    req<PythonImportResult>('POST', '/import/python', { code, name }),

  mcpStatus:  () =>
    req<{ mcp_installed: boolean; blacknode_cli: string | null; install_command: string; launch_command: string }>('GET', '/mcp/status'),
  consumeEditorActions: () =>
    req<{ actions: EditorAction[] }>('GET', '/editor/actions'),

  listLearnedNodes: () =>
    req<{ nodes: LearnedNodeSummary[]; count: number }>('GET', '/learned-nodes'),
  getLearnedNodeSource: (name: string) =>
    req<LearnedNodeSource>('GET', `/learned-nodes/${encodeURIComponent(name)}/source`),
  promoteLearnedNode: (name: string) =>
    req<{ status: string; node_type: string; category: string; path: string }>('POST', `/learned-nodes/${encodeURIComponent(name)}/promote`),
  deleteLearnedNode: (name: string) =>
    req<{ status: string; node_type: string }>('DELETE', `/learned-nodes/${encodeURIComponent(name)}`),
  learnedNodeEventsUrl: () => `${BASE}/learned-nodes/events`,

  listDeployments: () =>
    req<{ deployments: Deployment[] }>('GET', '/deployments'),
  deployGraph: (name: string, autostart = true) =>
    req<Deployment>('POST', '/deployments', { name, autostart }),
  startDeployment: (id: string) =>
    req<Deployment>('POST', `/deployments/${encodeURIComponent(id)}/start`),
  stopDeployment: (id: string) =>
    req<Deployment>('POST', `/deployments/${encodeURIComponent(id)}/stop`),
  deleteDeployment: (id: string) =>
    req<{ ok: boolean; id: string }>('DELETE', `/deployments/${encodeURIComponent(id)}`),
  exportDeployment: (id: string) =>
    req<{ ok: boolean; id: string; path: string }>('POST', `/deployments/${encodeURIComponent(id)}/export`),
  listCameras: () =>
    req<{ ok: boolean; cameras: Array<{ index: number; label: string; device: string; width: number; height: number }>; report: string }>('GET', '/cameras'),
  listYoloModels: () =>
    req<{ ok: boolean; builtin: string[]; custom: string[]; models_dir: string }>('GET', '/yolo-models'),
  deploymentLogs: (id: string) =>
    req<{ id: string; logs: string }>('GET', `/deployments/${encodeURIComponent(id)}/logs`),

  listRuns:   (limit = 50) =>
    req<{ runs: RunSummary[] }>('GET', `/runs?limit=${limit}`),
  getRun:     (runId: string) =>
    req<RunRecord>('GET', `/runs/${encodeURIComponent(runId)}`),
  deleteRun:  (runId: string) =>
    req<{ ok: boolean; run_id: string }>('DELETE', `/runs/${encodeURIComponent(runId)}`),
  clearRuns:  () =>
    req<{ ok: boolean; removed: number }>('DELETE', '/runs'),

  getSubgraph: (nodeId: string) =>
    req<{ node_meta: Record<string, any>; edges: any[] }>('GET', `/nodes/${nodeId}/subgraph`),
  updateSubgraph: (nodeId: string, node_meta: Record<string, any>, edges: any[]) =>
    req<any>('PATCH', `/nodes/${nodeId}/subgraph`, { node_meta, edges }),
  collapseToSubnet: (nodeIds: string[], label: string) =>
    req<{ subnet: any; removed_node_ids: string[] }>('POST', '/subnets', { node_ids: nodeIds, label }),
}
