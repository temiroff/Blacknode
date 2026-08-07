import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { spatialCameraCoordinates } from '../spatialCamera'

interface Vector3 { x?: number; y?: number; z?: number }
interface Quaternion extends Vector3 { w?: number }

interface IMUScene {
  frame?: string
  sequence?: number
  robot?: { length_m?: number; width_m?: number; height_m?: number }
  mounting?: {
    body_frame?: string
    sensor_frame?: string
    body_from_sensor_rpy_deg?: { roll?: number; pitch?: number; yaw?: number }
    body_from_sensor_quaternion?: Quaternion
  }
  imu?: {
    orientation?: Quaternion
    euler_rad?: { roll?: number; pitch?: number; yaw?: number }
    angular_velocity_rps?: Vector3
    linear_acceleration_mps2?: Vector3
    source_fresh?: boolean
    age_seconds?: number | null
    topic?: string
  }
}

interface Point3 { x: number; y: number; z: number }
interface Point2 extends Point3 { sx: number; sy: number; depth: number }
type NormalizedQuaternion = Required<Quaternion>

const LOGO_SOURCE = { x: 78, y: 48, width: 352, height: 415 } as const
const IMU_DEFAULT_CAMERA: { yaw: number; pitch: number; zoom: number } = {
  yaw: -0.68,
  pitch: -0.62,
  zoom: 1,
}
const IMU_CAMERA_MIN_PITCH = -1.52
const IMU_CAMERA_MAX_PITCH = -0.05

function finite(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value))
}

function normalizeQuaternion(value: Quaternion | undefined): NormalizedQuaternion {
  const quaternion = {
    x: finite(value?.x), y: finite(value?.y), z: finite(value?.z), w: finite(value?.w, 1),
  }
  const norm = Math.hypot(quaternion.x, quaternion.y, quaternion.z, quaternion.w) || 1
  return {
    x: quaternion.x / norm,
    y: quaternion.y / norm,
    z: quaternion.z / norm,
    w: quaternion.w / norm,
  }
}

function multiplyQuaternion(left: NormalizedQuaternion, right: NormalizedQuaternion): NormalizedQuaternion {
  return normalizeQuaternion({
    x: left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
    y: left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
    z: left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
    w: left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
  })
}

function inverseQuaternion(value: NormalizedQuaternion): NormalizedQuaternion {
  return { x: -value.x, y: -value.y, z: -value.z, w: value.w }
}

function quaternionEuler(value: NormalizedQuaternion): { roll: number; pitch: number; yaw: number } {
  const roll = Math.atan2(
    2 * (value.w * value.x + value.y * value.z),
    1 - 2 * (value.x * value.x + value.y * value.y),
  )
  const pitch = Math.asin(clamp(2 * (value.w * value.y - value.z * value.x), -1, 1))
  const yaw = Math.atan2(
    2 * (value.w * value.z + value.x * value.y),
    1 - 2 * (value.y * value.y + value.z * value.z),
  )
  return { roll, pitch, yaw }
}

function rotate(point: Point3, quaternion: Required<Quaternion>): Point3 {
  const { x: qx, y: qy, z: qz, w: qw } = quaternion
  const tx = 2 * (qy * point.z - qz * point.y)
  const ty = 2 * (qz * point.x - qx * point.z)
  const tz = 2 * (qx * point.y - qy * point.x)
  return {
    x: point.x + qw * tx + qy * tz - qz * ty,
    y: point.y + qw * ty + qz * tx - qx * tz,
    z: point.z + qw * tz + qx * ty - qy * tx,
  }
}

function degrees(value: unknown): string {
  return `${(finite(value) * 180 / Math.PI).toFixed(1)}°`
}

function vectorMagnitude(value: Vector3 | undefined): number {
  return Math.hypot(finite(value?.x), finite(value?.y), finite(value?.z))
}

export default function IMUOrientationViewer({
  scene,
  inputRail,
}: {
  scene: unknown
  inputRail?: ReactNode
}) {
  const parsed = (scene && typeof scene === 'object' ? scene : {}) as IMUScene
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const logoRef = useRef<HTMLImageElement | null>(null)
  const dragRef = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null)
  const [viewport, setViewport] = useState({ width: 1, height: 420, ratio: 1 })
  const [camera, setCamera] = useState({ ...IMU_DEFAULT_CAMERA })
  const [logoReady, setLogoReady] = useState(false)
  const [orientationMode, setOrientationMode] = useState<'zeroed' | 'absolute'>('zeroed')
  const [referenceQuaternion, setReferenceQuaternion] = useState<NormalizedQuaternion | null>(null)
  const [showSensorAxes, setShowSensorAxes] = useState(true)
  const rawQuaternion = useMemo(() => normalizeQuaternion(parsed.imu?.orientation), [
    parsed.imu?.orientation?.w,
    parsed.imu?.orientation?.x,
    parsed.imu?.orientation?.y,
    parsed.imu?.orientation?.z,
  ])
  const sensorMountQuaternion = useMemo(
    () => normalizeQuaternion(parsed.mounting?.body_from_sensor_quaternion),
    [
      parsed.mounting?.body_from_sensor_quaternion?.w,
      parsed.mounting?.body_from_sensor_quaternion?.x,
      parsed.mounting?.body_from_sensor_quaternion?.y,
      parsed.mounting?.body_from_sensor_quaternion?.z,
    ],
  )
  // ROS gives q_world_sensor. The URDF/TF mounting is q_body_sensor, so the
  // physical robot pose is q_world_body = q_world_sensor * inverse(q_body_sensor).
  const rawBodyQuaternion = useMemo(
    () => multiplyQuaternion(rawQuaternion, inverseQuaternion(sensorMountQuaternion)),
    [rawQuaternion, sensorMountQuaternion],
  )
  const hasOrientation = parsed.imu?.orientation !== undefined
  const quaternion = useMemo(() => {
    if (orientationMode === 'absolute') return rawBodyQuaternion
    if (!referenceQuaternion) return normalizeQuaternion(undefined)
    return multiplyQuaternion(rawBodyQuaternion, inverseQuaternion(referenceQuaternion))
  }, [orientationMode, rawBodyQuaternion, referenceQuaternion])
  const displayedSensorQuaternion = useMemo(
    () => multiplyQuaternion(quaternion, sensorMountQuaternion),
    [quaternion, sensorMountQuaternion],
  )
  const displayedEuler = useMemo(() => quaternionEuler(quaternion), [quaternion])

  useEffect(() => {
    setReferenceQuaternion(null)
    setOrientationMode('zeroed')
  }, [
    parsed.frame,
    parsed.imu?.topic,
    parsed.mounting?.body_from_sensor_quaternion?.w,
    parsed.mounting?.body_from_sensor_quaternion?.x,
    parsed.mounting?.body_from_sensor_quaternion?.y,
    parsed.mounting?.body_from_sensor_quaternion?.z,
  ])

  useEffect(() => {
    if (orientationMode === 'zeroed' && !referenceQuaternion && hasOrientation) {
      setReferenceQuaternion(rawBodyQuaternion)
    }
  }, [hasOrientation, orientationMode, rawBodyQuaternion, referenceQuaternion])

  useEffect(() => {
    let cancelled = false
    const logo = new Image()
    logo.onload = () => {
      if (!cancelled) {
        logoRef.current = logo
        setLogoReady(true)
      }
    }
    logo.src = '/blacknode-logo-dark.png'
    return () => {
      cancelled = true
      logoRef.current = null
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect
      if (!rect) return
      setViewport({
        width: Math.max(1, rect.width),
        height: Math.max(260, rect.height),
        ratio: Math.min(2, window.devicePixelRatio || 1),
      })
    })
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const bufferWidth = Math.max(1, Math.round(viewport.width * viewport.ratio))
    const bufferHeight = Math.max(1, Math.round(viewport.height * viewport.ratio))
    if (canvas.width !== bufferWidth) canvas.width = bufferWidth
    if (canvas.height !== bufferHeight) canvas.height = bufferHeight
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(viewport.ratio, 0, 0, viewport.ratio, 0, 0)
    context.clearRect(0, 0, viewport.width, viewport.height)

    const centerX = viewport.width / 2
    const centerY = viewport.height * 0.47
    const scale = Math.min(viewport.width, viewport.height) * 0.66 * camera.zoom
    const project = (point: Point3): Point2 => {
      const [cameraX, cameraY, cameraDepth] = spatialCameraCoordinates(
        point.x, point.y, point.z, camera.yaw, camera.pitch,
      )
      return {
        ...point,
        sx: centerX + cameraX * scale,
        sy: centerY - cameraY * scale,
        depth: cameraDepth,
      }
    }
    const bodyPoint = (x: number, y: number, z: number) => project(rotate({ x, y, z }, quaternion))
    const sensorPoint = (x: number, y: number, z: number) => project(
      rotate({ x, y, z }, displayedSensorQuaternion),
    )

    const gridReach = 0.72
    context.lineWidth = 1
    context.strokeStyle = 'rgba(117, 155, 181, 0.15)'
    for (let index = -6; index <= 6; index += 1) {
      const value = index * gridReach / 6
      const a = project({ x: value, y: -gridReach, z: -0.17 })
      const b = project({ x: value, y: gridReach, z: -0.17 })
      const c = project({ x: -gridReach, y: value, z: -0.17 })
      const d = project({ x: gridReach, y: value, z: -0.17 })
      context.beginPath()
      context.moveTo(a.sx, a.sy); context.lineTo(b.sx, b.sy)
      context.moveTo(c.sx, c.sy); context.lineTo(d.sx, d.sy)
      context.stroke()
    }

    const drawArrow = (start: Point2, end: Point2, color: string, label: string, width = 2.4) => {
      const angle = Math.atan2(end.sy - start.sy, end.sx - start.sx)
      context.strokeStyle = color
      context.fillStyle = color
      context.lineWidth = width
      context.beginPath()
      context.moveTo(start.sx, start.sy)
      context.lineTo(end.sx, end.sy)
      context.stroke()
      context.beginPath()
      context.moveTo(end.sx, end.sy)
      context.lineTo(end.sx - Math.cos(angle - 0.48) * 9, end.sy - Math.sin(angle - 0.48) * 9)
      context.lineTo(end.sx - Math.cos(angle + 0.48) * 9, end.sy - Math.sin(angle + 0.48) * 9)
      context.closePath()
      context.fill()
      context.font = '700 12px ui-monospace, SFMono-Regular, Menlo, monospace'
      context.fillText(label, end.sx + 6, end.sy - 5)
    }

    const origin = project({ x: 0, y: 0, z: -0.17 })
    drawArrow(origin, project({ x: 0.46, y: 0, z: -0.17 }), 'rgba(255, 91, 91, 0.42)', 'X', 1.4)
    drawArrow(origin, project({ x: 0, y: 0.46, z: -0.17 }), 'rgba(83, 224, 145, 0.42)', 'Y', 1.4)
    drawArrow(origin, project({ x: 0, y: 0, z: 0.29 }), 'rgba(83, 154, 255, 0.5)', 'Z', 1.4)

    const length = clamp(finite(parsed.robot?.length_m, 0.36), 0.05, 2)
    const width = clamp(finite(parsed.robot?.width_m, 0.28), 0.05, 2)
    const height = clamp(finite(parsed.robot?.height_m, 0.12), 0.02, 1)
    const half = { x: length / 2, y: width / 2, z: height / 2 }
    const vertices = [
      [-half.x, -half.y, -half.z], [half.x, -half.y, -half.z],
      [half.x, half.y, -half.z], [-half.x, half.y, -half.z],
      [-half.x, -half.y, half.z], [half.x, -half.y, half.z],
      [half.x, half.y, half.z], [-half.x, half.y, half.z],
    ].map(([x, y, z]) => bodyPoint(x, y, z))
    const faces = [
      { indices: [0, 1, 2, 3], fill: 'rgba(13, 104, 124, 0.50)' },
      { indices: [4, 5, 6, 7], fill: 'rgba(30, 199, 220, 0.38)' },
      { indices: [0, 1, 5, 4], fill: 'rgba(24, 160, 185, 0.40)' },
      { indices: [1, 2, 6, 5], fill: 'rgba(16, 133, 159, 0.46)' },
      { indices: [2, 3, 7, 6], fill: 'rgba(20, 148, 174, 0.40)' },
      { indices: [3, 0, 4, 7], fill: 'rgba(13, 118, 144, 0.46)' },
    ].sort((left, right) => {
      const depth = (face: typeof left) => face.indices.reduce((sum, index) => sum + vertices[index].depth, 0) / 4
      return depth(right) - depth(left)
    })
    context.shadowColor = 'rgba(43, 220, 238, 0.45)'
    context.shadowBlur = 12
    for (const face of faces) {
      context.beginPath()
      face.indices.forEach((index, offset) => {
        const point = vertices[index]
        if (offset === 0) context.moveTo(point.sx, point.sy)
        else context.lineTo(point.sx, point.sy)
      })
      context.closePath()
      context.fillStyle = face.fill
      context.fill()
      context.strokeStyle = 'rgba(124, 244, 255, 0.86)'
      context.lineWidth = 1.35
      context.stroke()
    }
    context.shadowBlur = 0

    const topCenter = bodyPoint(0, 0, half.z + 0.001)
    const topX = bodyPoint(length * 0.33, 0, half.z + 0.001)
    const topY = bodyPoint(0, width * 0.33, half.z + 0.001)
    const logo = logoRef.current
    context.save()
    context.transform(
      topX.sx - topCenter.sx, topX.sy - topCenter.sy,
      topY.sx - topCenter.sx, topY.sy - topCenter.sy,
      topCenter.sx, topCenter.sy,
    )
    context.rotate(-Math.PI / 2)
    context.globalCompositeOperation = 'screen'
    context.globalAlpha = 0.9
    if (logo) {
      context.drawImage(
        logo,
        LOGO_SOURCE.x, LOGO_SOURCE.y, LOGO_SOURCE.width, LOGO_SOURCE.height,
        -0.58, -0.50, 1.16, 1.0,
      )
    } else {
      context.fillStyle = '#e8fdff'
      context.font = '800 1px var(--font-ui)'
      context.textAlign = 'center'
      context.textBaseline = 'middle'
      context.fillText('B', 0, 0)
    }
    context.restore()

    const bodyOrigin = bodyPoint(0, 0, 0)
    const axisLength = Math.max(length, width) * 0.82
    if (showSensorAxes) {
      const sensorAxisLength = axisLength * 0.76
      drawArrow(bodyOrigin, sensorPoint(sensorAxisLength, 0, 0), '#ffc857', 'IMU X', 1.55)
      drawArrow(bodyOrigin, sensorPoint(0, sensorAxisLength, 0), '#cf8cff', 'IMU Y', 1.55)
      drawArrow(bodyOrigin, sensorPoint(0, 0, sensorAxisLength), '#72c8ff', 'IMU Z', 1.55)
    }
    drawArrow(bodyOrigin, bodyPoint(axisLength, 0, 0), '#ff5b5b', 'X')
    drawArrow(bodyOrigin, bodyPoint(0, axisLength, 0), '#53e091', 'Y')
    drawArrow(bodyOrigin, bodyPoint(0, 0, axisLength), '#539aff', 'Z')

    context.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
    context.fillStyle = parsed.imu?.source_fresh === true ? '#72ff9d' : '#facc15'
    context.fillText(parsed.imu?.source_fresh === true ? 'LIVE ORIENTATION' : 'WAITING / STALE', 14, 20)
  }, [camera, displayedSensorQuaternion, logoReady, parsed, quaternion, showSensorAxes, viewport])

  const angularRate = vectorMagnitude(parsed.imu?.angular_velocity_rps)
  const acceleration = vectorMagnitude(parsed.imu?.linear_acceleration_mps2)
  const age = parsed.imu?.age_seconds

  return (
    <div
      className="nodrag"
      onMouseDown={event => event.stopPropagation()}
      style={{
        margin: '7px 9px 8px', width: 'calc(100% - 18px)', flex: '1 1 auto', minHeight: 0,
        display: 'flex', flexDirection: 'column', boxSizing: 'border-box', overflow: 'hidden',
        border: '1px solid var(--line2)', borderRadius: 'var(--bn-node-inner-radius, 7px)', background: '#242424',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 7, padding: '5px 7px',
        borderBottom: '1px solid var(--line)', background: 'var(--panel)',
      }}>
        {inputRail}
        <button
          onClick={event => {
            event.stopPropagation()
            setReferenceQuaternion(rawBodyQuaternion)
            setOrientationMode('zeroed')
          }}
          disabled={!hasOrientation}
          title="Treat the robot's current pose as level and forward"
          style={{
            marginLeft: 'auto', height: 25, padding: '0 8px', border: '1px solid var(--line2)',
            background: orientationMode === 'zeroed' ? 'rgba(86, 217, 145, 0.16)' : 'var(--panel2)',
            color: orientationMode === 'zeroed' ? '#8df0b5' : 'var(--tx2)', fontSize: 11,
            cursor: hasOrientation ? 'pointer' : 'default',
          }}
        >
          Zero pose
        </button>
        <button
          onClick={event => { event.stopPropagation(); setOrientationMode('absolute') }}
          disabled={!hasOrientation}
          title="Show the unmodified ROS IMU orientation"
          style={{
            height: 25, padding: '0 8px', border: '1px solid var(--line2)',
            background: orientationMode === 'absolute' ? 'rgba(91, 154, 255, 0.16)' : 'var(--panel2)',
            color: orientationMode === 'absolute' ? '#91c4ff' : 'var(--tx2)', fontSize: 11,
            cursor: hasOrientation ? 'pointer' : 'default',
          }}
        >
          Absolute
        </button>
        <label
          title="Show the physical IMU calibration axes after applying its URDF mounting"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--tx2)', fontSize: 11 }}
        >
          <input
            type="checkbox"
            checked={showSensorAxes}
            onChange={event => setShowSensorAxes(event.target.checked)}
          />
          IMU axes
        </label>
        <button
          onClick={event => { event.stopPropagation(); setCamera({ ...IMU_DEFAULT_CAMERA }) }}
          style={{
            height: 25, padding: '0 8px', border: '1px solid var(--line2)',
            background: 'var(--panel2)', color: 'var(--tx2)', fontSize: 11, cursor: 'pointer',
          }}
        >
          Reset view
        </button>
      </div>
      <canvas
        ref={canvasRef}
        onMouseDown={event => {
          event.stopPropagation()
          dragRef.current = { x: event.clientX, y: event.clientY, yaw: camera.yaw, pitch: camera.pitch }
        }}
        onMouseMove={event => {
          const drag = dragRef.current
          if (!drag) return
          setCamera(current => ({
            ...current,
            yaw: drag.yaw + (event.clientX - drag.x) * 0.008,
            pitch: clamp(
              drag.pitch - (event.clientY - drag.y) * 0.008,
              IMU_CAMERA_MIN_PITCH,
              IMU_CAMERA_MAX_PITCH,
            ),
          }))
        }}
        onMouseUp={() => { dragRef.current = null }}
        onMouseLeave={() => { dragRef.current = null }}
        onWheel={event => {
          event.preventDefault()
          event.stopPropagation()
          setCamera(current => ({ ...current, zoom: clamp(current.zoom * Math.exp(-event.deltaY * 0.001), 0.55, 2.4) }))
        }}
        style={{ width: '100%', flex: '1 1 auto', minHeight: 260, cursor: 'grab', background: '#161b1d' }}
      />
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 1,
        borderTop: '1px solid var(--line)', background: 'var(--line)',
      }}>
        {[
          ['ROLL', degrees(displayedEuler.roll)],
          ['PITCH', degrees(displayedEuler.pitch)],
          ['YAW', degrees(displayedEuler.yaw)],
          ['ANGULAR', `${angularRate.toFixed(3)} rad/s`],
          ['ACCEL', `${acceleration.toFixed(3)} m/s²`],
          ['FRAME', parsed.frame || 'imu_link'],
        ].map(([label, value]) => (
          <div key={label} style={{ background: 'var(--panel)', minWidth: 0, padding: '6px 8px' }}>
            <div style={{ color: 'var(--tx3)', fontSize: 11, letterSpacing: '.08em' }}>{label}</div>
            <div style={{ color: 'var(--tx1)', fontFamily: 'var(--font-mono)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</div>
          </div>
        ))}
      </div>
      <div style={{ padding: '5px 8px', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--panel)' }}>
        {parsed.imu?.topic || 'normalized IMU'} • sample {finite(parsed.sequence)}
        {typeof age === 'number' ? ` • age ${age.toFixed(3)}s` : ''}
        {` • ${orientationMode === 'zeroed' ? 'startup-relative robot pose' : 'absolute robot pose'}`}
        {` • mount ${finite(parsed.mounting?.body_from_sensor_rpy_deg?.roll).toFixed(1)}°/`}
        {`${finite(parsed.mounting?.body_from_sensor_rpy_deg?.pitch).toFixed(1)}°/`}
        {`${finite(parsed.mounting?.body_from_sensor_rpy_deg?.yaw).toFixed(1)}°`}
        {' • drag to orbit • wheel to zoom'}
      </div>
    </div>
  )
}
