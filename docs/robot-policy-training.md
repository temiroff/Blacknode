# SO-ARM101 robot learning

Blacknode connects synchronized demonstrations, dataset validation, ACT
training, recorded-frame preview, policy artifacts, and safety-gated execution
into one repeatable robot-learning loop.

```text
SO-ARM101 teleoperation
          │
          v
20 synchronized episodes ─> validate ─> HDF5 export
                                              │
                                              v
                                    Blacknode ACT trainer
                                   train / validate split
                                              │
                              metrics ─> checkpoint ─> resume
                                              │
                                              v
                                  recorded-frame preview
                                              │
                                              v
                                      policy artifact
                                              │
                                              v
 camera streams + robot state ─> PolicyRuntime ─> PolicySafetyGate
                                                     │
                                                     v
                                             SO-ARM101 driver
                                                     │
                           metrics + replay log <────┘
```

The stable boundary is `blacknode.policy-artifact`. Training owns model
architecture and normalization. The runtime owns observation acquisition and
continuous inference. The safety gate owns authorization, source freshness,
joint and velocity limits, optional workspace bounds, emergency stop, and
takeover. The physical driver enforces calibrated joint limits and its command
watchdog again at the hardware boundary.

The current trainer adapter is Blacknode Native ACT. `LeRobotV3Export` provides
the implemented dataset interchange path for LeRobot-compatible datasets. A
trainer that emits the Blacknode policy artifact contract can connect to the
same runtime and safety workflow.

## Milestone: 20 demonstrations to interrupted deployment

Install `blacknode-robot`, `blacknode-ros2`, `blacknode-perception`,
`blacknode-dataset`, and `blacknode-training`. Calibrate the leader and follower
arms, bind each calibration to its physical USB identity, support both arms
whenever torque may be released, and keep a person at the controls.

### 1. Record 20 clean episodes

Open **SO-ARM101 Teleoperation Episode Recording**.

1. Set a narrow task and keep its wording stable.
2. Confirm the leader, follower, and every camera are live.
3. Give every camera a stable `stream_id`, such as `front` or `wrist`.
4. Arm leader-follower teleoperation.
5. Set `EpisodeRecorder.action=start`.
6. Complete one demonstration, then use `save`.
7. Use `discard` for failed, stale, bumped-camera, or interrupted attempts.
8. Repeat until the dataset contains exactly 20 successful episodes.

Vary task-relevant initial conditions, such as object position, while keeping
camera mounts, calibration, joint order, lighting, and task definition stable.
The recorder preserves recoverable journals after interruption and pauses after
three consecutive stale source reads.

### 2. Validate and export

Run `EpisodeDatasetValidate`. Resolve every error involving joint order,
dimensions, finite values, timestamps, camera schema, or frame counts. Set
`HDF5EpisodeExport.action=export` with `include_images=true`.

The HDF5 directory becomes the selected training dataset. Training validation
splits by whole episode, and normalization statistics come only from the
training episodes.

### 3. Train ACT

Open **Blacknode Native ACT Training**. Use its `DatasetBrowser` to choose the
native dataset root and dataset ID, inspect a representative episode/camera,
and run the connected validator. Set `HDF5EpisodeExport.action=export` once,
then return it to `check`; its output path feeds the ACT nodes directly.

1. Use `TrainingDatasetCheck` to confirm 20 episodes, expected cameras, and the
   six ordered SO-ARM101 joints.
2. Start with 5,000 steps, batch size 8, chunk size 32, validation fraction
   0.1, and automatic device selection.
3. Set `ACTTraining.action=check` and inspect the resolved output directory.
4. Set the action to `start`, cook once, then return it to `status` for
   monitoring.
5. Inspect progress, train loss, validation loss, logs, and the latest
   checkpoint on the training dashboard.
6. Use `stop` for cooperative shutdown. Set `resume=true` with the same output
   directory to continue from its newest compatible checkpoint.

Training also appears in the editor managed-runtime status. **Stop All** sends
active training jobs a cooperative stop request so their current step can
finish and checkpoint.

### 4. Preview and export the policy

Use `ACTCheckpointInspect` on the latest trusted local checkpoint. Then use
`ACTPolicyPreview` across several training and validation episodes, including
the start, contact, and completion portions of the task. Inspect action scale,
direction, smoothness, joint order, chunk continuity, and absolute error.

After exporting, load the artifact with `PolicyArtifactLoad` and run
`ACTPolicyReplay` on a selected recorded episode. The node evaluates every
frame, reports episode and per-joint prediction error, and emits the same replay
stream contract used by datasets. The training template connects the Dataset
Browser timeline to this replay, so playing or seeking the recorded video sends
the corresponding predicted action through `StreamPublisher` to Maya, ROS 2,
Isaac Sim, or another evaluation app.

Set `ACTPolicyExport.action=export`. The output contains:

```text
policy-00005000/
  manifest.json
  model.pt
```

The manifest declares ACT as the policy type, absolute joint-position actions
in radians, ordered cameras and joints, dimensions, normalization statistics,
metrics, and the source training step. `model.pt` contains inference weights
and model configuration; optimizer state remains in the training checkpoint.

### 5. Start disarmed deployment preview

Open **SO-ARM101 ACT Policy Deployment**.

1. Set `artifact_path` to the exported policy directory.
2. Keep each camera `stream_id` identical to its HDF5 camera name.
3. Set `follower_robot.action=start` and verify its hardware-bound calibration.
4. Keep `PolicyRuntime.action=status` while checking the graph.
5. Set `PolicyRuntime.action=check` and resolve every contract error.
6. Set `PolicyRuntime.action=start` to begin continuous prediction preview.

Starting the runtime leaves motion disarmed. It loads the model once, subscribes
to follower joint state, fetches fresh frames from the same Blacknode camera
stream contract used during recording, and records inference metrics. No robot
command is published during preview.

### Closed-loop evaluation in Isaac Sim

Open **Isaac Sim ACT Policy Deployment** to run the same artifact against live
simulator observations before physical evaluation. Start `IsaacPolicyBridge`,
then run `clients/isaac_policy_client.py` inside Isaac Sim with the articulation
root and one USD camera prim for every policy camera name. The client sends
measured joint positions, USD limits, and rendered RGB frames to Blacknode.

Set `IsaacPolicyRuntime.action=check`, then `start` for disarmed continuous
inference. Use a separate `arm` action only after inspecting predictions. The
first armed target matches the measured simulated pose; later targets pass
through USD limits, maximum velocity, maximum per-cycle step, workspace, and
freshness checks. The Isaac client clamps against USD limits again before
applying a target. `disarm`, `estop`, `takeover`, `stop`, **Stop All**, stale
observations, and faults suppress future articulation commands.

### 6. Arm, interrupt, and take over

Clear the workspace and lower speed limits for the first physical evaluation.
Keep `require_calibration=true`. Configure optional `workspace_limits` only
with a live `geometry_msgs/PoseStamped` `workspace_topic`; missing workspace
telemetry blocks motion when workspace limits are active.

1. Set `PolicyRuntime.action=arm` and cook once.
2. The runtime asks the driver to hold the current pose.
3. Its first joint command exactly matches the current measured pose.
4. Later predictions pass through calibrated joint bounds, maximum velocity,
   maximum per-cycle step, and freshness checks before publishing.
5. Use `disarm` for a normal motion stop.
6. Use `estop` for a latched emergency stop and torque-release request.
7. Use `takeover` to disarm and release torque for human correction.
8. Use `reset_estop` or `reset_takeover` only after inspecting the cause. Reset
   returns to disarmed preview and never re-arms automatically.

Source staleness, inference faults, runtime stop, **Stop All**, and server
shutdown suppress commands and request torque release. The SO-ARM101 driver
also releases torque when its command watchdog expires. Support the arm because
gravity may move it after torque release.

### 7. Review failures and retrain

Policy execution appends decisions and metrics to
`.blacknode/policy-runs/<run_id>.jsonl`: source age, inference latency, raw
prediction, gated command, clamps, faults, arm/disarm events, e-stop, and
takeover. Camera pixels stay in synchronized dataset episodes.

After takeover, record a clean corrected demonstration with the normal episode
recorder. Validate the expanded dataset, export a new HDF5 directory, train or
resume with an intentional configuration, preview a new checkpoint, export a
new artifact directory, and repeat the disarmed deployment check. Retain old
artifacts and logs so regressions can be traced to a dataset and training step.

## Node ownership

| Layer | Nodes and artifacts |
| --- | --- |
| Dataset | `EpisodeRecorder`, `EpisodeDatasetValidate`, `HDF5EpisodeExport`, `LeRobotV3Export` |
| Training | `TrainingDatasetCheck`, `ACTTraining`, `ACTCheckpointInspect`, `ACTPolicyPreview` |
| Artifact | `ACTPolicyExport`, `PolicyArtifactLoad`, `blacknode.policy-artifact` |
| Deployment | `PolicySafetyGate`, `PolicyRuntime`, `IsaacPolicySafetyGate`, `IsaacPolicyBridge`, `IsaacPolicyRuntime`, SO-ARM101 `Robot` |
| Monitoring | training dashboard, policy metrics, `.blacknode/policy-runs/*.jsonl`, dataset replay |

## Verification boundary

The automated suite uses synthetic HDF5 episodes, a compact ACT model, fake
camera/state sources, and a fake command transport. It verifies artifact
loading, inference dimensions, disarmed preview, current-pose synchronization,
joint/velocity/workspace gates, emergency stop, takeover semantics, shutdown,
and replay logging. Physical SO-ARM101 motion requires deliberate operator-led
hardware validation and is not established by the automated suite. The Isaac
suite exercises a real loopback bridge with synthetic RGB/state observations;
an actual USD stage and GPU renderer still require validation inside Isaac Sim.
