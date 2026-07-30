import { useEffect, useMemo, useRef, useState } from 'react'
import { Handle, Position, type NodeProps } from 'reactflow'

import {
  api,
  type HardwareDevice,
  type RobotTelemetryJoint,
  type RobotTelemetrySample,
} from '../api'
import {
  subscribeRobotTelemetry,
  type RobotMonitorConnection,
} from '../robotTelemetryStream'
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

export default function RobotServoNode({ id, data, selected }: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const nodes = useStore(state => state.nodes)
  const edges = useStore(state => state.edges)
  const [devices, setDevices] = useState<HardwareDevice[]>([])
  const [sample, setSample] = useState<RobotTelemetrySample | null>(null)
  const [connection, setConnection] = useState<RobotMonitorConnection>('idle')
  const [derivedVelocity, setDerivedVelocity] = useState(0)
  const previous = useRef<{ position: number; at: number } | null>(null)
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
  const sourceRobotId = source?.data.type === 'RobotMonitor'
    ? String(source.data.params?.robot_id ?? '').trim()
    : String(sourceRobot.robot_id ?? sourceRobot.device_id ?? '').trim()
  const sourceHardwareId = String(
    driver.hardware_id
    ?? (source?.data.portResults?.hardware as Record<string, unknown> | undefined)?.serial
    ?? '',
  ).trim()
  const mappedDevice = sourceHardwareId
    ? devices.find(device => (
      hardwareIdentity(device.remote_device_id).includes(hardwareIdentity(sourceHardwareId))
      || hardwareIdentity(device.id).includes(hardwareIdentity(sourceHardwareId))
    ))
    : undefined
  const robotId = directRobotId || sourceRobotId || mappedDevice?.id || ''
  const robotName = devices.find(device => device.id === robotId)?.name
    || String(source?.data.params?.robot_name ?? '')
    || String(source?.data.params?.profile_id ?? '')
    || 'Robot'

  useEffect(() => {
    let active = true
    void api.listDevices()
      .then(result => { if (active) setDevices(result.devices) })
      .catch(() => undefined)
    return () => { active = false }
  }, [])

  useEffect(() => {
    setSample(null)
    setDerivedVelocity(0)
    previous.current = null
    return subscribeRobotTelemetry(
      robotId,
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
  }, [robotId, servoId])

  const joints = sample?.payload?.joints || []
  const joint = joints.find(item => servoIdOf(item) === servoId)
  const detectedIds = [...new Set(joints.map(servoIdOf).filter((value): value is number => value != null))]
    .sort((a, b) => a - b)
  const sourcePositionUnit = sample?.payload?.position_unit || 'degree'
  const sourceVelocityUnit = sample?.payload?.velocity_unit || 'degree/s'
  const position = joint ? convert(joint.position, sourcePositionUnit, units) : 0
  const velocityValue = sample?.source === 'hardware' ? derivedVelocity : joint?.velocity ?? 0
  const velocity = convert(velocityValue, sourceVelocityUnit, `${units}/s`)
  const lower = joint?.lower_limit == null
    ? units === 'degrees' ? -180 : -Math.PI
    : convert(joint.lower_limit, sourcePositionUnit, units)
  const upper = joint?.upper_limit == null
    ? units === 'degrees' ? 180 : Math.PI
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
  const faults = (sample?.payload?.faults || []).filter(fault => fault.active !== false)
  const state = !robotId
    ? 'CONNECT ROBOT'
    : connection !== 'live'
      ? connection.toUpperCase()
      : sample?.stale
        ? 'STALE'
        : joint
          ? 'LIVE'
          : 'ID NOT REPORTED'
  const stateTone = state === 'LIVE' ? '#22c55e' : state === 'STALE' ? '#f59e0b' : '#ef4444'
  const unit = units === 'degrees' ? '°' : 'rad'

  const chooseServo = (next: number) => {
    void updateParam(id, 'servo_id', next)
    void updateParam(id, 'follow_feedback', true)
  }
  const setTarget = (next: number) => {
    void updateParam(id, 'follow_feedback', false)
    void updateParam(id, 'target_position', next)
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color="#14b8a6"
      nodeType={data.type}
      style={{ width: '100%', minWidth: 330 }}
    >
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
        <label className="nodrag" onMouseDown={event => event.stopPropagation()}>
          <span>ID</span>
          <input
            type="number"
            min={1}
            max={253}
            value={servoId}
            list={`servo-ids-${id}`}
            onChange={event => chooseServo(Number(event.target.value))}
          />
          <datalist id={`servo-ids-${id}`}>
            {detectedIds.map(value => <option key={value} value={value} />)}
          </datalist>
        </label>
      </header>

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
              <span>Target preview</span>
              <button
                type="button"
                onClick={() => { void updateParam(id, 'follow_feedback', true) }}
              >
                Use current
              </button>
            </div>
            <input
              type="range"
              min={lower}
              max={upper}
              step={units === 'degrees' ? 0.1 : 0.002}
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
            <span>Limits <strong>{hasCalibratedLimits ? 'Calibrated' : 'Profile/default'}</strong></span>
            <span>Torque <strong>{sample?.payload?.torque_enabled == null ? 'Unknown' : sample.payload.torque_enabled ? 'On' : 'Off'}</strong></span>
            <span>Temperature <strong>{temperature == null ? 'Not reported' : `${temperature.toFixed(1)} °C`}</strong></span>
            <span>Voltage <strong>{sample?.payload?.voltage_v == null ? 'Not reported' : `${sample.payload.voltage_v.toFixed(2)} V`}</strong></span>
            <span>Faults <strong className={faults.length ? 'is-error' : ''}>{faults.length || 'None'}</strong></span>
          </div>
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
            Preview only · connect <strong>joint</strong> and <strong>target</strong> to a motion node to execute.
          </div>
        </>
      ) : (
        <div className="bn-servo-node-empty">
          <strong>{robotId ? `Servo ID ${servoId} is not in this robot stream` : 'Connect a Robot or Robot Monitor'}</strong>
          <span>
            {detectedIds.length
              ? `Reported IDs: ${detectedIds.join(', ')}`
              : 'Run the Robot node or select a registered Robot Monitor target.'}
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
