# Native robot policy training

`blacknode-training` trains a camera-and-joint action-chunking policy directly
from Blacknode HDF5 episodes. It manages dataset checks, background training,
resumable checkpoints, metrics, checkpoint inspection, and recorded-frame
prediction previews.

```text
EpisodeRecorder
      │
      v
native dataset ─> validate ─> HDF5EpisodeExport
                                      │
                                      v
                            TrainingDatasetCheck
                                      │
                                      v
                                ACTTraining
                                      │
                                      v
                         resumable trusted checkpoint
                                      │
                                      v
                            ACTPolicyPreview
                         (recorded frames only)
```

## First experiment

Start with a narrow task and about 20 clean pilot demonstrations. Keep camera
mounts, lighting, task wording, robot calibration, and joint ordering stable.
Vary only the task-relevant initial conditions, such as object position. Save
successful demonstrations and discard failed or interrupted attempts.

1. Validate the native dataset.
2. Export it with `HDF5EpisodeExport`.
3. Open **Blacknode Native ACT Training**.
4. Set the HDF5 directory.
5. Set training to `check` and confirm episode, frame, camera, and joint counts.
6. Use a short baseline: 5,000 steps, batch size 8, chunk size 32, and automatic
   device selection.
7. Change the action to `start`, then immediately return it to `status` for
   monitoring.
8. Inspect the latest checkpoint and preview several held-out frames.

Loss should decrease, but low validation loss alone does not prove the robot
will complete the task. Inspect predicted joint chunks for scale, direction,
smoothness, and joint ordering before considering live inference.

## Lifecycle

`ACTTraining` supports `status`, `check`, `start`, and `stop`. `status` and
`check` are non-mutating. `start` creates the output directory and background
job. `stop` requests cooperative shutdown and writes a checkpoint after the
current step. Set `resume=true` only when the output directory already contains
a compatible checkpoint from the same configuration.

Live policy control is a separate safety-gated workflow. Its controller must
add explicit arming, calibration verification, stale-camera and stale-state
checks, joint and velocity clamps, reduced-speed testing, and an emergency
stop. A prediction preview is an inspection result and does not authorize
robot motion.

The installed package includes a complete node, model, checkpoint, and testing
contract in `packages/blacknode-training/README.md`.
