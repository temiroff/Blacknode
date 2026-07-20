---
name: blacknode-development
description: >
  Develop, extend, test, or debug Blacknode itself and its reusable extension
  ecosystem. Use when changing the Python or Rust runtime, MCP server, editor,
  package manager, exporters, node contracts, managed services, creating a
  reusable core/custom/community node, authoring an extension package, or
  modifying blacknode-cuda, blacknode-vision, blacknode-ros2, or
  blacknode-robot. Use blacknode-workflow when the requested result is only a
  workflow graph built from existing capabilities.
---

# Blacknode Development

Develop the smallest reusable layer that owns the requested capability, protect
saved-workflow compatibility, and prove the result through both focused tests
and a representative workflow when applicable.

## Start Here

1. Read the nearest `AGENTS.md`; package repositories have scoped guidance.
2. Inspect the current implementation, tests, and public documentation before
   choosing a layer.
3. Check Git status in the exact worktree being changed. `packages/*` are
   independent repositories, not tracked children of the core repository.
4. Decide whether the capability belongs in core, an extension package, a
   user-local custom node, or a workflow-local `PythonFn`.
5. Implement the narrowest coherent change, add tests, and update public docs.
6. Build a small workflow/template when it materially proves discovery, ports,
   runtime behavior, or package resolution.

## Choose the Ownership Layer

| Need | Put it here |
|---|---|
| Graph types, execution, validation, registry, CLI, MCP, exporters | `python/blacknode/` |
| Browser/editor behavior or UI | `editor/` |
| Editor HTTP API, runtime services, replay | `editor-server/` |
| Portable Rust graph/runtime/CLI behavior | `crates/` |
| Broad, dependency-light node | `python/blacknode/nodes/` |
| Hardware, GPU, ROS, vision, or large optional dependency | extension package |
| User-owned local reusable behavior | `custom-nodes/` |
| One graph's small adapter | `PythonFn` in the workflow |

Do not duplicate a domain implementation in core and a package. Keep the core
contract generic and place transport- or hardware-specific implementations
behind package nodes and runtime adapters.

## Preserve Hardware Replaceability

- Keep base robot contracts, profiles, and capability inspection functional
  with no vendor driver, sensor SDK, ROS installation, simulator, or accelerator
  package installed. Missing providers return a structured unavailable state
  and do not prevent unrelated capabilities from loading.
- Make applications, skills, planners, and controllers consume stable
  capability contracts rather than vendor SDKs, device paths, transports, or
  component implementations.
- Bind capability providers through robot profiles and component configuration.
  A compatible camera, LiDAR, actuator bus, simulator, or compute-provider swap
  must preserve mission logic, workflow connections, and semantic node names.
- Bind calibration, limits, and sensor extrinsics to stable physical identity,
  not merely a component or driver type.
- Supply a mock or replay provider for every hardware capability. Do not claim
  providers are interchangeable until the same contract suite passes against
  the mock and every supported provider.

## Develop a Node

1. Inspect `python/blacknode/node.py`, nearby nodes, and node tests.
2. Define stable, typed inputs and outputs with the existing `@node` contract.
3. Keep import-time behavior cheap and deterministic. Guard optional heavy
   dependencies and return actionable structured errors at runtime.
4. Separate one-shot cooking from persistent services. A stream/controller node
   starts or updates one managed service; it does not create a polling cook.
5. Add discovery/registration tests and behavior tests.
6. Exercise the node in a minimal validated workflow or package template.
7. Document configuration, outputs, dependencies, and lifecycle behavior.

Preserve old node names needed by saved workflows as compatibility aliases.
Use current generic names in new templates and docs.

## Author an Extension Package

Use `blacknode-cuda` as the smallest reference package. Read
`docs/packages.md` and `docs/custom-nodes.md` before authoring.

Required shape:

```text
blacknode-example/
  blacknode-package.toml
  nodes/
    __init__.py
  tests/
  templates/          # optional
  requirements.txt    # optional
  README.md
  AGENTS.md
```

- Declare `name`, `version`, `description`, and `requires-blacknode`.
- Declare import names under `dependencies.imports`, pip requirements under
  `dependencies.pip`, and Docker images when required.
- Keep package loading functional when optional runtime dependencies are absent;
  surface dependency warnings and actionable setup commands.
- Add `metadata.required_packages` to templates that use package nodes.
- Keep each package independently testable, versioned, documented, and
  publishable from its own Git repository.
- Add scoped `AGENTS.md` safety and test instructions. Create a package-specific
  skill only when users need a distinct, substantial operational workflow that
  cannot be routed clearly through `blacknode-workflow`.

## Cross-Layer Contracts

When changing node schemas, runtime events, managed services, or package APIs,
trace all consumers:

```text
node/package -> registry and schema -> editor-server/MCP -> editor -> template
             -> tests and documentation
```

Update each affected layer in the same change. Do not persist editor-only fields
such as `cookResult`, `cookError`, `cooking`, or `cookPort` in workflow JSON.

For hardware-facing contracts, test provider absence as well as provider
presence. A missing optional module must degrade only its advertised
capabilities, while compatible providers must produce the same normalized
state, lifecycle, status, error, and shutdown shapes.

## Hardware and Managed-Service Safety

- Keep robot motion disarmed until explicitly authorized.
- Never bypass calibrated limits, freshness checks, or emergency shutdown.
- Treat worker heartbeat and source-data freshness as separate signals.
- Preserve idempotent control behavior across retries.
- Make stop paths explicit and testable. Robot shutdown may release torque.
- Do not use physical hard stops to discover joint limits.

Read the target package's `AGENTS.md` before modifying CUDA, vision, ROS 2, or
robot code.

## Verification Matrix

| Change | Minimum verification |
|---|---|
| Python runtime, nodes, MCP, packages, templates | focused test plus `python -m unittest discover -s tests` |
| Editor | relevant tests plus `npm run build` in `editor/` |
| Rust | focused crate test plus `cargo test` |
| Extension package | package test command from its `AGENTS.md` |
| Workflow-facing capability | validate and run a representative graph |

Run broader checks when a shared schema or runtime contract changes. Report
checks that could not run because hardware, credentials, Docker, ROS, or CUDA
were unavailable; do not claim those paths were verified.

## Documentation

Update the closest public contract alongside code:

- `docs/agent-guide.md` for agent routing and workflow behavior.
- `docs/packages.md` for package format and lifecycle.
- `docs/custom-nodes.md` for node authoring.
- `CONTRIBUTING.md` for contributor setup and verification.
- The affected package README for package-specific behavior.

Write public documentation in a product-first voice: explain Blacknode's nodes,
workflows, artifacts, and outcomes directly. Avoid framing capabilities as the
absence of another product or comparing Blacknode with another ecosystem.
Reference external names only for implemented providers, protocols, formats, or
explicitly requested integration guides. Keep speculative integrations in
internal plans or issues.

Keep `skills/` and `.agents/skills/` synchronized when editing a shipped skill.
