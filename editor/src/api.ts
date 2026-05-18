const BASE = 'http://127.0.0.1:7777'

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

export const api = {
  nodeTypes: ()                              => req<string[]>('GET', '/node-types'),
  getGraph:  ()                              => req<{ nodes: any[]; edges: any[] }>('GET', '/graph'),
  addNode:   (type_name: string, pos: [number,number], params = {}) =>
    req('POST', '/nodes', { type_name, pos, params }),
  removeNode: (id: string)                  => req('DELETE', `/nodes/${id}`),
  updateParam:(id: string, key: string, value: unknown) =>
    req('PATCH', `/nodes/${id}/params`, { key, value }),
  updatePos:  (id: string, pos: [number,number]) =>
    req('PATCH', `/nodes/${id}/pos`, pos),
  connect:    (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('POST', '/edges', { from_id, from_port, to_id, to_port }),
  disconnect: (from_id: string, from_port: string, to_id: string, to_port: string) =>
    req('DELETE', `/edges?from_id=${from_id}&from_port=${from_port}&to_id=${to_id}&to_port=${to_port}`),
  cook:       (node_id: string, port = 'output') =>
    req<{ value: unknown; port: string }>('POST', '/cook', { node_id, port }),
  reset:      ()                             => req('POST', '/reset'),
}
