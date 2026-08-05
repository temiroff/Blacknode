import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

interface ViewerScene {
  kind?: string
  primitive?: string
  projection?: string
  frame?: string
  sequence?: number
  points?: unknown
  colors?: unknown
  current_points?: unknown
  current_colors?: unknown
  floor_points?: unknown
  floor_colors?: unknown
  occupied_points?: unknown
  occupied_colors?: unknown
  particles?: unknown
  particle_yaws?: unknown
  particle_scores?: unknown
  dynamic_points?: unknown
  dynamic_velocities?: unknown
  dynamic_scores?: unknown
  trajectory_paths?: unknown
  trajectory_scores?: unknown
  trajectory_safe?: unknown
  trajectory_best_index?: number
  trajectory_goal?: unknown
  point_count?: number
  current_point_count?: number
  accumulated_scan_count?: number
  display_count?: number
  device?: string
  kernel_ms?: number
  floor_point_count?: number
  floor_display_count?: number
  occupied_point_count?: number
  occupied_display_count?: number
  map_render_mode?: string
  occupancy?: {
    backend?: string
    device?: string
    kernel_ms?: number
    encode_ms?: number
    rays?: number
    grid_cells?: number
    grid_width?: number
    grid_height?: number
    free_cells?: number
    display_cells?: number
    occupied_cells?: number
    occupied_display_cells?: number
    display_limited?: boolean
    resolution_m?: number
    world_min_x?: number
    world_min_y?: number
    fixed_origin?: boolean
    encoding?: string
    data?: string
    revision?: number
  }
  sensor?: { x_m?: number; y_m?: number; yaw_rad?: number }
  robot?: { length_m?: number; width_m?: number; height_m?: number }
  scan?: {
    angle_min_rad?: number
    angle_max_rad?: number
    angle_increment_rad?: number
    range_min_m?: number
    range_max_m?: number
  }
  view?: { radius_m?: number; units?: string }
  history_registered?: boolean
  history_paused?: boolean
  pose_source?: string
  registration?: { tf_path?: string[] }
  loop_closures?: unknown
  slam?: {
    match_score?: number
    tracking_accepted?: boolean
    stationary_odometry_locked?: boolean
    scan_motion_override?: boolean
    tracking_correction_limited?: boolean
    map_update_rejected?: boolean
    deskewed?: boolean
    keyframes?: number
    constraints?: number
    loop_closures?: number
    map_resolution_m?: number
    matching_backend?: string
    matching_kernel_ms?: number
  }
  localization?: {
    state?: string
    backend?: string
    requested_particles?: number
    evaluated_particles?: number
    display_particles?: number
    beam_count?: number
    work_items?: number
    pipeline_ms?: number
    cpu_ms?: number
    speedup?: number
    max_score_error?: number
    limited?: boolean
    best_score?: number
    effective_sample_size?: number
    uncertainty?: { x_m?: number; y_m?: number; yaw_rad?: number }
  }
  dynamic_occupancy?: {
    state?: string
    backend?: string
    device?: string
    input_points?: number
    reference_points?: number
    dynamic_points?: number
    display_points?: number
    pipeline_ms?: number
    cpu_ms?: number
    speedup?: number
    max_error?: number
    comparison_limited?: boolean
    dt_s?: number
    stable_radius_m?: number
    tracking_radius_m?: number
    minimum_speed_mps?: number
    mean_speed_mps?: number
    max_speed_mps?: number
    trail_seconds?: number
    trail_distance_limit_m?: number
  }
  depth_projection?: {
    state?: string
    backend?: string
    device?: string
    width?: number
    height?: number
    input_pixels?: number
    valid_points?: number
    display_points?: number
    stride?: number
    fetch_ms?: number
    pipeline_ms?: number
    cpu_ms?: number
    speedup?: number
    max_error_m?: number
    mean_confidence?: number
    encoding?: string
    color_registered?: boolean
    color_fetch_ms?: number
    color_error?: string
  }
  reconstruction?: {
    kind?: string
    color_registered?: boolean
    pose_registered?: boolean
    integration?: {
      state?: string
      backend?: string
      device?: string
      frames_integrated?: number
      input_points?: number
      work_items?: number
      integration_ms?: number
      voxel_size_m?: number
      truncation_m?: number
      voxel_count?: number
      dimensions?: number[]
    }
    extraction?: {
      state?: string
      backend?: string
      surface_voxels?: number
      display_points?: number
      observed_voxels?: number
      allocated_voxels?: number
      extraction_ms?: number
      minimum_weight?: number
    }
  }
  sensor_fusion?: {
    state?: string
    backend?: string
    device?: string
    lidar_points?: number
    depth_points?: number
    fused_points?: number
    matched_points?: number
    unmatched_points?: number
    matched_ratio?: number
    mean_residual_m?: number
    rms_residual_m?: number
    p95_residual_m?: number
    maximum_alignment_distance_m?: number
    mean_confidence?: number
    calibration_hypotheses?: number
    calibration_work_items?: number
    best_score?: number
    correction?: { x_m?: number; y_m?: number; yaw_deg?: number }
    pipeline_ms?: number
    cpu_ms?: number
    speedup?: number
  }
  synchronization?: {
    state?: string
    depth_time_ns?: number
    lidar_time_ns?: number
    delta_seconds?: number
    tolerance_seconds?: number
    rgb_mode?: string
  }
  trajectory_evaluation?: {
    state?: string
    backend?: string
    device?: string
    trajectory_count?: number
    requested_trajectories?: number
    time_steps?: number
    work_items?: number
    safe_trajectories?: number
    unsafe_trajectories?: number
    display_trajectories?: number
    pipeline_ms?: number
    upload_ms?: number
    kernel_ms?: number
    cpu_ms?: number
    speedup?: number
    max_error?: number
    warmup?: boolean
    revision?: number
    best_terminal_distance_m?: number
    best_minimum_clearance_m?: number
    limited?: boolean
    commands_motion?: boolean
  }
  animation?: {
    enabled?: boolean
    show_rays?: boolean
    ray_trail_count?: number
    pulse_hz?: number
    sweep_direction?: string
    accumulate_hits?: boolean
  }
}

interface CameraState {
  zoom: number
  panX: number
  panY: number
  yaw: number
  pitch: number
}

interface GridFrame {
  x: number
  y: number
  yaw: number
}

interface Viewport {
  width: number
  height: number
  ratio: number
}

interface OccupancyTextureData {
  width: number
  height: number
  states: Uint8Array
}

const TOP_VIEW_YAW = Math.PI / 2

const DEFAULT_CAMERA: CameraState = {
  zoom: 1,
  panX: 0,
  panY: 0,
  yaw: TOP_VIEW_YAW,
  pitch: 0,
}

const ROBOT_LOGO_ROTATION_RAD = -Math.PI / 2
const ROBOT_LOGO_SOURCE = { x: 78, y: 48, width: 352, height: 415 } as const
const ROBOT_LOGO_FOOTPRINT_SCALE = 0.58
const ROBOT_FOOTPRINT_VISUAL_SCALE = 0.88
const ROBOT_FIT_RADIUS_MULTIPLIER = 1.65
const MIN_CAMERA_ZOOM = 0.1
const MAX_CAMERA_ZOOM = 120

function numericRows(value: unknown): number[][] {
  if (!Array.isArray(value)) return []
  return value
    .filter((row): row is unknown[] => Array.isArray(row) && row.length >= 2)
    .map(row => row.slice(0, 3).map(item => Number(item)))
    .filter(row => row.every(Number.isFinite))
}

function numericPaths(value: unknown): number[][][] {
  if (!Array.isArray(value)) return []
  return value.map(numericRows).filter(path => path.length >= 2)
}

function finite(value: unknown, fallback = 0): number {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value))
}

function shader(gl: WebGLRenderingContext, kind: number, source: string): WebGLShader {
  const result = gl.createShader(kind)
  if (!result) throw new Error('WebGL could not create a shader')
  gl.shaderSource(result, source)
  gl.compileShader(result)
  if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) {
    const detail = gl.getShaderInfoLog(result) || 'unknown shader error'
    gl.deleteShader(result)
    throw new Error(detail)
  }
  return result
}

function decodeOccupancyTexture(
  encoding: unknown,
  data: unknown,
  widthValue: unknown,
  heightValue: unknown,
): OccupancyTextureData | null {
  if (encoding !== 'u2-base64' || typeof data !== 'string' || !data) return null
  const width = Math.max(0, Math.round(finite(widthValue)))
  const height = Math.max(0, Math.round(finite(heightValue)))
  const cellCount = width * height
  if (!cellCount) return null
  try {
    const packed = window.atob(data)
    if (packed.length < Math.ceil(cellCount / 4)) return null
    const states = new Uint8Array(cellCount)
    for (let index = 0; index < cellCount; index += 1) {
      const value = (packed.charCodeAt(index >> 2) >> ((index & 3) * 2)) & 3
      states[index] = value === 1 ? 127 : value === 2 ? 255 : 0
    }
    return { width, height, states }
  } catch {
    return null
  }
}

function drawOccupancyTexture(
  gl: WebGLRenderingContext,
  bounds: number[][],
  textureData: OccupancyTextureData,
  showFreeSpace: boolean,
  viewport: Viewport,
  camera: CameraState,
  pixelsPerMeter: number,
): () => void {
  let vertex: WebGLShader | null = null
  let fragment: WebGLShader | null = null
  let program: WebGLProgram | null = null
  const positionBuffer = gl.createBuffer()
  const textureCoordinateBuffer = gl.createBuffer()
  const texture = gl.createTexture()
  try {
    vertex = shader(gl, gl.VERTEX_SHADER, `
      attribute vec2 a_position;
      attribute vec2 a_texcoord;
      varying vec2 v_texcoord;
      void main() {
        gl_Position = vec4(a_position, 0.0, 1.0);
        v_texcoord = a_texcoord;
      }
    `)
    fragment = shader(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      uniform sampler2D u_grid;
      uniform float u_show_free;
      varying vec2 v_texcoord;
      void main() {
        float state = texture2D(u_grid, v_texcoord).r;
        if (state < 0.25 || (state < 0.75 && u_show_free < 0.5)) discard;
        vec3 color = state < 0.75
          ? vec3(0.18, 0.68, 0.36)
          : vec3(0.78, 0.88, 0.94);
        gl_FragColor = vec4(color, 1.0);
      }
    `)
    program = gl.createProgram()
    if (!program || !positionBuffer || !textureCoordinateBuffer || !texture) throw new Error('occupancy texture resources unavailable')
    gl.attachShader(program, vertex)
    gl.attachShader(program, fragment)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('occupancy texture program link failed')
    gl.useProgram(program)
    gl.uniform1f(gl.getUniformLocation(program, 'u_show_free'), showFreeSpace ? 1 : 0)

    const positions = new Float32Array(bounds.length * 2)
    bounds.forEach((point, index) => {
      const [screenX, screenY] = worldToScreen(point[0], point[1], finite(point[2]), viewport, camera, pixelsPerMeter)
      positions[index * 2] = (screenX / viewport.width) * 2 - 1
      positions[index * 2 + 1] = 1 - (screenY / viewport.height) * 2
    })
    const textureCoordinates = new Float32Array([
      0, 0, 1, 0, 1, 1,
      0, 0, 1, 1, 0, 1,
    ])
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW)
    const positionLocation = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(positionLocation)
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)
    gl.bindBuffer(gl.ARRAY_BUFFER, textureCoordinateBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, textureCoordinates, gl.STATIC_DRAW)
    const textureCoordinateLocation = gl.getAttribLocation(program, 'a_texcoord')
    gl.enableVertexAttribArray(textureCoordinateLocation)
    gl.vertexAttribPointer(textureCoordinateLocation, 2, gl.FLOAT, false, 0, 0)
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texImage2D(
      gl.TEXTURE_2D, 0, gl.LUMINANCE,
      textureData.width, textureData.height, 0,
      gl.LUMINANCE, gl.UNSIGNED_BYTE, textureData.states,
    )
    gl.drawArrays(gl.TRIANGLES, 0, bounds.length)
  } catch {
    // Keep the live point cloud usable if a browser cannot allocate the map texture.
  }
  return () => {
    if (positionBuffer) gl.deleteBuffer(positionBuffer)
    if (textureCoordinateBuffer) gl.deleteBuffer(textureCoordinateBuffer)
    if (texture) gl.deleteTexture(texture)
    if (program) gl.deleteProgram(program)
    if (vertex) gl.deleteShader(vertex)
    if (fragment) gl.deleteShader(fragment)
  }
}

function worldToScreen(
  x: number,
  y: number,
  z: number,
  viewport: Viewport,
  camera: CameraState,
  pixelsPerMeter: number,
): [number, number] {
  const yawCosine = Math.cos(camera.yaw)
  const yawSine = Math.sin(camera.yaw)
  const yawX = yawCosine * x - yawSine * y
  const yawY = yawSine * x + yawCosine * y
  const pitchCosine = Math.cos(camera.pitch)
  const pitchSine = Math.sin(camera.pitch)
  const pitchedY = pitchCosine * yawY - pitchSine * z
  return [
    viewport.width / 2 + camera.panX + yawX * pixelsPerMeter,
    viewport.height / 2 + camera.panY - pitchedY * pixelsPerMeter,
  ]
}

function screenToWorldPlane(
  screenX: number,
  screenY: number,
  viewport: Viewport,
  camera: CameraState,
  pixelsPerMeter: number,
): [number, number] {
  const yawX = (screenX - viewport.width / 2 - camera.panX) / pixelsPerMeter
  const pitchCosine = Math.cos(camera.pitch)
  const safePitchCosine = Math.abs(pitchCosine) < 0.001
    ? Math.sign(pitchCosine || 1) * 0.001
    : pitchCosine
  const yawY = -(screenY - viewport.height / 2 - camera.panY) / pixelsPerMeter / safePitchCosine
  const yawCosine = Math.cos(camera.yaw)
  const yawSine = Math.sin(camera.yaw)
  return [
    yawCosine * yawX + yawSine * yawY,
    -yawSine * yawX + yawCosine * yawY,
  ]
}

function gridSpacing(pixelsPerMeter: number): number {
  const choices = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
  return choices.find(value => value * pixelsPerMeter >= 46) ?? 500
}

function meterLabel(value: number): string {
  if (Math.abs(value) >= 10) return `${Math.round(value)}m`
  if (Math.abs(value) >= 1) return `${Number(value.toFixed(1))}m`
  return `${Number(value.toFixed(2))}m`
}

function roundedPolygonPath(
  context: CanvasRenderingContext2D,
  points: number[][],
  radius: number,
): void {
  if (points.length < 3) return
  points.forEach((point, index) => {
    const previous = points[(index - 1 + points.length) % points.length]
    const next = points[(index + 1) % points.length]
    const previousLength = Math.max(0.001, Math.hypot(previous[0] - point[0], previous[1] - point[1]))
    const nextLength = Math.max(0.001, Math.hypot(next[0] - point[0], next[1] - point[1]))
    const appliedRadius = Math.min(radius, previousLength * 0.46, nextLength * 0.46)
    const startX = point[0] + (previous[0] - point[0]) / previousLength * appliedRadius
    const startY = point[1] + (previous[1] - point[1]) / previousLength * appliedRadius
    const endX = point[0] + (next[0] - point[0]) / nextLength * appliedRadius
    const endY = point[1] + (next[1] - point[1]) / nextLength * appliedRadius
    if (index === 0) context.moveTo(startX, startY)
    else context.lineTo(startX, startY)
    context.quadraticCurveTo(point[0], point[1], endX, endY)
  })
  context.closePath()
}

function controlStyle(active = false): React.CSSProperties {
  return {
    minWidth: 28,
    height: 25,
    padding: '0 7px',
    border: '1px solid var(--line2)',
    borderRadius: 5,
    background: active ? 'color-mix(in srgb, var(--accent) 22%, var(--panel2))' : 'var(--panel2)',
    color: 'var(--tx2)',
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    cursor: 'pointer',
  }
}

export default function PointCloudViewer({
  scene,
  inputRail,
  onClear,
  onAccumulationToggle,
  onGoalSet,
  clearPending = false,
  accumulationPending = false,
  goalPending = false,
}: {
  scene: unknown
  inputRail?: ReactNode
  onClear?: () => void
  onAccumulationToggle?: () => void
  onGoalSet?: (x: number, y: number) => void
  clearPending?: boolean
  accumulationPending?: boolean
  goalPending?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const occupancyCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
  const occupancyRasterRef = useRef<{
    texture: OccupancyTextureData
    showFreeSpace: boolean
    sensorX: number
    sensorY: number
    gradientDistance: number
    canvas: HTMLCanvasElement
  } | null>(null)
  const dragRef = useRef<{
    x: number
    y: number
    mode: 'pan' | 'rotate'
    camera: CameraState
  } | null>(null)
  const [camera, setCamera] = useState<CameraState>(DEFAULT_CAMERA)
  const [gridFrame, setGridFrame] = useState<GridFrame>({ x: 0, y: 0, yaw: 0 })
  const [showAxes, setShowAxes] = useState(false)
  const [showFreeSpace, setShowFreeSpace] = useState(true)
  const robotLogoRef = useRef<HTMLImageElement | null>(null)
  const [robotLogoReady, setRobotLogoReady] = useState(false)
  const clearViewRadiusFloorRef = useRef(0)
  const initialResetPendingRef = useRef(true)
  const [viewport, setViewport] = useState<Viewport>({ width: 1, height: 360, ratio: 1 })
  const parsed = (scene && typeof scene === 'object' ? scene : {}) as ViewerScene
  const points = useMemo(() => numericRows(parsed.points), [parsed.points])
  const colors = useMemo(() => numericRows(parsed.colors), [parsed.colors])
  const currentPoints = useMemo(() => numericRows(parsed.current_points), [parsed.current_points])
  const currentColors = useMemo(() => numericRows(parsed.current_colors), [parsed.current_colors])
  const floorPoints = useMemo(() => numericRows(parsed.floor_points), [parsed.floor_points])
  const floorColors = useMemo(() => numericRows(parsed.floor_colors), [parsed.floor_colors])
  const occupiedPoints = useMemo(() => numericRows(parsed.occupied_points), [parsed.occupied_points])
  const occupiedColors = useMemo(() => numericRows(parsed.occupied_colors), [parsed.occupied_colors])
  const particles = useMemo(() => numericRows(parsed.particles), [parsed.particles])
  const particleYaws = useMemo(
    () => Array.isArray(parsed.particle_yaws) ? parsed.particle_yaws.map(value => finite(value)) : [],
    [parsed.particle_yaws],
  )
  const particleScores = useMemo(
    () => Array.isArray(parsed.particle_scores) ? parsed.particle_scores.map(value => clamp(finite(value), 0, 1)) : [],
    [parsed.particle_scores],
  )
  const dynamicPoints = useMemo(() => numericRows(parsed.dynamic_points), [parsed.dynamic_points])
  const dynamicScores = useMemo(
    () => Array.isArray(parsed.dynamic_scores) ? parsed.dynamic_scores.map(value => clamp(finite(value), 0, 1)) : [],
    [parsed.dynamic_scores],
  )
  const trajectoryPaths = useMemo(() => numericPaths(parsed.trajectory_paths), [parsed.trajectory_paths])
  const trajectoryScores = useMemo(
    () => Array.isArray(parsed.trajectory_scores) ? parsed.trajectory_scores.map(value => clamp(finite(value), 0, 1)) : [],
    [parsed.trajectory_scores],
  )
  const trajectorySafe = useMemo(
    () => Array.isArray(parsed.trajectory_safe) ? parsed.trajectory_safe.map(Boolean) : [],
    [parsed.trajectory_safe],
  )
  const trajectoryGoal = useMemo(() => numericRows([parsed.trajectory_goal])[0] ?? [], [parsed.trajectory_goal])
  const visibleFloorPoints = useMemo(
    () => showFreeSpace ? floorPoints : [],
    [floorPoints, showFreeSpace],
  )
  const renderedPoints = useMemo(
    () => [...visibleFloorPoints, ...occupiedPoints, ...points, ...currentPoints],
    [currentPoints, occupiedPoints, points, visibleFloorPoints],
  )
  const occupancyBackground = useMemo(() => {
    if (parsed.occupancy?.fixed_origin !== true) return []
    const width = Math.max(0, Math.round(finite(parsed.occupancy.grid_width)))
    const height = Math.max(0, Math.round(finite(parsed.occupancy.grid_height)))
    const resolution = Math.max(0, finite(parsed.occupancy.resolution_m))
    const minimumX = Number(parsed.occupancy.world_min_x)
    const minimumY = Number(parsed.occupancy.world_min_y)
    if (!width || !height || !resolution || !Number.isFinite(minimumX) || !Number.isFinite(minimumY)) return []
    const maximumX = minimumX + width * resolution
    const maximumY = minimumY + height * resolution
    return [
      [minimumX, minimumY, -0.03], [maximumX, minimumY, -0.03], [maximumX, maximumY, -0.03],
      [minimumX, minimumY, -0.03], [maximumX, maximumY, -0.03], [minimumX, maximumY, -0.03],
    ]
  }, [
    parsed.occupancy?.fixed_origin,
    parsed.occupancy?.grid_height,
    parsed.occupancy?.grid_width,
    parsed.occupancy?.resolution_m,
    parsed.occupancy?.world_min_x,
    parsed.occupancy?.world_min_y,
  ])
  const occupancyTexture = useMemo(() => decodeOccupancyTexture(
    parsed.occupancy?.encoding,
    parsed.occupancy?.data,
    parsed.occupancy?.grid_width,
    parsed.occupancy?.grid_height,
  ), [
    parsed.occupancy?.data,
    parsed.occupancy?.encoding,
    parsed.occupancy?.grid_height,
    parsed.occupancy?.grid_width,
    parsed.occupancy?.revision,
  ])
  const [animationClock, setAnimationClock] = useState(0)
  const scanStartedRef = useRef(0)
  const sensor = useMemo(() => ({
    x: finite(parsed.sensor?.x_m),
    y: finite(parsed.sensor?.y_m),
    yaw: finite(parsed.sensor?.yaw_rad),
  }), [parsed.sensor?.x_m, parsed.sensor?.y_m, parsed.sensor?.yaw_rad])

  const animationEnabled = parsed.animation?.enabled !== false
  const hasCurrentPoints = currentPoints.length > 0
  const pulseHz = clamp(finite(parsed.animation?.pulse_hz, 1), 0.05, 30)
  const scanPeriodMs = 1000 / pulseHz
  const replayDurationMs = Math.max(scanPeriodMs, 700)
  const scanAngleMinimum = finite(parsed.scan?.angle_min_rad, -Math.PI)
  const scanAngleMaximum = finite(parsed.scan?.angle_max_rad, Math.PI)
  const scanAngleIncrement = finite(parsed.scan?.angle_increment_rad)
  const clockwiseScan = scanAngleIncrement < 0
  const scanCoverageRad = clamp(Math.abs(scanAngleMaximum - scanAngleMinimum), 0, Math.PI * 2)
  const scanCoverageDeg = scanCoverageRad * 180 / Math.PI
  const fullCircleScan = scanCoverageRad >= Math.PI * 2 - Math.PI / 180
  const robotHeadingYaw = sensor.yaw + (
    fullCircleScan ? 0 : (scanAngleMinimum + scanAngleMaximum) / 2
  )
  const animationPhase = animationEnabled
    ? clamp((animationClock - scanStartedRef.current) / replayDurationMs, 0, 1)
    : 1

  useEffect(() => {
    let cancelled = false
    const logo = new Image()
    logo.onload = () => {
      if (cancelled) return
      robotLogoRef.current = logo
      setRobotLogoReady(true)
    }
    logo.src = '/blacknode-logo-dark.png'
    return () => {
      cancelled = true
      robotLogoRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!animationEnabled || !hasCurrentPoints) return
    let frame = 0
    const now = performance.now()
    const replayInProgress = scanStartedRef.current > 0
      && now - scanStartedRef.current < replayDurationMs
    if (!replayInProgress) scanStartedRef.current = now
    setAnimationClock(now)
    const animate = (now: number) => {
      setAnimationClock(now)
      if (now - scanStartedRef.current < replayDurationMs) {
        frame = window.requestAnimationFrame(animate)
      }
    }
    frame = window.requestAnimationFrame(animate)
    return () => window.cancelAnimationFrame(frame)
  }, [animationEnabled, hasCurrentPoints, parsed.sequence, replayDurationMs])

  const automaticViewRadius = useMemo(() => {
    const pointRadius = renderedPoints.reduce(
      (largest, point) => Math.max(largest, Math.hypot(point[0], point[1])),
      0,
    )
    const configured = finite(parsed.view?.radius_m)
    return clamp(Math.max(configured, pointRadius * 1.08, Math.hypot(sensor.x, sensor.y) + 0.5), 0.5, 10_000)
  }, [parsed.view?.radius_m, renderedPoints, sensor.x, sensor.y])
  // Clear changes map contents, not the camera. Capture the pre-clear metric
  // radius while the request is pending and retain it after the empty scene is
  // applied so removing points cannot briefly enlarge the robot on screen.
  if (clearPending) {
    clearViewRadiusFloorRef.current = Math.max(
      clearViewRadiusFloorRef.current,
      automaticViewRadius,
    )
  }
  const viewRadius = Math.max(automaticViewRadius, clearViewRadiusFloorRef.current)
  const basePixelsPerMeter = Math.max(
    0.001,
    Math.min(viewport.width, viewport.height) / (viewRadius * 2.15),
  )
  const pixelsPerMeter = basePixelsPerMeter * camera.zoom
  const resetCamera = () => {
    clearViewRadiusFloorRef.current = 0
    const robotLength = clamp(finite(parsed.robot?.length_m, 0.25), 0.02, 5)
    const robotWidth = clamp(finite(parsed.robot?.width_m, 0.22), 0.02, 5)
    const focusRadius = Math.max(0.35, Math.max(robotLength, robotWidth) * ROBOT_FIT_RADIUS_MULTIPLIER)
    const viewportSpan = Math.max(1, Math.min(viewport.width, viewport.height))
    const focusedPixelsPerMeter = viewportSpan / (focusRadius * 2.15)
    const resetBasePixelsPerMeter = Math.max(
      0.001,
      viewportSpan / (automaticViewRadius * 2.15),
    )
    const zoom = clamp(
      focusedPixelsPerMeter / resetBasePixelsPerMeter,
      MIN_CAMERA_ZOOM,
      MAX_CAMERA_ZOOM,
    )
    const appliedPixelsPerMeter = resetBasePixelsPerMeter * zoom
    const resetYaw = TOP_VIEW_YAW - robotHeadingYaw
    const resetYawCosine = Math.cos(resetYaw)
    const resetYawSine = Math.sin(resetYaw)
    const focusedSensorX = resetYawCosine * sensor.x - resetYawSine * sensor.y
    const focusedSensorY = resetYawSine * sensor.x + resetYawCosine * sensor.y
    setGridFrame({ x: sensor.x, y: sensor.y, yaw: robotHeadingYaw })
    setCamera({
      zoom,
      yaw: resetYaw,
      pitch: 0,
      panX: -focusedSensorX * appliedPixelsPerMeter,
      panY: focusedSensorY * appliedPixelsPerMeter,
    })
  }

  useEffect(() => {
    if (!initialResetPendingRef.current || !scene || viewport.width <= 1 || viewport.height <= 1) return
    initialResetPendingRef.current = false
    resetCamera()
  }, [scene, viewport.height, viewport.width])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const width = Math.max(1, Math.round(canvas.clientWidth))
      const height = Math.max(1, Math.round(canvas.clientHeight))
      const ratio = Math.min(2, window.devicePixelRatio || 1)
      setViewport(previous => (
        previous.width === width && previous.height === height && previous.ratio === ratio
          ? previous
          : { width, height, ratio }
      ))
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const canvas = occupancyCanvasRef.current
    if (!canvas) return
    const bufferWidth = Math.max(1, Math.round(viewport.width * viewport.ratio))
    const bufferHeight = Math.max(1, Math.round(viewport.height * viewport.ratio))
    if (canvas.width !== bufferWidth) canvas.width = bufferWidth
    if (canvas.height !== bufferHeight) canvas.height = bufferHeight
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(1, 0, 0, 1, 0, 0)
    context.clearRect(0, 0, bufferWidth, bufferHeight)
    if (!occupancyTexture || occupancyBackground.length !== 6) return

    const gradientDistance = clamp(
      Math.max(viewport.width, viewport.height) / Math.max(1, pixelsPerMeter) * 0.55,
      0.5,
      Math.max(0.5, finite(parsed.view?.radius_m, viewRadius)),
    )
    const worldMinimumX = occupancyBackground[0][0]
    const worldMinimumY = occupancyBackground[0][1]
    const worldWidth = occupancyBackground[1][0] - worldMinimumX
    const worldHeight = occupancyBackground[5][1] - worldMinimumY
    let raster = occupancyRasterRef.current
    if (
      raster?.texture !== occupancyTexture
      || raster.showFreeSpace !== showFreeSpace
      || raster.sensorX !== sensor.x
      || raster.sensorY !== sensor.y
      || raster.gradientDistance !== gradientDistance
    ) {
      const rasterCanvas = document.createElement('canvas')
      rasterCanvas.width = occupancyTexture.width
      rasterCanvas.height = occupancyTexture.height
      const rasterContext = rasterCanvas.getContext('2d')
      if (!rasterContext) return
      const image = rasterContext.createImageData(occupancyTexture.width, occupancyTexture.height)
      occupancyTexture.states.forEach((state, index) => {
        const offset = index * 4
        if (state === 127 && showFreeSpace) {
          const column = index % occupancyTexture.width
          const row = Math.floor(index / occupancyTexture.width)
          const worldX = worldMinimumX + (column + 0.5) * worldWidth / occupancyTexture.width
          const worldY = worldMinimumY + (row + 0.5) * worldHeight / occupancyTexture.height
          const distanceMix = clamp(Math.hypot(worldX - sensor.x, worldY - sensor.y) / gradientDistance, 0, 1)
          const smoothMix = distanceMix * distanceMix * (3 - 2 * distanceMix)
          image.data[offset] = Math.round(48 + (55 - 48) * smoothMix)
          image.data[offset + 1] = Math.round(181 + (108 - 181) * smoothMix)
          image.data[offset + 2] = Math.round(108 + (190 - 108) * smoothMix)
          image.data[offset + 3] = Math.round(115 + (80 - 115) * smoothMix)
        } else if (state === 255) {
          image.data[offset] = 218
          image.data[offset + 1] = 235
          image.data[offset + 2] = 245
          image.data[offset + 3] = 235
        }
      })
      rasterContext.putImageData(image, 0, 0)
      raster = {
        texture: occupancyTexture,
        showFreeSpace,
        sensorX: sensor.x,
        sensorY: sensor.y,
        gradientDistance,
        canvas: rasterCanvas,
      }
      occupancyRasterRef.current = raster
    }

    const origin = worldToScreen(
      occupancyBackground[0][0], occupancyBackground[0][1], finite(occupancyBackground[0][2]),
      viewport, camera, pixelsPerMeter,
    )
    const xEnd = worldToScreen(
      occupancyBackground[1][0], occupancyBackground[1][1], finite(occupancyBackground[1][2]),
      viewport, camera, pixelsPerMeter,
    )
    const yEnd = worldToScreen(
      occupancyBackground[5][0], occupancyBackground[5][1], finite(occupancyBackground[5][2]),
      viewport, camera, pixelsPerMeter,
    )
    context.imageSmoothingEnabled = false
    context.globalCompositeOperation = 'screen'
    context.setTransform(
      viewport.ratio * (xEnd[0] - origin[0]) / occupancyTexture.width,
      viewport.ratio * (xEnd[1] - origin[1]) / occupancyTexture.width,
      viewport.ratio * (yEnd[0] - origin[0]) / occupancyTexture.height,
      viewport.ratio * (yEnd[1] - origin[1]) / occupancyTexture.height,
      viewport.ratio * origin[0],
      viewport.ratio * origin[1],
    )
    context.drawImage(raster.canvas, 0, 0)
    context.globalCompositeOperation = 'source-over'
  }, [camera, occupancyBackground, occupancyTexture, parsed.view?.radius_m, pixelsPerMeter, sensor.x, sensor.y, showFreeSpace, viewRadius, viewport])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { antialias: true, alpha: true })
    if (!gl) return
    const bufferWidth = Math.max(1, Math.round(viewport.width * viewport.ratio))
    const bufferHeight = Math.max(1, Math.round(viewport.height * viewport.ratio))
    if (canvas.width !== bufferWidth) canvas.width = bufferWidth
    if (canvas.height !== bufferHeight) canvas.height = bufferHeight
    gl.viewport(0, 0, bufferWidth, bufferHeight)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    const vertexCount = renderedPoints.length
    if (vertexCount === 0) return

    let vertex: WebGLShader | null = null
    let fragment: WebGLShader | null = null
    let program: WebGLProgram | null = null
    try {
      vertex = shader(gl, gl.VERTEX_SHADER, `
        attribute vec2 a_position;
        attribute vec3 a_color;
        attribute float a_size;
        attribute float a_square;
        varying vec3 v_color;
        varying float v_square;
        void main() {
          gl_Position = vec4(a_position, 0.0, 1.0);
          gl_PointSize = a_size;
          v_color = a_color;
          v_square = a_square;
        }
      `)
      fragment = shader(gl, gl.FRAGMENT_SHADER, `
        precision mediump float;
        varying vec3 v_color;
        varying float v_square;
        void main() {
          vec2 centered = gl_PointCoord - vec2(0.5);
          if (v_square < 0.5 && dot(centered, centered) > 0.25) discard;
          gl_FragColor = vec4(v_color, 1.0);
        }
      `)
      program = gl.createProgram()
      if (!program) return
      gl.attachShader(program, vertex)
      gl.attachShader(program, fragment)
      gl.linkProgram(program)
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return
      gl.useProgram(program)
    } catch {
      return
    }

    const positions = new Float32Array(vertexCount * 2)
    const palette = new Float32Array(vertexCount * 3)
    const pointSizes = new Float32Array(vertexCount)
    const squarePoints = new Float32Array(vertexCount)
    const occupancyCellSize = Math.max(
      1.25 * viewport.ratio,
      finite(parsed.occupancy?.resolution_m, 0.05) * pixelsPerMeter * viewport.ratio * 1.45,
    )
    renderedPoints.forEach((point, index) => {
      const vertexIndex = index
      const [screenX, screenY] = worldToScreen(
        point[0], point[1], finite(point[2]), viewport, camera, pixelsPerMeter,
      )
      positions[vertexIndex * 2] = (screenX / viewport.width) * 2 - 1
      positions[vertexIndex * 2 + 1] = 1 - (screenY / viewport.height) * 2
      const occupancyPointCount = visibleFloorPoints.length + occupiedPoints.length
      const mapIndex = index - occupancyPointCount
      const currentIndex = mapIndex - points.length
      const isFloor = index < visibleFloorPoints.length
      const isOccupied = !isFloor && index < occupancyPointCount
      const occupiedIndex = index - visibleFloorPoints.length
      const color = isFloor
        ? floorColors[index] ?? [0.18, 0.68, 0.36]
        : isOccupied
          ? occupiedColors[occupiedIndex] ?? [0.78, 0.88, 0.94]
        : currentIndex >= 0
          ? currentColors[currentIndex] ?? [0.0, 0.78, 1.0]
          : colors[mapIndex] ?? [0.04, 0.36, 0.48]
      palette[vertexIndex * 3] = clamp(color[0], 0, 1)
      palette[vertexIndex * 3 + 1] = clamp(color[1], 0, 1)
      palette[vertexIndex * 3 + 2] = clamp(color[2], 0, 1)
      pointSizes[vertexIndex] = isFloor || isOccupied
        ? occupancyCellSize
        : Math.max(3.5, 4.5 * viewport.ratio)
      squarePoints[vertexIndex] = isFloor || isOccupied ? 1 : 0
    })

    const positionBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW)
    const positionLocation = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(positionLocation)
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

    const colorBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, palette, gl.STATIC_DRAW)
    const colorLocation = gl.getAttribLocation(program, 'a_color')
    gl.enableVertexAttribArray(colorLocation)
    gl.vertexAttribPointer(colorLocation, 3, gl.FLOAT, false, 0, 0)

    const sizeBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, sizeBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, pointSizes, gl.STATIC_DRAW)
    const sizeLocation = gl.getAttribLocation(program, 'a_size')
    gl.enableVertexAttribArray(sizeLocation)
    gl.vertexAttribPointer(sizeLocation, 1, gl.FLOAT, false, 0, 0)

    const squareBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, squareBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, squarePoints, gl.STATIC_DRAW)
    const squareLocation = gl.getAttribLocation(program, 'a_square')
    gl.enableVertexAttribArray(squareLocation)
    gl.vertexAttribPointer(squareLocation, 1, gl.FLOAT, false, 0, 0)
    gl.drawArrays(gl.POINTS, 0, renderedPoints.length)

    return () => {
      gl.deleteBuffer(positionBuffer)
      gl.deleteBuffer(colorBuffer)
      gl.deleteBuffer(sizeBuffer)
      gl.deleteBuffer(squareBuffer)
      if (program) gl.deleteProgram(program)
      if (vertex) gl.deleteShader(vertex)
      if (fragment) gl.deleteShader(fragment)
    }
  }, [camera, colors, currentColors, floorColors, occupiedColors, occupiedPoints.length, parsed.occupancy?.resolution_m, pixelsPerMeter, points.length, renderedPoints, viewport, visibleFloorPoints.length])

  useEffect(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    const bufferWidth = Math.max(1, Math.round(viewport.width * viewport.ratio))
    const bufferHeight = Math.max(1, Math.round(viewport.height * viewport.ratio))
    if (overlay.width !== bufferWidth) overlay.width = bufferWidth
    if (overlay.height !== bufferHeight) overlay.height = bufferHeight
    const context = overlay.getContext('2d')
    if (!context) return
    context.setTransform(viewport.ratio, 0, 0, viewport.ratio, 0, 0)
    context.clearRect(0, 0, viewport.width, viewport.height)
    context.lineWidth = 1
    context.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'

    const gridHeadingCosine = Math.cos(gridFrame.yaw)
    const gridHeadingSine = Math.sin(gridFrame.yaw)
    const gridFrameToScreen = (forward: number, lateral: number, z: number) => worldToScreen(
      gridFrame.x + gridHeadingCosine * forward - gridHeadingSine * lateral,
      gridFrame.y + gridHeadingSine * forward + gridHeadingCosine * lateral,
      z,
      viewport,
      camera,
      pixelsPerMeter,
    )
    const spacing = gridSpacing(pixelsPerMeter)
    const reach = Math.min(
      10_000,
      Math.ceil((Math.hypot(viewport.width, viewport.height) + Math.hypot(camera.panX, camera.panY) * 2) / pixelsPerMeter / spacing) * spacing,
    )
    const steps = Math.min(100, Math.ceil(reach / spacing))
    context.strokeStyle = 'rgba(117, 155, 181, 0.14)'
    context.beginPath()
    for (let index = -steps; index <= steps; index += 1) {
      const value = index * spacing
      const [x1, y1] = gridFrameToScreen(value, -reach, 0)
      const [x2, y2] = gridFrameToScreen(value, reach, 0)
      const [x3, y3] = gridFrameToScreen(-reach, value, 0)
      const [x4, y4] = gridFrameToScreen(reach, value, 0)
      context.moveTo(x1, y1)
      context.lineTo(x2, y2)
      context.moveTo(x3, y3)
      context.lineTo(x4, y4)
    }
    context.stroke()

    if (showAxes) {
      const drawAxis = (endX: number, endY: number, endZ: number, color: string) => {
        const start = gridFrameToScreen(-endX, -endY, -endZ)
        const end = gridFrameToScreen(endX, endY, endZ)
        context.strokeStyle = color
        context.lineWidth = 1.5
        context.beginPath()
        context.moveTo(start[0], start[1])
        context.lineTo(end[0], end[1])
        context.stroke()
      }
      drawAxis(reach, 0, 0, 'rgba(255, 91, 91, 0.68)')
      drawAxis(0, reach, 0, 'rgba(83, 224, 145, 0.68)')
      drawAxis(0, 0, Math.min(reach, viewRadius * 0.45), 'rgba(83, 154, 255, 0.78)')

      context.fillStyle = 'rgba(186, 211, 228, 0.72)'
      for (let index = -steps; index <= steps; index += 1) {
        if (index === 0) continue
        const value = index * spacing
        const xTick = gridFrameToScreen(value, 0, 0)
        if (xTick[0] > 12 && xTick[0] < viewport.width - 28 && xTick[1] > 12 && xTick[1] < viewport.height - 12) {
          context.fillText(meterLabel(value), xTick[0] + 3, xTick[1] - 4)
        }
        const yTick = gridFrameToScreen(0, value, 0)
        if (yTick[0] > 12 && yTick[0] < viewport.width - 28 && yTick[1] > 12 && yTick[1] < viewport.height - 12) {
          context.fillText(meterLabel(value), yTick[0] + 4, yTick[1] - 3)
        }
      }
    }

    const sensorScreen = worldToScreen(sensor.x, sensor.y, 0, viewport, camera, pixelsPerMeter)
    const scanMinimum = sensor.yaw + scanAngleMinimum
    const scanMaximum = sensor.yaw + scanAngleMaximum
    const sweepOrderedPoints = [...currentPoints].sort((left, right) => {
      const leftAngle = Math.atan2(left[1] - sensor.y, left[0] - sensor.x)
      const rightAngle = Math.atan2(right[1] - sensor.y, right[0] - sensor.x)
      const direction = clockwiseScan ? -1 : 1
      const leftOffset = ((leftAngle - scanMinimum) * direction + Math.PI * 2) % (Math.PI * 2)
      const rightOffset = ((rightAngle - scanMinimum) * direction + Math.PI * 2) % (Math.PI * 2)
      return leftOffset - rightOffset
    })
    const rayLength = Math.min(viewRadius, Math.max(spacing * 2, viewRadius * 0.82))
    if (!fullCircleScan) {
      context.setLineDash([5, 5])
      context.strokeStyle = 'rgba(133, 162, 184, 0.42)'
      context.lineWidth = 1.3
      context.beginPath()
      for (const angle of [scanMinimum, scanMaximum]) {
        const end = worldToScreen(
          sensor.x + Math.cos(angle) * rayLength,
          sensor.y + Math.sin(angle) * rayLength,
          0,
          viewport,
          camera,
          pixelsPerMeter,
        )
        context.moveTo(sensorScreen[0], sensorScreen[1])
        context.lineTo(end[0], end[1])
      }
      context.stroke()
      context.setLineDash([])
    }

    if (animationEnabled && currentPoints.length > 0) {
      if (parsed.animation?.show_rays !== false) {
        const activeIndex = Math.min(
          sweepOrderedPoints.length - 1,
          Math.max(0, Math.floor(animationPhase * sweepOrderedPoints.length)),
        )
        const trailCount = clamp(finite(parsed.animation?.ray_trail_count, 96), 1, 512)
        const trailStart = Math.max(0, activeIndex - trailCount + 1)
        context.strokeStyle = 'rgba(80, 232, 145, 0.52)'
        context.lineWidth = 1.1
        context.beginPath()
        for (let index = trailStart; index <= activeIndex; index += 1) {
          const hit = sweepOrderedPoints[index]
          const projected = worldToScreen(
            hit[0], hit[1], finite(hit[2]), viewport, camera, pixelsPerMeter,
          )
          context.moveTo(sensorScreen[0], sensorScreen[1])
          context.lineTo(projected[0], projected[1])
        }
        context.stroke()
        const activeHit = sweepOrderedPoints[activeIndex]
        const projectedHit = worldToScreen(
          activeHit[0], activeHit[1], finite(activeHit[2]), viewport, camera, pixelsPerMeter,
        )
        context.strokeStyle = '#72ff9d'
        context.lineWidth = 2.6
        context.beginPath()
        context.moveTo(sensorScreen[0], sensorScreen[1])
        context.lineTo(projectedHit[0], projectedHit[1])
        context.stroke()
        context.fillStyle = '#b9ffca'
        context.beginPath()
        context.arc(projectedHit[0], projectedHit[1], 4.5, 0, Math.PI * 2)
        context.fill()
      }
    }

    if (particles.length > 0) {
      for (let index = 0; index < particles.length; index += 1) {
        const particle = particles[index]
        const score = particleScores[index] ?? 0
        const yaw = particleYaws[index] ?? 0
        const projected = worldToScreen(
          particle[0], particle[1], finite(particle[2]), viewport, camera, pixelsPerMeter,
        )
        const red = Math.round(143 - score * 57)
        const green = Math.round(105 + score * 139)
        const blue = Math.round(224 - score * 73)
        context.fillStyle = `rgba(${red}, ${green}, ${blue}, ${0.18 + score * 0.72})`
        context.beginPath()
        context.arc(projected[0], projected[1], 1.2 + score * 2.1, 0, Math.PI * 2)
        context.fill()
        if (score > 0.72) {
          const heading = worldToScreen(
            particle[0] + Math.cos(yaw) * 0.12,
            particle[1] + Math.sin(yaw) * 0.12,
            finite(particle[2]),
            viewport,
            camera,
            pixelsPerMeter,
          )
          context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${0.3 + score * 0.65})`
          context.lineWidth = 0.8 + score
          context.beginPath()
          context.moveTo(projected[0], projected[1])
          context.lineTo(heading[0], heading[1])
          context.stroke()
        }
      }
    }

    if (trajectoryPaths.length > 0) {
      context.save()
      context.lineCap = 'round'
      context.lineJoin = 'round'
      const bestIndex = Math.max(0, Math.min(
        trajectoryPaths.length - 1,
        Math.round(finite(parsed.trajectory_best_index)),
      ))
      for (let index = 0; index < trajectoryPaths.length; index += 1) {
        const path = trajectoryPaths[index]
        const score = trajectoryScores[index] ?? 0
        const safe = trajectorySafe[index] ?? false
        const best = index === bestIndex
        const color = best ? '91, 235, 255' : safe ? '102, 224, 145' : '255, 91, 91'
        context.strokeStyle = `rgba(${color}, ${best ? 0.96 : 0.18 + score * 0.38})`
        context.lineWidth = best ? 3.0 : 0.8 + score * 0.9
        context.shadowColor = best ? 'rgba(91, 235, 255, 0.78)' : 'transparent'
        context.shadowBlur = best ? 9 : 0
        context.beginPath()
        path.forEach((point, pointIndex) => {
          const projected = worldToScreen(
            point[0], point[1], finite(point[2]), viewport, camera, pixelsPerMeter,
          )
          if (pointIndex === 0) context.moveTo(projected[0], projected[1])
          else context.lineTo(projected[0], projected[1])
        })
        context.stroke()
      }
      if (trajectoryGoal.length >= 2) {
        const goal = worldToScreen(
          trajectoryGoal[0], trajectoryGoal[1], finite(trajectoryGoal[2]), viewport, camera, pixelsPerMeter,
        )
        context.shadowColor = 'rgba(91, 235, 255, 0.72)'
        context.shadowBlur = 8
        context.strokeStyle = 'rgba(145, 244, 255, 0.96)'
        context.lineWidth = 2
        context.beginPath()
        context.arc(goal[0], goal[1], 6, 0, Math.PI * 2)
        context.moveTo(goal[0] - 9, goal[1])
        context.lineTo(goal[0] + 9, goal[1])
        context.moveTo(goal[0], goal[1] - 9)
        context.lineTo(goal[0], goal[1] + 9)
        context.stroke()
      }
      context.restore()
    }

    if (dynamicPoints.length > 0) {
      // Motion is position-only for now: orange points communicate the moving
      // returns without implying a trustworthy direction vector.
      context.save()
      context.globalCompositeOperation = 'screen'
      for (let index = 0; index < dynamicPoints.length; index += 1) {
        const point = dynamicPoints[index]
        const score = dynamicScores[index] ?? 0
        const projected = worldToScreen(
          point[0], point[1], finite(point[2]), viewport, camera, pixelsPerMeter,
        )
        const color = '255, 169, 64'
        context.shadowColor = `rgba(${color}, 0.58)`
        context.shadowBlur = 4 + score * 4
        context.fillStyle = `rgba(${color}, ${0.68 + score * 0.24})`
        context.beginPath()
        context.arc(projected[0], projected[1], 2.5 + score * 1.8, 0, Math.PI * 2)
        context.fill()
      }
      context.restore()
    }

    const robotLength = clamp(finite(parsed.robot?.length_m, 0.25), 0.02, 5)
    const robotWidth = clamp(finite(parsed.robot?.width_m, 0.22), 0.02, 5)
    const visualRobotLength = robotLength * ROBOT_FOOTPRINT_VISUAL_SCALE
    const visualRobotWidth = robotWidth * ROBOT_FOOTPRINT_VISUAL_SCALE
    const headingCosine = Math.cos(robotHeadingYaw)
    const headingSine = Math.sin(robotHeadingYaw)
    const robotCorners = [
      [visualRobotLength / 2, visualRobotWidth / 2],
      [visualRobotLength / 2, -visualRobotWidth / 2],
      [-visualRobotLength / 2, -visualRobotWidth / 2],
      [-visualRobotLength / 2, visualRobotWidth / 2],
    ].map(([localX, localY]) => worldToScreen(
      sensor.x + headingCosine * localX - headingSine * localY,
      sensor.y + headingSine * localX + headingCosine * localY,
      0,
      viewport,
      camera,
      pixelsPerMeter,
    ))
    const shortestRobotEdge = robotCorners.reduce((shortest, corner, index) => {
      const next = robotCorners[(index + 1) % robotCorners.length]
      return Math.min(shortest, Math.hypot(next[0] - corner[0], next[1] - corner[1]))
    }, Number.POSITIVE_INFINITY)
    const robotCornerRadius = clamp(shortestRobotEdge * 0.44, 3, 14)
    context.shadowColor = 'rgba(43, 220, 238, 0.4)'
    context.shadowBlur = 9
    context.fillStyle = 'rgba(30, 199, 220, 0.3)'
    context.strokeStyle = 'rgba(124, 244, 255, 0.92)'
    context.lineWidth = 1.6
    context.beginPath()
    roundedPolygonPath(context, robotCorners, robotCornerRadius)
    context.fill()
    context.stroke()
    context.shadowBlur = 0

    const forwardUnit = worldToScreen(
      sensor.x + headingCosine,
      sensor.y + headingSine,
      0,
      viewport,
      camera,
      pixelsPerMeter,
    )
    const lateralUnit = worldToScreen(
      sensor.x - headingSine,
      sensor.y + headingCosine,
      0,
      viewport,
      camera,
      pixelsPerMeter,
    )
    const logo = robotLogoRef.current
    if (logo) {
      // Treat the B as a decal fixed to the robot plane. It shares the exact
      // forward/lateral projection used by the footprint. Compensating for the
      // footprint dimensions before that transform preserves the source ratio.
      const logoWorldScale = Math.min(
        visualRobotLength * ROBOT_LOGO_FOOTPRINT_SCALE / ROBOT_LOGO_SOURCE.height,
        visualRobotWidth * ROBOT_LOGO_FOOTPRINT_SCALE / ROBOT_LOGO_SOURCE.width,
      )
      const logoWidth = ROBOT_LOGO_SOURCE.width * logoWorldScale / visualRobotWidth
      const logoHeight = ROBOT_LOGO_SOURCE.height * logoWorldScale / visualRobotLength
      context.save()
      context.beginPath()
      roundedPolygonPath(context, robotCorners, robotCornerRadius)
      context.clip()
      context.transform(
        (forwardUnit[0] - sensorScreen[0]) * visualRobotLength,
        (forwardUnit[1] - sensorScreen[1]) * visualRobotLength,
        (lateralUnit[0] - sensorScreen[0]) * visualRobotWidth,
        (lateralUnit[1] - sensorScreen[1]) * visualRobotWidth,
        sensorScreen[0],
        sensorScreen[1],
      )
      context.rotate(ROBOT_LOGO_ROTATION_RAD)
      context.globalAlpha = 0.8
      context.globalCompositeOperation = 'screen'
      context.drawImage(
        logo,
        ROBOT_LOGO_SOURCE.x,
        ROBOT_LOGO_SOURCE.y,
        ROBOT_LOGO_SOURCE.width,
        ROBOT_LOGO_SOURCE.height,
        -logoWidth / 2,
        -logoHeight / 2,
        logoWidth,
        logoHeight,
      )
      context.restore()
    } else {
      context.fillStyle = 'rgba(220, 252, 255, 0.9)'
      context.font = `800 ${clamp(shortestRobotEdge * 0.66, 9, 18)}px var(--font-ui)`
      context.textAlign = 'center'
      context.textBaseline = 'middle'
      context.fillText('B', sensorScreen[0], sensorScreen[1])
      context.textAlign = 'start'
      context.textBaseline = 'alphabetic'
    }

    const scalePixels = spacing * pixelsPerMeter
    const scaleX = 16
    const scaleY = viewport.height - 18
    context.strokeStyle = 'rgba(238, 247, 255, 0.9)'
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(scaleX, scaleY - 4)
    context.lineTo(scaleX, scaleY)
    context.lineTo(scaleX + scalePixels, scaleY)
    context.lineTo(scaleX + scalePixels, scaleY - 4)
    context.stroke()
    context.fillStyle = 'rgba(238, 247, 255, 0.9)'
    context.fillText(meterLabel(spacing), scaleX, scaleY - 7)
  }, [
    animationEnabled,
    animationPhase,
    camera,
    currentPoints,
    dynamicPoints,
    dynamicScores,
    gridFrame,
    parsed.animation?.ray_trail_count,
    parsed.animation?.show_rays,
    particleScores,
    particleYaws,
    particles,
    parsed.robot?.length_m,
    parsed.robot?.width_m,
    parsed.scan?.angle_max_rad,
    parsed.scan?.angle_min_rad,
    parsed.scan?.angle_increment_rad,
    parsed.trajectory_best_index,
    pixelsPerMeter,
    robotHeadingYaw,
    robotLogoReady,
    sensor,
    showAxes,
    trajectoryGoal,
    trajectoryPaths,
    trajectorySafe,
    trajectoryScores,
    viewRadius,
    viewport,
  ])

  const pointCount = Number(parsed.point_count ?? points.length)
  const currentPointCount = Number(parsed.current_point_count ?? currentPoints.length)
  const accumulatedScanCount = Number(parsed.accumulated_scan_count ?? (points.length ? 1 : 0))
  const displayCount = Number(parsed.display_count ?? points.length)
  const kernelMs = Number(parsed.kernel_ms ?? 0)
  const occupancyKernelMs = Number(parsed.occupancy?.kernel_ms ?? 0)
  const occupancyEncodeMs = Number(parsed.occupancy?.encode_ms ?? 0)
  const freeCellCount = Number(parsed.floor_point_count ?? parsed.occupancy?.free_cells ?? floorPoints.length)
  const occupiedCellCount = Number(parsed.occupied_point_count ?? parsed.occupancy?.occupied_cells ?? occupiedPoints.length)
  const yawDegrees = Math.round(camera.yaw * 180 / Math.PI)
  const pitchDegrees = Math.round(camera.pitch * 180 / Math.PI)

  return (
    <div
      className="nodrag"
      onMouseDown={event => event.stopPropagation()}
      style={{
        margin: '7px 9px 8px',
        width: 'calc(100% - 18px)',
        flex: '1 1 auto',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        overflow: 'visible',
        border: '1px solid var(--line2)',
        borderRadius: 'var(--bn-node-inner-radius, 7px)',
        background: '#242424',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 5, padding: '5px 7px',
        borderBottom: '1px solid var(--line)', background: 'var(--panel)',
      }}>
        <button type="button" style={controlStyle()} title="Zoom out" onClick={() => setCamera(value => ({ ...value, zoom: clamp(value.zoom / 1.25, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM) }))}>−</button>
        <button type="button" style={controlStyle()} title="Zoom in" onClick={() => setCamera(value => ({ ...value, zoom: clamp(value.zoom * 1.25, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM) }))}>+</button>
        <button type="button" style={controlStyle()} title="Orbit left" onClick={() => setCamera(value => ({ ...value, yaw: value.yaw - Math.PI / 12 }))}>↶</button>
        <button type="button" style={controlStyle()} title="Orbit right" onClick={() => setCamera(value => ({ ...value, yaw: value.yaw + Math.PI / 12 }))}>↷</button>
        <button type="button" style={controlStyle()} title="Tilt camera up" onClick={() => setCamera(value => ({ ...value, pitch: clamp(value.pitch + Math.PI / 18, -1.45, 1.45) }))}>↑</button>
        <button type="button" style={controlStyle()} title="Tilt camera down" onClick={() => setCamera(value => ({ ...value, pitch: clamp(value.pitch - Math.PI / 18, -1.45, 1.45) }))}>↓</button>
        <button type="button" style={controlStyle(camera.pitch === 0 && camera.yaw === TOP_VIEW_YAW)} title="Top view with world +X (red axis) pointing up" onClick={() => setCamera(value => ({ ...value, yaw: TOP_VIEW_YAW, pitch: 0 }))}>Top</button>
        <button type="button" style={controlStyle()} title="Capture and align the grid at the current robot pose, then keep the grid and map fixed" onClick={resetCamera}>Reset</button>
        <label
          title="Show fixed map X, Y, and Z axes with metric tick labels"
          style={{ ...controlStyle(showAxes), display: 'inline-flex', alignItems: 'center', gap: 5, width: 'auto' }}
        >
          <input
            type="checkbox"
            checked={showAxes}
            onChange={event => setShowAxes(event.target.checked)}
            style={{ margin: 0, accentColor: 'var(--accent)' }}
          />
          Axes
        </label>
        {onAccumulationToggle && (!parsed.depth_projection || parsed.reconstruction) && (
          <button
            type="button"
            disabled={accumulationPending}
            style={controlStyle(!parsed.history_paused)}
            title={parsed.history_paused ? 'Resume adding scan returns to the fixed world cloud' : 'Freeze the fixed world cloud while keeping the live sweep visible'}
            onClick={onAccumulationToggle}
          >
            {accumulationPending ? 'Updating…' : `Accumulate: ${parsed.history_paused ? 'Off' : 'On'}`}
          </button>
        )}
        <button
          type="button"
          style={controlStyle(showFreeSpace)}
          title={showFreeSpace ? 'Hide free-space floor fill; stored occupancy data is preserved' : 'Show free-space floor fill'}
          onClick={() => setShowFreeSpace(value => !value)}
        >
          Floor: {showFreeSpace ? 'On' : 'Off'}
        </button>
        {onClear && (!parsed.depth_projection || parsed.reconstruction) && <button type="button" disabled={clearPending} style={controlStyle()} title={parsed.reconstruction ? 'Clear the persistent RGB-D reconstruction volume and pause integration' : 'Clear accumulated scan history and switch accumulation off'} onClick={onClear}>{clearPending ? 'Clearing…' : parsed.reconstruction ? 'Clear volume' : 'Clear history'}</button>}
        <span style={{ marginLeft: 'auto', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {camera.zoom.toFixed(2)}× · yaw {yawDegrees}° · pitch {pitchDegrees}°
        </span>
      </div>
      <div
        data-bn-viewer-canvas-region
        style={{ position: 'relative', flex: '1 1 auto', minHeight: 80 }}
      >
        {inputRail}
        <canvas
          ref={occupancyCanvasRef}
          aria-hidden="true"
          style={{ position: 'absolute', inset: 0, zIndex: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        />
        <canvas
          ref={canvasRef}
          className="bn-viewer-wheel-capture"
          aria-label="Interactive live point-cloud Viewer"
          onContextMenu={event => {
            event.preventDefault()
            event.stopPropagation()
          }}
          onDoubleClick={resetCamera}
          onPointerDown={event => {
            if (event.shiftKey && event.button === 0 && onGoalSet) {
              event.preventDefault()
              event.stopPropagation()
              if (goalPending) return
              const bounds = event.currentTarget.getBoundingClientRect()
              const [goalX, goalY] = screenToWorldPlane(
                event.clientX - bounds.left,
                event.clientY - bounds.top,
                viewport,
                camera,
                pixelsPerMeter,
              )
              onGoalSet(goalX, goalY)
              return
            }
            event.stopPropagation()
            event.currentTarget.setPointerCapture(event.pointerId)
            dragRef.current = {
              x: event.clientX,
              y: event.clientY,
              mode: event.button === 2 ? 'rotate' : 'pan',
              camera,
            }
          }}
          onPointerMove={event => {
            const drag = dragRef.current
            if (!drag) return
            const deltaX = event.clientX - drag.x
            const deltaY = event.clientY - drag.y
            if (drag.mode === 'rotate') {
              setCamera({
                ...drag.camera,
                yaw: drag.camera.yaw + deltaX * 0.008,
                pitch: clamp(drag.camera.pitch - deltaY * 0.008, -1.45, 1.45),
              })
            } else {
              setCamera({ ...drag.camera, panX: drag.camera.panX + deltaX, panY: drag.camera.panY + deltaY })
            }
          }}
          onPointerUp={event => {
            event.currentTarget.releasePointerCapture(event.pointerId)
            dragRef.current = null
          }}
          onPointerCancel={() => { dragRef.current = null }}
          onWheel={event => {
            event.preventDefault()
            event.stopPropagation()
            const bounds = event.currentTarget.getBoundingClientRect()
            const cursorX = event.clientX - bounds.left - viewport.width / 2
            const cursorY = event.clientY - bounds.top - viewport.height / 2
            const factor = Math.exp(-event.deltaY * 0.001)
            setCamera(value => {
              const zoom = clamp(value.zoom * factor, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM)
              const applied = zoom / value.zoom
              return {
                ...value,
                zoom,
                panX: cursorX - (cursorX - value.panX) * applied,
                panY: cursorY - (cursorY - value.panY) * applied,
              }
            })
          }}
          style={{ position: 'relative', zIndex: 1, display: 'block', width: '100%', height: '100%', cursor: 'grab', touchAction: 'none' }}
        />
        <canvas
          ref={overlayRef}
          aria-hidden="true"
          style={{ position: 'absolute', inset: 0, zIndex: 2, width: '100%', height: '100%', pointerEvents: 'none' }}
        />
        <div style={{
          position: 'absolute', zIndex: 3, top: 8, left: 9, display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 7px', borderRadius: 5, background: 'rgba(3, 10, 16, 0.78)',
          border: '1px solid rgba(86, 217, 145, 0.38)', color: '#8df0b5',
          fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
        }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: currentPoints.length ? '#56d991' : '#71808d' }} />
          {currentPoints.length
            ? parsed.sensor_fusion?.backend === 'warp-hash-grid'
              ? `SENSOR FUSION · ${Number(parsed.sensor_fusion.matched_points ?? 0).toLocaleString()} ALIGNED`
              : parsed.reconstruction?.integration?.backend === 'warp'
              ? `RGB-D RECONSTRUCTION · ${Number(parsed.reconstruction.integration.frames_integrated ?? 0).toLocaleString()} FRAMES`
              : parsed.depth_projection?.backend === 'warp'
              ? `METRIC DEPTH · ${Number(parsed.depth_projection.width ?? 0)}×${Number(parsed.depth_projection.height ?? 0)}`
              : `CURRENT SCAN #${Number(parsed.sequence ?? 0).toLocaleString()} · ${clockwiseScan ? 'CW' : 'CCW'} ${Math.round(animationPhase * 100)}%`
            : parsed.depth_projection ? 'WAITING FOR DEPTH' : 'WAITING FOR SCAN'}
        </div>
        {parsed.occupancy?.backend === 'warp' && (
          <div style={{
            position: 'absolute', zIndex: 3, top: 8, right: 9, display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 7px', borderRadius: 5, background: 'rgba(3, 10, 16, 0.82)',
            border: `1px solid ${parsed.history_paused ? 'rgba(242, 184, 75, 0.45)' : 'rgba(79, 192, 122, 0.48)'}`,
            color: parsed.history_paused ? '#f2c66d' : '#8df0b5',
            fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: parsed.history_paused ? '#f2b84b' : freeCellCount > 0 ? '#4fc07a' : '#71808d',
            }} />
            {parsed.history_paused
              ? 'WARP MAP · FROZEN'
              : freeCellCount > 0
                ? `WARP MAP · FILLING ${freeCellCount.toLocaleString()} FREE · ${occupiedCellCount.toLocaleString()} WALL`
                : 'WARP MAP · READY'}
          </div>
        )}
        {parsed.dynamic_occupancy?.backend === 'warp-hash-grid' && (
          <div style={{
            position: 'absolute', zIndex: 3, top: 39, right: 9, display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 7px', borderRadius: 5, background: 'rgba(18, 8, 12, 0.82)',
            border: '1px solid rgba(255, 169, 64, 0.48)', color: '#ffb257',
            fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: dynamicPoints.length ? '#ffa940' : '#8b685f' }} />
            {parsed.dynamic_occupancy.state === 'warming'
              ? 'HASHGRID MOTION · WARMING'
              : `HASHGRID MOTION · ${Number(parsed.dynamic_occupancy.dynamic_points ?? 0).toLocaleString()} MOVING`}
          </div>
        )}
        {parsed.sensor_fusion?.backend === 'warp-hash-grid' && (
          <div style={{
            position: 'absolute', zIndex: 3, top: 39, right: 9, display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 7px', borderRadius: 5, background: 'rgba(4, 18, 22, 0.84)',
            border: '1px solid rgba(91, 235, 255, 0.48)', color: '#91f4ff',
            fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: finite(parsed.sensor_fusion.matched_ratio) > 0.5 ? '#66e091' : '#f2b84b' }} />
            HASHGRID ALIGN · {(finite(parsed.sensor_fusion.mean_residual_m) * 100).toFixed(1)} CM · {(finite(parsed.sensor_fusion.matched_ratio) * 100).toFixed(0)}%
          </div>
        )}
        {parsed.trajectory_evaluation?.backend === 'warp' && (
          <div style={{
            position: 'absolute', zIndex: 3, top: parsed.dynamic_occupancy?.backend === 'warp-hash-grid' ? 70 : 39, right: 9,
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 7px', borderRadius: 5, background: 'rgba(4, 18, 22, 0.84)',
            border: '1px solid rgba(91, 235, 255, 0.48)', color: '#91f4ff',
            fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: trajectoryPaths.length ? '#5bebff' : '#637b80' }} />
            {parsed.trajectory_evaluation.warmup
              ? 'WARP PATHS · WARMING'
              : `WARP PATHS · ${Number(parsed.trajectory_evaluation.safe_trajectories ?? 0).toLocaleString()} SAFE · ${Number(parsed.trajectory_evaluation.unsafe_trajectories ?? 0).toLocaleString()} BLOCKED`}
          </div>
        )}
        <div style={{
          position: 'absolute', zIndex: 3, right: 8, bottom: 7, padding: '3px 6px', borderRadius: 4,
          background: 'rgba(3, 10, 16, 0.72)', color: 'rgba(217, 232, 241, 0.74)',
          fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
        }}>
          {onGoalSet ? 'shift-click goal · ' : ''}left-drag pan · right-drag orbit · middle-drag pan · wheel zoom · double-click reset
        </div>
      </div>
      <div data-bn-viewer-telemetry style={{
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'nowrap',
        height: 28, flex: '0 0 28px', overflow: 'hidden', whiteSpace: 'nowrap',
        padding: '6px 9px', borderTop: '1px solid var(--line)',
        color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span>
          {pointCount > 0
            ? parsed.sensor_fusion?.backend === 'warp-hash-grid'
              ? `${pointCount.toLocaleString()} fused sensor points`
              : parsed.reconstruction?.extraction?.backend === 'warp'
              ? `${pointCount.toLocaleString()} reconstructed surface voxels`
              : parsed.depth_projection?.backend === 'warp'
              ? `${pointCount.toLocaleString()} projected depth points`
              : `${pointCount.toLocaleString()} accumulated returns`
            : currentPoints.length ? 'Live scan; map is empty' : 'Waiting for points'}
        </span>
        {currentPointCount > 0 && <span>{currentPointCount.toLocaleString()} current</span>}
        {accumulatedScanCount > 0 && (!parsed.depth_projection || parsed.reconstruction) && <span>{accumulatedScanCount.toLocaleString()} {parsed.reconstruction ? 'RGB-D frames' : 'scans'}</span>}
        {displayCount > 0 && displayCount !== pointCount && <span>{displayCount.toLocaleString()} displayed</span>}
        {kernelMs > 0 && <span>{kernelMs.toFixed(3)} ms Warp</span>}
        {parsed.occupancy?.backend === 'warp' && (
          <span style={{ color: '#74e7a5' }}>
            Warp occupancy {occupancyKernelMs.toFixed(3)} ms · encode {occupancyEncodeMs.toFixed(3)} ms · {Number(parsed.occupancy.rays ?? 0).toLocaleString()} rays · {freeCellCount.toLocaleString()} free · {occupiedCellCount.toLocaleString()} occupied · {Number(parsed.occupancy.grid_cells ?? 0).toLocaleString()} grid cells
          </span>
        )}
        {parsed.device && <span>{parsed.device}</span>}
        {parsed.frame && <span>{parsed.frame}</span>}
        {parsed.slam && <span>{Number(parsed.slam.keyframes ?? 0).toLocaleString()} keyframes · score {finite(parsed.slam.match_score).toFixed(2)} · {parsed.slam.matching_backend === 'warp' ? `Warp match ${finite(parsed.slam.matching_kernel_ms).toFixed(3)} ms` : 'CPU match'} · {parsed.slam.deskewed ? 'deskew on' : 'deskew unavailable'} · {Number(parsed.slam.loop_closures ?? 0).toLocaleString()} loops</span>}
        {parsed.localization?.state === 'ready' && (
          <span style={{ color: '#9df0c2' }}>
            {parsed.localization.backend === 'warp' ? 'Warp' : 'CPU'} particles {Number(parsed.localization.evaluated_particles ?? 0).toLocaleString()} × {Number(parsed.localization.beam_count ?? 0).toLocaleString()} beams = {Number(parsed.localization.work_items ?? 0).toLocaleString()} scores · {finite(parsed.localization.pipeline_ms).toFixed(3)} ms
            {finite(parsed.localization.effective_sample_size) > 0 ? ` · ESS ${Math.round(finite(parsed.localization.effective_sample_size)).toLocaleString()}` : ''}
            {finite(parsed.localization.speedup) > 0 ? ` · ${finite(parsed.localization.speedup).toFixed(1)}× CPU` : ''}
          </span>
        )}
        {parsed.dynamic_occupancy?.state === 'ready' && (
          <span style={{ color: '#ffb257' }}>
            Warp HashGrid {Number(parsed.dynamic_occupancy.input_points ?? 0).toLocaleString()} queries · {Number(parsed.dynamic_occupancy.dynamic_points ?? 0).toLocaleString()} moving · {finite(parsed.dynamic_occupancy.pipeline_ms).toFixed(3)} ms · mean {finite(parsed.dynamic_occupancy.mean_speed_mps).toFixed(2)} m/s
            {finite(parsed.dynamic_occupancy.speedup) > 0 ? ` · ${finite(parsed.dynamic_occupancy.speedup).toFixed(1)}× CPU` : ''}
          </span>
        )}
        {parsed.depth_projection?.state === 'ready' && (
          <span style={{ color: '#7cf4ff' }}>
            Warp depth {Number(parsed.depth_projection.input_pixels ?? 0).toLocaleString()} pixels · {Number(parsed.depth_projection.valid_points ?? 0).toLocaleString()} valid · stride {Number(parsed.depth_projection.stride ?? 1)} · {finite(parsed.depth_projection.pipeline_ms).toFixed(3)} ms · fetch {finite(parsed.depth_projection.fetch_ms).toFixed(3)} ms · confidence {finite(parsed.depth_projection.mean_confidence).toFixed(2)}
            {finite(parsed.depth_projection.speedup) > 0 ? ` · ${finite(parsed.depth_projection.speedup).toFixed(1)}× CPU` : ''}
          </span>
        )}
        {parsed.reconstruction?.integration?.state === 'ready' && parsed.reconstruction.extraction?.state === 'ready' && (
          <span style={{ color: '#9df0c2' }}>
            Warp TSDF {Number(parsed.reconstruction.integration.frames_integrated ?? 0).toLocaleString()} frames · {Number(parsed.reconstruction.integration.work_items ?? 0).toLocaleString()} integration samples · {finite(parsed.reconstruction.integration.integration_ms).toFixed(3)} ms · extraction {finite(parsed.reconstruction.extraction.extraction_ms).toFixed(3)} ms · {Number(parsed.reconstruction.extraction.observed_voxels ?? 0).toLocaleString()} observed · {Number(parsed.reconstruction.extraction.surface_voxels ?? 0).toLocaleString()} surface · {parsed.reconstruction.color_registered ? 'RGB color' : 'depth confidence color'}
          </span>
        )}
        {parsed.sensor_fusion?.state === 'ready' && (
          <span style={{ color: '#91f4ff' }}>
            Warp fusion {Number(parsed.sensor_fusion.lidar_points ?? 0).toLocaleString()} LiDAR + {Number(parsed.sensor_fusion.depth_points ?? 0).toLocaleString()} RGB-D · {Number(parsed.sensor_fusion.matched_points ?? 0).toLocaleString()} matched · mean {(finite(parsed.sensor_fusion.mean_residual_m) * 100).toFixed(1)} cm · p95 {(finite(parsed.sensor_fusion.p95_residual_m) * 100).toFixed(1)} cm · {Number(parsed.sensor_fusion.calibration_hypotheses ?? 0).toLocaleString()} hypotheses · {finite(parsed.sensor_fusion.pipeline_ms).toFixed(3)} ms · sync {(finite(parsed.synchronization?.delta_seconds) * 1000).toFixed(1)} ms
            {finite(parsed.sensor_fusion.speedup) > 0 ? ` · ${finite(parsed.sensor_fusion.speedup).toFixed(1)}× CPU` : ''}
          </span>
        )}
        {parsed.trajectory_evaluation?.state === 'ready' && (
          <span style={{ color: '#91f4ff' }}>
            Warp paths {Number(parsed.trajectory_evaluation.trajectory_count ?? 0).toLocaleString()} × {Number(parsed.trajectory_evaluation.time_steps ?? 0).toLocaleString()} steps = {Number(parsed.trajectory_evaluation.work_items ?? 0).toLocaleString()} evaluations · {finite(parsed.trajectory_evaluation.pipeline_ms).toFixed(3)} ms · best clearance {finite(parsed.trajectory_evaluation.best_minimum_clearance_m).toFixed(2)} m
            {finite(parsed.trajectory_evaluation.speedup) > 0 ? ` · ${finite(parsed.trajectory_evaluation.speedup).toFixed(1)}× CPU` : ''}
          </span>
        )}
        {!parsed.depth_projection && <span>{scanCoverageDeg >= 359.5 ? `360° scan · ${clockwiseScan ? 'CW' : 'CCW'} paced replay` : `${scanCoverageDeg.toFixed(1)}° scan · ${clockwiseScan ? 'CW' : 'CCW'} paced replay`}</span>}
        <span>{parsed.sensor_fusion ? '3D orbit · synchronized LiDAR and colorized depth alignment' : parsed.reconstruction ? '3D orbit · persistent pose-registered RGB-D surface' : parsed.depth_projection ? '3D orbit · calibrated metric surface' : '3D orbit · LaserScan lies on XY plane'}</span>
      </div>
      <div data-bn-viewer-legend style={{
        display: 'flex', alignItems: 'center', gap: 11, flexWrap: 'nowrap',
        height: 25, flex: '0 0 25px', overflow: 'hidden', whiteSpace: 'nowrap', padding: '0 9px 7px',
        color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span style={{ color: '#7cf4ff' }}>B robot {Math.round(finite(parsed.robot?.length_m, 0.25) * 100)}×{Math.round(finite(parsed.robot?.width_m, 0.22) * 100)} cm</span>
        {!parsed.depth_projection && <span style={{ color: '#72ff9d' }}>— active beam</span>}
        {!parsed.depth_projection && !fullCircleScan && <span style={{ color: '#85a2b8' }}>┄ scan limits</span>}
        <span style={{ color: '#32d8ef' }}>{parsed.sensor_fusion ? '● LiDAR cyan · RGB-D green aligned / red residual' : parsed.reconstruction ? '● reconstructed surface · aligned RGB when available' : parsed.depth_projection ? '● projected depth · brightness is surface confidence' : '● filtered laser returns'}</span>
        {parsed.sensor_fusion && <span style={{ color: '#91f4ff' }}>calibration Δ {finite(parsed.sensor_fusion.correction?.x_m).toFixed(3)} m X · {finite(parsed.sensor_fusion.correction?.y_m).toFixed(3)} m Y · {finite(parsed.sensor_fusion.correction?.yaw_deg).toFixed(2)}° yaw</span>}
        {parsed.occupancy?.fixed_origin === true && <span style={{ color: '#486070' }}>■ unknown map extent</span>}
        {parsed.map_render_mode === 'occupancy-texture' && <span style={{ color: '#74e7a5' }}>GPU map texture · all cells</span>}
        {showFreeSpace && freeCellCount > 0 && <span style={{ color: '#4fc07a' }}>■ {freeCellCount.toLocaleString()} fixed free-floor cells</span>}
        {occupiedCellCount > 0 && <span style={{ color: '#c7e0ef' }}>■ {occupiedCellCount.toLocaleString()} occupied wall cells</span>}
        {particles.length > 0 && <span style={{ color: '#9df0c2' }}>● GPU pose hypotheses · purple low / green high confidence</span>}
        {dynamicPoints.length > 0 && <span style={{ color: '#ffa940' }}>● coherent motion · orange points</span>}
        {trajectoryPaths.length > 0 && <span><b style={{ color: '#66e091' }}>— safe</b> · <b style={{ color: '#ff5b5b' }}>— blocked</b> · <b style={{ color: '#5bebff' }}>— best GPU path</b></span>}
        {showAxes && <span>map <b style={{ color: '#ff6b6b' }}>X</b> / <b style={{ color: '#53e091' }}>Y</b> / <b style={{ color: '#539aff' }}>Z</b> axes</span>}
        {parsed.history_registered === true && <span style={{ color: '#74e7a5' }}>pose-registered history · {parsed.pose_source || 'pose stream'}</span>}
        {Array.isArray(parsed.registration?.tf_path) && parsed.registration.tf_path.length > 1 && (
          <span>{parsed.registration.tf_path.join(' → ')}</span>
        )}
        {parsed.history_registered === false && !parsed.depth_projection && <span style={{ color: '#f2b84b' }}>history is sensor-local; moving the robot requires odometry</span>}
        {parsed.history_paused === true && <span style={{ color: '#f2b84b' }}>accumulation paused</span>}
        {parsed.slam?.tracking_accepted === false && <span style={{ color: '#f2b84b' }}>uncertain scan match rejected · odometry prior kept</span>}
        {parsed.slam?.stationary_odometry_locked === true && <span style={{ color: '#74e7a5' }}>stationary odometry lock · dynamic returns cannot move map</span>}
        {parsed.slam?.scan_motion_override === true && <span style={{ color: '#74e7a5' }}>whole-scene motion accepted · robot pose updated</span>}
        {parsed.slam?.tracking_correction_limited === true && <span style={{ color: '#74e7a5' }}>large pose correction smoothed across scans</span>}
        {parsed.slam?.map_update_rejected === true && <span style={{ color: '#f2b84b' }}>uncertain keyframe excluded from map</span>}
        {parsed.occupancy?.fixed_origin === true && <span style={{ color: '#74e7a5' }}>fixed map grid · floor cells never follow robot pose</span>}
        {parsed.occupancy?.display_limited === true && <span style={{ color: '#f2b84b' }}>occupancy display capped; full evidence remains on device</span>}
      </div>
    </div>
  )
}
