# Contributing to Blacknode

Thank you for your interest in contributing.

## Ways to contribute

- **Bug reports** — open an issue with steps to reproduce, expected vs actual behavior, and your OS/Python/Node versions.
- **Feature requests** — open an issue describing the use case before writing code.
- **Code** — fork the repo, make your changes on a branch, and open a pull request.

## Development setup

```bash
# Backend
cd editor-server
pip install -r requirements.txt
python server.py

# Frontend (separate terminal)
cd editor
npm install
npm run dev
```

Install the root project with development dependencies when changing the Python
runtime, nodes, packages, CLI, or MCP server:

```bash
python -m pip install -e ".[dev,mcp]"
```

## Working with coding agents

Read [`AGENTS.md`](AGENTS.md) before making repository changes.

- Use the shipped `blacknode-workflow` skill to create, validate, run, inspect,
  and export workflows using existing nodes and packages.
- Use `blacknode-development` to modify core, editor, MCP, reusable nodes, or
  extension packages.
- Treat every folder under `packages/` as a separate Git repository. Read its
  own `AGENTS.md`, check its status independently, and do not include package
  changes in a core-repository commit.
- If workflow construction reveals a missing reusable capability, implement and
  test it through the development path, then validate it in a workflow.

See the [Agent Guide](docs/agent-guide.md) for routing and the
[Extension Packages guide](docs/packages.md) for package authoring.

## Verification

Run checks appropriate to the changed areas:

```bash
python -m unittest discover -s tests
cd editor && npm run build
cargo test
```

Run package tests from the core root with `python -m pytest
packages/<package>/tests`, or follow the package's `AGENTS.md`. Hardware,
network, provider, CUDA, camera, Docker, and ROS paths may skip locally; state
clearly which paths were not exercised.

## Pull request guidelines

- One logical change per PR.
- Keep commit messages concise: subject line + optional body paragraph.
- If you add a new node type, include a short description in the PR body.
- Update the nearest public documentation and add a representative validated
  workflow/template when it materially proves the capability.
- Run `npm run build` in `editor/` before submitting to catch TypeScript errors.

## License

By contributing you agree that your changes will be licensed under the project's [Apache License 2.0](LICENSE).
