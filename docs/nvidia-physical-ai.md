# NVIDIA Physical AI with Blacknode

Blacknode can provide the visible orchestration layer around NVIDIA's Physical
AI stack while leaving Isaac Lab-Arena, Isaac Teleop, Isaac ROS, GR00T, and
LEAPP responsible for the specialized work they already do well.

The shortest useful integration today is:

```text
Robot + cameras
      │
      v
Blacknode teleoperation + EpisodeRecorder
      │
      ├─> recoverable native Parquet/MP4 dataset
      ├─> ACT-style HDF5 episodes (general interchange)
      └─> LeRobot v3 export ─> Hugging Face/local storage
                                  │
                                  v
                       GR00T modality validation
                                  │
                                  v
                      GR00T fine-tune/checkpoint
                                  │
                                  v
                         LEAPP export (x86_64)
                                  │
                                  v
                       Isaac ROS deploy on Jetson
```

## What the NVIDIA workflow establishes

NVIDIA's current Unitree G1 reference workflow has two independent acquisition
paths. Simulation records Isaac Lab-Arena HDF5 and converts it to LeRobot. The
real robot records ROS 2/MCAP through Isaac Teleop and converts it to LeRobot.
Both paths train GR00T 1.7 from LeRobot data. Simulation evaluation uses a
GR00T policy server with Isaac Lab-Arena; real deployment converts the trained
checkpoint to a LEAPP bundle and runs it through Isaac ROS on Jetson AGX Thor.

That makes LeRobot—not raw HDF5 or MCAP—the stable handoff point Blacknode
should target first.

## Current Blacknode coverage

| NVIDIA phase | Blacknode capability now | Boundary |
| --- | --- | --- |
| Hardware and ROS readiness | Package health, `ROS2Status`, `Robot`, `Camera`, and live dashboards | Platform-specific JetPack, Isaac ROS, networking, and safety setup remain NVIDIA procedures. |
| Teleoperation | Typed leader/follower robot and multi-camera streams | Current template targets SO-ARM101, not Unitree G1 whole-body control or XR retargeting. |
| Recording | Fixed-rate synchronized episodes with crash recovery, pause/save/discard, source timestamps, actions, observations, and any number of cameras | This is a Blacknode-native recorder, not Isaac Teleop MCAP. |
| Dataset export | `LeRobotV3Export`, `HDF5EpisodeExport`, validation, and explicit Hugging Face upload | GR00T compatibility still requires an embodiment-specific modality mapping and validation against the pinned GR00T release. |
| Fine-tuning | The exported LeRobot directory can be mounted into NVIDIA's training environment | Blacknode does not yet own a GR00T training service or checkpoint lifecycle node. |
| Evaluation/deployment | ROS 2 and package architecture provide integration points | Isaac Lab-Arena policy serving, LEAPP export, CUDA MPS, blend ratios, and real-hardware safety gates are not yet wrapped. |

## Why Blacknode can make this easier

NVIDIA's reference is a sequence of repositories, containers, environment
variables, converters, commands, and manual validation gates. Blacknode can
represent the same lifecycle as a typed graph with inspectable artifacts:

- one hardware and camera selection surface;
- explicit record, pause, discard, validate, and export state;
- reusable dataset handles instead of copied paths;
- non-mutating `check` actions before expensive or external operations;
- visible training configuration and logs;
- recorded provenance from dataset through checkpoint and deployment bundle;
- agent-assisted diagnosis using the Blacknode development/workflow skills;
- safety gates that cannot be bypassed merely because an upstream process
  produced output.

## Recommended NVIDIA extension package

Keep NVIDIA lifecycle integration in a separate `blacknode-nvidia-physical-ai`
package rather than coupling it to recording. Its first nodes should be:

1. `GR00TEnvironmentCheck` — verify architecture, GPU/VRAM, container runtime,
   pinned repositories, model access, and mounted paths without changing them.
2. `GR00TDatasetCheck` — validate LeRobot metadata, FPS, camera/state/action
   features, joint order, episode counts, and an explicit modality config.
3. `GR00TFineTune` — launch the pinned container or remote GPU job, stream logs,
   expose metrics/checkpoints, and support cancellation/resume.
4. `GR00TPolicyServer` and `IsaacArenaEvaluate` — make the ZeroMQ server/client
   contract and success metrics visible in the graph.
5. `LEAPPExport` — require checkpoint, dataset, embodiment tag, and joint config;
   validate the YAML and ONNX bundle before returning it.
6. `IsaacROSDeploy` — stage a validated bundle on Jetson, but keep controller
   enablement and blend-ratio changes behind explicit human safety approval.

Training and export nodes should default to `check`, just like dataset upload
and HDF5 export. A graph cook must not silently start an expensive GPU job,
publish a dataset, enable a controller, or move a robot.

## Format decision

`HDF5EpisodeExport` is deliberately ACT-style: one file per episode with
`observations/qpos`, `action`, timestamps, and RGB camera arrays. NVIDIA's
Isaac Lab-Arena converter expects a different source schema, including an ego
camera under `observations/camera_obs/robot_head_cam_rgb` and configurable
simulation state/action field names. Blacknode should not relabel its HDF5 as
Arena-compatible without an explicit, tested Arena export profile.

For GR00T 1.7, use this route:

1. Record and validate in Blacknode.
2. Run `LeRobotV3Export`.
3. Add and validate the robot-specific GR00T modality config.
4. Pin the NVIDIA repository/tag or commit used for training.
5. Fine-tune in the NVIDIA environment or a suitable remote NVIDIA GPU.
6. Validate in simulation before any real-hardware deployment.
7. For a supported real robot, export with LEAPP and deploy through Isaac ROS
   with NVIDIA's safety procedure.

## Official references reviewed

- [NVIDIA GR00T end-to-end workflow](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/index.html)
- [Concepts and architecture](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/getting-started/concepts-overview.html)
- [Simulation HDF5 to LeRobot](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/simulation-workflow/sim-data-export.html)
- [Simulation fine-tuning](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/simulation-workflow/groot-fine-tuning-sim.html)
- [Simulation evaluation](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/simulation-workflow/sim-evaluation.html)
- [Real robot recording](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-record.html)
- [MCAP to LeRobot](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-data-export.html)
- [Real-data fine-tuning](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-fine-tuning-and-leapp.html)
- [LEAPP export](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-leapp-export.html)
- [Jetson/Isaac ROS deployment](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-deployment.html)
