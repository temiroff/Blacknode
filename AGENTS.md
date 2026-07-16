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
