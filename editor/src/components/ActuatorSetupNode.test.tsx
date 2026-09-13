import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { NodeProps } from 'reactflow'
import type { NodeData } from '../store'
import ActuatorSetupNode from './ActuatorSetupNode'
import ActuatorServoSetupNode from './ActuatorServoSetupNode'

const { control, update, targets, state } = vi.hoisted(() => ({
  control: vi.fn(), update: vi.fn(), targets: vi.fn(),
  state: { nodes: [{ id: 'setup', data: { params: { serial_port: 'COM3', baudrate: 1000000 } } }],
    edges: [{ source: 'setup', target: 'servo', targetHandle: 'bus' }] },
}))
vi.mock('../api', () => ({ api: { controlNode: control, listRobotMonitorTargets: targets } }))
vi.mock('../store', () => ({ useStore: (selector: (s: unknown) => unknown) => selector({ ...state, controlNode: control, updateParam: update }) }))
vi.mock('reactflow', () => ({ Handle: () => null, Position: { Right: 'right', Left: 'left' } }))
vi.mock('@reactflow/node-resizer', () => ({ NodeResizer: () => null }))
vi.mock('./NodeFrame', () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  state.nodes[0].data.params.serial_port = 'COM3'
  targets.mockResolvedValue({ targets: [{ id: 'usb', kind: 'local_usb', port: 'COM3', hardware_id: 'physical' }], profiles: [] })
  update.mockResolvedValue(undefined)
  control.mockResolvedValue({ ok: true, outputs: { report: 'Found 2 servos on COM3.' } })
})

function showServo(overrides = {}) {
  return render(<ActuatorServoSetupNode {...({ id: 'servo', selected: false, data: {
    params: { servo_id: 1, profile_id: '' }, portResults: {
      actuator: { servo_id: 1, model: 'STS3215', model_number: 777, assignment_supported: true,
        torque_enabled: false, raw_position: 2048, settings: { max_position_ticks: 4095 } },
      present: true, serial_port: 'COM3', baudrate: 1000000, scanned_at: Date.now() / 1000,
      scan_token: 'fresh-token', scan_count: 1, ...overrides,
    },
  } } as unknown as NodeProps<NodeData>)} />)
}

it('requires only a USB port and scans only when pressed', async () => {
  render(<ActuatorSetupNode {...({ id: 'setup', data: { params: { serial_port: 'COM3' } } } as unknown as NodeProps<NodeData>)} />)
  await screen.findByRole('option', { name: 'COM3 · physical' })
  expect(control).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('Robot profile')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Scan' }))
  await screen.findByText('Found 2 servos on COM3.')
  expect(control).toHaveBeenCalledExactlyOnceWith('setup', 'scan', { confirm_read_only: true })
})

it('sets the entered ID in one click with no checkbox or cached scan token', async () => {
  showServo()
  expect(screen.getByText('Servo 1')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '1. Set ID' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByLabelText('New ID')).toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: 'Settings' }))
  expect(screen.getByText('4095')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '1. Set ID' }))
  fireEvent.change(screen.getByLabelText('New ID'), { target: { value: '6' } })
  const assign = screen.getByRole('button', { name: 'Set ID' })
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(assign).toBeEnabled()
  fireEvent.click(assign)
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'assign', {
    new_id: 6, operator_action: 'assign', confirm_read_only: true,
  }))
})

it('uses fresh backend preflight even when an old scan showed several servos', async () => {
  control.mockResolvedValue({ ok: false, outputs: { report: 'Connect exactly one actuator' } })
  showServo({ scan_count: 4 })
  fireEvent.click(screen.getByRole('button', { name: 'Set ID' }))
  await screen.findByText('Connect exactly one actuator')
  expect(control).toHaveBeenCalledWith('servo', 'assign', expect.objectContaining({ operator_action: 'assign' }))
})

it('does not disable Set ID because discovery expired and rejects invalid numbers', () => {
  showServo({ scanned_at: Date.now() / 1000 - 121, scan_token: '' })
  expect(screen.getByRole('button', { name: 'Set ID' })).toBeEnabled()
  fireEvent.change(screen.getByLabelText('New ID'), { target: { value: '254' } })
  expect(screen.getByRole('button', { name: 'Set ID' })).toBeDisabled()
  expect(screen.getByText('Enter an ID from 1 to 253.')).toBeInTheDocument()
})

it('shows an unresolved address and explains a failed fresh assignment check', async () => {
  control.mockResolvedValue({ ok: false, outputs: { report: 'This address is unresolved. Connect one actuator and scan until its ID and model can be read' } })
  showServo({ actuator: { servo_id: 1, discovery_status: 'unreadable', errors: ['Unreadable reply'], assignment_supported: false } })
  expect(screen.getByText('Unresolved ID 1')).toBeInTheDocument()
  expect(screen.getByText(/physical count unknown/)).toBeInTheDocument()
  expect(screen.getByText('Unreadable reply')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Set ID' }))
  await screen.findByText(/This address is unresolved/)
})

it('uses live torque and position in the card after Arm, slider movement and Stop', async () => {
  let ticks = 1500
  let torque = false
  control.mockImplementation(async (_id, action, payload) => {
    if (action === 'state-status') return { ok: true, outputs: { saved: true,
      states: { points: { min: 1000, home: 2000, max: 3000 } }, test_limits: { min: 1020, home: 2000, max: 2980 } } }
    if (action === 'arm-test') torque = true
    if (action === 'stop-test') torque = false
    if (action === 'test-target') ticks = payload.ticks
    return { ok: true, outputs: { raw_position: ticks, torque_enabled: torque,
      ...(action === 'read-position' ? {} : { armed: torque, target_ticks: ticks }) } }
  })
  showServo()
  expect(screen.getByText('Off')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '2. Calibrate / test' }))
  await screen.findByText('1500 ticks')
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  await screen.findByText('On')
  expect(screen.getByText('Torque · live')).toHaveTextContent('On')
  expect(screen.queryByText('Off')).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('slider'), { target: { value: '1600' } })
  await screen.findByText('1600 ticks')
  expect(control).toHaveBeenCalledWith('servo', 'test-target', { ticks: 1600, issued_at: expect.any(Number) })
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
  await screen.findByText('Off')
  expect(screen.getByText('Torque · live')).toHaveTextContent('Off')
})

it('separates ID setup from calibration and explains Arm preflight requirements', async () => {
  showServo()
  expect(screen.queryByRole('button', { name: 'Arm' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '2. Calibrate / test' }))
  expect(screen.getByRole('button', { name: 'Arm' })).toBeEnabled()
  expect(screen.getByRole('note')).toHaveTextContent('Capture Min and Max before testing. Home is optional.')
  expect(screen.queryByLabelText('New ID')).not.toBeInTheDocument()
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'state-status'))
  fireEvent.click(screen.getByRole('tab', { name: '1. Set ID' }))
  expect(screen.getByLabelText('New ID')).toBeVisible()
})
