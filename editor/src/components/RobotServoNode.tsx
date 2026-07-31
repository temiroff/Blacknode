import { useEffect, useMemo, useRef, useState } from 'react'
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

function hardwareIdentity(value: unknown): string {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function servoIdOf(joint: RobotTelemetryJoint): number | null {
  if (Number.isInteger(joint.servo_id)) return Number(joint.servo_id)
  const match = /^(?:servo|joint)_(\d+)$/.exec(joint.name)
  return match ? Number(match[1]) : null
}

function convert(value: number, source: string, target: string): number {
  const sourceRadians = source.toLowerCase().startsWith('radian')
  const targetRadians = target.toLowerCase().startsWith('radian')
  if (sourceRadians === targetRadians) return value
  return sourceRadians ? value * 180 / Math.PI : value * Math.PI / 180
}

type QueuedMotionCommand = {
  command: Record<string, unknown>
}

export default function RobotServoNode({ id, data, selected }: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const nodes = useStore(state => state.nodes)
  const edges = useStore(state => state.edges)
  const [devices, setDevices] = useState<RobotMonitorTarget[]>([])
  const [profiles, setProfiles] = useState<DeviceRobotProfile[]>([])
  const [sample, setSample] = useState<RobotTelemetrySample | null>(null)
  const [connection, setConnection] = useState<RobotMonitorConnection>('idle')
  const [derivedVelocity, setDerivedVelocity] = useState(0)
  const [motionReport, setMotionReport] = useState('')
  const [servoArmed, setServoArmed] = useState(false)
  const [armPending, setArmPending] = useState(false)
  const previous = useRef<{ position: number; at: number } | null>(null)
  const servoArmedRef = useRef(false)
  const motionQueue = useRef<{ running: boolean; pending?: QueuedMotionCommand }>({
    running: false,
  })
  const servoId = Math.max(1, Math.min(253, Number(data.params?.servo_id ?? 1) || 1))
  const units = String(data.params?.units ?? 'degrees')

  const source = useMemo(() => {
    const edge = edges.find(item => item.target === id && item.targetHandle === 'robot')
    return edge ? nodes.find(node => node.id === edge.source) : undefined
  }, [edges, id, nodes])
  const sourceRobot = (
    source?.data.portResults?.robot
    && typeof source.data.portResults.robot === 'object'
  )
    ? source.data.portResults.robot as Record<string, unknown>
    : {}
  const driver = (
    sourceRobot.driver
    && typeof sourceRobot.driver === 'object'
  )
    ? sourceRobot.driver as Record<string, unknown>
    : {}
  const directRobotId = String(data.params?.robot_id ?? '').trim()
  const directProfileId = String(data.params?.profile_id ?? 'auto').trim() || 'auto'
  const sourceRobotId = source?.data.type === 'RobotMonitor'
    ? String(source.data.params?.robot_id ?? '').trim()
    : String(sourceRobot.robot_id ?? sourceRobot.device_id ?? '').trim()
  const sourceProfileId = source?.data.type === 'RobotMonitor'
    ? String(source.data.params?.profile_id ?? 'auto').trim() || 'auto'
    : String(source?.data.params?.profile_id ?? 'auto').trim() || 'auto'
  const sourceHardwareId = String(
    driver.hardware_id
    ?? (source?.data.portResults?.hardware as Record<string, unknown> | undefined)?.serial
    ?? '',
  ).trim()
  const mappedDevice = sourceHardwareId
    ? devices.find(device => (
      hardwareIdentity(device.hardware_id).includes(hardwareIdentity(sourceHardwareId))
      || hardwareIdentity(device.id).includes(hardwareIdentity(sourceHardwareId))
    ))
    : undefined
  const robotId = directRobotId || sourceRobotId || mappedDevice?.id || ''
  const profileId = directRobotId ? directProfileId : source ? sourceProfileId : directProfileId
  const robotName = devices.find(device => device.id === robotId)?.name
    || String(source?.data.params?.robot_name ?? '')
    || String(source?.data.params?.profile_id ?? '')
    || 'Robot'

  useEffect(() => {
    let active = true
    void api.listRobotMonitorTargets(profileId)
      .then(result => {
        if (!active) return
        setDevices(result.targets)
        setProfiles(result.profiles || [])
      })
      .catch(() => undefined)
    return () => { active = false }
  }, [profileId])

  useEffect(() => {
    setSample(null)
    setDerivedVelocity(0)
    previous.current = null
    return subscribeRobotTelemetry(
      robotId,
      profileId,
      next => {
        const joint = (next.payload?.joints || []).find(item => servoIdOf(item) === servoId)
        if (joint) {
          const now = Date.now()
          const prior = previous.current
          if (prior && now > prior.at) {
            setDerivedVelocity((joint.position - prior.position) / ((now - prior.at) / 1000))
          }
          previous.current = { position: joint.position, at: now }
        }
        setSample(next)
      },
      setConnection,
    )
  }, [profileId, robotId, servoId])

  useEffect(() => {
    servoArmedRef.current = servoArmed
  }, [servoArmed])

  useEffect(() => () => {
    if (servoArmedRef.current) {
      void api.controlNode(id, 'disarm').catch(() => undefined)
    }
  }, [id])

  const joints = sample?.payload?.joints || []
  const joint = joints.find(item => servoIdOf(item) === servoId)
  const detectedIds = [...new Set(joints.map(servoIdOf).filter((value): value is number => value != null))]
    .sort((a, b) => a - b)
  const sourcePositionUnit = sample?.payload?.position_unit || 'degree'
  const sourceVelocityUnit = sample?.payload?.velocity_unit || 'degree/s'
  const rawMode = sample?.payload?.raw_mode === true || sourcePositionUnit === 'ticks'
  const position = joint
    ? rawMode ? joint.position : convert(joint.position, sourcePositionUnit, units)
    : 0
  const velocityValue = sample?.source === 'hardware' ? derivedVelocity : joint?.velocity ?? 0
  const velocity = rawMode
    ? velocityValue
    : convert(velocityValue, sourceVelocityUnit, `${units}/s`)
  const lower = joint?.lower_limit == null
    ? rawMode ? 0 : units === 'degrees' ? -180 : -Math.PI
    : convert(joint.lower_limit, sourcePositionUnit, units)
  const upper = joint?.upper_limit == null
    ? rawMode ? 4095 : units === 'degrees' ? 180 : Math.PI
    : convert(joint.upper_limit, sourcePositionUnit, units)
  const hasCalibratedLimits = Boolean(
    sample?.payload?.calibrated
    && joint?.lower_limit != null
    && joint?.upper_limit != null,
  )
  const followFeedback = data.params?.follow_feedback !== false
  const targetParam = Number(data.params?.target_position ?? 0)
  const target = Math.max(lower, Math.min(upper, followFeedback ? position : targetParam))
  const temperature = sample?.payload?.temperatures_c?.[joint?.name || '']
    ?? sample?.payload?.temperatures_c?.[`servo_${servoId}`]
    ?? joint?.temperature_c
  const voltage = joint?.voltage_v ?? sample?.payload?.voltage_v
  const hardwareFlags = Number(joint?.hardware_error_flags || 0)
  const hardwareErrors = joint?.hardware_errors || []
  const faults = (sample?.payload?.faults || []).filter(fault => {
    if (fault.active === false) return false
    const faultJoint = String(fault.details?.joint || '')
    return !faultJoint || [
      joint?.name,
      joint?.semantic_name,
      `servo_${servoId}`,
    ].includes(faultJoint)
  })
  const bus = sample?.payload?.bus
  const state = !robotId
    ? 'CONNECT ROBOT'
    : connection !== 'live'
      ? connection.toUpperCase()
      : sample?.stale
        ? 'STALE'
        : joint
          ? hardwareFlags || faults.length ? 'WARNING' : 'LIVE'
          : 'ID NOT REPORTED'
  const stateTone = state === 'LIVE'
    ? '#22c55e'
    : state === 'STALE' || state === 'WARNING'
      ? '#f59e0b'
      : '#ef4444'
  const unit = rawMode ? 'ticks' : units === 'degrees' ? '°' : 'rad'

  const disarmServo = async (report = 'Motion disarmed') => {
    motionQueue.current.pending = undefined
    try {
      await api.controlNode(id, 'disarm')
    } catch {
      // Parameter changes also disarm on the server; keep the UI fail-safe.
    }
    servoArmedRef.current = false
    setServoArmed(false)
    setMotionReport(report)
  }
  const chooseServo = (next: number) => {
    if (servoArmedRef.current) void disarmServo('Motion disarmed because the servo ID changed')
    void updateParam(id, 'servo_id', next)
    void updateParam(id, 'follow_feedback', true)
  }
  const stepServo = (delta: number) => {
    chooseServo(Math.max(1, Math.min(253, servoId + delta)))
  }
  const queueMotionCommand = (queued: QueuedMotionCommand) => {
    motionQueue.current.pending = queued
    if (motionQueue.current.running) return
    motionQueue.current.running = true
    void (async () => {
      try {
        while (motionQueue.current.pending) {
          const pending = motionQueue.current.pending
          motionQueue.current.pending = undefined
          const command = { ...pending.command, issued_at: Date.now() / 1000 }
          const result = await api.controlNode(id, 'joint-command', { command })
          const armed = result.outputs.armed === true
          servoArmedRef.current = armed
          setServoArmed(armed)
          setMotionReport(String(result.outputs.report || 'Joint command accepted'))
        }
      } catch (error) {
        servoArmedRef.current = false
        setServoArmed(false)
        setMotionReport(error instanceof Error ? error.message : String(error))
      } finally {
        motionQueue.current.running = false
        if (motionQueue.current.pending) {
          const next = motionQueue.current.pending
          motionQueue.current.pending = undefined
          queueMotionCommand(next)
        }
      }
    })()
  }
  const setTarget = (next: number) => {
    const jointName = String(joint?.name || joint?.semantic_name || data.params?.joint_name || '').trim()
    void (async () => {
      if (jointName && data.params?.joint_name !== jointName) {
        await updateParam(id, 'joint_name', jointName)
      }
      void updateParam(id, 'follow_feedback', false)
      void updateParam(id, 'target_position', next)
      if (!servoArmedRef.current) {
        setMotionReport('Preview only — press Arm on this Servo node to enable motion')
        return
      }
      if (!jointName) {
        setMotionReport('Motion blocked — the live joint name is unavailable')
        return
      }
      if (
        connection !== 'live'
        || sample?.stale
        || !hasCalibratedLimits
        || hardwareFlags !== 0
        || faults.length > 0
      ) {
        setMotionReport('Motion blocked — live, calibrated, warning-free feedback is required')
        return
      }
      queueMotionCommand({
        command: {
          kind: 'blacknode.joint-command-request',
          schema_version: 1,
          joint_name: jointName,
          servo_id: servoId,
          position_rad: units === 'degrees' ? next * Math.PI / 180 : next,
          source: 'RobotServo',
          requires_motion_authorization: true,
        },
      })
    })()
  }
  const toggleServoArm = async () => {
    if (armPending) return
    setArmPending(true)
    try {
      if (servoArmedRef.current) {
        await disarmServo()
        return
      }
      const jointName = String(joint?.name || joint?.semantic_name || data.params?.joint_name || '').trim()
      if (!robotId) throw new Error('Choose a local USB robot before arming')
      if (!robotId.startsWith('local-usb-')) {
        throw new Error('Direct Servo motion currently requires a local USB robot')
      }
      if (!profileId || profileId === 'none') {
        throw new Error('Choose a calibrated profile before arming; None is read-only')
      }
      if (!jointName) throw new Error(`Servo ID ${servoId} is not reported by this robot`)
      if (
        connection !== 'live'
        || sample?.stale
        || rawMode
        || !hasCalibratedLimits
        || joint?.communication_ok === false
        || hardwareFlags !== 0
        || faults.length > 0
      ) {
        throw new Error('Motion blocked — live, calibrated, warning-free feedback is required')
      }

      await updateParam(id, 'robot_id', robotId)
      await updateParam(id, 'profile_id', profileId)
      await updateParam(id, 'joint_name', jointName)
      const result = await api.controlNode(id, 'arm', {
        robot_id: robotId,
        profile_id: profileId,
      })
      const armed = result.outputs.armed === true
      servoArmedRef.current = armed
      setServoArmed(armed)
      setMotionReport(String(
        result.outputs.report
        || (armed ? `Motion armed for ${jointName}` : 'Motion remains disarmed'),
      ))
    } catch (error) {
      servoArmedRef.current = false
      setServoArmed(false)
      setMotionReport(error instanceof Error ? error.message : String(error))
    } finally {
      setArmPending(false)
    }
  }
  const chooseRobot = (nextId: string) => {
    if (servoArmedRef.current) void disarmServo('Motion disarmed because the robot changed')
    void updateParam(id, 'robot_id', nextId)
  }
  const chooseProfile = async (nextProfileId: string) => {
    if (servoArmedRef.current) {
      await disarmServo('Motion disarmed because the profile changed')
    }
    const current = devices.find(item => item.id === robotId)
    await updateParam(id, 'profile_id', nextProfileId)
    try {
      const result = await api.listRobotMonitorTargets(nextProfileId)
      setDevices(result.targets)
      setProfiles(result.profiles || [])
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
        }
      }
    } catch {
      // The stream status remains visible and will retry after target refresh.
    }
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color="#14b8a6"
      nodeType={data.type}
      style={{
        width: '100%',
        height: '100%',
        minWidth: 330,
        minHeight: 350,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={330}
        minHeight={350}
        isVisible={selected}
        lineStyle={{ borderColor: '#14b8a6' }}
        handleStyle={{
          background: '#14b8a6',
          borderColor: '#14b8a6',
          width: 8,
          height: 8,
          borderRadius: 2,
        }}
      />

      <Handle
        type="target"
        position={Position.Left}
        id="robot"
        title="robot · Dict"
        style={{ top: 72, background: '#a855f7', width: 10, height: 10 }}
      />
      <header className="bn-servo-node-title">
        <div>
          <span>SERVO</span>
          <strong>{joint?.semantic_name || joint?.name || `ID ${servoId}`}</strong>
          <small>{robotName}</small>
        </div>
        <div className="bn-servo-id-field nodrag" onMouseDown={event => event.stopPropagation()}>
          <label htmlFor={`servo-id-${id}`}>ID</label>
          <div className="bn-servo-id-control">
            <input
              id={`servo-id-${id}`}
              type="number"
              min={1}
              max={253}
              value={servoId}
              list={`servo-ids-${id}`}
              onChange={event => chooseServo(Number(event.target.value))}
            />
            <div className="bn-servo-id-stepper">
              <button
                type="button"
                aria-label="Increase servo ID"
                title="Increase servo ID"
                disabled={servoId >= 253}
                onClick={() => stepServo(1)}
              >
                ▲
              </button>
              <button
                type="button"
                aria-label="Decrease servo ID"
                title="Decrease servo ID"
                disabled={servoId <= 1}
                onClick={() => stepServo(-1)}
              >
                ▼
              </button>
            </div>
          </div>
          <datalist id={`servo-ids-${id}`}>
            {detectedIds.map(value => <option key={value} value={value} />)}
          </datalist>
        </div>
      </header>

      <div
        className="bn-servo-source-pickers nodrag"
        onMouseDown={event => event.stopPropagation()}
        onClick={event => event.stopPropagation()}
      >
        <label className="bn-servo-robot-picker">
          <span>Profile</span>
          <select
            value={profileId}
            disabled={Boolean(source && !directRobotId)}
            onChange={event => void chooseProfile(event.target.value)}
            aria-label="Profile for local USB servo telemetry"
          >
            <option value="auto">
              {source && !directRobotId ? 'From connected node · Auto' : 'Auto · match hardware'}
            </option>
            <option value="none">None · raw read-only</option>
            {profiles.map(profile => (
              <option key={profile.id} value={profile.id}>
                {profile.name} · {profile.id}
              </option>
            ))}
          </select>
        </label>
        <label className="bn-servo-robot-picker">
          <span>Robot source</span>
          <select
            value={directRobotId}
            onChange={event => chooseRobot(event.target.value)}
            aria-label="Robot for servo telemetry"
          >
            <option value="">
              {source ? `Connected node · ${robotName}` : 'Choose a robot…'}
            </option>
            {devices.some(device => device.kind === 'local_usb') && (
              <optgroup label="Local USB">
                {devices.filter(device => device.kind === 'local_usb').map(device => (
                  <option key={device.id} value={device.id} disabled={!device.available}>
                    {device.name}{device.available ? '' : ' (profile needed)'}
                  </option>
                ))}
              </optgroup>
            )}
            {devices.some(device => device.kind === 'registered') && (
              <optgroup label="Registered robots">
                {devices.filter(device => device.kind === 'registered').map(device => (
                  <option key={device.id} value={device.id}>{device.name}</option>
                ))}
              </optgroup>
            )}
            {directRobotId && !devices.some(device => device.id === directRobotId) && (
              <option value={directRobotId}>{directRobotId} (unavailable)</option>
            )}
          </select>
        </label>
      </div>

      <div className="bn-servo-node-state" style={{ color: stateTone }}>
        <span style={{ background: stateTone }} />
        {state}
      </div>

      {joint ? (
        <>
          <div className="bn-servo-node-reading">
            <div>
              <span>Position</span>
              <strong>{position.toFixed(2)} {unit}</strong>
            </div>
            <div>
              <span>Velocity</span>
              <strong>{velocity.toFixed(2)} {unit}/s</strong>
            </div>
            <div>
              <span>Raw</span>
              <strong>{joint.raw_position ?? '—'}</strong>
            </div>
          </div>

          <div className="bn-servo-node-slider nodrag" onMouseDown={event => event.stopPropagation()}>
            <div>
              <span>
                {rawMode
                  ? 'Target unavailable in raw mode'
                  : servoArmed
                    ? 'Live target'
                    : 'Target preview'}
              </span>
              <div className="bn-servo-node-slider-actions">
                <button
                  type="button"
                  disabled={rawMode}
                  onClick={() => { void updateParam(id, 'follow_feedback', true) }}
                >
                  Use current
                </button>
                <button
                  type="button"
                  className={`bn-servo-motion-arm${servoArmed ? ' is-armed' : ''}`}
                  disabled={rawMode || armPending}
                  onClick={() => { void toggleServoArm() }}
                >
                  {armPending ? 'Working…' : servoArmed ? 'Disarm' : 'Arm'}
                </button>
              </div>
            </div>
            <input
              type="range"
              disabled={rawMode}
              min={lower}
              max={upper}
              step={rawMode ? 1 : units === 'degrees' ? 0.1 : 0.002}
              value={target}
              onChange={event => setTarget(Number(event.target.value))}
            />
            <div>
              <span>{lower.toFixed(2)} {unit}</span>
              <strong>{target.toFixed(2)} {unit}</strong>
              <span>{upper.toFixed(2)} {unit}</span>
            </div>
          </div>

          <div className="bn-servo-node-facts">
            <span>Limits <strong>{rawMode ? 'Unknown · raw' : hasCalibratedLimits ? 'Calibrated' : 'Profile/default'}</strong></span>
            <span>Communication <strong>{joint.communication_ok === false ? 'Failed' : 'Responding'}</strong></span>
            <span>Torque <strong>{sample?.payload?.torque_enabled == null ? 'Unknown' : sample.payload.torque_enabled ? 'On' : 'Off'}</strong></span>
            <span>Temperature <strong>{temperature == null ? 'Not reported' : `${temperature.toFixed(1)} °C`}</strong></span>
            <span>Voltage <strong>{voltage == null ? 'Not reported' : `${voltage.toFixed(2)} V`}</strong></span>
            <span>Status <strong className={hardwareFlags ? 'is-warning' : ''}>{hardwareFlags ? `0x${hardwareFlags.toString(16).padStart(2, '0')}` : '0x00'}</strong></span>
            <span>Faults <strong className={faults.length ? 'is-error' : ''}>{faults.length || 'None'}</strong></span>
            <span>Timeouts <strong className={bus?.timeout_count ? 'is-warning' : ''}>{bus?.timeout_count ?? 'Not reported'}</strong></span>
            <span>Packet errors <strong className={bus?.serial_packet_error_count ? 'is-warning' : ''}>{bus?.serial_packet_error_count ?? 'Not reported'}</strong></span>
          </div>
          {hardwareErrors.length > 0 && (
            <div className="bn-servo-node-warning">
              <strong>Hardware warning</strong>
              <span>
                0x{hardwareFlags.toString(16).padStart(2, '0')} · {hardwareErrors.join(', ')}
              </span>
              <small>{hardwareWarningHint(joint)}</small>
            </div>
          )}
          {faults.length > 0 && (
            <div className="bn-servo-node-fault">
              {faults.map((fault, index) => (
                <span key={`${fault.code || 'fault'}-${index}`}>
                  {fault.code || 'fault'}: {fault.message || 'Device fault reported'}
                </span>
              ))}
            </div>
          )}
          <div className="bn-servo-node-note">
            {rawMode
              ? 'Read-only raw ticks · select a profile before calibration or motion.'
              : servoArmed
                ? <>Live motion armed · dragging this slider moves <strong>{joint?.name || joint?.semantic_name}</strong>.</>
                : 'Preview only · press Arm here to enable live motion.'}
            {motionReport && <small>{motionReport}</small>}
          </div>
        </>
      ) : (
        <div className="bn-servo-node-empty">
          <strong>{robotId ? `Servo ID ${servoId} is not in this robot stream` : 'Connect a Robot or Robot Monitor'}</strong>
          <span>
            {detectedIds.length
              ? `Reported IDs: ${detectedIds.join(', ')}`
              : 'Connect a Robot node or choose a local USB or registered robot above.'}
          </span>
        </div>
      )}

      {[
        ['servo', 82],
        ['joint', 112],
        ['position', 142],
        ['target_position', 172],
        ['command', 202],
      ].map(([port, top]) => (
        <Handle
          key={String(port)}
          type="source"
          position={Position.Right}
          id={String(port)}
          title={String(port)}
          style={{ top: Number(top), background: '#14b8a6', width: 9, height: 9 }}
        />
      ))}
    </NodeFrame>
  )
}
