# Robot episode datasets

Blacknode records demonstrations through `blacknode-dataset`, independently
of LeRobot. The native format is optimized for safe acquisition and recovery;
separate export steps create ACT-style HDF5 episodes or the current LeRobot v3
Parquet/MP4 layout.

## Architecture

```text
ROS2LeaderFollower.sample_stream ─┐
                                  ├─> EpisodeRecorder ─> native dataset
Camera.frame_stream ──────────────┘                         │
                                                          ├─> validate
                                                          ├─> HDF5 episode export
                                                          └─> LeRobot v3 export ─> Hugging Face ─> GR00T
```

The robot stream contains the synchronized leader pose, follower observation,
and action that was computed for the follower. All joint vectors use the same
ordered joint names and radians. The camera stream supplies fresh JPEG frames
with capture sequence and nanosecond timestamps. These are generic HTTP handle
contracts, so the recorder has no ROS, camera-library, or LeRobot dependency.

The `Camera` node discovers connected cameras, selects camera `0`, starts its
stream, and displays its live preview. To add a camera, duplicate `Camera` and
its preview, choose selection `1`, `2`, and so on, and drag the new
`frame_stream` to the camera list's dashed **connect to add** socket. The editor
creates `camera_1`, `camera_2`, and further inputs dynamically, so the recorder
does not impose a camera-count limit.

## Safe workflow

Install `blacknode-robot`, `blacknode-ros2`, `blacknode-vision`, and
`blacknode-dataset`, then open **SO-ARM101 Teleoperation Episode Recording**.
The template selects robot indexes `0` and `1`; swap them if the discovered
leader/follower order is reversed. Calibrate both robots before recording. For
a permanent setup, optionally pin each role to its adapter serial in the
Robot's **Advanced** properties. The template starts the follower disarmed and
the recorder with `action=status`.

For each demonstration:

1. Confirm leader/follower and camera dashboards are live.
2. Arm teleoperation, then set the recorder action to `start`.
3. Use `pause` and `resume` if the demonstration is interrupted.
4. Use `save`/`finalize` for a successful episode, or `discard` for a failed one.
5. Run `EpisodeDatasetValidate` before export.

`stop` and Blacknode **Stop All** halt capture but preserve the journal under
`incomplete/<run-id>`. This prevents an application or device failure from
silently deleting the acquisition. Three consecutive stale or unavailable
source reads automatically pause the recorder. After reopening Blacknode, use
the same dataset and run ID with `save`/`finalize` to commit that journal, or
`discard` to remove it.

## LeRobot and Hugging Face

`HDF5EpisodeExport` defaults to the non-mutating `check` action. With
`action=export`, it writes one `episode_<index>.hdf5` per episode with
`observations/qpos`, `observations/leader`, `action`, RGB camera arrays,
ordered joint names, and original robot/camera/wall-clock timing. This is an
ACT-style robotics layout, not a claim that all HDF5-based tools share one
schema. In particular, NVIDIA Isaac Lab-Arena uses its own HDF5 field layout.

`LeRobotV3Export` writes LeRobot v3 metadata, chunked Parquet episodes, and MP4
camera files without installing or importing LeRobot. This clean boundary lets
recording stay stable while downstream formats evolve. Pin and validate the
specific LeRobot release used by your training environment, since its schema
can change after this exporter ships.

`HuggingFaceDatasetUpload` defaults to `check`. Publishing only occurs after
setting `action=upload`; authentication uses the normal Hugging Face login or
`HF_TOKEN`, and credentials are not persisted in the dataset.

For the NVIDIA GR00T path and the exact boundary between current support and
future orchestration nodes, see [NVIDIA Physical AI with Blacknode](nvidia-physical-ai.md).

To train directly from HDF5 without LeRobot, Hugging Face, or GR00T, continue
with [Native robot policy training](robot-policy-training.md).
