import type { CSSProperties } from 'react'

type GlyphKind =
  | 'agent'
  | 'camera'
  | 'controller'
  | 'cuda'
  | 'dataset'
  | 'model'
  | 'output'
  | 'robot'
  | 'ros'
  | 'vision'
  | 'workflow'

function glyphKind(type: string, category = ''): GlyphKind {
  const value = `${type} ${category}`.toLowerCase()
  if (/cuda|nvidia|gpu|tensor|kernel/.test(value)) return 'cuda'
  if (/camera|video|stream/.test(value)) return 'camera'
  if (/detect|perception|vision|image|track|segment/.test(value)) return 'vision'
  if (/ros2|\bros\b|topic|service|action/.test(value)) return 'ros'
  if (/controller|control|follow|motion|navigate|planner/.test(value)) return 'controller'
  if (/robot|lidar|joint|pose|calibration/.test(value)) return 'robot'
  if (/agent|reason|llm|chat|prompt/.test(value)) return 'agent'
  if (/model|train|embed|inference/.test(value)) return 'model'
  if (/dataset|record|trajectory/.test(value)) return 'dataset'
  if (/output|print|write|export|reply/.test(value)) return 'output'
  return 'workflow'
}

const PATHS: Record<GlyphKind, React.ReactNode> = {
  agent: (
    <>
      <path d="M5.2 5.3a2.8 2.8 0 0 1 5.5.4 2.4 2.4 0 0 1-.4 4.5H5.8a2.6 2.6 0 0 1-.6-4.9Z" />
      <path d="M6.3 7.4h.01M9.7 7.4h.01M6.5 12.2 8 10.3l1.5 1.9" />
    </>
  ),
  camera: (
    <>
      <rect x="2.2" y="4.4" width="11.6" height="8.1" rx="2" />
      <circle cx="8" cy="8.45" r="2.25" />
      <path d="m5 4.4.8-1.3h4.4l.8 1.3" />
    </>
  ),
  controller: (
    <>
      <path d="M4 3v10M12 3v10M2.5 6h3M10.5 9.7h3" />
      <circle cx="4" cy="6" r="1.45" />
      <circle cx="12" cy="9.7" r="1.45" />
    </>
  ),
  cuda: (
    <path d="M9 1.8 3.8 8h3L7 14.2 12.2 8h-3L9 1.8Z" />
  ),
  dataset: (
    <>
      <ellipse cx="8" cy="3.8" rx="5" ry="2" />
      <path d="M3 3.8v4c0 1.1 2.2 2 5 2s5-.9 5-2v-4M3 7.8v4c0 1.1 2.2 2 5 2s5-.9 5-2v-4" />
    </>
  ),
  model: (
    <>
      <path d="m8 2.2 4.8 2.7v5.6L8 13.8l-4.8-3.3V4.9L8 2.2Z" />
      <path d="m3.2 4.9 4.8 3 4.8-3M8 7.9v5.9" />
    </>
  ),
  output: (
    <>
      <path d="M2.5 8h8.2M8 5.3 10.7 8 8 10.7" />
      <path d="M11.5 3.2h2v9.6h-2" />
    </>
  ),
  robot: (
    <>
      <rect x="2.5" y="4.5" width="11" height="8.5" rx="2" />
      <path d="M8 2v2.5M5.4 8h.01M10.6 8h.01M5.5 10.6h5" />
    </>
  ),
  ros: (
    <>
      <circle cx="8" cy="8" r="1.5" />
      <circle cx="3.3" cy="4" r="1.2" />
      <circle cx="12.7" cy="4" r="1.2" />
      <circle cx="3.3" cy="12" r="1.2" />
      <circle cx="12.7" cy="12" r="1.2" />
      <path d="m4.3 4.8 2.6 2.3M9.1 7.1l2.6-2.3M6.9 8.9l-2.6 2.3M9.1 8.9l2.6 2.3" />
    </>
  ),
  vision: (
    <>
      <path d="M1.8 8s2.3-4 6.2-4 6.2 4 6.2 4-2.3 4-6.2 4-6.2-4-6.2-4Z" />
      <circle cx="8" cy="8" r="2.1" />
    </>
  ),
  workflow: (
    <>
      <circle cx="3" cy="8" r="1.5" />
      <circle cx="12.8" cy="4" r="1.5" />
      <circle cx="12.8" cy="12" r="1.5" />
      <path d="m4.4 7.4 7-2.8M4.4 8.6l7 2.8" />
    </>
  ),
}

export default function NodeGlyph({
  type,
  category,
  className = '',
  style,
}: {
  type: string
  category?: string
  className?: string
  style?: CSSProperties
}) {
  const kind = glyphKind(type, category)
  return (
    <span className={`bn-node-glyph ${className}`.trim()} data-glyph={kind} style={style} aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none">
        <g
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {PATHS[kind]}
        </g>
      </svg>
    </span>
  )
}
