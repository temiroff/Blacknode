# VLA Training

Blacknode Cloud VLA Training turns a versioned robotics dataset into a persisted
Blacknode model. V0 supports OpenPI π0.5 LoRA training through its native JAX
stack. Warp remains available for simulation and synthetic-data workloads; it
is not part of the supervised π0.5 training path.

## V0 workflow

Use the **OpenPI π0.5 Fine-Tune** template. It contains two outcome-producing
nodes:

1. `LeRobotDataset` resolves a local LeRobot v3 dataset or an immutable Hugging
   Face dataset revision as a `blacknode.dataset-source`.
2. `OpenPIFineTune` adapts the source to the OpenPI-pinned LeRobot format,
   computes normalization statistics, runs π0.5 JAX LoRA training, and exports
   a `blacknode.vla-model`.

The workflow entrypoint is the trained `model` output. It has no confirmation,
checker, or pass-through output nodes. Required dataset validation and artifact
integrity checks run inside the nodes that own those responsibilities.

For a remote source, replace `PIN_DATASET_COMMIT` with the dataset repository's
immutable commit SHA before submitting the workflow. The Cloud executor uses an
NVIDIA L40S profile for this V0 workload.

## BlacknodeDataset boundary

`BlacknodeDataset` is the model-independent data boundary. Its lazy adapter
exposes episode metadata, timestamps, observations, actions, task language,
robot identity, and camera-frame references without loading a complete dataset
into memory. V0 provides native and LeRobot v3 adapters. Future ROS bag,
simulation, and robot-recorder sources can implement the same adapter contract.

The OpenPI provider performs model-specific conversion. This keeps OpenPI,
JAX, checkpoint layout, action transforms, and normalization details outside
the dataset core.

## Model artifact

A completed run writes a `blacknode.vla-model` manifest alongside:

- the LoRA checkpoint archive;
- training configuration and pinned OpenPI revision;
- normalization statistics;
- structured metrics and logs;
- dataset URI and immutable revision;
- inference compatibility metadata.

The artifact remains disarmed: `physical_motion_authorized` is always `false`.
Deployment and real-robot inference are separate, guarded workflows.
