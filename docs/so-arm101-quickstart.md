# SO-ARM101 Quickstart

This guide connects an SO-ARM101, verifies live state, performs one bounded
movement, and shuts down the managed runtime safely.

## Requirements

- An assembled, powered SO-ARM101 with its USB serial adapter
- A physical power cutoff within reach
- Blacknode with `blacknode-robot` and `blacknode-ros2` installed
- Package dependencies installed with `blacknode packages setup blacknode-robot`
- A clear workspace and physical support for the arm when torque is disabled

Leave `transport=auto`. Blacknode uses native ROS 2 when `rclpy` is available;
otherwise it prepares the local rosbridge service automatically.

## Connect and Test Motion

1. Start Blacknode and open **Templates**.
2. Plug in and power the SO-ARM101.
3. Open **SO-ARM101 Motion Test** from `blacknode-robot`.
4. Confirm the generic `Robot` dropdown is set to `so_arm101`. Its hardware
   input is connected to USB discovery, so Blacknode selects calibration for
   the connected device when one has been saved.
5. Keep `ROS2SetJoint.armed` set to `false`.
6. Press **Run**.
7. Inspect **Robot Connection Dashboard**. USB, driver, ROS 2, and live state
   should show ready. The joint table shows live positions, home references,
   safe ranges, and whether they came from saved calibration or profile
   defaults. `PROFILE DEFAULTS` means no calibration was found for the displayed
   profile and hardware ID.
8. Clear the workspace. Set `joint` to `shoulder_pan`, choose a small target
   close to the current value, and only then set `armed=true`.
9. Cook the final output once. Confirm the motion dashboard shows the before,
   target, and after values.
10. Press **Stop all**. Confirm the runtime panel reports no robot driver. The
    normal SO-ARM101 shutdown disables actuator torque, so support the arm.

If the arm twitches when the driver starts, stop immediately and investigate.
The bundled Feetech driver reads the current pose and seeds each servo goal
before enabling torque to prevent movement toward a stale target.

## Follow a Colored Cube

Open **Cube Follow — Local Camera** from `blacknode-skills` (follow-person component, ROS 2 adapter).
The workflow is:

```text
USB camera
  → colored-cube tracker
  → latest detection stream
  → continuous shoulder_pan controller
  → motion dashboard + Blacknode run replay
```

The tracker draws target and deadband guides over its live preview. The
controller clamps each correction, respects robot limits, suppresses commands
for missing or stale detections, and starts disarmed.

1. Set the tracker target to one high-contrast color such as `green cube`.
2. Use `shoulder_pan` only.
3. Keep `armed=false` and move the cube through the preview to verify detection.
4. Clear the workspace, set `armed=true`, and cook the persistent follow node
   once.
5. Move the cube slowly left and right. The managed controller continues in the
   background; do not repeatedly cook the graph.
6. Press **Stop all** when finished. This stops the camera, tracker, controller,
   rosbridge processes, and robot driver through their registered shutdown
   paths.

Blacknode run history records graph startup and node results for later replay.

## Expected Results

- USB discovery identifies the serial adapter without a robot-specific
  discovery node.
- Selecting the profile supplies the driver contract without manual commands.
- The driver starts without moving toward a stale goal.
- Live values appear for all configured joints.
- Motion remains blocked while `armed=false`.
- Commands stay within configured limits.
- **Stop all** leaves no managed controller or robot driver active.

## Create a Custom Robot Profile

Open **Editable SO-ARM101 Profile** to use the SO-ARM101 as a starting point.
Rename the profile, change its joint list and provisional properties, then save
it. Use **Robot Guided Calibration** to release torque, record each joint's
intended physical range, capture a home pose, and save a safety-margined
calibration for the connected hardware ID.

The reusable definition lives at `robots/<profile_id>/profile.json`; measured
values live separately at
`robots/<profile_id>/calibrations/<hardware_id>.json`. Two physical assemblies
can therefore share a logical profile without sharing mechanical zeroes or
limits. A new bus protocol still requires a protocol driver, while another arm
using an existing protocol can be described without editing package source.
