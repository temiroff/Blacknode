import type { ReactNode } from 'react'

interface ViewerStatus {
  state?: string
  error?: string
  label?: string
  encoding?: string
  depth_scale?: number
}

export default function ImageSensorViewer({
  preview,
  status,
  sensorKind,
  inputRail,
}: {
  preview: unknown
  status: unknown
  sensorKind: 'camera' | 'depth'
  inputRail?: ReactNode
}) {
  const source = typeof preview === 'string' ? preview : ''
  const parsed = status && typeof status === 'object' ? status as ViewerStatus : {}
  const label = String(parsed.label || (sensorKind === 'depth' ? 'Depth' : 'Camera'))
  const state = String(parsed.state || (source ? 'ready' : 'waiting'))

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
