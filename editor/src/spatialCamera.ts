// Shared orthographic camera basis for every Z-up spatial viewer.
// World coordinates are +X forward, +Y left, +Z up. Upright orbit controls
// keep pitch in the negative polar interval: -90° is a level/front view,
// nearly 0° is overhead, and approaching -180° moves toward the underside.
export function spatialCameraCoordinates(
  x: number,
  y: number,
  z: number,
  yaw: number,
  pitch: number,
): [number, number, number] {
  const yawCosine = Math.cos(yaw)
  const yawSine = Math.sin(yaw)
  const yawX = yawCosine * x - yawSine * y
  const yawY = yawSine * x + yawCosine * y
  const pitchCosine = Math.cos(pitch)
  const pitchSine = Math.sin(pitch)
  const cameraY = pitchCosine * yawY - pitchSine * z
  const cameraDepth = -pitchSine * yawY - pitchCosine * z
  return [yawX, cameraY, cameraDepth]
}
