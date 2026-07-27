import { useEffect, useRef, useState } from 'react'
import { Handle, Position, type NodeProps } from 'reactflow'

import {
  api,
  deviceMonitorSocketUrl,
  type HardwareDevice,
  type RobotTelemetryJoint,
  type RobotTelemetrySample,
} from '../api'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'

type MonitorConnection = 'idle' | 'connecting' | 'live' | 'offline'

type JointTrace = {
  position: number[]
  velocity: number[]
}

export default function RobotMonitorNode({ id, data, selected }: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const [robots, setRobots] = useState<HardwareDevice[]>([])
  const [listError, setListError] = useState('')
  const robotId = String(data.params?.robot_id || '').trim()
  const savedName = String(data.params?.robot_name || '').trim()
  const selectedRobot = robots.find(robot => robot.id === robotId)
  const robotName = selectedRobot?.name || savedName || 'Choose a robot'

  useEffect(() => {
    let active = true
    api.listDevices()
      .then(result => {
        if (!active) return
        setRobots(result.devices)
        setListError('')
      })
      .catch(error => {
        if (!active) return
        setListError(error instanceof Error ? error.message : String(error))
      })
    return () => { active = false }
  }, [])

  const chooseRobot = async (nextId: string) => {
    const robot = robots.find(item => item.id === nextId)
    await updateParam(id, 'robot_id', nextId)
    await updateParam(id, 'robot_name', robot?.name || '')
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color="#00b8d9"
      nodeType={data.type}
      style={{ width: '100%', minWidth: 620 }}
    >
      <header className="bn-robot-monitor-node-title">
        <div>
          <span>ROBOT MONITOR</span>
          <strong>{robotName}</strong>
        </div>
        <label
          className="nodrag"
          onMouseDown={event => event.stopPropagation()}
          onClick={event => event.stopPropagation()}
        >
          <span>Robot</span>
          <select
            value={robotId}
            onChange={event => void chooseRobot(event.target.value)}
            aria-label="Robot to monitor"
          >
            <option value="">Choose a robot…</option>
            {robots.map(robot => (
              <option key={robot.id} value={robot.id}>{robot.name}</option>
            ))}
            {robotId && !selectedRobot && (
              <option value={robotId}>{savedName || robotId} (unavailable)</option>
            )}
          </select>
        </label>
      </header>

      <RobotLiveMonitor
        robotId={robotId}
        robotName={robotName}
        emptyMessage={listError}
      />

      <Handle
        type="source"
        position={Position.Right}
        id="robot"
        title="robot · Dict"
        style={{ background: '#a855f7', width: 10, height: 10 }}
      />
    </NodeFrame>
  )
}

export function RobotLiveMonitor({
  robotId,
  robotName,
  emptyMessage,
}: {
  robotId: string
  robotName: string
  emptyMessage: string
}) {
  const [sample, setSample] = useState<RobotTelemetrySample | null>(null)
  const [connection, setConnection] = useState<MonitorConnection>(
    robotId ? 'connecting' : 'idle',
  )
  const [traces, setTraces] = useState<Record<string, JointTrace>>({})
  const previous = useRef<Record<string, { position: number; at: number }>>({})
  const activeSource = useRef('')

  useEffect(() => {
    setSample(null)
    setTraces({})
    previous.current = {}
    activeSource.current = ''
    if (!robotId) {
      setConnection('idle')
      return
    }

    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined

    const connect = () => {
      if (stopped) return
      setConnection('connecting')
      socket = new WebSocket(deviceMonitorSocketUrl(robotId))
      socket.onopen = () => setConnection('live')
      socket.onmessage = event => {
        let next: RobotTelemetrySample
        try {
          next = JSON.parse(String(event.data)) as RobotTelemetrySample
        } catch {
          return
        }
        const sourceKey = `${next.source || 'unknown'}:${next.source_label || ''}`
        if (activeSource.current && activeSource.current !== sourceKey) {
          previous.current = {}
          setTraces({})
        }
        activeSource.current = sourceKey
        const receivedAt = Date.now()
        if (next.available && next.payload?.joints) {
          const normalized = next.payload.joints.map(joint => {
            const prior = previous.current[joint.name]
            const elapsed = prior ? (receivedAt - prior.at) / 1000 : 0
            const derivedVelocity = elapsed > 0
              ? (joint.position - prior.position) / elapsed
              : 0
            previous.current[joint.name] = {
              position: joint.position,
              at: receivedAt,
            }
            return {
              ...joint,
              velocity: next.source === 'hardware'
                ? derivedVelocity
                : Number.isFinite(joint.velocity) ? joint.velocity : derivedVelocity,
            }
          })
          next = {
            ...next,
            payload: {
              ...next.payload,
              joints: normalized,
            },
          }
          setTraces(current => {
            const updated = { ...current }
            for (const joint of normalized) {
              const trace = updated[joint.name] || { position: [], velocity: [] }
              updated[joint.name] = {
                position: [...trace.position, joint.position].slice(-80),
                velocity: [...trace.velocity, joint.velocity].slice(-80),
              }
            }
            return updated
          })
        }
        setSample(next)
      }
      socket.onerror = () => socket?.close()
      socket.onclose = () => {
        if (stopped) return
        setConnection('offline')
        reconnectTimer = window.setTimeout(connect, 1200)
      }
    }

    connect()
    return () => {
      stopped = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [robotId])

  const joints = sample?.payload?.joints || []
  const cameras = sample?.payload?.camera_streams || []
  const sourceLabel = sample?.source === 'deployment'
    ? `Deployment · ${sample.source_label || sample.deployment?.name || 'workflow'}`
    : 'Robot Hardware'
  const stateLabel = connection !== 'live'
    ? connection
    : sample?.stale
      ? 'stale'
      : sample?.available
        ? 'live'
        : 'waiting'
  const connected = sample?.payload?.connected
  const armed = sample?.payload?.armed
  const torque = sample?.payload?.torque_enabled
  const battery = sample?.payload?.battery

  return (
    <section
      className="bn-robot-monitor bn-robot-monitor-node-panel"
      aria-label={`Live monitoring for ${robotName}`}
    >
      <div className="bn-robot-monitor-head">
        <div>
          <span className={`bn-robot-monitor-pulse is-${stateLabel}`} aria-hidden="true" />
          <div>
            <strong>Live robot state</strong>
            <span>{robotId ? sourceLabel : 'Select a registered robot above'}</span>
          </div>
        </div>
        <div className="bn-robot-monitor-status">
          <span className={`is-${stateLabel}`}>{stateLabel.toUpperCase()}</span>
          {sample?.sequence != null && <span>#{sample.sequence}</span>}
        </div>
      </div>

      {robotId && (
        <div className="bn-robot-monitor-overview">
          <MonitorFact
            label="Hardware"
            value={connected == null ? 'Waiting' : connected ? 'Connected' : 'Disconnected'}
            tone={connected == null ? 'muted' : connected ? 'ok' : 'error'}
          />
          <MonitorFact
            label="Motion"
            value={armed == null ? 'Unknown' : armed ? 'Armed' : 'Disarmed'}
            tone={armed ? 'warning' : armed === false ? 'ok' : 'muted'}
          />
          <MonitorFact
            label="Torque"
            value={torque == null ? 'Unknown' : torque ? 'On' : 'Off'}
            tone={torque ? 'warning' : torque === false ? 'ok' : 'muted'}
          />
          <MonitorFact
            label="Telemetry"
            value={sample?.stale ? 'Stale' : sample?.available ? 'Streaming' : 'Waiting'}
            tone={sample?.stale ? 'warning' : sample?.available ? 'live' : 'muted'}
          />
          {battery && (
            <MonitorFact
              label="Battery"
              value={formatBattery(battery)}
              tone={battery.level != null && battery.level <= 0.2 ? 'warning' : 'ok'}
            />
          )}
          <MonitorFact
            label="Source"
            value={sample?.source === 'deployment' ? 'Deployment' : 'Hardware'}
            tone="live"
          />
        </div>
      )}

      {!robotId || !sample?.available ? (
        <div className="bn-robot-monitor-empty" role="status">
          <strong>
            {!robotId
              ? 'Choose a robot to start monitoring'
              : connection === 'connecting'
                ? 'Connecting to robot…'
                : connection === 'offline'
                  ? 'Reconnecting…'
                  : 'Waiting for live telemetry'}
          </strong>
          <span>
            {emptyMessage
              || sample?.message
              || (robotId
                ? 'Live data appears here as soon as Robot Hardware or its active deployment reports it.'
                : 'This node remembers the selected robot with the workflow.')}
          </span>
        </div>
      ) : (
        <>
          <div className="bn-robot-monitor-meta">
            <span>{joints.length} joints</span>
            <span>{cameras.length} streams</span>
            <span>{sample.payload?.position_unit || 'degree'}</span>
            <span>
              Updated {sample.received_at
                ? new Date(sample.received_at).toLocaleTimeString()
                : 'now'}
            </span>
          </div>

          {cameras.length > 0 && (
            <div className="bn-robot-monitor-cameras">
              {cameras.map(camera => (
                <article key={camera.id}>
                  <strong>{camera.label || camera.id}</strong>
                  {camera.url
                    ? <img src={camera.url} alt={`${camera.label || camera.id} live stream`} />
                    : <span>Stream URL unavailable</span>}
                </article>
              ))}
            </div>
          )}

          {joints.length > 0 ? (
            <div className="bn-robot-monitor-grid">
              {joints.map(joint => (
                <JointMonitorCard
                  key={joint.name}
                  joint={joint}
                  trace={traces[joint.name]}
                  positionUnit={sample.payload?.position_unit || 'degree'}
                  velocityUnit={sample.payload?.velocity_unit || 'degree/s'}
                />
              ))}
            </div>
          ) : (
            <div className="bn-robot-monitor-empty" role="status">
              <strong>Telemetry is live</strong>
              <span>This robot is not reporting joint positions yet.</span>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function MonitorFact({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'ok' | 'warning' | 'error' | 'live' | 'muted'
}) {
  return (
    <div className={`bn-robot-monitor-fact is-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function JointMonitorCard({
  joint,
  trace,
  positionUnit,
  velocityUnit,
}: {
  joint: RobotTelemetryJoint
  trace?: JointTrace
  positionUnit: string
  velocityUnit: string
}) {
  return (
    <article className="bn-joint-monitor-card">
      <div className="bn-joint-monitor-title">
        <strong title={joint.name}>{joint.name.replace(/_/g, ' ')}</strong>
        <span>{joint.position.toFixed(2)} {shortUnit(positionUnit)}</span>
      </div>
      <TelemetrySparkline values={trace?.position || []} />
      <div className="bn-joint-monitor-speed">
        <span>Speed</span>
        <strong>{joint.velocity.toFixed(2)} {shortUnit(velocityUnit)}</strong>
      </div>
    </article>
  )
}

function TelemetrySparkline({ values }: { values: number[] }) {
  const width = 180
  const height = 44
  const finite = values.filter(Number.isFinite)
  const minimum = finite.length ? Math.min(...finite) : 0
  const maximum = finite.length ? Math.max(...finite) : 0
  const range = Math.max(maximum - minimum, 0.001)
  const points = finite.map((value, index) => {
    const x = finite.length <= 1 ? width : index * width / (finite.length - 1)
    const y = height - 4 - ((value - minimum) / range) * (height - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg
      className="bn-joint-monitor-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Recent joint position"
    >
      <line x1="0" y1={height / 2} x2={width} y2={height / 2} />
      {points && <polyline points={points} />}
    </svg>
  )
}

function formatBattery(battery: NonNullable<NonNullable<RobotTelemetrySample['payload']>['battery']>) {
  const parts: string[] = []
  if (battery.level != null) {
    const percentage = battery.level <= 1 ? battery.level * 100 : battery.level
    parts.push(`${Math.round(percentage)}%`)
  }
  if (battery.voltage != null) parts.push(`${battery.voltage.toFixed(1)} V`)
  if (battery.charging) parts.push('Charging')
  return parts.join(' · ') || 'Reported'
}

function shortUnit(unit: string): string {
  return unit.replace('degree', '°')
}
