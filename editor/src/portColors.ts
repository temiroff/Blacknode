export const PORT_COLORS: Record<string, string> = {
  Text:      '#f59e0b',  // amber
  Int:       '#22c55e',  // green
  Float:     '#22c55e',  // green
  Number:    '#22c55e',  // green
  Bool:      '#3b82f6',  // blue
  List:      '#f97316',  // orange
  Dict:      '#a855f7',  // purple
  Embedding: '#ec4899',  // pink
  Fn:        '#ef4444',  // red
  Any:       '#6b7280',  // grey
}

export function portColor(type: string): string {
  return PORT_COLORS[type] ?? PORT_COLORS.Any
}
