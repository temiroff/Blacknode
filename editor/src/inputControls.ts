const WIRE_ONLY_TYPES = new Set(['List', 'Dict', 'Fn', 'Embedding'])
const WIRE_ONLY_PORTS = new Set(['TelegramReply.image'])

export function isWireOnlyInput(nodeType: string, portName: string, portType: string): boolean {
  return WIRE_ONLY_TYPES.has(portType) || WIRE_ONLY_PORTS.has(`${nodeType}.${portName}`)
}
