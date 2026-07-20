# Robot episode datasets

`blacknode-dataset` records synchronized robot demonstrations as recoverable
Blacknode episodes. A recording can include follower observations, leader
positions, commanded actions, and any number of camera streams.

## Architecture

```text
ROS2LeaderFollower.sample_stream ─┐
                                  ├─> EpisodeRecorder ─> native dataset
Camera.frame_stream ──────────────┘                         │
                                                          ├─> validate
                                                          ├─> HDF5 export
                                                          ├─> Parquet/MP4 export
                                                          └─> repository upload
```

The robot sample stream carries synchronized leader pose, follower observation,
and the action computed for the follower. Joint vectors use stable ordered
joint names and radians. Each camera stream carries fresh JPEG frames, capture
sequence numbers, and nanosecond timestamps.

Both are Blacknode latest-value HTTP stream handles. This keeps acquisition
nodes reusable across robot drivers, camera implementations, exporters, and
training workflows.

## Add cameras

The `Camera` node discovers connected cameras, selects one by index, starts its
stream, and displays a live preview. Use `selection=0` for the first camera.
Duplicate the node and choose `1`, `2`, and so on for additional cameras.

Connect every `frame_stream` to the camera list's dashed **connect to add**
socket. The list grows dynamically as connections are added, so an episode can
record any practical number of cameras. Assign a unique camera name to each
input and keep those names stable across the dataset.

## Record an episode

Install `blacknode-robot`, `blacknode-ros2`, `blacknode-perception`, and
`blacknode-dataset`, then open **SO-ARM101 Teleoperation Episode Recording**.
The template selects robot indexes `0` and `1`; swap them if the discovered
leader and follower order is reversed. Calibrate both robots before recording.
For a permanent setup, pin each role to its adapter serial in the Robot node's
**Advanced** properties.

The template starts with the follower disarmed and the recorder set to
`action=status`.

1. Confirm the leader, follower, and camera dashboards are live.
2. Arm teleoperation.
3. Set `EpisodeRecorder.action=start`.
4. Use `pause` and `resume` when needed.
5. Use `save` or `finalize` for a successful episode.
6. Use `discard` for a failed demonstration.
7. Run `EpisodeDatasetValidate` before export or training.

`stop` and Blacknode **Stop All** halt capture while preserving the journal
under `incomplete/<run-id>`. Three consecutive stale or unavailable source
reads pause the recorder automatically. Reopen the same dataset and run ID to
`save`/`finalize` the journal or `discard` it.

## Native dataset

The native layout separates durable metadata, synchronized numeric samples,
camera frames, and incomplete journals:

```text
<dataset>/
  dataset.json
  episodes/
    episode_000000/
      episode.json
      samples.parquet
      cameras/
        front/
        wrist/
  incomplete/
    <run-id>/
```

Episode metadata records the task, robot identity, joint schema, units, camera
schema, FPS, source timestamps, sample counts, and completion state. Writes use
temporary files and atomic replacement so a completed episode is never exposed
half-written.

## Validation

`EpisodeDatasetValidate` checks:

- stable state and action dimensions
- stable joint order and units
- finite numeric values
- camera names, resolutions, and frame counts
- timestamp monotonicity and stream freshness
- matching sample counts across episode artifacts

Resolve validation errors before export or training. The validator reports
specific episode and field locations so damaged or inconsistent demonstrations
can be isolated.

## Export and publish

`HDF5EpisodeExport` defaults to the non-mutating `check` action. With
`action=export`, it writes one `episode_<index>.hdf5` per episode containing:

```text
/observations/qpos
/observations/leader
/observations/images/<camera>
/action
/metadata/joint_names
/metadata/source_timestamps
```

`LeRobotV3Export` is the structured Parquet/MP4 export profile. It writes
chunked tabular episode data, encoded camera video, and dataset metadata for
tools that consume that schema. Pin the schema version used by the target
environment and validate the exported directory before publishing it.

`HuggingFaceDatasetUpload` publishes an already-exported directory only when
its action is set to `upload`. Authentication comes from the configured
repository login or token environment. Credentials are never stored in the
workflow or dataset.

For Blacknode policy training, export HDF5 episodes and continue with
[Native robot policy training](robot-policy-training.md).

## Nodes

| Node | Purpose |
| --- | --- |
| `EpisodeDatasetCreate` | Create or inspect native dataset metadata. |
| `EpisodeRecorder` | Start, pause, resume, save, discard, and recover synchronized recordings. |
| `EpisodeDatasetValidate` | Validate native dataset structure and episode consistency. |
| `HDF5EpisodeExport` | Check or export one HDF5 file per episode. |
| `LeRobotV3Export` | Check or create the structured Parquet/MP4 export profile. |
| `HuggingFaceDatasetUpload` | Explicitly publish an exported directory to a dataset repository. |

## Operational rules

- Recording only consumes streams and never commands motion.
- Every robot and camera role uses a unique selection index in shipped
  templates.
- Camera names and joint order remain stable across all episodes.
- Interrupted recordings remain recoverable until explicitly saved or
  discarded.
- Upload is always a separate explicit action after local validation.
