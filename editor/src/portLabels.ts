export function portDisplayName(port: string, direction: 'input' | 'output'): string {
  if (direction === 'input' && port === 'trigger') return 'run after'
  if (direction === 'output' && port === 'report') return 'done'
  return port.replace(/_/g, ' ')
}

export function portDisplayHint(port: string, direction: 'input' | 'output'): string {
  if (direction === 'input' && port === 'trigger') return 'Runs after the connected upstream node finishes.'
  if (direction === 'output' && port === 'report') return 'Completion output; its detailed report remains available in Properties and results.'
  return `${direction} port: ${port}`
}
