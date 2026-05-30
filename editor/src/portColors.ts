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
  Any:       '#6b7280',  // grey
}

// Which target types a source type can connect to
const COMPAT: Record<string, Set<string>> = {
  Text:      new Set(['Text', 'Any']),
  Int:       new Set(['Int', 'Float', 'Number', 'Any']),
  Float:     new Set(['Float', 'Int', 'Number', 'Any']),
  Number:    new Set(['Number', 'Int', 'Float', 'Any']),
  Bool:      new Set(['Bool', 'Any']),
  List:      new Set(['List', 'Any']),
  Dict:      new Set(['Dict', 'Any']),
  Embedding: new Set(['Embedding', 'Any']),
  Fn:        new Set(['Fn', 'Any']),
  Model:     new Set(['Model', 'Text', 'Any']),
  Image:     new Set(['Image', 'Any']),
}

export function portColor(type: string): string {
  return PORT_COLORS[type] ?? PORT_COLORS.Any
}

/** Returns true if a source port of `fromType` can connect to a target port of `toType`. */
export function portsCompatible(fromType: string, toType: string): boolean {
  if (fromType === 'Any' || toType === 'Any') return true
  if (fromType === toType) return true
  return COMPAT[fromType]?.has(toType) ?? false
}
