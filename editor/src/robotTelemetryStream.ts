import {
  deviceMonitorSocketUrl,
  type RobotTelemetrySample,
} from './api'

export type RobotMonitorConnection = 'idle' | 'connecting' | 'live' | 'offline'

type Listener = {
  onSample: (sample: RobotTelemetrySample) => void
  onConnection: (connection: RobotMonitorConnection) => void
}

type Stream = {
  robotId: string
  profileId: string
  listeners: Set<Listener>
  socket: WebSocket | null
  reconnectTimer?: number
  connection: RobotMonitorConnection
  latest: RobotTelemetrySample | null
  stopped: boolean
}

const streams = new Map<string, Stream>()

function publishConnection(stream: Stream, connection: RobotMonitorConnection) {
  stream.connection = connection
  for (const listener of stream.listeners) listener.onConnection(connection)
}

function connect(stream: Stream) {
  if (stream.stopped || stream.listeners.size === 0) return
  publishConnection(stream, 'connecting')
  const socket = new WebSocket(
    deviceMonitorSocketUrl(stream.robotId, stream.profileId),
  )
  stream.socket = socket
  socket.onopen = () => publishConnection(stream, 'live')
  socket.onmessage = event => {
    let sample: RobotTelemetrySample
    try {
      sample = JSON.parse(String(event.data)) as RobotTelemetrySample
    } catch {
      return
    }
    stream.latest = sample
    for (const listener of stream.listeners) listener.onSample(sample)
  }
  socket.onerror = () => socket.close()
  socket.onclose = () => {
    if (stream.socket === socket) stream.socket = null
    if (stream.stopped || stream.listeners.size === 0) return
    publishConnection(stream, 'offline')
    stream.reconnectTimer = window.setTimeout(() => connect(stream), 1200)
  }
}

export function subscribeRobotTelemetry(
  robotId: string,
  profileId: string,
  onSample: Listener['onSample'],
  onConnection: Listener['onConnection'],
): () => void {
  const cleanId = String(robotId || '').trim()
  const cleanProfileId = String(profileId || 'auto').trim() || 'auto'
  if (!cleanId) {
    onConnection('idle')
    return () => undefined
  }
  const streamKey = `${cleanId}\u0000${cleanProfileId}`
  let stream = streams.get(streamKey)
  if (!stream) {
    stream = {
      robotId: cleanId,
      profileId: cleanProfileId,
      listeners: new Set(),
      socket: null,
      connection: 'connecting',
      latest: null,
      stopped: false,
    }
    streams.set(streamKey, stream)
  }
  const listener = { onSample, onConnection }
  stream.listeners.add(listener)
  onConnection(stream.connection)
  if (stream.latest) onSample(stream.latest)
  if (!stream.socket && stream.reconnectTimer === undefined) connect(stream)

  return () => {
    stream!.listeners.delete(listener)
    if (stream!.listeners.size > 0) return
    stream!.stopped = true
    if (stream!.reconnectTimer !== undefined) {
      window.clearTimeout(stream!.reconnectTimer)
      stream!.reconnectTimer = undefined
    }
    const socket = stream!.socket
    stream!.socket = null
    socket?.close()
    streams.delete(streamKey)
  }
}
