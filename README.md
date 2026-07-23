<p align="center">
  <img src="editor/public/blacknode-logo.png" alt="Blacknode logo" width="128" height="128">
</p>

# Blacknode

[![CI](https://github.com/temiroff/Blacknode/actions/workflows/ci.yml/badge.svg)](https://github.com/temiroff/Blacknode/actions/workflows/ci.yml)

**Build, run, inspect, and deploy robot behavior as typed visual workflows.**

Blacknode connects robot hardware, perception, controllers, datasets, training,
simulation, and deployment on one visual canvas. Start with a tested robot
template, inspect live state, authorize a bounded action, and follow every
result through run history and replay.

Workflows stay readable as systems grow: each node has typed ports, each
connection is validated, and hardware-specific implementations remain behind
stable robot capabilities.

<p align="center">
  <a href="docs/images/blacknode-light-theme.png">
    <img src="docs/images/blacknode-light-theme.png" alt="Blacknode visual workflow editor" width="860">
  </a>
</p>

## A Robot Workflow, Layer by Layer

A Blacknode robot workflow moves from task intent to physical hardware through
explicit, replaceable layers:

```text
Operator / application / agent
              │
              ▼
Task skills and mission workflows
              │
       ┌──────┴──────┐
       ▼             ▼
  Perception    Controllers + safety
       │             │
       └──────┬──────┘
              ▼
Robot profile, capabilities, calibration, and limits
              │
              ▼
Transport adapters and ROS 2 integration
              │
              ▼
Hardware drivers, cameras, buses, and the physical robot
              │
              └──────── live state and observations flow back up
```

| Layer | What it owns | Packages |
|---|---|---|
| Tasks and missions | Reusable robot skills, planning, confirmation, and orchestration | [`blacknode-skills`](https://github.com/temiroff/blacknode-skills), [`blacknode-agent`](https://github.com/temiroff/blacknode-agent) |
| Perception | Cameras, tracking, VLMs, and spatial observations | [`blacknode-perception`](https://github.com/temiroff/blacknode-perception) |
| Control and safety | Joint control, mobile bases, manipulation, policies, arbitration, limits, freshness checks, and stop paths | [`blacknode-controllers`](https://github.com/temiroff/blacknode-controllers) |
| Robot model | Robot profiles, capability contracts, calibration, discovery, and connection health | [`blacknode-robot`](https://github.com/temiroff/blacknode-robot) |
| Integration | ROS 2 graph, topics, services, processes, native transport, and rosbridge | [`blacknode-ros2`](https://github.com/temiroff/blacknode-ros2) |
| Devices | Generic hardware contracts, replaceable adapters, physical drivers, and firmware protocols | `blacknode-hardware`, [`blacknode-drivers`](https://github.com/temiroff/blacknode-drivers) |
| Learning and deployment | Episode recording, policy training, simulation, and accelerated compute | [`blacknode-dataset`](https://github.com/temiroff/blacknode-dataset), [`blacknode-training`](https://github.com/temiroff/blacknode-training), [`blacknode-isaac`](https://github.com/temiroff/blacknode-isaac), [`blacknode-cuda`](https://github.com/temiroff/blacknode-cuda) |

The workflow depends on stable capabilities such as a camera, joint controller,
mobile base, or navigation interface. Robot profiles select the concrete
providers, so compatible hardware or transport changes do not require mission
logic to be rebuilt.

## What You Can Build

```text
Discover robot
  → load its profile and calibrated limits
  → start drivers and transport services
  → inspect live camera and joint state
  → run a perception or control skill
  → authorize motion
  → record an episode
  → train and preview a policy
  → deploy to simulation or the robot
  → inspect metrics and replay
```

Common workflows include:

- Move one named joint to a bounded angle.
- Track an object and turn a robot toward it.
- Follow a person with camera, controller, and mobile-base safety nodes.
- Record synchronized camera and robot-state episodes.
- Train an action-chunking policy and preview its artifact.
- Deploy a policy through a safety gate to Isaac Sim or supported hardware.

Physical motion is disarmed by default. Motion nodes preserve joint limits,
state freshness checks, explicit authorization, and shutdown behavior across
supported transports.

## Start Blacknode

Python 3.11+ and Node.js 20.19+ or 22.12+ are required.

Windows:

```powershell
git clone https://github.com/temiroff/Blacknode.git
cd Blacknode
.\start.bat
```

macOS/Linux:

```bash
git clone https://github.com/temiroff/Blacknode.git
cd Blacknode
chmod +x start.sh
./start.sh
```

The launcher prepares the Python environment, installs editor dependencies,
starts the runtime and editor, and opens the browser. On first launch, use the
**Packages** tab to install the robot capabilities needed by a template.

Continue with the [Beginner Walkthrough](docs/walkthrough.md), or connect an
SO-ARM101 with the [robot quickstart](docs/so-arm101-quickstart.md).

## Run a Real Robot Workflow

The **SO-ARM101 Motion Test** template organizes first motion into observable
stages:

```text
USB discovery
  → robot profile
  → driver and ROS 2 readiness
  → live six-joint state
  → joint name + target angle
  → Armed safety control
  → bounded movement
  → safe stop
```

Use the workflow dashboard to confirm the physical robot, transport, live
state, selected joint, and allowed range before enabling **Armed**. See:

- [SO-ARM101 quickstart](docs/so-arm101-quickstart.md)
- [ROSBridge robot quickstart](docs/rosbridge-robot-quickstart.md)
- [SO-ARM101 leader/follower setup](docs/so-arm101-leader-follower.md)
- [Robot episode datasets](docs/episode-datasets.md)
- [Robot policy training](docs/robot-policy-training.md)

## Extension Packages

Blacknode core provides the graph model, typed runtime, editor, package system,
run replay, exports, and agent-facing APIs. Robot capabilities live in focused
extension packages with their own nodes, components, templates, dependencies,
and tests.

Install a package from the editor or CLI:

```bash
blacknode packages install https://github.com/temiroff/blacknode-robot.git
blacknode packages setup blacknode-robot
```

Templates declare their required packages. Blacknode can resolve those
requirements, present missing capabilities, and load the nodes after
installation. Optional SDKs and hardware providers report their availability
without preventing unrelated packages from loading.

Read [Extension Packages](docs/packages.md) for package installation,
components, dependency resolution, authoring, and lifecycle details.

## Core Platform

- **Visual workflow editor:** compose and inspect typed node graphs.
- **Validated runtime:** catch missing ports, incompatible types, and graph
  cycles before execution.
- **Managed services:** keep cameras, robot drivers, ROS processes, and
  controllers visible and stoppable.
- **Run history and replay:** inspect node timing, values, model calls, tool
  calls, and errors.
- **Portable artifacts:** save workflow JSON and export supported graphs to
  Python or framework integrations.
- **Control APIs:** create, connect, validate, run, save, and inspect workflows
  through MCP, HTTP, and WebSocket APIs.

## Documentation

### Build Robot Workflows

| Guide | Use it for |
|---|---|
| [Beginner Walkthrough](docs/walkthrough.md) | Install Blacknode, navigate the editor, run templates, and inspect results. |
| [SO-ARM101 Quickstart](docs/so-arm101-quickstart.md) | Discover, connect, verify, move, and stop an SO-ARM101 safely. |
| [Robot Episode Datasets](docs/episode-datasets.md) | Record, validate, export, and publish synchronized robot episodes. |
| [Robot Policy Training](docs/robot-policy-training.md) | Train, preview, and deploy a robot policy artifact. |
| [YOLO Object Detection](docs/yolo-object-detection.md) | Connect camera streams to object detection workflows. |

### Extend the Platform

| Guide | Use it for |
|---|---|
| [Extension Packages](docs/packages.md) | Install, manage, and author modular capability packages. |
| [Workflow Schema](docs/workflow-schema.md) | Understand the portable workflow JSON format. |
| [Custom Nodes](docs/custom-nodes.md) | Create reusable Python nodes and node libraries. |
| [Agent Guide](docs/agent-guide.md) | Route workflow construction and reusable development tasks. |
| [Framework Export](docs/framework-export.md) | Export workflows to Python and supported framework formats. |
| [MCP Quickstart](docs/quickstart-mcp.md) | Connect an MCP client to the Blacknode control surface. |

### Integrations

- [NVIDIA Agent Stack](docs/nvidia-agent-stack.md)
- [NVIDIA GPU and CUDA blocks](docs/nvidia-gpu-blocks.md)
- [Docker deployment](docs/docker-compose.md)
- [Python round-trip](docs/python-roundtrip.md)

## Project Map

| Path | Purpose |
|---|---|
| `python/blacknode/` | Python graph model, runtime, registry, packages, CLI, exports, and MCP server |
| `editor-server/` | Editor API, managed runtime services, sessions, and run replay |
| `editor/` | React visual workflow editor |
| `templates/` | Core starter workflows |
| `packages/` | Independently versioned extension-package checkouts |
| `docs/` | Robot guides, platform references, and integration documentation |
| `crates/` | Rust graph types, runtime, bindings, and CLI |

## Development

Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup and verification. Repository
architecture and safety invariants are documented in [AGENTS.md](AGENTS.md).

## License

Blacknode is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
