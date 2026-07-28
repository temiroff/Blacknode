export const PORT_COLORS: Record<string, string> = {
  Text:      '#f59e0b',  // amber
  Int:       '#22c55e',  // green
  Float:     '#06b6d4',  // cyan
  Number:    '#34d399',  // emerald (generic numeric)
  Bool:      '#e879f9',  // fuchsia
  List:      '#f97316',  // orange
  Dict:      '#a855f7',  // purple
  Embedding: '#ec4899',  // pink
  Fn:        '#ef4444',  // red
  Model:     '#76b900',  // nvidia green
  Image:     '#fb7185',  // rose
  Video:     '#f43f5e',  // deep rose
  Color:     '#e11d48',  // color picker value
  HSV:       '#0ea5e9',  // hue/saturation/value triplet
  Any:       '#6b7280',  // grey
}

export const TEST_UI_PORT_COLORS: Record<string, string> = {
  Text:       '#fbbf24',  // yellow
  Bool:       '#4ade80',  // green
  Int:        '#84cc16',  // lime
  Float:      '#22d3ee',  // cyan
  Number:     '#34d399',  // emerald
  Image:      '#f472b6',  // pink
  Frame:      '#3b82f6',  // blue
  Video:      '#6366f1',  // indigo
  Pose:       '#22d3ee',  // cyan
  Transform:  '#06b6d4',  // cyan
  PointCloud: '#0ea5e9',  // sky
  Tensor:     '#ef4444',  // red
  Audio:      '#14b8a6',  // teal
  Dict:       '#a855f7',  // purple
  List:       '#f97316',  // orange
  Embedding:  '#ec4899',  // pink
  Fn:         '#f43f5e',  // rose
  Model:      '#a78bfa',  // violet
  ROS:        '#2e9fe6',  // ROS blue
  GPU:        '#76b900',  // NVIDIA lime
  Color:      '#e11d48',  // color picker value
  HSV:        '#0ea5e9',  // hue/saturation/value triplet
  Bytes:      '#94a3b8',  // slate
  Any:        '#6b7280',  // grey
}

// Which target types a source type can connect to.
// Image values are always plain strings at runtime (data URL, http URL, or
// path) - there is no separate binary representation - so Text and Image
// are mutually compatible. Keep in sync with python/blacknode/workflow.py's
// _COMPAT table.
const COMPAT: Record<string, Set<string>> = {
  Text:      new Set(['Text', 'Color', 'Image', 'Any']),
  Int:       new Set(['Int', 'Float', 'Number', 'Any']),
  Float:     new Set(['Float', 'Int', 'Number', 'Any']),
  Number:    new Set(['Number', 'Int', 'Float', 'Any']),
  Bool:      new Set(['Bool', 'Any']),
  List:      new Set(['List', 'Any']),
  Dict:      new Set(['Dict', 'Any']),
  Embedding: new Set(['Embedding', 'Any']),
  Fn:        new Set(['Fn', 'Any']),
  Model:     new Set(['Model', 'Text', 'Any']),
  Image:     new Set(['Image', 'Text', 'Any']),
  Video:     new Set(['Video', 'Any']),
  Color:     new Set(['Color', 'Text', 'Any']),
  HSV:       new Set(['HSV', 'Text', 'Any']),
}

export function portColor(type: string): string {
  return colorFromMap(type, PORT_COLORS)
}

export function portVisualColor(type: string): string {
  return colorFromMap(type, TEST_UI_PORT_COLORS)
}

function colorFromMap(type: string, colors: Record<string, string>): string {
  if (colors[type]) return colors[type]
  const lower = type.toLowerCase()
  const nested = Object.keys(colors).find(key => (
    key !== 'Any'
    && new RegExp(`(^|[^a-z])${key.toLowerCase()}([^a-z]|$)`).test(lower)
  ))
  return nested ? colors[nested] : colors.Any
}

/** Returns true if a source port of `fromType` can connect to a target port of `toType`. */
export function portsCompatible(fromType: string, toType: string): boolean {
  if (fromType === 'Any' || toType === 'Any') return true
  if (fromType === toType) return true
  return COMPAT[fromType]?.has(toType) ?? false
}
