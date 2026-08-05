import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../api'

interface ViewerStatus {
  state?: string
  error?: string
  label?: string
  encoding?: string
  depth_scale?: number
  frame_url?: string
  display?: {
    range?: string
    near_m?: number
    far_m?: number
    palette?: string
    invalid_color?: string
  }
}

export interface DepthDisplaySettings {
  auto_range: boolean
  near_m: number
  far_m: number
  palette: 'grayscale' | 'turbo'
  invalid_color: 'black' | 'magenta'
}

type DepthDisplayKey = keyof DepthDisplaySettings

interface MetricDepthFrame {
  width: number
  height: number
  values: Float32Array
}

function parseMetricDepthFrame(payload: ArrayBuffer): MetricDepthFrame {
  const bytes = new Uint8Array(payload)
  if (bytes.length < 12 || new TextDecoder().decode(bytes.subarray(0, 8)) !== 'BNDEPTH1') {
    throw new Error('Invalid metric depth frame')
  }
  const view = new DataView(payload)
  const headerSize = view.getUint32(8, true)
  const headerEnd = 12 + headerSize
  if (headerEnd > bytes.length) throw new Error('Truncated metric depth header')
  const header = JSON.parse(new TextDecoder().decode(bytes.subarray(12, headerEnd))) as Record<string, unknown>
  const width = Number(header.width ?? 0)
  const height = Number(header.height ?? 0)
  const encoding = String(header.encoding ?? '').toLowerCase()
  const bytesPerPixel = encoding === '32fc1' ? 4 : 2
  const step = Number(header.step ?? width * bytesPerPixel)
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0
    || !['mono16', '16uc1', '32fc1'].includes(encoding)
    || step < width * bytesPerPixel || headerEnd + height * step > bytes.length) {
    throw new Error('Unsupported metric depth frame')
  }
  const littleEndian = header.is_bigendian !== true
  const values = new Float32Array(width * height)
  for (let y = 0; y < height; y += 1) {
    const row = headerEnd + y * step
    for (let x = 0; x < width; x += 1) {
      const offset = row + x * bytesPerPixel
      values[y * width + x] = encoding === '32fc1'
        ? view.getFloat32(offset, littleEndian)
        : view.getUint16(offset, littleEndian)
    }
  }
  return { width, height, values }
}

const turboCoefficients = [
  [0.13572138, 4.61539260, -42.66032258, 132.13108234, -152.94239396, 59.28637943],
  [0.09140261, 2.19418839, 4.84296658, -14.18503333, 4.27729857, 2.82956604],
  [0.10667330, 12.64194608, -60.58204836, 110.36276771, -89.90310912, 27.34824973],
]

function turboChannel(x: number, coefficients: number[]): number {
  let value = 0
  let power = 1
  for (const coefficient of coefficients) {
    value += coefficient * power
    power *= x
  }
  return Math.round(Math.max(0, Math.min(1, value)) * 255)
}

function renderMetricDepth(
  canvas: HTMLCanvasElement,
  frame: MetricDepthFrame,
  settings: DepthDisplaySettings,
  depthScale: number,
) {
  let near = settings.near_m
  let far = settings.far_m
  if (settings.auto_range) {
    const sample: number[] = []
    const stride = Math.max(1, Math.floor(frame.values.length / 8192))
    for (let index = 0; index < frame.values.length; index += stride) {
      const value = frame.values[index] * depthScale
      if (Number.isFinite(value) && value > 0) sample.push(value)
    }
    sample.sort((left, right) => left - right)
    if (sample.length > 0) {
      near = sample[Math.floor((sample.length - 1) * 0.02)]
      far = sample[Math.floor((sample.length - 1) * 0.98)]
    }
  }
  if (!(far > near)) far = near + 0.001
  canvas.width = frame.width
  canvas.height = frame.height
  const context = canvas.getContext('2d')
  if (!context) return
  const image = context.createImageData(frame.width, frame.height)
  for (let index = 0; index < frame.values.length; index += 1) {
    const depth = frame.values[index] * depthScale
    const target = index * 4
    if (!Number.isFinite(depth) || depth <= 0) {
      image.data[target] = settings.invalid_color === 'magenta' ? 255 : 0
      image.data[target + 1] = 0
      image.data[target + 2] = settings.invalid_color === 'magenta' ? 255 : 0
    } else {
      const intensity = Math.max(0, Math.min(1, 1 - (depth - near) / (far - near)))
      if (settings.palette === 'turbo') {
        image.data[target] = turboChannel(intensity, turboCoefficients[0])
        image.data[target + 1] = turboChannel(intensity, turboCoefficients[1])
        image.data[target + 2] = turboChannel(intensity, turboCoefficients[2])
      } else {
        const gray = Math.round(intensity * 255)
        image.data[target] = gray
        image.data[target + 1] = gray
        image.data[target + 2] = gray
      }
    }
    image.data[target + 3] = 255
  }
  context.putImageData(image, 0, 0)
}

const depthControl: React.CSSProperties = {
  height: 23,
  minWidth: 0,
  border: '1px solid var(--line2)',
  borderRadius: 4,
  background: 'var(--lift)',
  color: 'var(--tx1)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  padding: '1px 4px',
  boxSizing: 'border-box',
}

export default function ImageSensorViewer({
  preview,
  nodeId,
  status,
  sensorKind,
  inputRail,
  depthDisplay,
  onDepthDisplayChange,
}: {
  preview: unknown
  nodeId: string
  status: unknown
  sensorKind: 'camera' | 'depth'
  inputRail?: ReactNode
  depthDisplay?: DepthDisplaySettings
  onDepthDisplayChange?: (key: DepthDisplayKey, value: boolean | number | string) => void
}) {
  const rawSource = typeof preview === 'string' ? preview : ''
  const parsed = status && typeof status === 'object' ? status as ViewerStatus : {}
  const settings: DepthDisplaySettings = depthDisplay ?? {
    auto_range: parsed.display?.range !== 'fixed',
    near_m: Number(parsed.display?.near_m ?? 0.2),
    far_m: Number(parsed.display?.far_m ?? 2.0),
    palette: parsed.display?.palette === 'turbo' ? 'turbo' : 'grayscale',
    invalid_color: parsed.display?.invalid_color === 'magenta' ? 'magenta' : 'black',
  }
  const source = rawSource
  const frameUrl = String(parsed.frame_url || '')
  const depthScale = Number(parsed.depth_scale) || 1
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const latestFrameRef = useRef<MetricDepthFrame | null>(null)
  const settingsRef = useRef(settings)
  settingsRef.current = settings
  const [depthError, setDepthError] = useState('')
  const label = String(parsed.label || (sensorKind === 'depth' ? 'Depth' : 'Camera'))
  const state = String(parsed.state || (source ? 'ready' : 'waiting'))
  const setDepthDisplay = (key: DepthDisplayKey, value: boolean | number | string) => {
    onDepthDisplayChange?.(key, value)
  }

  useEffect(() => {
    if (sensorKind !== 'depth' || !frameUrl) return undefined
    let active = true
    let timer: number | undefined
    let controller: AbortController | undefined
    const poll = async () => {
      controller = new AbortController()
      try {
        const payload = await api.depthFrame(nodeId, controller.signal)
        if (!active) return
        const frame = parseMetricDepthFrame(payload)
        latestFrameRef.current = frame
        if (canvasRef.current) renderMetricDepth(canvasRef.current, frame, settingsRef.current, depthScale)
        setDepthError('')
      } catch (error) {
        if (!active || (error as { name?: string })?.name === 'AbortError') return
        setDepthError(error instanceof Error ? error.message : String(error))
      }
      if (active) timer = window.setTimeout(poll, 100)
    }
    void poll()
    return () => {
      active = false
      controller?.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [depthScale, frameUrl, nodeId, sensorKind])

  useEffect(() => {
    if (canvasRef.current && latestFrameRef.current) {
      renderMetricDepth(canvasRef.current, latestFrameRef.current, settings, depthScale)
    }
  }, [depthScale, settings.auto_range, settings.far_m, settings.invalid_color, settings.near_m, settings.palette])

  return (
    <div
      className="nodrag"
      onMouseDown={event => event.stopPropagation()}
      style={{
        margin: '7px 9px 8px', width: 'calc(100% - 18px)', flex: '1 1 auto', minHeight: 0,
        display: 'flex', flexDirection: 'column', boxSizing: 'border-box', overflow: 'hidden',
        border: '1px solid var(--line2)', borderRadius: 'var(--bn-node-inner-radius, 7px)', background: '#15191d',
      }}
    >
      <div style={{
        minHeight: 31, display: 'flex', alignItems: 'center', gap: 8, padding: '3px 7px',
        borderBottom: '1px solid var(--line)', color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        {inputRail}
        <span style={{ marginLeft: 'auto' }}>{label}</span>
        <span style={{ color: state === 'ready' ? 'var(--ok)' : state === 'error' ? 'var(--err)' : 'var(--warn)' }}>
          {state.toUpperCase()}
        </span>
      </div>
      <div style={{ flex: '1 1 auto', minHeight: 0, display: 'grid', placeItems: 'center', overflow: 'hidden', background: '#090c0f' }}>
        {sensorKind === 'depth' && frameUrl ? (
          <>
            <canvas
              ref={canvasRef}
              aria-label={`${label} locally rendered metric depth view`}
              style={{ width: '100%', height: '100%', objectFit: 'contain', imageRendering: 'pixelated' }}
            />
            {depthError && (
              <span style={{ gridArea: '1 / 1', color: 'var(--err)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                {depthError}
              </span>
            )}
          </>
        ) : source ? (
          <img
            src={source}
            alt={`${label} sensor view`}
            draggable={false}
            onDragStart={event => event.preventDefault()}
            style={{ width: '100%', height: '100%', objectFit: 'contain', imageRendering: sensorKind === 'depth' ? 'pixelated' : 'auto' }}
          />
        ) : (
          <span style={{ color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            Waiting for processed {sensorKind} frames
          </span>
        )}
      </div>
      {sensorKind === 'depth' && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: '5px 7px', alignItems: 'center',
          padding: '6px 7px', borderTop: '1px solid var(--line)', color: 'var(--tx2)',
          fontFamily: 'var(--font-mono)', fontSize: 11,
        }}>
          <label title="Use per-frame percentile contrast" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={settings.auto_range}
              onChange={event => setDepthDisplay('auto_range', event.target.checked)}
            />
            Auto
          </label>
          <label style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 4, alignItems: 'center' }}>
            Near m
            <input
              type="number"
              min={0}
              max={Math.max(0, settings.far_m - 0.001)}
              step={0.05}
              disabled={settings.auto_range}
              value={settings.near_m}
              onChange={event => {
                const value = Number(event.target.value)
                if (Number.isFinite(value)) setDepthDisplay('near_m', Math.max(0, Math.min(value, settings.far_m - 0.001)))
              }}
              style={{ ...depthControl, opacity: settings.auto_range ? 0.5 : 1 }}
            />
          </label>
          <label style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 4, alignItems: 'center' }}>
            Far m
            <input
              type="number"
              min={settings.near_m + 0.001}
              step={0.05}
              disabled={settings.auto_range}
              value={settings.far_m}
              onChange={event => {
                const value = Number(event.target.value)
                if (Number.isFinite(value)) setDepthDisplay('far_m', Math.max(settings.near_m + 0.001, value))
              }}
              style={{ ...depthControl, opacity: settings.auto_range ? 0.5 : 1 }}
            />
          </label>
          <span title="Display changes update live and do not recook the graph">LIVE</span>
          <label style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 4, alignItems: 'center' }}>
            Palette
            <select
              value={settings.palette}
              onChange={event => setDepthDisplay('palette', event.target.value)}
              style={depthControl}
            >
              <option value="grayscale">Gray</option>
              <option value="turbo">Turbo</option>
            </select>
          </label>
          <label style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 4, alignItems: 'center' }}>
            Missing
            <select
              value={settings.invalid_color}
              onChange={event => setDepthDisplay('invalid_color', event.target.value)}
              style={depthControl}
            >
              <option value="black">Black</option>
              <option value="magenta">Magenta</option>
            </select>
          </label>
        </div>
      )}
      <div style={{
        minHeight: 25, display: 'flex', alignItems: 'center', gap: 10, padding: '0 9px',
        borderTop: '1px solid var(--line)', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span>{sensorKind === 'depth' ? 'metric depth image' : 'camera image'}</span>
        {parsed.encoding && <span>{parsed.encoding}</span>}
        {sensorKind === 'depth' && Number(parsed.depth_scale) > 0 && <span>scale {Number(parsed.depth_scale)} m/unit</span>}
        {parsed.error && <span style={{ color: 'var(--err)' }}>{parsed.error}</span>}
      </div>
    </div>
  )
}
