import { useEffect, useRef, useState } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'

import {
  api,
  type DeviceRobotProfile,
  type RobotMonitorTarget,
  type RobotTelemetryJoint,
  type RobotTelemetrySample,
} from '../api'
import {
  subscribeRobotTelemetry,
  type RobotMonitorConnection,
} from '../robotTelemetryStream'
import { hardwareWarningHint } from '../robotTelemetryDiagnostics'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'

type JointTrace = {
  position: number[]
  velocity: number[]
}

export default function RobotMonitorNode({ id, data, selected }: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const [robots, setRobots] = useState<RobotMonitorTarget[]>([])
  const [profiles, setProfiles] = useState<DeviceRobotProfile[]>([])
  const [listError, setListError] = useState('')
  const profileId = String(data.params?.profile_id || 'auto').trim() || 'auto'
  const robotId = String(data.params?.robot_id || '').trim()
  const savedName = String(data.params?.robot_name || '').trim()
  const selectedRobot = robots.find(robot => robot.id === robotId)
  const robotName = selectedRobot?.name || savedName || 'Choose a robot'

  useEffect(() => {
    let active = true
    api.listRobotMonitorTargets(profileId)
      .then(result => {
        if (!active) return
        setRobots(result.targets)
        setProfiles(result.profiles || [])
        setListError('')
      })
      .catch(error => {
        if (!active) return
        setListError(error instanceof Error ? error.message : String(error))
      })
    return () => { active = false }
  }, [profileId])

  const chooseRobot = async (nextId: string) => {
    const robot = robots.find(item => item.id === nextId)
    await updateParam(id, 'robot_id', nextId)
    await updateParam(id, 'robot_name', robot?.name || '')
  }

  const chooseProfile = async (nextProfileId: string) => {
    const current = robots.find(item => item.id === robotId)
    await updateParam(id, 'profile_id', nextProfileId)
    try {
      const result = await api.listRobotMonitorTargets(nextProfileId)
      setRobots(result.targets)
      setProfiles(result.profiles || [])
      setListError('')
      if (current?.kind === 'local_usb') {
        const replacement = result.targets.find(item => (
          item.kind === 'local_usb'
          && (
            item.hardware_id === current.hardware_id
            || item.port === current.port
          )
        ))
        if (replacement) {
          await updateParam(id, 'robot_id', replacement.id)
          await updateParam(id, 'robot_name', replacement.name)
        }
      }
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color="#00b8d9"
      nodeType={data.type}
      style={{
        width: '100%',
        height: '100%',
        minWidth: 620,
        minHeight: 260,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={620}
        minHeight={260}
        isVisible={selected}
        lineStyle={{ borderColor: '#00b8d9' }}
        handleStyle={{
          background: '#00b8d9',
          borderColor: '#00b8d9',
          width: 8,
          height: 8,
          borderRadius: 2,
        }}
      />

      <header className="bn-robot-monitor-node-title">
        <div>
          <span>ROBOT MONITOR</span>
          <strong>{robotName}</strong>
        </div>
        <div
          className="bn-robot-monitor-node-pickers nodrag"
          onMouseDown={event => event.stopPropagation()}
          onClick={event => event.stopPropagation()}
        >
          <label>
            <span>Profile</span>
            <select
              value={profileId}
              onChange={event => void chooseProfile(event.target.value)}
              aria-label="Profile for local USB monitoring"
            >
              <option value="auto">Auto · match this hardware</option>
              <option value="none">None · raw read-only</option>
              {profiles.map(profile => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} · {profile.id}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Robot</span>
            <select
              value={robotId}
              onChange={event => void chooseRobot(event.target.value)}
              aria-label="Robot to monitor"
            >
              <option value="">Choose a robot…</option>
              {robots.some(robot => robot.kind === 'local_usb') && (
                <optgroup label="Local USB">
                  {robots.filter(robot => robot.kind === 'local_usb').map(robot => (
                    <option key={robot.id} value={robot.id} disabled={!robot.available}>
                      {robot.name}{robot.available ? '' : ' (profile needed)'}
                    </option>
                  ))}
                </optgroup>
              )}
              {robots.some(robot => robot.kind === 'registered') && (
                <optgroup label="Registered robots">
                  {robots.filter(robot => robot.kind === 'registered').map(robot => (
                    <option key={robot.id} value={robot.id}>{robot.name}</option>
                  ))}
                </optgroup>
              )}
              {robotId && !selectedRobot && (
                <option value={robotId}>{savedName || robotId} (unavailable)</option>
              )}
            </select>
          </label>
        </div>
      </header>

      <RobotLiveMonitor
        robotId={robotId}
        robotName={robotName}
        profileId={profileId}
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
  profileId = 'auto',
  emptyMessage,
}: {
  robotId: string
  robotName: string
  profileId?: string
  emptyMessage: string
}) {
  const [sample, setSample] = useState<RobotTelemetrySample | null>(null)
  const [connection, setConnection] = useState<RobotMonitorConnection>(
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

    return subscribeRobotTelemetry(
      robotId,
      profileId,
      nextSample => {
        let next = nextSample
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
      },
      setConnection,
    )
  }, [profileId, robotId])

  const joints = sample?.payload?.joints || []
  const cameras = sample?.payload?.camera_streams || []
  const sourceLabel = sample?.source === 'deployment'
    ? `Deployment · ${sample.source_label || sample.deployment?.name || 'workflow'}`
    : sample?.source_label || 'Robot Hardware'
  const stateLabel = connection !== 'live'
    ? connection
    : sample?.stale
      ? 'stale'
      : sample?.available
        ? 'live'
        : 'waiting'
  const connected = sample?.payload?.connected
  const armed = sample?.payload?.armed ?? sample?.deployment?.motion_armed
  const torque = sample?.payload?.torque_enabled
  const battery = sample?.payload?.battery
  const calibrated = sample?.payload?.calibrated
  const calibration = sample?.payload?.calibration
  const rawMode = sample?.payload?.raw_mode === true
  const topologyJointCount = Object.keys(calibration?.topology || {}).length
  const calibratedJointCount = Object.keys(calibration?.joints || {}).length
  const expectedJointCount = Number(calibration?.joint_count)
    || topologyJointCount
    || calibratedJointCount
  const jointCoverageComplete = expectedJointCount > 0 && joints.length === expectedJointCount
  const calibrationLabel = rawMode
    ? 'Needs profile'
    : calibrated === true
    ? calibration?.name || 'Active'
    : calibrated === false
      ? calibration && Object.keys(calibration).length > 0 ? 'Not active' : 'None'
      : calibration && Object.keys(calibration).length > 0 ? 'Reported' : 'Unknown'
  const bus = sample?.payload?.bus
  const hardwareWarningCount = joints.filter(
    joint => Number(joint.hardware_error_flags || 0) !== 0,
  ).length

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
          <MonitorFact
            label="Profile"
            value={rawMode ? 'None · raw' : calibration?.profile_id || 'Unknown'}
            tone={rawMode ? 'warning' : calibration?.profile_id ? 'ok' : 'muted'}
          />
          <MonitorFact
            label="Calibration"
            value={calibrationLabel}
            tone={calibrated === true ? 'ok' : calibrated === false ? 'warning' : 'muted'}
          />
          <MonitorFact
            label="Joint coverage"
            value={expectedJointCount > 0 ? `${joints.length} / ${expectedJointCount}` : String(joints.length)}
            tone={jointCoverageComplete ? 'ok' : expectedJointCount > 0 ? 'warning' : 'muted'}
          />
          <MonitorFact
            label="Servo warnings"
            value={String(hardwareWarningCount)}
            tone={hardwareWarningCount ? 'warning' : joints.length ? 'ok' : 'muted'}
          />
          <MonitorFact
            label="Bus timeouts"
            value={bus?.timeout_count == null ? 'Unknown' : String(bus.timeout_count)}
            tone={bus?.timeout_count ? 'warning' : bus ? 'ok' : 'muted'}
          />
          <MonitorFact
            label="Packet errors"
            value={bus?.serial_packet_error_count == null
              ? 'Unknown'
              : String(bus.serial_packet_error_count)}
            tone={bus?.serial_packet_error_count ? 'warning' : bus ? 'ok' : 'muted'}
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
            {calibration?.hardware_id && <span title={calibration.hardware_id}>Hardware {calibration.hardware_id}</span>}
            <span>{cameras.length} streams</span>
            <span>{sample.payload?.position_unit || 'degree'}</span>
            <span>
              Updated {sample.received_at
                ? new Date(sample.received_at).toLocaleTimeString()
                : 'now'}
            </span>
            {bus?.operation_count != null && <span>{bus.operation_count} bus operations</span>}
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
              {[...joints]
                .sort((left, right) => (
                  Number(left.servo_id ?? Number.MAX_SAFE_INTEGER)
                  - Number(right.servo_id ?? Number.MAX_SAFE_INTEGER)
                ))
                .map(joint => (
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
  const lowerLimit = joint.lower_limit
  const upperLimit = joint.upper_limit
  const hasLimits = Number.isFinite(lowerLimit)
    && Number.isFinite(upperLimit)
    && Number(upperLimit) > Number(lowerLimit)
  const unit = shortUnit(positionUnit)
  const hardwareFlags = Number(joint.hardware_error_flags || 0)
  const hardwareErrors = joint.hardware_errors || []
  const warning = hardwareFlags !== 0

  return (
    <article className={`bn-joint-monitor-card${warning ? ' is-warning' : ''}`}>
      <div className="bn-joint-monitor-title">
        <div>
          <strong title={joint.semantic_name || joint.name}>
            {(joint.semantic_name || joint.name).replace(/_/g, ' ')}
          </strong>
          <small>
            {joint.servo_id == null ? joint.name : `Servo ID ${joint.servo_id}`}
          </small>
        </div>
        <span>{joint.position.toFixed(2)} {unit}</span>
      </div>
      <TelemetrySparkline
        values={trace?.position || []}
        lowerLimit={lowerLimit}
        upperLimit={upperLimit}
      />
      {hasLimits && (
        <div className="bn-joint-monitor-range">
          <span>{Number(lowerLimit).toFixed(0)} {unit}</span>
          <span>Joint limits</span>
          <span>{Number(upperLimit).toFixed(0)} {unit}</span>
        </div>
      )}
      <div className="bn-joint-monitor-speed">
        <span>Speed</span>
        <strong>{joint.velocity.toFixed(2)} {shortUnit(velocityUnit)}</strong>
      </div>
      <div className="bn-joint-monitor-diagnostics">
        <span>Raw <strong>{joint.raw_position ?? '—'}</strong></span>
        <span>Response <strong>{joint.communication_ok === false ? 'Failed' : 'OK'}</strong></span>
        <span>Voltage <strong>{joint.voltage_v == null ? '—' : `${joint.voltage_v.toFixed(2)} V`}</strong></span>
        <span>Temp <strong>{joint.temperature_c == null ? '—' : `${joint.temperature_c.toFixed(1)} °C`}</strong></span>
        <span>Status <strong>{`0x${hardwareFlags.toString(16).padStart(2, '0')}`}</strong></span>
      </div>
      {warning && (
        <div className="bn-joint-monitor-warning">
          <strong>Hardware warning</strong>
          <span>{hardwareErrors.join(', ') || 'Vendor status flag reported'}</span>
          <small>{hardwareWarningHint(joint)}</small>
        </div>
      )}
    </article>
  )
}

function TelemetrySparkline({
  values,
  lowerLimit,
  upperLimit,
}: {
  values: number[]
  lowerLimit?: number
  upperLimit?: number
}) {
  const width = 180
  const height = 44
  const finite = values.filter(Number.isFinite)
  const hasLimits = Number.isFinite(lowerLimit)
    && Number.isFinite(upperLimit)
    && Number(upperLimit) > Number(lowerLimit)
  const minimum = hasLimits ? Number(lowerLimit) : finite.length ? Math.min(...finite) : 0
  const maximum = hasLimits ? Number(upperLimit) : finite.length ? Math.max(...finite) : 0
  const range = Math.max(maximum - minimum, 0.001)
  const points = finite.map((value, index) => {
    const x = finite.length <= 1 ? width : index * width / (finite.length - 1)
    const normalized = Math.min(1, Math.max(0, (value - minimum) / range))
    const y = height - 4 - normalized * (height - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg
      className="bn-joint-monitor-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={hasLimits
        ? 'Recent joint position scaled to configured limits'
        : 'Recent joint position'}
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
