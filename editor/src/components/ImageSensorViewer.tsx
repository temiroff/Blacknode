import type { ReactNode } from 'react'

interface ViewerStatus {
  state?: string
  error?: string
  label?: string
  encoding?: string
  depth_scale?: number
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

function depthPreviewUrl(source: string, settings: DepthDisplaySettings, depthScale: number): string {
  if (!source || !/^https?:\/\//i.test(source)) return source
  try {
    const url = new URL(source)
    url.searchParams.set('depth_range', settings.auto_range ? 'auto' : 'fixed')
    url.searchParams.set('depth_scale', String(depthScale))
    url.searchParams.set('depth_palette', settings.palette)
    url.searchParams.set('depth_invalid', settings.invalid_color)
    if (settings.auto_range) {
      url.searchParams.delete('depth_near_m')
      url.searchParams.delete('depth_far_m')
    } else {
      url.searchParams.set('depth_near_m', String(settings.near_m))
      url.searchParams.set('depth_far_m', String(settings.far_m))
    }
    return url.toString()
  } catch {
    return source
  }
}

const depthControl: React.CSSProperties = {
  height: 23,
  minWidth: 0,
  border: '1px solid var(--line2)',
  borderRadius: 4,
  background: 'var(--lift)',
  color: 'var(--tx1)',
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  padding: '1px 4px',
  boxSizing: 'border-box',
}

export default function ImageSensorViewer({
  preview,
  status,
  sensorKind,
  inputRail,
  depthDisplay,
  onDepthDisplayChange,
}: {
  preview: unknown
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
  const source = sensorKind === 'depth'
    ? depthPreviewUrl(rawSource, settings, Number(parsed.depth_scale) || 1)
    : rawSource
  const label = String(parsed.label || (sensorKind === 'depth' ? 'Depth' : 'Camera'))
  const state = String(parsed.state || (source ? 'ready' : 'waiting'))
  const setDepthDisplay = (key: DepthDisplayKey, value: boolean | number | string) => {
    onDepthDisplayChange?.(key, value)
  }

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
        {source ? (
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
          fontFamily: 'var(--font-mono)', fontSize: 10,
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
