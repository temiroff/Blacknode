import { useEffect, useState } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'

import {
  api,
  type ComputeDevice,
  type SshRuntimeInspection,
} from '../api'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'


const OUTPUTS = [
  ['configured', '#f59e0b'],
  ['inspection_available', '#f59e0b'],
  ['device', '#a855f7'],
  ['inspection', '#a855f7'],
  ['report', '#38bdf8'],
] as const


export default function ComputeDeviceNode({
  id,
  data,
  selected,
}: NodeProps<NodeData>) {
  const updateParam = useStore(state => state.updateParam)
  const [devices, setDevices] = useState<ComputeDevice[]>([])
  const [error, setError] = useState('')
  const deviceId = String(data.params?.device_id || '').trim()
  const deviceName = String(data.params?.device_name || '').trim()
  const inspection = (
    data.params?.inspection && typeof data.params.inspection === 'object'
      ? data.params.inspection
      : {}
  ) as SshRuntimeInspection
  const selectedDevice = devices.find(device => device.id === deviceId)
  const graph = inspection.ros2_graph
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

  const saveSelection = async (device: ComputeDevice | undefined) => {
    await updateParam(id, 'device_id', device?.id || '')
    await updateParam(id, 'device_name', device?.name || '')
    await updateParam(id, 'inspection', device?.last_inspection || {})
  }

  const chooseDevice = async (nextId: string) => {
    await saveSelection(devices.find(device => device.id === nextId))
  }

  const refreshSnapshot = async () => {
    const current = await loadDevices()
    await saveSelection(current.find(device => device.id === deviceId))
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
        minHeight: 220,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={420}
        minHeight={220}
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

      <header className="bn-compute-device-node-title">
        <div>
          <span>COMPUTE DEVICE</span>
          <strong>{selectedDevice?.name || deviceName || 'Choose a device'}</strong>
        </div>
        <span className={inspection.ok ? 'is-ready' : 'is-idle'}>
          {inspection.ok ? 'INSPECTED' : 'NO SNAPSHOT'}
        </span>
      </header>

      <div className="bn-compute-device-node-body nodrag">
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
          <button type="button" onClick={() => void refreshSnapshot()}>
            Refresh saved snapshot
          </button>
          <small>
            {error
              || (selectedDevice?.inspection_updated_at
                ? `Captured ${new Date(selectedDevice.inspection_updated_at).toLocaleString()}`
                : 'Inspect this target from Devices to capture a snapshot.')}
          </small>
        </div>
      </div>

      {OUTPUTS.map(([port, color], index) => (
        <Handle
          key={port}
          type="source"
          position={Position.Right}
          id={port}
          title={port}
          style={{
            background: color,
            width: 9,
            height: 9,
            top: 48 + index * 27,
          }}
        />
      ))}
    </NodeFrame>
  )
}
