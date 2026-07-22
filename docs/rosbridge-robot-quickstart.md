# Rosbridge Robot Quickstart

This guide connects Blacknode to any ROS 2 robot whose bringup runs
`rosbridge_server`, verifies the link by reading a live topic, then performs
one safety-gated 0.1 m/s drive test on a mobile base. Nothing is installed on
the robot: Blacknode talks to the rosbridge WebSocket (port 9090 by default)
over the network, so this works from Windows, macOS, or Linux without a local
ROS installation.

## Requirements

- A powered robot with `rosbridge_server` running (many educational and
  commercial ROS 2 robots start it on boot; otherwise launch
  `rosbridge_server rosbridge_websocket_launch.xml` on the robot)
- Blacknode and the robot on the same network, and the robot's IP address
- `blacknode-ros2` installed, with prerequisites (`roslibpy`) installed via
  the Packages tab or `blacknode packages setup blacknode-ros2`
- For the drive test: a physical power switch within reach, and either 1 m of
  clear floor space or a stand that lets the wheels spin freely

You also need three topic names from your robot's documentation (or from
`ros2 topic list` on the robot): the velocity command topic (a
`geometry_msgs/msg/Twist` subscriber, conventionally `/cmd_vel`), the LiDAR
topic (`/scan`), and the odometry topic (`/odom`). The templates default to
those conventions; change the params if your robot remaps them.

## Connection Test

1. Open **Templates** and open **Connect to a Robot Over WiFi** from
   `blacknode-ros2`.
2. Replace `ROBOT_IP` with the robot's IP on all three nodes.
3. Optionally change the echo node's topic — `/joint_states` is a safe
   default on most robots; a battery or IMU topic works just as well.
4. Press **Run**.

Expected results: the rosbridge status node reports the WebSocket is
reachable, and the echo node returns one live message as JSON. The publish
node sends a harmless `std_msgs/msg/String` by default; point it at a buzzer
or LED topic on your robot (with the matching message type and a JSON
payload) to get a physical acknowledgment. Robot-specific message types work
as long as the robot itself knows them — the bridge does the translation.

If the robot runs `web_video_server`, its camera streams are listed at
`http://ROBOT_IP:8080` in a browser.

## Base Motion Test

The drive chain is deliberately strict:

```text
ROS2LaserScanCheck  →  clearance_m
                          │
BaseSafetyGate (armed?) → authorization (speed/turn/duration caps, 30 s freshness)
                          │
ROS2BaseMove            → clamped velocity stream on the cmd_vel topic, then zero
                          │
ROS2BaseStop            → explicit final stop
                          │
ROS2OdomState           → pose readback
```

`ROS2BaseMove` refuses to run without a fresh authorization, clamps every
command to the gate's caps and to hard module limits (0.5 m/s, 1.5 rad/s,
5 s per move), and always streams zero-velocity stop frames — even if the
connection drops mid-move.

1. Place the robot on the floor with at least 1 m of clear space ahead, or on
   a stand with the wheels free.
2. Open **Rosbridge Base Motion Test** from `blacknode-ros2`, replace
   `ROBOT_IP` on every node, and set the cmd_vel, scan, and odom topics to
   your robot's names.
3. Press **Run** once with the gate as shipped. The move must report
   `base move BLOCKED: ... gate is disarmed`. This proves the safety chain is
   wired before anything can drive.
4. Check the LiDAR node's report: it shows the closest obstacle within a
   ±30° forward sector and must say `CLEAR`.
5. Set `armed=true` on the **BaseSafetyGate** node and run again.

Expected results: the robot drives forward about 10 cm over one second and
stops. The odometry report shows the pose after the move.

To stop the base at any time, run the **ROS2BaseStop** node — it needs no
authorization and simply streams zero velocity.

## Notes and Troubleshooting

- **ws://ROBOT_IP:9090 refused** — rosbridge is not running or the IP is
  wrong. Start it on the robot, or check your robot vendor's bringup.
- **No scan message** — the LiDAR is not publishing, or the topic name
  differs; check the scan node's topic param.
- **Robot fights or ignores commands** — another node (a vendor app, a
  joystick teleop, a navigation stack) may be publishing to the same
  velocity topic. Drive from one source at a time.
- **The base keeps moving after a command** — most chassis controllers stop
  when commands cease, and the move node always ends with zero-velocity
  frames. If your robot latches the last velocity instead, keep
  **ROS2BaseStop** wired and reachable, and prefer a stand for early tests.
