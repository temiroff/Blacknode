import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ServoCalibrationControls from './ServoCalibrationControls'

const { control } = vi.hoisted(() => ({ control: vi.fn() }))
vi.mock('../api', () => ({ api: { controlNode: control } }))
vi.mock('./ActuatorSetupNode', () => ({ setupError: (error: unknown) => String(error) }))
afterEach(cleanup)
const saved = { states: { points: { min: 1000, home: 2000, max: 3000 }, poses: { Ready: 2100 } },
  saved: true, test_limits: { min: 1000, home: 2000, max: 3000 } }
beforeEach(() => {
  vi.clearAllMocks()
  control.mockImplementation(async (_id, action) => ({ ok: true, outputs:
    action === 'state-status' ? saved : action === 'read-position' ? { raw_position: 2000, torque_enabled: false }
      : action === 'arm-test' ? { armed: true, target_ticks: 2000 }
      : action === 'test-target' ? { armed: true, target_ticks: 2001, raw_position: 2001 }
        : action === 'stop-test' ? { armed: false } : { ...saved, report: 'Saved successfully' } }))
})
function show() {
  return render(<ServoCalibrationControls id="servo" selection="COM3/1" enabled position={2000} onArmedChange={() => undefined} />)
}

it('loads saved states and reads position without motion before explicit arm', async () => {
  show()
  await screen.findByText('Capture Home · 2000')
  expect(control.mock.calls.map(call => call[1])).toEqual(['state-status', 'read-position'])
  const slider = screen.getByRole('slider', { name: 'Test position' })
  expect(slider).toHaveAttribute('min', '1000')
  expect(slider).toHaveAttribute('max', '3000')
  fireEvent.change(screen.getByLabelText('Saved pose'), { target: { value: 'Ready' } })
  fireEvent.pointerUp(slider)
  expect(control.mock.calls.map(call => call[1])).toEqual(['state-status', 'read-position'])
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Arm' })).toBeEnabled()
})

it('follows hand movement before calibration and stops reading when closed', async () => {
  let ticks = 500
  control.mockImplementation(async (_id, action) => ({ ok: true, outputs: action === 'state-status'
    ? { saved: false, states: { points: {} }, test_limits: {} }
    : { raw_position: ticks, torque_enabled: false, position_range: { min: 0, max: 4095 } } }))
  const view = show()
  await screen.findByText('Measured position · 500 ticks')
  ticks = 3500
  await screen.findByText('Measured position · 3500 ticks')
  expect(screen.getByRole('slider')).toHaveValue('3500')
  expect(control.mock.calls.every(call => ['state-status', 'read-position'].includes(call[1]))).toBe(true)
  view.unmount()
  const count = control.mock.calls.length
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(control).toHaveBeenCalledTimes(count)
})

it('sends a fresh bounded slider command after arm and stops on unmount', async () => {
  const view = show()
  await screen.findByText('Capture Home · 2000')
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  await screen.findByText(/Armed · drag the slider/)
  expect(control).toHaveBeenCalledWith('servo', 'arm-test', { operator_action: 'arm-test', save_calibration: true })
  const slider = screen.getByRole('slider', { name: 'Test position' })
  fireEvent.change(slider, { target: { value: '2001' } })
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'test-target', {
    ticks: 2001, issued_at: expect.any(Number),
  }))
  expect(screen.getByRole('button', { name: 'Capture Min · 1000' })).toBeDisabled()
  view.unmount()
  expect(control).toHaveBeenCalledWith('servo', 'stop-test')
})

it('allows Arm to accept captured endpoints without a separate Save click', async () => {
  control.mockImplementation(async (_id, action) => ({ ok: true, outputs:
    action === 'state-status' ? { ...saved, saved: false, states: { points: { min: 3000, max: 1000 }, dirty: true } }
      : action === 'read-position' ? { raw_position: 2000, torque_enabled: false }
        : { armed: true, saved: true, target_ticks: 2000 } }))
  show()
  await screen.findByText('Capture Min · 3000')
  expect(screen.getByRole('slider')).toHaveStyle({ direction: 'rtl' })
  expect(screen.getByText('Min · 3000')).toBeInTheDocument()
  expect(screen.getByText('Max · 1000')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Arm' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  await screen.findByText(/Armed · drag the slider/)
  expect(control).toHaveBeenCalledWith('servo', 'arm-test', { operator_action: 'arm-test', save_calibration: true })
  expect(control.mock.calls.some(call => call[1] === 'save-states')).toBe(false)
})

it('shows an Arm hardware failure beside the controls', async () => {
  control.mockImplementation(async (_id, action) => action === 'arm-test'
    ? { ok: false, outputs: { ok: false, armed: false, report: 'USB port is busy' } }
    : { ok: true, outputs: action === 'state-status' ? saved : { raw_position: 1000, torque_enabled: false } })
  show()
  await screen.findByText('Measured position · 1000 ticks')
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('USB port is busy')
  expect(screen.getByRole('button', { name: 'Arm' })).toBeEnabled()
})

it('holds on Arm and sends both exact captured endpoints', async () => {
  control.mockImplementation(async (_id, action) => ({ ok: true, outputs: action === 'state-status' ? saved
    : action === 'read-position' ? { raw_position: 1000, torque_enabled: false }
      : { armed: true, raw_position: 1000, target_ticks: 1000 } }))
  show()
  await screen.findByText('Measured position · 1000 ticks')
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  await screen.findByText(/Armed · drag the slider/)
  const slider = screen.getByRole('slider')
  expect(slider).toHaveValue('1000')
  for (const ticks of [3000, 1000]) {
    fireEvent.change(slider, { target: { value: String(ticks) } })
    await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'test-target', { ticks, issued_at: expect.any(Number) }))
    expect(slider).toHaveValue(String(ticks))
  }
})

it('captures calibration or named pose and saves states explicitly', async () => {
  show()
  await screen.findByText('Capture Home · 2000')
  fireEvent.click(screen.getByRole('button', { name: 'Capture Min · 1000' }))
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'capture-state', { point: 'min' }))
  fireEvent.change(screen.getByLabelText('Pose name'), { target: { value: 'Ready' } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Capture pose' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Capture pose' }))
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'capture-state', { point: 'pose', name: 'Ready' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save states' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Save states' }))
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'save-states', {}))
})

it('stops an arm response that arrives after the card was closed', async () => {
  let finish: ((value: unknown) => void) | undefined
  control.mockImplementation(async (_id, action) => action === 'arm-test'
    ? new Promise(resolve => { finish = resolve }) : { ok: true, outputs: saved })
  const view = show()
  await screen.findByText('Capture Home · 2000')
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  view.unmount()
  control.mockClear()
  finish?.({ ok: true, outputs: { armed: true } })
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'stop-test'))
})

it('keeps dragging responsive and sends only the newest waiting target', async () => {
  let finish: ((value: unknown) => void) | undefined
  let commands = 0
  control.mockImplementation(async (_id, action) => {
    if (action === 'state-status') return { ok: true, outputs: saved }
    if (action === 'test-target' && commands++ === 0) return new Promise(resolve => { finish = resolve })
    if (action === 'test-status') return { ok: true, outputs: { armed: true, target_ticks: 2001 } }
    return { ok: true, outputs: { armed: action !== 'stop-test' } }
  })
  show()
  await screen.findByText('Capture Home · 2000')
  fireEvent.click(screen.getByRole('button', { name: 'Arm' }))
  await screen.findByText(/Armed · drag the slider/)
  const slider = screen.getByRole('slider', { name: 'Test position' })
  for (const value of ['2001', '2010', '2020']) fireEvent.change(slider, { target: { value } })
  expect(slider).toBeEnabled()
  expect(control.mock.calls.filter(call => call[1] === 'test-target')).toHaveLength(1)
  await waitFor(() => expect(control).toHaveBeenCalledWith('servo', 'test-status'))
  expect(slider).toHaveValue('2020')
  finish?.({ ok: true, outputs: { armed: true, target_ticks: 2001 } })
  await waitFor(() => expect(control.mock.calls.filter(call => call[1] === 'test-target')).toHaveLength(2))
  expect(control.mock.calls.filter(call => call[1] === 'test-target').map(call => call[2].ticks)).toEqual([2001, 2020])
  expect(slider).toHaveValue('2020')
})
