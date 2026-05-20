# Today's Goal - 2026-05-20

Make Blacknode portable and runnable outside the browser editor.

## Checklist

- [x] Fix repo hygiene: align project license metadata and remove conflicting legacy license artifacts.
- [x] Define a versioned workflow JSON schema.
- [x] Add workflow validation for missing nodes, invalid ports, bad type connections, duplicate IDs, and missing output nodes.
- [x] Add a CLI runner: `blacknode validate workflow.json` and `blacknode run workflow.json --output result.json`.
- [x] Add Python export: `blacknode export-python workflow.json > workflow.py`.
- [ ] Add structured run logs with node start, finish, error, duration, tool call, and model call events.
