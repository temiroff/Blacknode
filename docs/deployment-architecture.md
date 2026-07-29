# Modular Device Deployment

Blacknode separates workflow deployment, communication transport, runtime
execution, hardware control, and platform updates. Each layer has a stable
contract and replaceable providers, allowing a device to use direct HTTP today
and a broker, edge data fabric, container executor, or OTA platform later.

## Architecture

```mermaid
flowchart LR
    E[Blacknode Editor] --> C[Deployment Coordinator]
    C --> T[Deployment Transport]
    T --> H[HTTP adapter]
    T -. optional .-> Q[MQTT adapter]
    T -. optional .-> Z[Zenoh adapter]
    H --> S[Runtime Deployment Service]
    Q -.-> S
    Z -.-> S
    S --> A[Artifact Store]
    S --> X[Execution Backend]
    S --> D[Hardware Service]

    F[Platform Release Manager] --> U[Platform Update Provider]
    U -. optional .-> M[Mender adapter]
    M -. updates .-> P[OS, Blacknode, runtime, hardware, drivers]
```

Solid lines describe the current direct deployment path. Dotted lines are
provider boundaries intended for optional integrations.

The two update lifecycles remain separate:

- **Workflow deployment** is frequent and interactive. It validates, stages,
  starts, stops, logs, and rolls back a workflow artifact.
- **Platform update** is infrequent and administrative. It updates the
  operating system, Blacknode installation, runtime, hardware package, drivers,
  and device configuration.

An OTA provider may install a new runtime version, but it does not replace the
runtime's workflow-aware deployment service.

## Stable contracts

### Deployment artifact

Every transport carries the same logical artifact:

| Field | Purpose |
|---|---|
| `schema_version` | Selects the artifact contract |
| `name` | Human-readable deployment name |
| `project_id` | Stable owning Project ID when deployed from a Project |
| `workflow_slug` | Saved workflow identity within the owning Project |
| `workflow_hash` | Binds the artifact to the exact validated graph |
| `artifact_hash` | Identifies the exported executable content |
| `entrypoint` | Declares what the runtime executes |
| `required_capabilities` | Declares required device capabilities |
| `required_packages` | Declares required target packages |
| `package_requirements` | Declares package source and published version |
| `content` | Executable workflow or a reference to immutable content |

Large artifacts do not have to travel through the command transport. An MQTT
or Zenoh command can carry a content-addressed HTTPS or object-store reference,
while the same artifact manifest and hashes remain authoritative.

`project_id` and `workflow_slug` are an optional pair. The editor validates
that the project links the workflow and target device before staging. The
runtime preserves ownership across revisions and rejects an update that would
move an existing owned deployment to another project or workflow. Deployment
records created before ownership support remain valid and report empty fields.

The editor persists deployment requirements in workflow metadata. A remote
robot deployment currently targets one physical robot. Additional robots use
separate workflows and are deployed one at a time to the computer connected to
each robot. The Deployments panel guides robot setup in three steps:

1. choose the profile for the workflow's `Robot` node;
2. choose the matching physical robot calibration, or open the guided
   calibration workflow to create one; and
3. check the setup before sending the workflow to the device.

Several calibrations may be saved for the same profile because each calibration
has a human-readable name and is bound to a stable physical hardware identity.
The `Robot` node and Deployment Step 2 show the same selector with both values,
select exactly one calibration, and record its stable identity in workflow
metadata. Changing the selection in either place updates the other; the Robot
node always states the calibration name and hardware identity that deployment
will use. Deployment Step 2 keeps this open-graph selection visible even before
the paired device authenticates and when calibration is optional for a
read-only workflow.

Blacknode derives `metadata.required_capabilities` from the workflow. Robot
motion workflows receive `joint_group`, `position_feedback`, and `servo_bus`.
Guided calibration workflows receive the feedback and bus capabilities they
need while calibration is being created.

Hardware-bound calibration is declared separately as
`metadata.device_calibration`:

```json
{
  "metadata": {
    "required_capabilities": [
      "joint_group",
      "position_feedback",
      "servo_bus"
    ],
    "device_calibration": {
      "profile_id": "so_arm101_v002",
      "hardware_id": "5B41531481"
    }
  }
}
```

Selecting a calibration records the intended profile and physical hardware in
the workflow. When exactly one paired device reports that hardware identity,
the Deployments panel selects it automatically and shows the calibration match.
The Devices panel can rename a paired robot without asking for its pairing
tokens again. **Check setup** verifies the connected hardware identity and
automatically activates a matching saved calibration while the device is
disarmed. Preflight accepts `joint_group` only when the
workflow selection, Robot profile, device hardware identity, and device's
active calibration all match. The staged workflow embeds the same profile and
calibration so the robot driver applies the reviewed home positions and safe
joint ranges. When the selected calibration belongs to another USB identity,
preflight identifies both the selected and connected hardware and blocks
activation instead of offering to upload another robot's calibration.

### Deployment transport

A transport adapter exposes these semantic operations regardless of protocol:

| Operation | Meaning |
|---|---|
| `manifest` | Read runtime identity, versions, features, and package inventory |
| `list` / `get` | Read desired and observed deployment state |
| `stage` | Validate and store a revision without starting it |
| `start` | Explicitly run the staged revision |
| `stop` | Idempotently stop its complete process or service group |
| `logs` | Read logs using a cursor or bounded tail |
| `rollback` | Select a previous revision, without implicit motion |
| `delete` | Remove a stopped deployment and its stored revisions |

The current provider maps these operations to authenticated HTTP endpoints.
Future providers must preserve the same request and response shapes rather than
leaking protocol-specific topics, sessions, or query objects into the editor.

Every mutating request will support:

- a unique operation ID for idempotent retries;
- device ID and deployment ID;
- expected workflow and revision hashes;
- creation and expiry timestamps;
- explicit acknowledgement and structured errors; and
- authenticated caller identity.

### Runtime deployment service

The runtime owns deployment state independently from its network adapter. Its
service contract is responsible for:

- synchronizing declared extension packages and activating the workflow's
  required components and adapters through a replaceable package provider
  before artifact staging;
- validating artifact size, schema, hash, and executable form;
- preserving revisions;
- separating stage from start;
- supervising execution;
- reporting observed state and bounded logs;
- stopping complete process groups; and
- selecting previous revisions.

The current execution backend uses a supervised Python process. A systemd,
container, or another executor can implement the same backend contract later.
The current package provider uses the Blacknode package index and package
manifests. Future image-based executors may resolve the same requirements into
an immutable container or platform release instead.

### Hardware service

The hardware service remains the authority for physical state and commands.
Transport and runtime providers never bypass:

- explicit arming;
- calibration and joint limits;
- command freshness and expiry;
- hardware identity;
- emergency stop and shutdown behavior; or
- capability availability.

The deployment coordinator checks connectivity and disarmed state before a
remote start. Hardware-facing commands still pass through the hardware
service's own safety checks after a workflow starts.

### Platform update provider

A platform update provider reports inventory and manages releases of:

- the operating system and kernel;
- Blacknode core;
- `blacknode-runtime`;
- `blacknode-robot` device and telemetry components;
- device drivers and optional packages; and
- service definitions and non-secret configuration.

Its lifecycle is distinct from workflow revisions:

`available -> downloaded -> installed -> verified -> committed`

A platform rollback restores a software or operating-system release. A
workflow rollback only selects a previous workflow revision.

## Provider roles

| Provider | Intended role | Status |
|---|---|---|
| Direct HTTP | Local-network discovery, commands, state, and logs | Current |
| MQTT 5 | Brokered commands, acknowledgements, status events, and offline fleet communication | Planned adapter |
| Zenoh | Edge queries, pub/sub state, logs, and routed or peer-to-peer communication | Planned adapter |
| Mender | Fleet inventory and OTA updates for device software and operating systems | Planned platform-update adapter |

MQTT and Zenoh are deployment transports. Mender is a platform update
provider. A device may use one from each category—for example, Zenoh for live
deployment control and Mender for signed operating-system updates.

Relevant provider specifications:

- [MQTT 5.0 specification](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html)
- [Zenoh documentation](https://zenoh.io/docs/)
- [Mender Update Modules](https://docs.mender.io/client-installation/use-an-updatemodule)
- [Mender operating-system updates](https://docs.mender.io/operating-system-updates-yocto-project/overview)

## Configuration and discovery

Provider selection belongs to device configuration, not workflow graphs. A
paired device record will eventually select providers using a shape such as:

```json
{
  "device_id": "workshop-arm",
  "deployment_transport": {
    "provider": "http",
    "endpoint": "http://192.168.1.87:8766"
  },
  "platform_updates": {
    "provider": "none"
  }
}
```

Credentials are referenced by a local credential ID or operating-system secret
store. They are never embedded in workflows, deployment artifacts, browser
responses, logs, or provider-neutral configuration.

The editor registers the compute device and its shared runtime first. A device
record owns the runtime URL on port `8766` and the server-side runtime pairing
credential. Each child robot record uses the exact hardware service URL printed
by `blacknode-robot` device pairing. On a multi-robot computer, hardware services
use `8765`, `8767`, `8768`, and subsequent assigned ports. The editor rejects
`8766` as a robot hardware endpoint and binds every child robot to its parent
device's runtime.

Existing paired-robot records migrate into this hierarchy by grouping their
shared runtime URL. Their robot IDs remain unchanged, so saved Project links
and deployment targets continue to resolve. Run
`blacknode-runtime/service.sh pairing` when the device runtime needs to be
paired manually. The editor stores that credential once on the compute device
and reuses it for all of its robots.

For a workflow containing one `Robot` node, deployment also embeds the serial
path reported by the selected hardware service and disables runtime USB
auto-discovery. This makes the editor device selection authoritative when
multiple robots share one computer: each deployment opens the physical bus
behind the paired service it targeted.

Immediately before the runtime starts that workflow, the editor asks only the
targeted hardware service to release its read-only serial monitor. Stopping or
rolling back the deployment resumes that monitor. Other paired robot services
and serial buses remain active. The Devices panel names the running deployment
that owns a serial lease and can stop it directly. If no deployment is running,
checking the device recovers the stale lease and reconnects the monitor.

The deployment plan sends package source and version from the editor. The
runtime package provider is generic: it does not contain a list of perception,
robot, training, or other extension packages. Publishing a new extension
package or a newer package version therefore does not require a new runtime
release. Package ownership can come from the official package index, explicit
workflow metadata, or the editor's live package registry and Git origin.

## Compatibility requirements

Optional providers must satisfy one shared contract suite. Blacknode considers
a provider compatible only when it demonstrates:

- identical deployment state transitions;
- idempotent retries and duplicate-command handling;
- bounded payload and log behavior;
- reconnect and timeout behavior;
- authentication failures that do not expose credentials;
- revision and workflow-hash enforcement;
- explicit start, stop, and rollback behavior; and
- unchanged hardware safety checks.

The direct HTTP implementation remains the reference provider while additional
adapters are developed.
