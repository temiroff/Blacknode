# Sim-to-real policy lifecycle

Blacknode now uses a provider-neutral contract for the train, evaluate, export,
qualify, and deploy lifecycle. A robot or simulator extension supplies the
environment and hardware capabilities; the training and motion packages keep
the lifecycle consistent across providers.

## Lifecycle

```text
RL environment provider
  -> PPOTraining
  -> PPOPolicyEvaluate
  -> PPOPolicyExport
  -> PPOPolicyQualify
  -> PolicyDeploymentAuthorize
  -> PolicyRuntime start (preview/disarmed)
  -> PolicyRuntime arm (explicit physical action)
```

`PPOTraining` and `PPOPolicyEvaluate` never connect to hardware. Export creates
a TorchScript actor by default and fingerprints the model bytes together with
its compatibility contract. Qualification binds one or more simulator results
and explicit thresholds to that fingerprint. It still leaves physical motion
unauthorized.

`PolicyDeploymentAuthorize` binds the qualified fingerprint to one calibrated
robot identity and one safety-gate configuration. Its default action is
`check`; authorization also requires `action=authorize` and
`authorize_physical_motion=true`. `PolicyRuntime` starts in preview mode and a
separate `arm` action is required before any command can be published.

## Environment provider contract

A simulator package emits `blacknode.rl-environment` schema version 2. The
provider owns dynamics, reset, observation, reward, termination, randomized
parameters, and optional preview rendering. Training resolves the factory from
the loaded extension package.

```json
{
  "kind": "blacknode.rl-environment",
  "schema_version": 2,
  "provider": {
    "package": "blacknode-my-simulator",
    "component": "runtime",
    "environment_type": "my-balance-task-v1",
    "factory": "blacknode.pkg.blacknode_my_simulator.rl:BalanceEnvironment"
  },
  "task": "balance",
  "robot_profile": "my_robot",
  "joint_names": ["left_joint", "right_joint"],
  "environment_count": 1024,
  "episode_steps": 256,
  "simulation_hz": 200,
  "control_hz": 50,
  "observation": {
    "dimension": 6,
    "fields": [
      {"name": "q", "source": "joint_positions_rad", "size": 2, "normalization": "joint_limits"},
      {"name": "qd", "source": "joint_velocities_rad_s", "size": 2, "scale": 0.05},
      {"name": "last_action", "source": "previous_action", "size": 2}
    ]
  },
  "action": {
    "dimension": 2,
    "type": "bounded_joint_position_delta",
    "minimum": -1.0,
    "maximum": 1.0,
    "scale_rad": 0.05,
    "units": "normalized"
  },
  "domain_randomization": {
    "mass_scale": [0.8, 1.2],
    "friction_scale": [0.7, 1.3],
    "sensor_latency_ms": [0, 20]
  },
  "safety": {
    "simulation_only": true,
    "physical_motion_authorized": false
  }
}
```

The factory class accepts `(spec, device=...)` and exposes
`torch_device`, `environment_count`, `observe()`, `reset()`, `step(actions)`,
and `close()`. `step` returns `(observation, reward, done, info)` tensors. The
current evaluator expects `info.success` and `info.distance_m` so qualification
can apply task-independent success and error thresholds. Preview methods are
optional for headless training providers.

## What a new robot package supplies

The robot profile binds stable capabilities to replaceable simulator and
hardware components. A new robot package supplies:

1. A simulator environment provider implementing the contract above.
2. A physical `Robot` provider with ordered joints, live state, calibrated safe
   limits, stable hardware identity, and explicit torque controls.
3. Observation sources matching the exported semantic field list. The ROS 2
   runtime supplies ordered positions, velocities, calibrated limits, previous
   actions, and workspace position. Task values such as a goal can enter through
   `PolicyRuntime.observation_context`; a provider can supply richer live values
   through the same context contract.
4. Mock or replay implementations that pass the same capability and safety
   contract tests before hardware is enabled.

Changing a camera, actuator bus, simulator, or transport then changes the robot
profile binding, not the PPO lifecycle nodes.

## Qualification and deployment

Connect `PPOPolicyEvaluate.metrics` and `PPOPolicyExport.artifact` to
`PPOPolicyQualify`. Set the success, completed-episode, distance, and scenario
thresholds for the task. The qualification record is saved next to the policy
as `qualification.json`.

For a physical workflow, connect the policy, qualification, calibrated Robot,
and `PolicySafetyGate` to `PolicyDeploymentAuthorize`. Connect its authorization
output to `PolicyRuntime.authorization`. Stage the workflow to the selected
device in the editor, inspect the staged revision, and start it. Staging never
starts motion; the policy runtime begins disarmed.

Watch preview inference, freshness, clamps, and telemetry before choosing the
separate `arm` action. Any stale input, safety-gate rejection, emergency stop,
human takeover, inference fault, or shutdown suppresses commands and releases
torque. The managed Runtime retains the previous workflow revision for explicit
rollback; required-telemetry failure stops the active revision.

The bundled `SO-ARM101 PPO Cloud Demo` is the reference vertical slice. Its
provider is replaceable: another robot package can emit the same environment
contract and reuse the training, export, qualification, and deployment nodes.
