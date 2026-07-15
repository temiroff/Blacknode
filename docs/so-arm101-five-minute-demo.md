# Connect and Control an SO-ARM101 in Five Minutes

This is Blacknode's primary robotics demo:

> Connect a robot and control it visually in five minutes.

It proves generic hardware discovery, additive robot presets, visual component
composition, live state, bounded motion, and safe lifecycle management on a
real arm.

## What You Need

- An assembled, powered SO-ARM101 with its USB serial adapter
- A physical power cutoff within reach
- Blacknode with `blacknode-robot` and `blacknode-ros2` installed
- The package dependencies installed with `blacknode packages setup blacknode-robot`
- A clear workspace and physical support for the arm when torque is disabled

Leave `transport=auto`. Blacknode uses native ROS 2 when `rclpy` is available;
otherwise it prepares the local rosbridge service automatically.

## Demo 1: Plug and Control

1. Start Blacknode and open **Templates**.
2. Plug in and power the SO-ARM101.
3. Open **SO-ARM101 Motion Test** from `blacknode-robot`.
4. Confirm `RobotDriverPreset.preset` is `so_arm101`.
5. Keep `ROS2SetJoint.armed` set to `false`.
6. Press **Run**.
7. Inspect **Robot Connection Dashboard**. USB, driver, ROS 2, and live state
   should all show ready, and the panel should list live joint positions.
8. Clear the workspace. Set `joint` to `shoulder_pan`, choose a small target
   close to the current value, and only then set `armed=true`.
9. Cook the final output once. Confirm the motion dashboard shows the before,
   target, and after values.
10. Press **Stop all**. Confirm the runtime panel reports no robot driver and
    remember that the normal SO-ARM101 shutdown disables actuator torque.

If the arm twitches when the driver starts, stop immediately and investigate.
The bundled Feetech driver reads the current pose and seeds each servo goal
before torque enable specifically to prevent startup snapping.

## Demo 2: Follow a Colored Cube

Use **Blacknode Vision CV2 Cube Continuous Follow** from `blacknode-vision` for
the persistent controller path. The graph is:

```text
USB camera
  → colored-cube tracker
  → latest detection stream
  → continuous shoulder_pan controller
  → motion dashboard + Blacknode run replay
```

The tracker draws target and deadband guides over its live preview. The
controller clamps each correction, respects robot limits, suppresses commands
for missing or stale detections, and is disarmed by default.

For the most reproducible first behavior:

- Set the tracker target to one high-contrast color such as `green cube`.
- Use `shoulder_pan` only.
- Start with `armed=false` and move the cube through the preview to verify the
  detection center and follow guides.
- Clear the workspace, then set `armed=true` and cook the persistent follow
  node once.
- Move the cube slowly left and right. Do not repeatedly cook the graph; the
  managed controller continues in the background.
- Press **Stop all** at the end. This stops the camera/tracker, continuous
  controller, rosbridge processes, and robot driver through their registered
  shutdown paths.

Blacknode's run history records the graph startup and node results for replay.
For the public demo asset, screen-record the editor so the live camera overlay,
dashboard, and Stop-all state are captured together.

## 60–90 Second Recording Shot List

| Time | Shot | Proof |
|---|---|---|
| 0–8s | Unplugged arm and open template | Real starting state |
| 8–18s | Plug in USB; cook discovery | Generic serial discovery |
| 18–28s | Show `so_arm101` preset; press Run | Additive robot support and driver launch |
| 28–42s | Open connection dashboard | USB, driver, ROS 2, and live joint positions |
| 42–58s | Arm one small `shoulder_pan` move | Explicit safety gate and real motion |
| 58–70s | Show before/target/after dashboard | Observable result |
| 70–82s | Press Stop all; show inactive runtime | Safe shutdown and lifecycle ownership |

Record the cube-follow behavior as a second short clip. Keeping the connection
demo and behavior demo separate makes failures easier to diagnose and the core
claim easier to understand.

## Pass Criteria

- The serial device is discovered without a robot-specific discovery node.
- Selecting the preset supplies the driver contract without manual commands.
- The driver starts without startup movement.
- Live values appear for all six joints.
- Motion cannot occur while `armed=false`.
- One small shoulder movement stays within configured limits.
- **Stop all** leaves no managed controller or robot driver active.

Do not advance to remote deployment until this path is repeatable from a clean
checkout and can be recorded without manual recovery steps.

## Turn the Preset into Your Robot

After the five-minute demo works, open **Editable SO-ARM101 Profile**. It shows
the SO-ARM101 as ordinary visual joint definitions rather than an opaque preset.
Rename the profile, change the joint list and provisional properties, then save
it. Use **Robot Guided Calibration** to release torque, record each joint's
intended physical range, capture a home pose, and save a safety-margined
calibration for that connected hardware ID.

The reusable definition lives at `robots/<profile_id>/profile.json`; measured
values live separately at
`robots/<profile_id>/calibrations/<hardware_id>.json`. This lets two assemblies
share a logical robot profile without incorrectly sharing mechanical zeroes or
limits. A new bus protocol still needs a protocol driver, but another arm using
an existing protocol can be described without editing package source.
