import { useEffect, useState } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'

import {
  api,
  type ComputeDevice,
  type SshRuntimeInspection,
} from '../api'
import { portColor, portVisualColor } from '../portColors'
import { portDisplayName } from '../portLabels'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'
import NodeGlyph from './NodeGlyph'


const OUTPUTS = ['configured', 'inspection_available', 'device', 'inspection', 'report'] as const

const OUTPUT_TYPE_FALLBACKS: Record<(typeof OUTPUTS)[number], string> = {
  configured: 'Bool',
  inspection_available: 'Bool',
  device: 'Dict',
  inspection: 'Dict',
  report: 'Text',
}

function DeviceOutputPort({
  name,
  type,
}: {
  name: (typeof OUTPUTS)[number]
  type: string
}) {
  const color = portColor(type)
  const visualColor = portVisualColor(type)

  return (
    <div
      className="bn-port-row"
      data-direction="output"
      style={{
        position: 'relative',
        display: 'flex',
        minHeight: 27,
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: 5,
        padding: '4px 12px 4px 10px',
        '--bn-port-color': visualColor,
      } as React.CSSProperties}
    >
      <Handle
        type="source"
        position={Position.Right}
        id={name}
        title={`${name}: ${type}`}
        style={{
          right: -5,
          width: 9,
          height: 9,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
          background: color,
        }}
      />
      <span className="bn-compute-device-port-label">
        {portDisplayName(name, 'output')}
      </span>
      <span
        className="bn-port-type-pill"
        title={`${portDisplayName(name, 'output')}: ${type}`}
        style={{
          borderColor: `${visualColor}66`,
          background: `${visualColor}16`,
          color: visualColor,
        }}
      >
        {type.toUpperCase()}
      </span>
    </div>
  )
}


export default function ComputeDeviceNode({
  id,
  data,
  selected,
}: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const [devices, setDevices] = useState<ComputeDevice[]>([])
  const [error, setError] = useState('')
  const [liveInspection, setLiveInspection] = useState<SshRuntimeInspection | null>(null)
  const [checkingLive, setCheckingLive] = useState(false)
  const deviceId = String(data.params?.device_id || '').trim()
  const deviceName = String(data.params?.device_name || '').trim()
  const selectedDevice = devices.find(device => device.id === deviceId)
  const graph = liveInspection?.ros2_graph
  const capabilityCount = graph?.capabilities?.length || 0

  const loadDevices = async () => {
    try {
      const result = await api.listComputeDevices()
      setDevices(result.devices)
      setError('')
      return result.devices
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      return []
    }
  }

  useEffect(() => {
    void loadDevices()
  }, [])

  const refreshLive = async (nextDeviceId = deviceId) => {
    if (!nextDeviceId) {
      setLiveInspection(null)
      setError('')
      return
    }
    setCheckingLive(true)
    try {
      const result = await api.computeDeviceLiveInspection(nextDeviceId)
      setLiveInspection(result)
      setError(result.ok ? '' : result.error || result.ros2_graph?.report || 'Runtime is unavailable')
    } catch (reason) {
      setLiveInspection(null)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setCheckingLive(false)
    }
  }

  useEffect(() => {
    void refreshLive(deviceId)
  }, [deviceId])

  const saveSelection = async (device: ComputeDevice | undefined) => {
    await updateParam(id, 'device_id', device?.id || '')
    await updateParam(id, 'device_name', device?.name || '')
    // Keep credentials and captured machine state out of saved workflows.
    // The editor injects current state immediately before every cook.
    await updateParam(id, 'inspection', {})
  }

  const chooseDevice = async (nextId: string) => {
    await saveSelection(devices.find(device => device.id === nextId))
  }

  const refreshDevice = async () => {
    const current = await loadDevices()
    const selected = current.find(device => device.id === deviceId)
    if (!selected) {
      setLiveInspection(null)
      return
    }
    await refreshLive(selected.id)
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
        minWidth: 420,
        minHeight: 460,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={420}
        minHeight={460}
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

      <header
        className="bn-node-header bn-compute-device-node-title"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 6,
          padding: '6px 10px',
          borderRadius: '8px 8px 0 0',
          background: '#14b8a6',
        }}
      >
        <NodeGlyph type={data.type} className="bn-node-header-glyph" />
        <div className="bn-compute-device-node-identity">
          <strong className="bn-node-title">
            {selectedDevice?.name || deviceName || 'Choose a device'}
          </strong>
          <span className="bn-node-type">Compute Device</span>
        </div>
        <div
          className="bn-node-runtime-state"
          data-tone={liveInspection?.live ? 'ready' : 'idle'}
          title={liveInspection?.live ? 'Current state returned by the paired Runtime' : 'Paired Runtime is not live'}
        >
          <i />
          <span>{checkingLive ? 'Checking' : liveInspection?.live ? 'Live' : 'Offline'}</span>
        </div>
      </header>

      <div className="bn-node-parameter-area bn-compute-device-node-body nodrag">
        <label>
          <span>Registered device</span>
          <select
            value={deviceId}
            onChange={event => void chooseDevice(event.target.value)}
            aria-label="Compute device"
          >
            <option value="">Choose a device…</option>
            {devices.map(device => (
              <option key={device.id} value={device.id}>
                {device.name}{device.inspection_only ? ' · inspection only' : ''}
              </option>
            ))}
            {deviceId && !selectedDevice && (
              <option value={deviceId}>{deviceName || deviceId} · unavailable</option>
            )}
          </select>
        </label>

        <div className="bn-compute-device-node-facts">
          <span>
            ROS 2 <strong>{graph?.available ? graph.distribution || 'available' : 'unavailable'}</strong>
          </span>
          <span>
            Topics <strong>{graph?.inventory?.topics?.length || graph?.topics?.length || 0}</strong>
          </span>
          <span>
            Capabilities <strong>{capabilityCount}</strong>
          </span>
          <span>
            Access <strong>read only</strong>
          </span>
        </div>

        <div className="bn-compute-device-node-actions">
          <button type="button" disabled={checkingLive} onClick={() => void refreshDevice()}>
            {checkingLive ? 'Checking Runtime…' : 'Refresh live device'}
          </button>
          <small>
            {error
              || (liveInspection?.checked_at
                ? `Live ROS state checked ${new Date(liveInspection.checked_at).toLocaleTimeString()}`
                : 'Run once reads current state from the paired Runtime; no SSH password is needed.')}
          </small>
        </div>
      </div>

      <div className="bn-node-ports bn-compute-device-node-ports">
        <div className="bn-port-section-label is-output">Outputs</div>
        {OUTPUTS.map(port => (
          <DeviceOutputPort
            key={port}
            name={port}
            type={data.output_types?.[port] || OUTPUT_TYPE_FALLBACKS[port]}
          />
        ))}
      </div>
    </NodeFrame>
  )
}
