import { useEffect, useState } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'
import { api, type RobotMonitorTarget } from '../api'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'
import './ActuatorSetupNode.css'

export function setupError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  return message.includes('does not expose direct controls')
    ? 'Restart Blacknode once to activate the new setup controls.' : message
}

export default function ActuatorSetupNode({ id, data, selected }: NodeProps<NodeData>) {
  const updateParam = useStore(s => s.updateParam)
  const controlNode = useStore(s => s.controlNode)
  const [ports, setPorts] = useState<RobotMonitorTarget[]>([])
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState('Pick your USB adapter and press Scan.')
  const port = String(data.params?.serial_port || '')
  const baudrate = Number(data.params?.baudrate || 1000000)
  const refreshPorts = async () => {
    try {
      const result = await api.listRobotMonitorTargets('none')
      setPorts(result.targets.filter(target => target.kind === 'local_usb'))
    } catch (error) { setReport(setupError(error)) }
  }
  useEffect(() => { void refreshPorts() }, [])

  const configure = async (key: string, value: unknown) => {
    setBusy(true)
    try {
      await updateParam(id, key, value)
      if (data.params?.profile_id) await updateParam(id, 'profile_id', '')
      setReport('Press Scan to discover the servos on this adapter.')
    } catch (error) { setReport(setupError(error)) }
    finally { setBusy(false) }
  }
  const scan = async () => {
    setBusy(true)
    setReport('Scanning IDs 0–253. Servo cards will appear when the scan finishes…')
    try {
      if (data.params?.profile_id) await updateParam(id, 'profile_id', '')
      const result = await controlNode(id, 'scan', { confirm_read_only: true })
      setReport(String(result.outputs.report || ''))
      if (result.ok) window.requestAnimationFrame(() => window.dispatchEvent(new Event('blacknode:fit-view')))
    } catch (error) { setReport(setupError(error)) }
    finally { setBusy(false) }
  }
  return <NodeFrame id={id} data={data} selected={selected} color="#14b8a6" style={{
    width: '100%', height: '100%', minWidth: 370, minHeight: 380, display: 'flex', flexDirection: 'column',
  }}>
    <NodeResizer minWidth={370} minHeight={380} isVisible={selected}
      lineStyle={{ borderColor: '#14b8a6' }}
      handleStyle={{ background: '#14b8a6', borderColor: '#14b8a6', width: 10, height: 10, borderRadius: 2 }} />
    <div className="bn-actuator-title"><strong>Actuator Setup</strong><span>USB → Scan → Servo cards</span></div>
    <div className="bn-actuator-setup nodrag nowheel" onMouseDown={event => event.stopPropagation()}>
      <label>USB port<select value={port} disabled={busy} onChange={event => void configure('serial_port', event.target.value)}>
        <option value="">Choose USB adapter…</option>
        {ports.map(target => <option key={target.id} value={target.port}>{target.port} · {target.hardware_id}</option>)}
        {port && !ports.some(target => target.port === port) && <option value={port}>{port} (disconnected)</option>}
      </select></label>
      <button className="bn-actuator-scan" disabled={!port || busy} onClick={() => void scan()}>{busy ? 'Working…' : 'Scan'}</button>
      <div className="bn-actuator-report" role="status">{report}</div>
      <p>Each responding servo appears as a separate node. Scanning reads settings and preserves torque.</p>
      <details><summary>Advanced</summary>
        <label>Baud rate<select value={baudrate} disabled={busy} onChange={event => void configure('baudrate', Number(event.target.value))}>
          {[1000000, 500000, 250000, 128000, 115200, 57600, 38400, 19200, 14400, 9600, 4800].map(rate => <option key={rate}>{rate}</option>)}
        </select></label>
        <button disabled={busy} onClick={() => void refreshPorts()}>Refresh USB ports</button>
        <p>If the port is busy, close other monitors and stop sessions using this adapter.</p>
      </details>
    </div>
    <div className="bn-actuator-resize-hint">Select this node, then drag a corner to resize ↘</div>
    <Handle type="source" position={Position.Right} id="bus" title="Discovered servo bus" style={{ top: 28, background: '#14b8a6' }} />
  </NodeFrame>
}
