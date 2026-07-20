# Blacknode Agent Instructions

These instructions apply to the Blacknode core repository. Extension packages
under `packages/` are separate Git repositories and carry their own `AGENTS.md`.

## Route the task

- Use `.agents/skills/blacknode-workflow/SKILL.md` when the requested result is
  a workflow graph, template, editor run, replay, validation, or export.
- Use `.agents/skills/blacknode-development/SKILL.md` when changing Blacknode,
  adding a reusable node, modifying the editor/runtime/MCP API, or creating an
  extension package.
- When a workflow exposes a missing reusable capability, switch to the
  development skill, implement and test it, then return to the workflow skill
  to integrate and validate the graph.

## Repository map

| Area | Responsibility |
|---|---|
| `python/blacknode/` | Python graph model, runtime, nodes, CLI, packages, exporters, and MCP |
| `editor-server/` | FastAPI editor backend, runtime services, sessions, and run replay |
| `editor/` | React/TypeScript visual editor |
| `crates/` | Rust types, core, runtime, Python bindings, and CLI |
| `templates/` | Tracked reusable workflow graphs |
| `tests/` | Core Python and integration tests |
| `packages/` | Independently versioned extension-package checkouts |

## Change rules

- Inspect the live node schema or the node decorator contract before adding or
  connecting ports. Do not invent port names or persisted runtime fields.
- Keep core broadly useful. Put hardware stacks, large optional dependencies,
  and domain-specific integrations in extension packages.
- Preserve compatibility for saved workflow node names unless a migration is
  included. New workflows should use the current generic names.
- Keep templates portable: declare `kind`, `schema_version`, an explicit
  entrypoint, complete port metadata, and any `metadata.required_packages`.
- Never commit API keys, run logs, local workflows, editor state, caches, robot
  calibration data, or generated scratch exports.
- Treat camera, CUDA, ROS, and robot streams as managed services. Do not turn a
  one-shot cook into a polling loop.
- Keep physical motion disarmed by default. Retain stale-data, joint-limit, and
  shutdown safeguards in every transport path.

## Hardware modularity invariants

- Base robot contracts, profiles, and capability inspection must load and work
  when no vendor driver, sensor SDK, ROS installation, simulator, or accelerator
  package is present. Missing providers report a structured unavailable state;
  they do not break package discovery or unrelated capabilities.
- Applications, skills, planners, and controllers depend on stable capability
  contracts such as `Camera`, `LiDAR`, `MobileBase`, `Pick`, or `Navigate`.
  They must not depend directly on a vendor SDK, device path, transport, or
  component implementation.
- Robot profiles bind required capabilities to replaceable components and carry
  provider configuration. Replacing a compatible camera, LiDAR, actuator bus,
  simulator, or compute provider should change the profile/component selection,
  not mission logic, workflow connections, or semantic node names.
- Keep calibration, limits, and sensor extrinsics bound to stable physical
  hardware identity rather than only a component or driver name.
- Every hardware capability needs a mock or replay implementation for
  hardware-free development. Claim interchangeability only after the same
  contract tests pass against the mock and each supported provider.

## Verification

Run the smallest relevant checks first, then the wider suite when shared
contracts changed:

```powershell
python -m unittest discover -s tests
cd editor
npm run build
cd ..
cargo test
```

Package changes must also run the package's own tests from that package
worktree. See `CONTRIBUTING.md` and `docs/agent-guide.md` for the public guide.

## Documentation voice

- Describe Blacknode through its own capabilities, workflows, nodes, artifacts,
  and user outcomes.
- Lead with what the product does. Avoid positioning it through negation or
  comparisons such as "not X", "without X", or "unlike X".
- Mention another product only when it is an actual supported integration,
  provider, file format, protocol, or required configuration in the documented
  workflow.
- Keep speculative integrations and competitor comparisons in internal plans
  or issues unless the user explicitly requests a dedicated integration guide.
