# Provider Authoring

Blacknode connects workflows to replaceable hardware, services, simulators, and
transports through stable capabilities. A workflow asks for a capability such
as `camera`, `mobile_base`, or `joint_group`; a robot profile binds that
capability to an installed package component and optional adapter.

Use this guide when adding a new physical device, vendor SDK, ROS 2 driver,
simulator, replay source, or alternative implementation of an existing
capability.

## The provider model

```text
Workflow or skill
       |
       v
Stable capability contract
       |
       v
Robot-profile capability binding
       |
       v
Provider component + optional adapter
       |
       v
Vendor SDK, ROS 2 graph, service, simulator, or replay
```

The terms have distinct meanings:

| Term | Meaning |
|---|---|
| Capability | A stable behavior or data contract consumed by workflows, such as `camera`, `mobile_base`, or `joint_group`. |
| Contract | The normalized commands, state, lifecycle, status, errors, timestamps, and units shared by compatible providers. |
| Provider | One implementation of a capability for concrete hardware, a service, simulation, or replay. |
| Adapter | An optional integration boundary, such as ROS 2, nested under the component that owns the domain capability. |
| Binding | The robot-profile record that selects a provider package, component, optional adapter, configuration, and hardware identity. |
| Node | A typed workflow operation. A provider may expose nodes, but the provider and node are not the same abstraction. |

Manifest capabilities describe what an installable component supplies. Robot
profile capabilities describe what the configured robot can do. Keep both
stable, but do not assume their identifiers are interchangeable.

## Choose the owner first

Add the provider to the narrowest package that owns the capability:

| Provider responsibility | Owner |
|---|---|
| Robot profiles, capability bindings, calibration identity, normalized device state | `blacknode-robot` |
| Concrete device protocols, vendor SDKs, firmware bridges, serial, CAN, USB, or I2C access | `blacknode-drivers` |
| Camera, depth, LiDAR, IMU, tracking, or other perception behavior | `blacknode-perception` |
| Arm, base, navigation, policy, arbitration, or motion safety | `blacknode-motion` |
| ROS 2 graph, topic, service, process, and diagnostic primitives | `blacknode-ros2` |
| Simulator-specific implementation | The simulator package, such as `blacknode-isaac` |
| Reusable task behavior over capabilities | `blacknode-skills` |

A domain node that uses ROS 2 stays with its domain. For example, a camera ROS
2 provider belongs under `blacknode-perception/camera`, while generic topic and
process primitives belong in `blacknode-ros2`. Domain adapters depend on the
integration layer; the integration layer does not depend on domain packages.

Create a separate extension package when the implementation introduces a new
vendor SDK, hardware stack, large optional dependency, or independently
versioned provider family. Keep a small workflow-local conversion in
`PythonFn` only when it is not reusable.

## Find or define the contract

Inspect the live contract before writing provider code. Current robot device
contracts include:

- [`DeviceState`, `JointState`, `FaultState`, and `MobileBaseProvider`](../packages/blacknode-robot/blacknode_robot/devices/contracts.py)
- [`JointGroupState`, `JointGroupCommand`, and `JointGroupProvider`](../packages/blacknode-robot/blacknode_robot/devices/joint_group.py)
- capability bindings and status normalization in
  [`capabilities.py`](../packages/blacknode-robot/nodes/capabilities.py)
- attachment lifecycle and interface requirements in
  [Managed robot attachments](managed-robot-attachments.md)

Provider contracts are capability-specific. Blacknode does not define one
universal Python `Provider` class. An implementation may be:

1. An in-process object implementing a capability `Protocol`.
2. A managed process or ROS 2 launch whose interfaces are described by an
   attachment or driver descriptor.
3. A capability-specific registration hook defined by the owning package.
4. A simulator or replay implementation returning the same normalized
   contract.

If the capability has no reusable contract, add the transport-neutral contract
to its owning package first. Include a mock or replay provider and contract
tests before adding vendor-specific behavior. Applications and workflows must
not import a provider class directly.

## Scaffold the extension

An independently versioned provider package normally has this shape:

```text
blacknode-example/
  blacknode-package.toml
  AGENTS.md
  README.md
  components/
    device-family/
      nodes/
        __init__.py
        provider.py
      adapters/
        ros2/
          nodes/
            __init__.py
          ros2_ws/          # only when this package owns colcon sources
  templates/
  tests/
  requirements.txt         # optional
```

Start from `blacknode-cuda` for a small flat package or `blacknode-drivers` for
a component and adapter package. Package worktrees under `packages/` are
independent Git repositories and use their own `AGENTS.md`.

## Implement the provider

Use the exact methods and normalized state type declared by the capability
contract. The existing mobile-base contract, for example, requires `state`,
`arm`, `disarm`, `command`, and `stop`. Its I2C reference implementation is
[`I2CMecanumBase`](../packages/blacknode-robot/blacknode_robot/devices/adapters/i2c_mecanum.py).

Every hardware provider must preserve these common behaviors:

- Import optional SDKs only when the provider is used. Package discovery must
  still work when the hardware library, ROS installation, or device is absent.
- Keep discovery and checking read-only. Never start a provider or authorize
  motion as a side effect of inspection.
- Start explicitly and idempotently. Repeating the same start request should
  reuse or safely reconcile the service.
- Return normalized state, units, timestamps, freshness, faults, and hardware
  identity defined by the contract.
- Treat communication presence and hardware health separately. Valid telemetry
  may coexist with a warning; motion authorization remains strict.
- Stop explicitly and idempotently. Stop the complete managed process group and
  place hardware in the contract's safe shutdown state.
- Return a structured unavailable or unhealthy status with an actionable
  reason. Do not raise during package import or break unrelated capabilities.

Persistent streams, controllers, subscriptions, and launched drivers are
managed services. A workflow cook may start or update one service, but it must
not become a polling loop.

## Declare the component

Declare only implemented capabilities. A component becomes public after its
implementation, dependencies, lifecycle, unavailable state, and tests exist.

```toml
[package]
name = "blacknode-example"
version = "0.1.0"
description = "Example hardware provider for Blacknode."
requires-blacknode = ">=0.3.0"
layer = "drivers"
component-mode = true

[components.device-family]
description = "Concrete example device provider."
default = false
capabilities = ["driver.example-device"]
nodes = ["components/device-family/nodes"]
node-types = ["ExampleDeviceCheck"]

[components.device-family.dependencies]
pip = ["example-sdk>=1"]
imports = ["example_sdk"]

[components.device-family.adapters.ros2]
description = "ROS 2 adapter for the example device."
default = false
capabilities = ["adapter.example-device.ros2"]
nodes = ["components/device-family/adapters/ros2/nodes"]

[components.device-family.adapters.ros2.dependencies]
requires = [
  { package = "blacknode-ros2", component = "core", version = ">=0.5.0,<1.0.0" }
]
```

Use the established capability identifier from the owning package when one
exists. Do not publish placeholder components or planned capabilities in the
manifest.

If the package owns a colcon workspace, declare its relative path on the
component or adapter:

```toml
ros2-workspaces = ["components/device-family/adapters/ros2/ros2_ws"]
```

The path must remain inside the package. `build/`, `install/`, and `log/` are
generated artifacts and must not be committed. An external robot workspace is
part of device deployment configuration; do not escape the package with an
absolute manifest path.

## Connect the binding to the implementation

The manifest makes provider code loadable, and the robot profile selects a
package/component/adapter. Neither operation starts hardware by itself. The
capability-owning package supplies the resolver that connects that binding to
an implementation.

Use the resolver already defined by the capability:

- Calibration control discovers capability-specific provider registrations and
  opens the implementation selected by the profile.
- Servo motion discovers `_bn_robot_joint_motion_provider` registrations and
  opens only the package/component selected by the profile's `joint_group`,
  `calibration_control`, or `position_feedback` binding. A session supplies
  `sample()`, `hold()`, `command(positions_deg, deadline=...)`, `release()`,
  and `close()`. `hold()` seeds every configured joint from current feedback
  before torque; `command()` verifies freshness, torque, and hardware health at
  the physical driver boundary.
- Managed attachments synchronize the selected package, build a process
  descriptor from provider configuration, and ask Runtime to start or reuse it.
- Existing-topic providers remain read-only and use ROS interface checks as
  their live provider status.
- In-process device facades construct an object that implements their declared
  capability `Protocol`.

When a new capability has no resolver, add one to the owning domain package. It
must read the normalized binding, merge provider configuration explicitly,
match only the requested package/component/adapter, return structured
unavailable status when no implementation matches, and start hardware only
after an explicit action. Keep provider selection out of the editor server and
workflow-specific code.

## Bind the provider to a robot

Robot profiles select providers through a versioned capability binding:

```json
{
  "kind": "blacknode.robot-capability-binding",
  "schema_version": 1,
  "capability": "camera",
  "provider": {
    "package": "blacknode-perception",
    "component": "camera",
    "adapter": "ros2"
  },
  "configuration": {
    "ros2_interfaces": [
      {
        "kind": "topic",
        "direction": "output",
        "topic": "/camera/image_raw",
        "message_type": "sensor_msgs/msg/Image",
        "frame_id": "camera_link"
      }
    ]
  },
  "hardware_identity": {
    "id": "camera-serial-123"
  },
  "required": true
}
```

Use `RobotCapabilityBinding`, `RobotAttachment`, and
`RobotCapabilityProfile` to create these records visually. Configuration may
change when a provider changes; the semantic capability and downstream
workflow ports remain stable.

Calibration, limits, and sensor extrinsics bind to stable physical hardware
identity. Do not bind them only to a component, device path, or enumeration
index.

## Add ROS 2 behavior

Choose one lifecycle owner for each ROS process:

- **Existing topics:** inspect and consume a provider already started by the
  robot's bringup stack.
- **Blacknode-managed process:** start it explicitly through Runtime and
  `blacknode-ros2` process primitives, then verify required interfaces and
  freshness.

Do not start a second copy of an existing driver. A ROS transport reconnect
must not restart healthy physical hardware.

Keep topic names, message types, frames, launch arguments, and provider
configuration behind the binding or attachment. Workflows consume normalized
capabilities instead of vendor topic names.

## Expose workflow nodes and templates

Add typed nodes only for useful operator or workflow actions:

- A read-only discovery or check node.
- A generic capability facade or status node.
- An explicit managed-service start/stop node when the owning package defines
  that lifecycle.
- Advanced adapter nodes when direct ROS or vendor configuration is useful.

Use semantic public names. Keep vendor, SDK, device-path, and transport details
inside the component or under advanced controls. Preserve old public node names
as compatibility aliases when saved workflows may use them.

Add a minimal template that proves package resolution, provider configuration,
status, and safe stop behavior. Declare `metadata.required_packages`,
`metadata.required_components`, and `metadata.required_adapters` as applicable.

## Prove compatibility

Run one shared contract suite against the mock or replay provider and every
supported real provider. Cover:

- package discovery with optional dependencies absent;
- structured unavailable state when the SDK, ROS graph, permission, or device
  is missing;
- normalized state shape, units, timestamps, faults, and hardware identity;
- repeated start, reconnect, command, stop, and shutdown behavior;
- worker heartbeat separately from source-data freshness;
- wrong or stale hardware identity;
- malformed configuration and bounded error/log payloads;
- provider-specific safeguards at the physical boundary;
- template validation and one representative workflow.

Motion providers additionally test disarmed startup, current-pose
synchronization before torque, command expiry, calibrated limits, emergency
stop, and torque release. Hardware-free tests do not establish physical safety;
report the exact hardware paths exercised.

Use the target package's `AGENTS.md` for its focused test command. When shared
core contracts change, also run:

```powershell
python -m unittest discover -s tests
```

Validate package templates from the repository root:

```powershell
Get-ChildItem packages\<package>\templates\*.json |
  ForEach-Object { blacknode validate $_.FullName }
```

## Definition of done

A provider is complete when:

- the owning capability contract remains transport- and vendor-neutral;
- package discovery works when the provider is absent;
- the manifest declares only implemented components and dependencies;
- a robot profile can bind configuration and stable hardware identity;
- status distinguishes available, unavailable, and unhealthy;
- start, reconnect, stop, and shutdown are explicit and testable;
- a mock or replay provider passes the same contract suite;
- a validated template demonstrates the provider;
- the package README documents configuration, lifecycle, outputs, dependencies,
  and hardware verification.

See [Extension Packages](packages.md), [Custom Nodes](custom-nodes.md),
[Managed robot attachments](managed-robot-attachments.md), and
[Modular Device Deployment](deployment-architecture.md) for the supporting
package, node, attachment, and deployment contracts.
