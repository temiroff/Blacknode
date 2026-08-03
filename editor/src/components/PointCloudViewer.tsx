import { useEffect, useMemo, useRef, useState } from 'react'

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
  point_count?: number
  current_point_count?: number
  accumulated_scan_count?: number
  display_count?: number
  device?: string
  kernel_ms?: number
  sensor?: { x_m?: number; y_m?: number; yaw_rad?: number }
  scan?: {
    angle_min_rad?: number
    angle_max_rad?: number
    range_min_m?: number
    range_max_m?: number
  }
  view?: { radius_m?: number; units?: string }
  history_registered?: boolean
  pose_source?: string
  animation?: {
    enabled?: boolean
    show_rays?: boolean
    ray_trail_count?: number
    pulse_hz?: number
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

interface Viewport {
  width: number
  height: number
  ratio: number
}

const DEFAULT_CAMERA: CameraState = {
  zoom: 1,
  panX: 0,
  panY: 22,
  yaw: -0.35,
  pitch: 0.62,
}

function numericRows(value: unknown): number[][] {
  if (!Array.isArray(value)) return []
  return value
    .filter((row): row is unknown[] => Array.isArray(row) && row.length >= 2)
    .map(row => row.slice(0, 3).map(item => Number(item)))
    .filter(row => row.every(Number.isFinite))
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

function gridSpacing(pixelsPerMeter: number): number {
  const choices = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
  return choices.find(value => value * pixelsPerMeter >= 46) ?? 500
}

function meterLabel(value: number): string {
  if (Math.abs(value) >= 10) return `${Math.round(value)}m`
  if (Math.abs(value) >= 1) return `${Number(value.toFixed(1))}m`
  return `${Number(value.toFixed(2))}m`
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
  onClear,
  clearPending = false,
}: {
  scene: unknown
  onClear?: () => void
  clearPending?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
  const dragRef = useRef<{
    x: number
    y: number
    mode: 'pan' | 'rotate'
    camera: CameraState
  } | null>(null)
  const [camera, setCamera] = useState<CameraState>(DEFAULT_CAMERA)
  const [viewport, setViewport] = useState<Viewport>({ width: 1, height: 360, ratio: 1 })
  const parsed = (scene && typeof scene === 'object' ? scene : {}) as ViewerScene
  const points = useMemo(() => numericRows(parsed.points), [parsed.points])
  const colors = useMemo(() => numericRows(parsed.colors), [parsed.colors])
  const currentPoints = useMemo(() => numericRows(parsed.current_points), [parsed.current_points])
  const [animationClock, setAnimationClock] = useState(0)
  const scanStartedRef = useRef(0)
  const sequenceRef = useRef<number | undefined>(undefined)

  const animationEnabled = parsed.animation?.enabled !== false
  const pulseHz = clamp(finite(parsed.animation?.pulse_hz, 1), 0.05, 30)
  const animationPhase = animationEnabled
    ? ((animationClock - scanStartedRef.current) / 1000 * pulseHz + 10) % 1
    : 1

  useEffect(() => {
    const sequence = Number(parsed.sequence ?? 0)
    if (sequenceRef.current !== sequence) {
      sequenceRef.current = sequence
      scanStartedRef.current = performance.now()
    }
  }, [parsed.sequence])

  useEffect(() => {
    if (!animationEnabled || currentPoints.length === 0) return
    let frame = 0
    let previous = 0
    const animate = (now: number) => {
      if (now - previous >= 30) {
        previous = now
        setAnimationClock(now)
      }
      frame = window.requestAnimationFrame(animate)
    }
    frame = window.requestAnimationFrame(animate)
    return () => window.cancelAnimationFrame(frame)
  }, [animationEnabled, currentPoints.length])

  const sensor = useMemo(() => ({
    x: finite(parsed.sensor?.x_m),
    y: finite(parsed.sensor?.y_m),
    yaw: finite(parsed.sensor?.yaw_rad),
  }), [parsed.sensor?.x_m, parsed.sensor?.y_m, parsed.sensor?.yaw_rad])

  const viewRadius = useMemo(() => {
    const pointRadius = points.reduce(
      (largest, point) => Math.max(largest, Math.hypot(point[0], point[1])),
      0,
    )
    const configured = finite(parsed.view?.radius_m)
    return clamp(Math.max(configured, pointRadius * 1.08, Math.hypot(sensor.x, sensor.y) + 0.5), 0.5, 10_000)
  }, [parsed.view?.radius_m, points, sensor.x, sensor.y])

  const basePixelsPerMeter = Math.max(
    0.001,
    Math.min(viewport.width, viewport.height) / (viewRadius * 2.15),
  )
  const pixelsPerMeter = basePixelsPerMeter * camera.zoom

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
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { antialias: true, alpha: false })
    if (!gl) return
    const bufferWidth = Math.max(1, Math.round(viewport.width * viewport.ratio))
    const bufferHeight = Math.max(1, Math.round(viewport.height * viewport.ratio))
    if (canvas.width !== bufferWidth) canvas.width = bufferWidth
    if (canvas.height !== bufferHeight) canvas.height = bufferHeight
    gl.viewport(0, 0, bufferWidth, bufferHeight)
    gl.clearColor(0.012, 0.022, 0.035, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    if (points.length === 0) return

    let vertex: WebGLShader | null = null
    let fragment: WebGLShader | null = null
    let program: WebGLProgram | null = null
    try {
      vertex = shader(gl, gl.VERTEX_SHADER, `
        attribute vec2 a_position;
        attribute vec3 a_color;
        varying vec3 v_color;
        void main() {
          gl_Position = vec4(a_position, 0.0, 1.0);
          gl_PointSize = ${Math.max(3.5, 4.5 * viewport.ratio).toFixed(2)};
          v_color = a_color;
        }
      `)
      fragment = shader(gl, gl.FRAGMENT_SHADER, `
        precision mediump float;
        varying vec3 v_color;
        void main() {
          vec2 centered = gl_PointCoord - vec2(0.5);
          if (dot(centered, centered) > 0.25) discard;
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

    const positions = new Float32Array(points.length * 2)
    const palette = new Float32Array(points.length * 3)
    points.forEach((point, index) => {
      const [screenX, screenY] = worldToScreen(
        point[0], point[1], finite(point[2]), viewport, camera, pixelsPerMeter,
      )
      positions[index * 2] = (screenX / viewport.width) * 2 - 1
      positions[index * 2 + 1] = 1 - (screenY / viewport.height) * 2
      const color = colors[index] ?? [0.0, 0.78, 1.0]
      palette[index * 3] = clamp(color[0], 0, 1)
      palette[index * 3 + 1] = clamp(color[1], 0, 1)
      palette[index * 3 + 2] = clamp(color[2], 0, 1)
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
    gl.drawArrays(gl.POINTS, 0, points.length)

    return () => {
      gl.deleteBuffer(positionBuffer)
      gl.deleteBuffer(colorBuffer)
      if (program) gl.deleteProgram(program)
      if (vertex) gl.deleteShader(vertex)
      if (fragment) gl.deleteShader(fragment)
    }
  }, [camera, colors, pixelsPerMeter, points, viewport])

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
      const [x1, y1] = worldToScreen(value, -reach, 0, viewport, camera, pixelsPerMeter)
      const [x2, y2] = worldToScreen(value, reach, 0, viewport, camera, pixelsPerMeter)
      const [x3, y3] = worldToScreen(-reach, value, 0, viewport, camera, pixelsPerMeter)
      const [x4, y4] = worldToScreen(reach, value, 0, viewport, camera, pixelsPerMeter)
      context.moveTo(x1, y1)
      context.lineTo(x2, y2)
      context.moveTo(x3, y3)
      context.lineTo(x4, y4)
    }
    context.stroke()

    const drawAxis = (endX: number, endY: number, endZ: number, color: string) => {
      const start = worldToScreen(-endX, -endY, -endZ, viewport, camera, pixelsPerMeter)
      const end = worldToScreen(endX, endY, endZ, viewport, camera, pixelsPerMeter)
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
      const xTick = worldToScreen(value, 0, 0, viewport, camera, pixelsPerMeter)
      if (xTick[0] > 12 && xTick[0] < viewport.width - 28 && xTick[1] > 12 && xTick[1] < viewport.height - 12) {
        context.fillText(meterLabel(value), xTick[0] + 3, xTick[1] - 4)
      }
      const yTick = worldToScreen(0, value, 0, viewport, camera, pixelsPerMeter)
      if (yTick[0] > 12 && yTick[0] < viewport.width - 28 && yTick[1] > 12 && yTick[1] < viewport.height - 12) {
        context.fillText(meterLabel(value), yTick[0] + 4, yTick[1] - 3)
      }
    }

    const sensorScreen = worldToScreen(sensor.x, sensor.y, 0, viewport, camera, pixelsPerMeter)
    const scanMinimum = sensor.yaw + finite(parsed.scan?.angle_min_rad, -Math.PI)
    const scanMaximum = sensor.yaw + finite(parsed.scan?.angle_max_rad, Math.PI)
    const rayLength = Math.min(viewRadius, Math.max(spacing * 2, viewRadius * 0.82))
    context.setLineDash([5, 5])
    context.strokeStyle = 'rgba(255, 198, 72, 0.62)'
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

    if (animationEnabled && currentPoints.length > 0) {
      for (const [ringIndex, offset] of [0, 0.22, 0.44].entries()) {
        const phase = (animationPhase - offset + 1) % 1
        const radius = Math.max(0.01, viewRadius * phase)
        context.strokeStyle = `rgba(40, 145, 232, ${0.48 - ringIndex * 0.1})`
        context.lineWidth = 1.2
        context.beginPath()
        for (let segment = 0; segment <= 80; segment += 1) {
          const angle = Math.PI * 2 * segment / 80
          const point = worldToScreen(
            sensor.x + Math.cos(angle) * radius,
            sensor.y + Math.sin(angle) * radius,
            0,
            viewport,
            camera,
            pixelsPerMeter,
          )
          if (segment === 0) context.moveTo(point[0], point[1])
          else context.lineTo(point[0], point[1])
        }
        context.stroke()
      }

      if (parsed.animation?.show_rays !== false) {
        const activeIndex = Math.min(
          currentPoints.length - 1,
          Math.max(0, Math.floor(animationPhase * currentPoints.length)),
        )
        const trailCount = clamp(finite(parsed.animation?.ray_trail_count, 96), 1, 512)
        const trailStart = Math.max(0, activeIndex - trailCount + 1)
        context.strokeStyle = 'rgba(42, 133, 224, 0.32)'
        context.lineWidth = 0.8
        context.beginPath()
        for (let index = trailStart; index <= activeIndex; index += 1) {
          const hit = currentPoints[index]
          const projected = worldToScreen(
            hit[0], hit[1], finite(hit[2]), viewport, camera, pixelsPerMeter,
          )
          context.moveTo(sensorScreen[0], sensorScreen[1])
          context.lineTo(projected[0], projected[1])
        }
        context.stroke()
        const activeHit = currentPoints[activeIndex]
        const projectedHit = worldToScreen(
          activeHit[0], activeHit[1], finite(activeHit[2]), viewport, camera, pixelsPerMeter,
        )
        context.strokeStyle = '#ffd12f'
        context.lineWidth = 2
        context.beginPath()
        context.moveTo(sensorScreen[0], sensorScreen[1])
        context.lineTo(projectedHit[0], projectedHit[1])
        context.stroke()
        context.fillStyle = '#fff176'
        context.beginPath()
        context.arc(projectedHit[0], projectedHit[1], 4.5, 0, Math.PI * 2)
        context.fill()
      }
    }

    const forwardLength = Math.max(spacing * 1.4, viewRadius * 0.12)
    const forward = worldToScreen(
      sensor.x + Math.cos(sensor.yaw) * forwardLength,
      sensor.y + Math.sin(sensor.yaw) * forwardLength,
      0,
      viewport,
      camera,
      pixelsPerMeter,
    )
    context.strokeStyle = '#ffd166'
    context.fillStyle = '#ffd166'
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(sensorScreen[0], sensorScreen[1])
    context.lineTo(forward[0], forward[1])
    context.stroke()
    const arrowAngle = Math.atan2(forward[1] - sensorScreen[1], forward[0] - sensorScreen[0])
    context.beginPath()
    context.moveTo(forward[0], forward[1])
    context.lineTo(forward[0] - Math.cos(arrowAngle - 0.55) * 8, forward[1] - Math.sin(arrowAngle - 0.55) * 8)
    context.lineTo(forward[0] - Math.cos(arrowAngle + 0.55) * 8, forward[1] - Math.sin(arrowAngle + 0.55) * 8)
    context.closePath()
    context.fill()
    context.beginPath()
    context.arc(sensorScreen[0], sensorScreen[1], 6, 0, Math.PI * 2)
    context.fillStyle = '#ff6b6b'
    context.fill()
    context.strokeStyle = '#fff3d0'
    context.lineWidth = 1.5
    context.stroke()
    context.fillStyle = '#ffd166'
    context.fillText('LiDAR forward', forward[0] + 7, forward[1] - 7)

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
    parsed.animation?.ray_trail_count,
    parsed.animation?.show_rays,
    parsed.scan?.angle_max_rad,
    parsed.scan?.angle_min_rad,
    pixelsPerMeter,
    sensor,
    viewRadius,
    viewport,
  ])

  const pointCount = Number(parsed.point_count ?? points.length)
  const currentPointCount = Number(parsed.current_point_count ?? currentPoints.length)
  const accumulatedScanCount = Number(parsed.accumulated_scan_count ?? (points.length ? 1 : 0))
  const displayCount = Number(parsed.display_count ?? points.length)
  const kernelMs = Number(parsed.kernel_ms ?? 0)
  const yawDegrees = Math.round(camera.yaw * 180 / Math.PI)
  const pitchDegrees = Math.round(camera.pitch * 180 / Math.PI)

  return (
    <div
      className="nodrag"
      onMouseDown={event => event.stopPropagation()}
      style={{
        margin: '7px 9px 3px',
        overflow: 'hidden',
        border: '1px solid var(--line2)',
        borderRadius: 'var(--bn-node-inner-radius, 7px)',
        background: '#03070d',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5, padding: '5px 7px',
        borderBottom: '1px solid var(--line)', background: 'var(--panel)',
      }}>
        <button type="button" style={controlStyle()} title="Zoom out" onClick={() => setCamera(value => ({ ...value, zoom: clamp(value.zoom / 1.25, 0.1, 30) }))}>−</button>
        <button type="button" style={controlStyle()} title="Zoom in" onClick={() => setCamera(value => ({ ...value, zoom: clamp(value.zoom * 1.25, 0.1, 30) }))}>+</button>
        <button type="button" style={controlStyle()} title="Orbit left" onClick={() => setCamera(value => ({ ...value, yaw: value.yaw - Math.PI / 12 }))}>↶</button>
        <button type="button" style={controlStyle()} title="Orbit right" onClick={() => setCamera(value => ({ ...value, yaw: value.yaw + Math.PI / 12 }))}>↷</button>
        <button type="button" style={controlStyle()} title="Tilt camera up" onClick={() => setCamera(value => ({ ...value, pitch: clamp(value.pitch + Math.PI / 18, -1.45, 1.45) }))}>↑</button>
        <button type="button" style={controlStyle()} title="Tilt camera down" onClick={() => setCamera(value => ({ ...value, pitch: clamp(value.pitch - Math.PI / 18, -1.45, 1.45) }))}>↓</button>
        <button type="button" style={controlStyle(camera.pitch === 0 && camera.yaw === 0)} onClick={() => setCamera(value => ({ ...value, yaw: 0, pitch: 0 }))}>Top</button>
        <button type="button" style={controlStyle()} onClick={() => setCamera(DEFAULT_CAMERA)}>Fit</button>
        {onClear && <button type="button" disabled={clearPending} style={controlStyle()} title="Clear accumulated scan history" onClick={onClear}>{clearPending ? 'Clearing…' : 'Clear'}</button>}
        <span style={{ marginLeft: 'auto', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {camera.zoom.toFixed(2)}× · yaw {yawDegrees}° · pitch {pitchDegrees}°
        </span>
      </div>
      <div style={{ position: 'relative', height: 360 }}>
        <canvas
          ref={canvasRef}
          aria-label="Interactive live point-cloud Viewer"
          onContextMenu={event => event.preventDefault()}
          onDoubleClick={() => setCamera(DEFAULT_CAMERA)}
          onPointerDown={event => {
            event.stopPropagation()
            event.currentTarget.setPointerCapture(event.pointerId)
            dragRef.current = {
              x: event.clientX,
              y: event.clientY,
              mode: event.button === 1 || event.button === 2 || event.shiftKey ? 'pan' : 'rotate',
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
              const zoom = clamp(value.zoom * factor, 0.1, 30)
              const applied = zoom / value.zoom
              return {
                ...value,
                zoom,
                panX: cursorX - (cursorX - value.panX) * applied,
                panY: cursorY - (cursorY - value.panY) * applied,
              }
            })
          }}
          style={{ display: 'block', width: '100%', height: '100%', cursor: 'grab', touchAction: 'none' }}
        />
        <canvas
          ref={overlayRef}
          aria-hidden="true"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        />
        <div style={{
          position: 'absolute', top: 8, left: 9, display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 7px', borderRadius: 5, background: 'rgba(3, 10, 16, 0.78)',
          border: '1px solid rgba(86, 217, 145, 0.38)', color: '#8df0b5',
          fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
        }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: currentPoints.length ? '#56d991' : '#71808d' }} />
          {currentPoints.length ? `CURRENT SCAN #${Number(parsed.sequence ?? 0).toLocaleString()} · ${Math.round(animationPhase * 100)}%` : 'WAITING FOR SCAN'}
        </div>
        <div style={{
          position: 'absolute', right: 8, bottom: 7, padding: '3px 6px', borderRadius: 4,
          background: 'rgba(3, 10, 16, 0.72)', color: 'rgba(217, 232, 241, 0.74)',
          fontFamily: 'var(--font-mono)', fontSize: 11, pointerEvents: 'none',
        }}>
          drag orbit · Shift/right-drag pan · wheel zoom · double-click fit
        </div>
      </div>
      <div style={{
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
        padding: '6px 9px', borderTop: '1px solid var(--line)',
        color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span>{points.length ? `${pointCount.toLocaleString()} accumulated returns` : 'Waiting for points'}</span>
        {currentPointCount > 0 && <span>{currentPointCount.toLocaleString()} current</span>}
        {accumulatedScanCount > 0 && <span>{accumulatedScanCount.toLocaleString()} scans</span>}
        {displayCount > 0 && displayCount !== pointCount && <span>{displayCount.toLocaleString()} displayed</span>}
        {kernelMs > 0 && <span>{kernelMs.toFixed(3)} ms Warp</span>}
        {parsed.device && <span>{parsed.device}</span>}
        {parsed.frame && <span>{parsed.frame}</span>}
        <span>3D orbit · LaserScan lies on XY plane</span>
      </div>
      <div style={{
        display: 'flex', gap: 11, flexWrap: 'wrap', padding: '0 9px 7px',
        color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span style={{ color: '#ff7b7b' }}>● sensor</span>
        <span style={{ color: '#ffd166' }}>→ forward / scan limits</span>
        <span style={{ color: '#32d8ef' }}>● filtered laser returns</span>
        <span><b style={{ color: '#ff6b6b' }}>X</b> / <b style={{ color: '#53e091' }}>Y</b> / <b style={{ color: '#539aff' }}>Z</b> axes</span>
        {parsed.history_registered === false && <span style={{ color: '#f2b84b' }}>history is sensor-local; moving the robot requires odometry</span>}
      </div>
    </div>
  )
}
