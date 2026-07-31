import type { RobotTelemetryJoint } from './api'

export function hardwareWarningHint(joint: RobotTelemetryJoint): string {
  const errors = joint.hardware_errors || []
  if (errors.includes('voltage')) {
    const measured = joint.voltage_v == null
      ? ''
      : ` at ${joint.voltage_v.toFixed(1)} V`
    return (
      `Input voltage protection is active${measured}. `
      + 'Check that the connected power supply matches this robot and servo '
      + 'voltage rating; follower and leader supplies may differ. Keep torque '
      + 'off until the warning clears.'
    )
  }
  return 'Read-only telemetry remains available. Inspect the hardware warning before enabling motion.'
}
