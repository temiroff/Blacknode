import { useEffect, useState } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'
import { api, type DeviceRobotProfile } from '../api'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'
import { setupError } from './ActuatorSetupNode'
import ServoCalibrationControls, { type ServoFeedback } from './ServoCalibrationControls'
import './ActuatorSetupNode.css'

type Actuator = {
  discovery_status?: string
  servo_id?: number; model?: string; model_number?: number; assignment_supported?: boolean
  torque_enabled?: boolean; raw_position?: number; voltage_v?: number; temperature_c?: number
  hardware_error_flags?: number; hardware_errors?: string[]; errors?: string[]
  settings?: Record<string, number>; settings_errors?: string[]
}
const SETTING_LABELS: Record<string, string> = {
  baud_rate_code: 'Baud rate code', min_position_ticks: 'Min position (ticks)',
  max_position_ticks: 'Max position (ticks)', max_torque: 'Max torque (raw)',
  operating_mode: 'Operating mode', eeprom_locked: 'EEPROM lock',
}

export default function ActuatorServoSetupNode({ id, data, selected }: NodeProps<NodeData>) {
  const controlNode = useStore(s => s.controlNode)
  const updateParam = useStore(s => s.updateParam)
  const nodes = useStore(s => s.nodes)
  const edges = useStore(s => s.edges)
  const parentId = edges.find(edge => edge.target === id && edge.targetHandle === 'bus')?.source
  const parent = nodes.find(node => node.id === parentId)
  const results = data.portResults || {}
  const row = (results.actuator || {}) as Actuator
  const unresolved = row.discovery_status === 'unreadable'
  const servoId = Number(data.params?.servo_id ?? 1)
  const profileId = String(data.params?.profile_id || '')
  const scannedAt = Number(results.scanned_at || 0)
  const present = results.present === true && results.serial_port === parent?.data.params?.serial_port
    && results.baudrate === Number(parent?.data.params?.baudrate || 1000000)
  const [newId, setNewId] = useState(servoId)
  const [busy, setBusy] = useState(false)
  const [testArmed, setTestArmed] = useState(false)
  const [feedback, setFeedback] = useState<ServoFeedback | null>(null)
  const [report, setReport] = useState('')
  const [profiles, setProfiles] = useState<DeviceRobotProfile[]>([])
  const [panel, setPanel] = useState<'id' | 'calibration' | 'settings'>('id')
  useEffect(() => { setNewId(servoId) }, [servoId])
  useEffect(() => { setFeedback(null) }, [servoId, scannedAt])
  const measuredPosition = feedback ? (feedback.live ? feedback.raw_position : undefined) : row.raw_position
  const measuredTorque = feedback ? (feedback.live ? feedback.torque_enabled : undefined) : row.torque_enabled
  const feedbackSource = feedback?.live ? 'live' : feedback ? 'waiting' : 'scan'
  const canWrite = Boolean(parentId && parent?.data.params?.serial_port) && !busy && !testArmed
  const canAssign = canWrite && Number.isInteger(newId) && newId >= 1 && newId <= 253
  const idBlocked = testArmed ? 'Stop the motion test before changing the ID.'
    : !parentId || !parent?.data.params?.serial_port ? 'Select the USB port on the scanner.'
      : !Number.isInteger(newId) || newId < 1 || newId > 253 ? 'Enter an ID from 1 to 253.' : ''

  const act = async (action: string) => {
    setBusy(true)
    if (action === 'assign') setReport('Checking the connected actuator and setting its ID…')
    try {
      const result = await controlNode(id, action, {
        confirm_read_only: true, operator_action: action, new_id: newId,
      })
      setReport(String(result.outputs.report || ''))
    } catch (error) { setReport(setupError(error)) }
    finally { setBusy(false) }
  }
  return <NodeFrame id={id} data={data} selected={selected} color="#14b8a6" style={{
    width: '100%', height: '100%', minWidth: 370, minHeight: 420, display: 'flex', flexDirection: 'column',
  }}>
    <NodeResizer minWidth={370} minHeight={420} isVisible={selected}
      lineStyle={{ borderColor: '#14b8a6' }}
      handleStyle={{ background: '#14b8a6', borderColor: '#14b8a6', width: 10, height: 10, borderRadius: 2 }} />
    <div className="bn-actuator-title"><strong>{unresolved ? 'Unresolved ID' : 'Servo'} {servoId}</strong>
      <span>{present ? `${unresolved ? 'Unreadable reply · physical count unknown' : row.model || 'Unknown model'} · ${results.serial_port}` : 'Not detected · scan the USB bus'}</span></div>
    <div className="bn-actuator-setup bn-actuator-servo-panel nodrag nowheel" onMouseDown={event => event.stopPropagation()}>
      <div className="bn-actuator-facts">
        <span>Position · {feedbackSource}<strong>{present ? measuredPosition ?? 'Unknown' : '—'} ticks</strong></span>
        <span>Torque · {feedbackSource}<strong>{!present || measuredTorque == null ? 'Unknown' : measuredTorque ? 'On' : 'Off'}</strong></span>
        <span>Voltage<strong>{present ? row.voltage_v ?? '—' : '—'} V</strong></span>
        <span>Temperature<strong>{present ? row.temperature_c ?? '—' : '—'} °C</strong></span>
      </div>
      {present && Boolean(row.hardware_error_flags || row.errors?.length) && <div className="bn-actuator-report">
        {[...(row.hardware_errors || []), ...(row.errors || [])].join('; ') || `Hardware status ${row.hardware_error_flags}`}
      </div>}
      <div className="bn-actuator-tabs" role="tablist" aria-label="Servo setup steps">
        <button role="tab" aria-selected={panel === 'id'} onClick={() => setPanel('id')}>1. Set ID</button>
        <button role="tab" aria-selected={panel === 'calibration'} onClick={() => setPanel('calibration')}>2. Calibrate / test</button>
        <button role="tab" aria-selected={panel === 'settings'} onClick={() => setPanel('settings')}>Settings</button>
      </div>
      {panel === 'calibration' && <ServoCalibrationControls id={id} enabled={present && !unresolved && row.assignment_supported === true}
        selection={`${parent?.data.params?.serial_port}/${parent?.data.params?.baudrate}/${servoId}/${scannedAt}`}
        position={row.raw_position} onArmedChange={setTestArmed} onFeedback={setFeedback} />}
      {panel === 'id' && <fieldset disabled={busy || testArmed}>
        <legend>Servo ID</legend>
        <label>New ID<input type="number" min={1} max={253} value={Number.isNaN(newId) ? '' : newId}
          onChange={event => setNewId(event.target.valueAsNumber)} /></label>
        <p>Keep only this actuator connected and supported. Changing its ID resets saved calibration for this assembly.</p>
        <button disabled={!canAssign} title={idBlocked || undefined} onClick={() => void act('assign')}>{busy ? 'Working…' : 'Set ID'}</button>
        <small>The button scans, checks torque is off, writes the ID and verifies it.</small>
        {present && row.torque_enabled !== false && <button disabled={!canWrite} onClick={() => void act('release')}>Release torque</button>}
        {idBlocked && <small>{idBlocked}</small>}
      </fieldset>}
      {panel === 'settings' && <><details open><summary>Hardware settings · read only</summary>
        {present ? <><small>Model number: {row.model_number ?? 'Unknown'}</small>
          <dl>{Object.entries(row.settings || {}).map(([key, value]) => <div key={key}><dt>{SETTING_LABELS[key] || key}</dt><dd>{value}</dd></div>)}</dl>
          {(row.settings_errors || []).map((error, index) => <small key={index}>{error}</small>)}
          <small>Register limits are not a calibrated safe motion range.</small>
        </> : <p>Scan the bus to read this servo’s settings.</p>}
      </details>
      <details onToggle={event => {
        if (event.currentTarget.open && !profiles.length) void api.listRobotMonitorTargets('none')
          .then(result => setProfiles(result.profiles || [])).catch(error => setReport(setupError(error)))
      }}><summary>Whole-robot calibration</summary>
        <p>Reconnect the complete robot. Select its profile to record calibration and test within safe limits.</p>
        <label>Robot profile<select value={profileId} disabled={busy} onChange={event => {
          void updateParam(id, 'profile_id', event.target.value).catch(error => setReport(setupError(error)))
        }}><option value="">Choose a profile…</option>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name} · {profile.id}</option>)}</select></label>
        <div className="bn-actuator-actions"><button disabled={busy || !profileId} onClick={() => void act('calibrate')}>Calibrate</button>
          <button disabled={busy || !profileId} onClick={() => void act('monitor')}>Open motion test</button></div>
      </details></>}
      <button disabled={busy || testArmed || !parentId} onClick={() => void act('scan')}>{busy ? 'Working…' : 'Rescan USB bus'}</button>
      {Boolean(report || results.report) && <div className="bn-actuator-report" role="status">{report || (unresolved ? 'Unresolved address. Other discovered servos remain available.' : String(results.report))}</div>}
      {present && <small>Last scan: {new Date(scannedAt * 1000).toLocaleTimeString()} · snapshot</small>}
    </div>
    <div className="bn-actuator-resize-hint">Select this node, then drag a corner to resize ↘</div>
    <Handle type="target" position={Position.Left} id="bus" title="USB scanner" style={{ top: 28, background: '#14b8a6' }} />
    <Handle type="source" position={Position.Right} id="report" title="report" style={{ top: 28, background: '#14b8a6' }} />
  </NodeFrame>
}
