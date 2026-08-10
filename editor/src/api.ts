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
  categories: string[]
  required_packages: string[]
  required_capabilities: string[]
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

export type RobotAttachmentType =
  | 'camera'
  | 'depth_camera'
  | 'lidar'
  | 'imu'
  | 'gps'
  | 'microphone'
  | 'custom'

export type RobotAttachmentProviderProfile =
  | 'existing_topics'
  | 'usb_cam'
  | 'blacknode_rgbd'
  | 'custom_launch'

export interface RobotAttachmentCheck {
  ok: boolean
  status:
    | 'streaming'
    | 'topic_present'
    | 'missing'
    | 'no_publisher'
    | 'type_mismatch'
    | 'unavailable'
  topic: string
  expected_message_type: string
  actual_message_type: string
  publisher_count: number | null
  checked_at: string
  message: string
  service_state?: 'running' | 'stopped' | 'failed'
  missing?: string[]
  interfaces?: Array<Record<string, unknown>>
}

export interface RobotAttachment {
  kind: 'blacknode.robot-attachment'
  schema_version: 1
  id: string
  display_name: string
  attachment_type: RobotAttachmentType
  capability: string
  provider: {
    package: string
    component: string
    adapter: string
    profile?: RobotAttachmentProviderProfile
  }
  hardware_identity: {
    id: string
    serial?: string
    vendor_id?: string
    product_id?: string
    path?: string
  }
  parent_frame: string
  frame_id: string
  mount: {
    translation_m: [number, number, number]
    rotation_rpy_rad: [number, number, number]
  }
  interfaces: Array<{
    kind: 'topic'
    role?: 'camera_info' | 'depth' | 'points'
    direction: 'output'
    topic: string
    candidates: string[]
    message_type: string
    frame_id: string
    required?: boolean
  }>
  service?: {
    id: string
    profile: RobotAttachmentProviderProfile
    launch_package: string
    launch_target: string
    launch_arguments: string[]
  }
  required: boolean
  enabled: boolean
  last_check?: RobotAttachmentCheck
  binding: Record<string, unknown>
}

export interface RobotAttachmentInput {
  attachment_id: string
  display_name: string
  attachment_type: RobotAttachmentType
  capability: string
  provider_package: string
  provider_component: string
  provider_adapter: string
  provider_profile: RobotAttachmentProviderProfile
  topic: string
  message_type: string
  camera_info_topic: string
  depth_topic: string
  point_cloud_topic: string
  launch_package: string
  launch_target: string
  launch_arguments: string[]
  parent_frame: string
  frame_id: string
  x_m: number
  y_m: number
  z_m: number
  roll_rad: number
  pitch_rad: number
  yaw_rad: number
  hardware_id: string
  required: boolean
  enabled: boolean
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
  attachments?: RobotAttachment[]
  created_at: string
  updated_at: string
}

export interface RobotMonitorTarget {
  id: string
  name: string
  kind: 'registered' | 'local_usb'
  available: boolean
  profile_id?: string
  requested_profile_id?: string
  raw_mode?: boolean
  hardware_id?: string
  port?: string
  message?: string
  device?: HardwareDevice
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
  inspection_only?: boolean
  inspection_updated_at?: string
  last_inspection?: SshRuntimeInspection
  inspection_connection?: {
    ssh_host: string
    ssh_port: number
    ssh_username: string
    host_fingerprint: string
  }
  managed_runtime?: {
    management_mode?: 'ssh' | 'local'
    ssh_host?: string
    ssh_port?: number
    ssh_username?: string
    host_fingerprint?: string
    instance_id: string
    runtime_port: number
    service_name: string
    install_root?: string
    runtime_dir: string
    packages_dir?: string
    firewall_source?: string
    delivery_mode?: 'pc_assisted' | 'device_online'
    core_dir?: string
    python_dir?: string
    python_version?: string
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
  install_root?: string
  runtime_dir: string
  packages_dir?: string
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

export interface SshRos2CapabilityCandidate {
  kind: 'blacknode.robot-capability-candidate'
  schema_version: 1
  capability: string
  confidence: 'high' | 'medium' | 'low'
  score: number
  state_topics: string[]
  command_topics: string[]
  safe_to_read: boolean
  requires_confirmation: boolean
  evidence: Array<{
    capability: string
    kind: 'topic'
    name: string
    message_type: string
    role: 'state' | 'metadata' | 'command'
    score: number
    reason: string
  }>
}

export interface SshRos2GraphInspection {
  available: boolean
  state: 'available' | 'partial' | 'empty' | 'unavailable' | 'unsupported' | string
  distribution: string
  domain_id: string
  read_only: true
  daemon_used: false
  topics: string[]
  nodes: string[]
  services: string[]
  errors: string[]
  found: boolean
  capabilities: SshRos2CapabilityCandidate[]
  unclassified: Array<{
    name: string
    message_types: string[]
  }>
  inventory: {
    topics: Array<{
      name: string
      message_types: string[]
    }> | string[]
    nodes: string[]
    services: string[]
    classified_topic_count?: number
    unclassified_topic_count?: number
  }
  report: string
}

export interface SshRuntimeInspection {
  ok: boolean
  live?: boolean
  read_only?: boolean
  checked_at?: string
  source?: 'paired_runtime' | string
  error?: string
  host_fingerprint?: string
  instances: SshRuntimeInstance[]
  environment: SshHostEnvironment
  ros2_graph: SshRos2GraphInspection
  suggested_port: number
  suggested_instance_id: string
  device?: ComputeDevice
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
    packages?: Array<{
      name: string
      version: string
      source?: string
    }>
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
  semantic_name?: string
  servo_id?: number
  position: number
  velocity: number
  effort?: number
  raw_position?: number
  lower_limit?: number
  upper_limit?: number
  communication_ok?: boolean
  temperature_c?: number
  voltage_v?: number
  hardware_error_flags?: number
  hardware_errors?: string[]
  servo_status?: number
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
    motion_armed?: boolean
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
    raw_mode?: boolean
    position_unit: string
    velocity_unit: string
    joints: RobotTelemetryJoint[]
    error?: string
    calibrated?: boolean
    calibration?: {
      name?: string
      profile_id?: string
      hardware_id?: string
      units?: string
      activated_at?: string
      joint_count?: number
      digest?: string
      topology?: Record<string, string>
      joints?: Record<string, {
        safe_min_deg?: number
        safe_max_deg?: number
        home_ticks?: number
        home_offset_deg?: number
        invert?: boolean
      }>
    }
    faults?: Array<{
      code?: string
      message?: string
      severity?: string
      active?: boolean
      recoverable?: boolean
      vendor_code?: string
      details?: Record<string, unknown>
    }>
    temperatures_c?: Record<string, number>
    voltage_v?: number
    voltages_v?: Record<string, number>
    bus?: {
      operation_count?: number
      timeout_count?: number
      serial_packet_error_count?: number
      serial_packet_error_rate?: number
      exception_count?: number
      hardware_error_count?: number
      scan_miss_count?: number
      hardware_error_flags?: Record<string, number>
      hardware_errors?: Record<string, string[]>
      servo_status?: Record<string, number>
      voltages_v?: Record<string, number>
      last_full_feedback_time?: number
      last_diagnostic_time?: number
    }
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

export function deviceMonitorSocketUrl(id: string, profileId = 'auto'): string {
  const path = `${BASE}/devices/${encodeURIComponent(id)}/monitor/ws`
  const url = new URL(path, window.location.href)
  url.searchParams.set('profile_id', String(profileId || 'auto'))
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
  extension_packages?: {
    ok: boolean
    installed: Array<{ name: string; version: string }>
    already_present: Array<{ name: string; version: string }>
    activated: Array<{
      package: string
      component: string
      adapter: string
    }>
    messages: string[]
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
      source_mode?: 'git' | 'snapshot' | 'missing'
      update_strategy?: 'fast_forward' | 'replace'
      migration_required?: boolean
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
    install_root?: string
    runtime_dir: string
    packages_dir?: string
    firewall_source?: string
    delivery_mode?: 'pc_assisted' | 'device_online'
    core_dir?: string
    python_dir?: string
    python_version?: string
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
  entrypoint?: { node_id: string; port: string } | null
}

export interface FileBrowserListing {
  path: string
  parent: string
  roots: string[]
  selected: string
  entries: Array<{
    name: string
    path: string
    is_directory: boolean
    size: number | null
  }>
}

export interface CanvasSchemaNodeChange {
  id: string
  type: string
  added_inputs: string[]
  removed_inputs: string[]
  added_outputs: string[]
  removed_outputs: string[]
  types_changed: boolean
  defaults_changed: boolean
}

export interface CanvasSchemaRefreshResult {
  ok: boolean
  loaded: Array<{ path?: string; new_types?: string[] }>
  failed: Array<{ path?: string; error?: string }>
  updated_nodes: CanvasSchemaNodeChange[]
  removed_edges: Array<{ from: string; from_port: string; to: string; to_port: string }>
  graph?: GraphSnapshot
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
  action?:
    | 'activate_calibration'
    | 'select_calibration'
    | 'choose_matching_hardware'
    | 'enable_editor_dependencies'
  action_data?: {
    packages?: Array<{ name: string; git_url: string }>
    components?: Array<{ package: string; component: string }>
    adapters?: Array<{ package: string; component: string; adapter: string }>
  }
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

export interface RemoteRos2Diagnostics {
  ok: boolean
  available: boolean
  checked_at: string
  summary: string
  nodes: string[]
  stale_nodes?: string[]
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

export type CloudJobStatus =
  | 'QUEUED'
  | 'PROVISIONING'
  | 'STARTING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELED'
  | 'TIMED_OUT'

export interface CloudStatus {
  configured: boolean
  gpu: string
  url: string
  authenticated: boolean
  account: CloudAccount | null
  credits: CloudCredits | null
  compute_providers: CloudProviderCatalog | null
}

export type CloudProviderPreference = 'auto' | 'nvcf' | 'nebius'

export interface CloudProviderOption {
  id: CloudProviderPreference
  label: string
  gpu: string
  available: boolean
}

export interface CloudProviderCatalog {
  preference: CloudProviderPreference
  options: CloudProviderOption[]
}

export interface HostedEditorStatus {
  hosted: boolean
  workspace_persistence: 'session' | 'local'
  execution: 'cloud-only' | 'local-and-cloud'
}

export interface CloudAccount {
  id: string
  organization_id: string
  email: string
  display_name: string
  created_at: string
  email_verified_at?: string | null
  compute_provider_preference: CloudProviderPreference
}

export interface CloudCredits {
  unit: 'gpu-second'
  balance: number
  reserved: number
  available: number
  locked?: number
}

export interface CloudCreditEntry {
  id: string
  delta_seconds: number
  reason: string
  reference_id: string
  created_at: string
}

export interface CloudCreditHistory {
  unit: 'gpu-second'
  entries: CloudCreditEntry[]
}

export interface CloudJob {
  id: string
  project_ref: string | null
  workflow_name: string
  status: CloudJobStatus
  cleanup_status: string
  progress: number
  compute: { gpu_class: 'l40s'; gpu_count: 1; max_runtime_seconds: number }
  runtime: { release: string }
  error_code: string | null
  error_message: string | null
  result: unknown
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface CloudJobEvent {
  seq: number
  type: 'state' | 'log' | 'progress' | 'metric' | 'artifact'
  created_at: string
  payload: Record<string, unknown>
}

export interface CloudArtifact {
  id: string
  name: string
  kind: string
  size_bytes: number
  sha256: string
  media_type: string
  locator: string
  created_at: string
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

export interface NewtonSceneTransform {
  translate_m: [number, number, number]
  rotate_deg: [number, number, number]
  scale: [number, number, number]
}

export interface NewtonSceneMaterial {
  base_color: [number, number, number]
  metallic: number
  roughness: number
  opacity: number
}

export interface NewtonSceneItem {
  path: string
  parent_path: string
  name: string
  type_name: string
  render_role?: 'visual' | 'collider' | string
  visible: boolean
  visibility_editable?: boolean
  available?: boolean
  editable: boolean
  material_editable: boolean
  transform: NewtonSceneTransform
  material: NewtonSceneMaterial
  light?: {
    kind: 'scope' | 'distant' | 'dome' | string
    enabled?: boolean
    selected?: boolean
    intensity?: number
    color?: string
    angle_deg?: number
    rotation_deg?: [number, number, number]
    show_background?: boolean
    hdri?: string
    hdri_path?: string
  }
}

export interface NewtonWorkspaceJoint {
  name: string
  units: 'radians' | 'metres' | string
  position: number
  target: number
  applied_target?: number
  reference_position?: number | null
  tracking_error?: number | null
  limits: [number, number]
  stiffness: number
  damping: number
  passive_damping?: number
  child_body?: string
  child_body_mass_kg?: number
  child_body_inertia_kg_m2?: [number, number, number]
  max_velocity?: number
  max_step?: number
}

export interface NewtonDigitalTwinSample {
  received_at: number
  observed_at?: number | null
  source: string
  source_latency_seconds: number | null
  joint_errors: Record<string, number>
  max_abs_error: number
  rms_error: number
}

export interface NewtonDigitalTwinStatus {
  available: boolean
  source: string
  received_at?: number
  observed_at?: number | null
  age_seconds: number | null
  source_latency_seconds: number | null
  stale_after_seconds: number
  stale: boolean
  matched_joint_count: number
  reference_positions: Record<string, number>
  simulated_positions: Record<string, number>
  joint_errors: Record<string, number>
  max_abs_error: number
  rms_error: number
  history: NewtonDigitalTwinSample[]
  history_limit: number
  ghost?: {
    visible: boolean
    placement: 'overlay' | 'beside' | 'custom'
    offset_m: [number, number, number]
    beside_offset_m: [number, number, number]
    opacity: number
    color_rgb: [number, number, number]
  }
  baseline?: {
    artifact_id: string
    name: string
    created_at: string
    source: string
    matched_joint_names: string[]
    summary: Record<string, number>
    history: NewtonDigitalTwinSample[]
  }
}

export interface NewtonDigitalTwinArtifactSummary {
  artifact_id: string
  kind: 'blacknode.newton-run-artifact'
  schema_version: 1
  name: string
  created_at: string
  path: string
  source: string
  scene_label: string
  joint_names: string[]
  joint_units: Record<string, string>
  sample_count: number
  duration_seconds: number
  max_abs_error: number
  rms_error: number
}

export interface NewtonWorkspaceStatus {
  kind: 'blacknode.newton-workspace'
  schema_version: 1
  open: boolean
  simulation_running: boolean
  running: boolean
  paused: boolean
  phase: string
  armed: boolean
  viewer_url: string
  viewer_provider?: string
  available_viewers?: string[]
  asset_path: string
  scene_label: string
  dynamic_body_count: number
  authored_dynamic_body_names?: string[]
  usd_mesh_count?: number
  usd_meshes_with_normals?: number
  usd_collision_mesh_count?: number
  warning: string
  last_error: string
  frame_count: number
  fps?: number
  substeps?: number
  solver_iterations?: number
  show_grid: boolean
  show_visuals: boolean
  show_colliders: boolean
  digital_twin?: NewtonDigitalTwinStatus
  environment: {
    background_color: string
    hdri: string
    hdri_path: string
    hdri_enabled: boolean
    show_background: boolean
    intensity: number
    distant_light: {
      enabled: boolean
      intensity: number
      color: string
      angle_deg: number
      rotation_deg: [number, number, number]
    }
    custom_hdri_supported: boolean
  }
  scene_items: NewtonSceneItem[]
  selected_path: string
  selected_item: NewtonSceneItem | null
  joints: NewtonWorkspaceJoint[]
  friction_override_matches?: Record<string, number>
  digital_twin_artifacts?: NewtonDigitalTwinArtifactSummary[]
  digital_twin_artifact_error?: string
}

export interface NewtonStreamControlStatus {
  open: boolean
  armed: boolean
  simulation_running: boolean
  phase: string
  accepted: boolean
  command_count: number
  clamped: string[]
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

async function binaryReq(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const res = await fetchBackend(path, { method: 'GET', signal })
  if (!res.ok) await responseJson<never>(res, path)
  return res.arrayBuffer()
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
  hostedStatus: ()                           => req<HostedEditorStatus>('GET', '/hosted/status'),
  nodeTypes: ()                              => req<string[]>('GET', '/node-types'),
  nodeDefs:  ()                              => req<Record<string, BnNodeDef>>('GET', '/node-defs'),
  depthFrame: (nodeId: string, signal?: AbortSignal) =>
    binaryReq(`/nodes/${encodeURIComponent(nodeId)}/depth-frame`, signal),
  // withGit runs per-package git status (branch/ahead/behind), which the
  // Packages panel shows. Leave it off for the frequent node-grouping refresh so
  // switching tabs or saving a script doesn't fire a burst of git commands.
  packages:  (withGit = false)               => req<{ packages: BnPackage[] }>('GET', withGit ? '/packages?git=true' : '/packages'),
  packageIndex: ()                           => req<BnPackageIndex>('GET', '/packages/index'),
  reloadPackages: ()                         => req<{ ok: boolean; index_refreshed: boolean }>('POST', '/packages/reload'),
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
  cloudStatus: ()                            => req<CloudStatus>('GET', '/cloud/status'),
  registerCloudAccount: (email: string, password: string, displayName: string) =>
    req<CloudStatus>('POST', '/cloud/auth/register', {
      email,
      password,
      display_name: displayName,
    }),
  loginCloudAccount: (email: string, password: string) =>
    req<CloudStatus>('POST', '/cloud/auth/login', { email, password }),
  updateCloudAccount: (settings: {
    display_name?: string
    compute_provider_preference?: CloudProviderPreference
  }) => req<CloudStatus>('PATCH', '/cloud/account', settings),
  verifyCloudEmail: (token: string) =>
    req<{ verified: boolean; account: CloudAccount }>('POST', '/cloud/auth/verify-email', { token }),
  logoutCloudAccount: () =>
    req<{ ok: boolean; revoked: boolean }>('POST', '/cloud/auth/logout'),
  getCloudCreditHistory: () =>
    req<CloudCreditHistory>('GET', '/cloud/credits/history'),
  createCloudJob: (
    entrypoint: { node_id: string; port: string },
    workflowName: string,
    projectRef?: string | null,
  ) => req<CloudJob>('POST', '/cloud/jobs', {
    entrypoint,
    workflow_name: workflowName,
    project_ref: projectRef ?? null,
  }),
  getCloudJob: (jobId: string) =>
    req<CloudJob>('GET', `/cloud/jobs/${encodeURIComponent(jobId)}`),
  cancelCloudJob: (jobId: string) =>
    req<CloudJob>('DELETE', `/cloud/jobs/${encodeURIComponent(jobId)}`),
  getCloudJobLogs: (jobId: string, afterSeq = 0) =>
    req<{ job_id: string; events: CloudJobEvent[]; next_seq: number }>(
      'GET',
      `/cloud/jobs/${encodeURIComponent(jobId)}/logs?after_seq=${afterSeq}`,
    ),
  getCloudJobArtifacts: (jobId: string) =>
    req<{ job_id: string; artifacts: CloudArtifact[] }>(
      'GET',
      `/cloud/jobs/${encodeURIComponent(jobId)}/artifacts`,
    ),
  cloudArtifactDownloadUrl: (jobId: string, artifactId: string) =>
    `${BASE}/cloud/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
  setGraph:  (
    nodes: any[],
    edges: any[],
    metadata: WorkflowMetadata = {},
    entrypoint: GraphSnapshot['entrypoint'] = null,
  ) => req<GraphSnapshot>('POST', '/graph', { nodes, edges, metadata, entrypoint }),
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
  robotProfileEditorGraph: (profileId: string) =>
    req<GraphSnapshot>(
      'GET',
      `/graph/profiles/${encodeURIComponent(profileId)}/editor`,
      undefined,
      10000,
    ),
  addNode:   (type_name: string, pos: [number,number], params = {}) =>
    req<BnNodeMeta>('POST', '/nodes', { type_name, pos, params }),
  removeNode: (id: string)                  => req('DELETE', `/nodes/${id}`),
  updateParam:(id: string, key: string, value: unknown) =>
    req('PATCH', `/nodes/${id}/params`, { key, value }, 10000),
  controlNode:(id: string, action: string, payload: Record<string, unknown> = {}) =>
    req<{ ok: boolean; node_id: string; outputs: Record<string, unknown> }>(
      'POST',
      `/nodes/${id}/control`,
      { action, payload },
    ),
  pickDirectory:(initialPath = '', title = '') =>
    req<{ selected: string; cancelled: boolean }>(
      'POST',
      '/filesystem/pick-directory',
      { initial_path: initialPath, title },
    ),
  pickFile:(initialPath = '', title = '', extensions: string[] = []) =>
    req<{ selected: string; cancelled: boolean }>(
      'POST',
      '/filesystem/pick-file',
      { initial_path: initialPath, title, extensions },
    ),
  browseFiles:(path = '', extensions: string[] = []) =>
    req<FileBrowserListing>(
      'POST',
      '/filesystem/browse',
      { path, extensions },
      15000,
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
  spatialViewerRuntimeStatus: () => req<RuntimeStatus>('GET', '/runtime/spatial-viewers'),
  newtonWorkspaceStatus: () =>
    req<NewtonWorkspaceStatus>('GET', '/newton/workspace'),
  controlNewtonWorkspace: (action: string, payload: Record<string, unknown> = {}) =>
    req<NewtonWorkspaceStatus>(
      'POST',
      `/newton/workspace/${encodeURIComponent(action)}`,
      { payload },
      ['open_asset', 'open_usd', 'set_viewer', 'set_grid', 'set_visibility', 'set_transform',
        'set_light',
        'set_material', 'set_environment', 'set_render_options', 'set_joint_properties',
        'set_digital_twin_ghost', 'clear_digital_twin_history',
        'save_digital_twin_artifact', 'load_digital_twin_baseline',
        'clear_digital_twin_baseline',
        'set_joint_motion'].includes(action)
        ? 120000
        : 30000,
    ),
  controlNewtonStream: (action: string, payload: Record<string, unknown> = {}) =>
    req<NewtonStreamControlStatus>(
      'POST',
      `/newton/workspace/${encodeURIComponent(action)}`,
      { payload },
      5000,
    ),
  consoleLog: (limit = 100) => req<ConsoleLog>('GET', `/console?limit=${limit}`),
  consoleClear: () => req<{ ok: boolean }>('POST', '/console/clear'),
  consoleRun: (id: string) => req<Record<string, unknown>>('POST', `/console/run/${encodeURIComponent(id)}`),
  consoleExec: (command: string, timeout = 20) =>
    req<Record<string, unknown>>('POST', '/console/exec', { command, timeout }),
  ollamaModels: (endpointUrl: string) =>
    req<{ ok: boolean; models: string[]; error?: string }>('GET', `/ollama/models?endpoint_url=${encodeURIComponent(endpointUrl)}`),
  stopRuntime: () => req<RuntimeStopResult>('POST', '/runtime/stop', undefined, 15000),
  cookStream: (node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-stream', { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookGraphStream: (targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook('/cook-graph-stream', { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} terminal nodes`, onEvent, signal),
  cookSubgraphStream: (subnet_id: string, node_id: string, port = 'output', onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-stream`, { node_id, port, run_mode }, `${node_id}.${port}`, onEvent, signal),
  cookSubgraphGraphStream: (subnet_id: string, targets: GraphRunTarget[], onEvent: (event: CookEvent) => void, signal?: AbortSignal, run_mode: 'once' | 'live' = 'once') =>
    streamCook(`/nodes/${subnet_id}/cook-graph-stream`, { targets: targets.map(target => ({ node_id: target.id, port: target.port })), run_mode }, `${targets.length} subnet terminal nodes`, onEvent, signal),
  reset:      ()                             => req('POST', '/reset'),
  execNode:   (code: string)                 => req<{ ok: boolean; new_types: string[]; registered_types: string[] }>('POST', '/exec-node', { code }),
  saveCustomNode: (filename: string, code: string) =>
    req<{ ok: boolean; path: string; new_types: string[] }>('POST', '/custom-nodes', { filename, code }),
  reloadCustomNodes: () =>
    req<{ ok: boolean; loaded: Array<Record<string, unknown>>; failed: Array<Record<string, unknown>> }>('POST', '/custom-nodes/reload'),
  refreshCanvasSchemas: () =>
    req<CanvasSchemaRefreshResult>('POST', '/graph/refresh-node-schemas'),
  listCustomNodes: () =>
    req<{ directory: string; files: string[]; registered: BnNodeDef[] }>('GET', '/custom-nodes'),
  getCustomNodeSource: (filename: string) =>
    req<{ filename: string; path: string; code: string }>('GET', `/custom-nodes/source?filename=${encodeURIComponent(filename)}`),
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
    name = '',
    register = false,
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
        name,
        save_inspection: register,
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
    action:
      | 'runtime_only'
      | 'install'
      | 'reuse'
      | 'replace_runtime'
      | 'replace'
      | 'side_by_side'
      | 'isolated_stack',
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
  computeDeviceLiveInspection: (id: string) =>
    req<SshRuntimeInspection>(
      'GET',
      `/device-hosts/${encodeURIComponent(id)}/live-inspection`,
      undefined,
      90000,
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
  discoverAndPairRobots: (hostId: string, password: string) =>
    req<{
      ok: boolean
      robots: HardwareDevice[]
      statuses: Record<string, HardwareDeviceStatus>
      errors: string[]
      summary: string
    }>(
      'POST',
      `/device-hosts/${encodeURIComponent(hostId)}/robots/discover`,
      { password },
      60000,
    ),
  installComputeDeviceHardware: (
    hostId: string,
    password: string,
    onProgress: (progress: DeviceActionProgress) => void,
  ) =>
    streamDeviceAction<{
      ok: boolean
      device: ComputeDevice
      install: {
        instance_id: string
        hardware_dir: string
        stack_mode: 'isolated'
      }
      summary: string
    }>(
      `/device-hosts/${encodeURIComponent(hostId)}/hardware-package/install-stream`,
      { password },
      onProgress,
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
  listRobotMonitorTargets: (profileId = 'auto') =>
    req<{
      targets: RobotMonitorTarget[]
      profiles: DeviceRobotProfile[]
      profile_id: string
    }>(
      'GET',
      `/robot-monitor-targets?profile_id=${encodeURIComponent(profileId || 'auto')}`,
    ),
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
  listRobotAttachments: (id: string) =>
    req<{ device_id: string; attachments: RobotAttachment[] }>(
      'GET',
      `/devices/${encodeURIComponent(id)}/attachments`,
    ),
  createRobotAttachment: (id: string, attachment: RobotAttachmentInput) =>
    req<{ device: HardwareDevice; attachment: RobotAttachment }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/attachments`,
      attachment,
    ),
  updateRobotAttachment: (
    id: string,
    attachmentId: string,
    attachment: RobotAttachmentInput,
  ) =>
    req<{ device: HardwareDevice; attachment: RobotAttachment }>(
      'PUT',
      `/devices/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`,
      attachment,
    ),
  deleteRobotAttachment: (id: string, attachmentId: string) =>
    req<{ ok: boolean; id: string; device: HardwareDevice }>(
      'DELETE',
      `/devices/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`,
    ),
  checkRobotAttachment: (id: string, attachmentId: string) =>
    req<{
      device: HardwareDevice
      attachment: RobotAttachment
      check: RobotAttachmentCheck
    }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/check`,
      {},
      90000,
    ),
  startRobotAttachment: (id: string, attachmentId: string) =>
    req<{
      device: HardwareDevice
      attachment: RobotAttachment
      service: Record<string, unknown>
      check: RobotAttachmentCheck
    }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/start`,
      {},
      30000,
    ),
  stopRobotAttachment: (id: string, attachmentId: string) =>
    req<{
      device: HardwareDevice
      attachment: RobotAttachment
      service: Record<string, unknown>
      check: RobotAttachmentCheck
    }>(
      'POST',
      `/devices/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/stop`,
      {},
      30000,
    ),
  deviceMonitor:    (id: string) =>
    req<RobotTelemetrySample>(
      'GET',
      `/devices/${encodeURIComponent(id)}/monitor`,
      undefined,
      7000,
    ),
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
    start: boolean,
    onProgress: (progress: DeviceActionProgress) => void,
    deploymentId?: string,
    projectId?: string,
    workflowSlug?: string,
  ) =>
    streamDeviceAction<{
      deployment: RemoteDeployment
      workflow_hash: string
      started: boolean
      superseded_deployments: string[]
      cleanup_warnings: string[]
    }>(
      `/devices/${encodeURIComponent(deviceId)}/deployments-stream`,
      {
        name,
        workflow_hash: workflowHash,
        start,
        deployment_id: deploymentId ?? null,
        project_id: projectId ?? null,
        workflow_slug: workflowSlug ?? null,
      },
      onProgress,
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
    req<RemoteRos2Diagnostics>(
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
