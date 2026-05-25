# Learned Nodes Internals

Learned nodes are normal registry entries with a different execution path.

## Load Path

On `import blacknode`, built-in node modules register first. Then
`blacknode.learned.registry.load_all()` scans `nodes/learned/*/manifest.json`.
Each manifest is validated against the v1 schema, and invalid manifests are
logged and skipped without blocking startup.

For every valid learned node, `register_one(name)`:

1. validates `manifest.json`
2. verifies `node.py` exists
3. refuses to replace built-in node types
4. registers a wrapper through the existing `@node` decorator
5. tags the runtime function with `_bn_source = "learned"`

The public hot-registration entry point is:

```python
register_one(name: str, *, learned_dir: str | Path | None = None) -> LearnedNodeManifest
```

MCP creation and the editor internal add endpoint both use this function.

## Safety Boundary

The host process may read learned-node files and parse source with `ast.parse`.
It must not execute, import, eval, or compile learned-node source.

At cook time, the wrapper calls:

```python
docker_runner.run_in_container(
    code=source_path.read_text(encoding="utf-8"),
    inputs=ctx_subset,
    permissions=manifest.permissions,
    node_name=manifest.name,
)
```

The sandbox runner imports `node.py` inside the container, calls `run(**inputs)`,
and writes `output.json`. If the runner records an error payload, the host raises
a sandbox execution error with the learned-node name and container traceback.

## Manifests

The v1 manifest schema has exact keys:

```json
{
  "name": "ParseRSS",
  "description": "Parse RSS XML text into a list of entries.",
  "inputs": ["feed:Text"],
  "outputs": ["entries:List"],
  "permissions": { "network": false },
  "created_at": "2026-05-24T18:00:00Z",
  "created_by": "claude-via-mcp",
  "schema_version": 1
}
```

Unknown manifest keys and unknown permission keys are rejected. The only v1
permission is `network`.

## Editor Events

The editor backend exposes `GET /learned-nodes/events` as Server-Sent Events.
Events are:

- `learned_node_added`
- `learned_node_deleted`

The frontend uses native `EventSource`, so dropped SSE connections reconnect
automatically.
