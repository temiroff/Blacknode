# SO-ARM101 Leader–Follower Control

Use **SO-ARM101 Leader Follower** to move one released leader arm by hand and
stream its calibrated joint coordinates into a separate follower arm.

## Prepare both arms

1. Connect both arms and run each `Robot` with `action=check`.
2. Select or create the logical profile for each arm. Matching arms may use the
   same profile because calibration is stored separately per USB serial.
3. Calibrate each physical arm and successfully save both calibrations.
4. Open **SO-ARM101 Leader Follower**. It selects robot indexes `0` and `1` by
   default. If leader and follower are reversed, swap the two indexes.
5. Select each profile and keep the supplied `/leader` and `/follower` prefixes.

Indexes are the easiest setup and do not require USB filters. For a permanent
or unattended installation, open **Advanced**, promote `hardware_filter`, and
bind each role to its reported adapter serial. This prevents identical robots
from exchanging roles if operating-system discovery order changes.

## Start safely

1. Support the leader arm and clear the follower workspace.
2. Keep `ROS2LeaderFollower.armed=false` and press **Go live**.
3. Confirm leader torque is released and the dashboard shows live leader, safe
   target, and follower values. Moving the leader must not move the follower.
4. Set `armed=true`. The live controller applies this immediately while limits,
   bounded steps, deadband, and stale-message suppression remain active.
5. Set `armed=false` or press **Stop all** before touching the follower.

Matching joint names map automatically. Otherwise set `joint_map` as
`{ "leader_joint": "follower_joint" }`. `scale` and `offset_deg` are keyed by
leader joint; a scale of `-1` mirrors direction.

The initial controller uses rosbridge for persistent dual-arm streams. Both
profiles share the rosbridge host and port but must keep distinct topic prefixes.
