# Learned Nodes

Learned nodes let an MCP-connected agent create a new permanent Blacknode node
type when the current catalog does not contain the capability it needs. The node
is stored as plain Python under `nodes/learned/<Name>/`, appears in the editor
palette under **Learned**, and can be reused in later workflows.

This feature is opt-in. On first use, `create_node_type` refuses the request
unless `BLACKNODE_LEARNED_NODES_CONSENT=1` is set. After opt-in, consent is
persisted at `~/.blacknode/learned-nodes-consent.json`; delete that file to
revoke consent.

## What Agents Can Create

Agents call the MCP tool:

```text
create_node_type(
  name="ParseRSS",
  description="Parse RSS XML text into a list of entries.",
  inputs=["feed:Text"],
  outputs=["entries:List"],
  code="def run(feed): ...",
  requires_network=False,
)
```

The tool validates:

- PascalCase node name, 3-40 characters
- unique node type name
- port declarations in `name:Type` format
- allowed port types: `Text`, `Int`, `Float`, `Bool`, `List`, `Dict`, `Any`
- AST-only static check for dangerous imports and names
- presence of `def run(...)`
- exact match between `run` parameters and input port names
- description length of 10-200 characters

The generated files are:

```text
nodes/learned/<Name>/
  node.py
  manifest.json
```

## Execution Model

Built-in `@node` functions execute in the host Python process. Learned nodes do
not. They are registered in the same node registry, but their implementation is
a wrapper that delegates to `blacknode.sandbox.docker_runner.run_in_container`.

That wrapper reads `node.py` as text and sends it to a fresh Docker container.
The user code is imported and executed only inside the container runner.

## Editor Behavior

When `create_node_type` succeeds, the MCP tool notifies the editor backend. The
backend broadcasts a Server-Sent Event, and the frontend refreshes:

- `/learned-nodes`
- `/node-defs`
- the **Learned** palette category
- the read-only **Learned Nodes** sidebar tab

Newly added learned nodes pulse briefly in the palette so the user can see the
new capability appear without restarting the editor.

The sidebar is intentionally read-only. Edit learned nodes in files on disk, not
through the UI.

## Running

Learned nodes require Docker Desktop or a compatible Docker daemon.

```powershell
blacknode doctor
```

`blacknode doctor` reports Docker reachability, whether
`blacknode-sandbox:latest` is present, how many learned nodes are loaded, and the
last sandbox run duration recorded in the current process.

Run the camera-demo dry run:

```powershell
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
python scripts\demo_dry_run.py
```

The script starts the editor backend when needed, creates a temporary learned
RSS parser through MCP, verifies it appears in `/learned-nodes`, runs a workflow
through the Docker sandbox, and deletes the node.
