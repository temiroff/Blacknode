---
name: blacknode-workflow
description: >
  Use this skill when the task asks an agent to create, edit, validate, run,
  export, debug, visualize, or open Blacknode workflows. Trigger phrases include
  Blacknode, visual workflow, node graph, MCP workflow builder, run replay,
  NVIDIA NIM workflow, workflow JSON, open in editor, and export to Python.
---

# Blacknode Workflow

Blacknode is the visual workflow layer for agent harnesses. Use it when a chat
or coding agent needs a typed node graph instead of raw JSON or ad hoc scripts.

## When to Use

Use this skill for:

- Building a new workflow graph from a user request.
- Loading, validating, or repairing `blacknode.workflow` JSON.
- Opening a workflow in the running visual editor.
- Running a workflow or template and inspecting the structured event log.
- Exporting a workflow to readable Python.
- Creating NVIDIA NIM, local NIM, RAG, tool-agent, or research-pipeline demos.

Use the ordinary answer path for prose-only questions. Use this skill when the
workflow artifact, editor state, run trace, or exported Python matters.

## Available Surfaces

Preferred MCP stdio command:

```bash
blacknode mcp
```

Streamable HTTP command for AI-Q or NeMo Agent Toolkit MCP clients:

```bash
blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp
```

Visual editor:

```bash
./start.sh
```

On Windows:

```powershell
start.bat
```

CLI checks:

```powershell
blacknode doctor
blacknode validate templates\text-pipeline.json
blacknode run templates\text-pipeline.json
blacknode export-python templates\text-pipeline.json --output workflow.py
```

## MCP Flow

1. Call `list_nodes` to inspect node types and ports.
2. Call `list_templates` when the task may match a shipped starter graph.
3. Prefer `run_template_in_editor` for demo paths that should appear in the UI.
4. For custom graphs, call `create_workflow`, `add_node`, and `connect_nodes`.
5. Call `validate_workflow` after each meaningful mutation.
6. Call `run_workflow` for headless execution or `cook_editor_node` for live UI execution.
7. Call `list_recent_runs` and `get_run` to inspect replay events, model calls, tool calls, and errors.
8. Call `export_python` when the user needs a handoff script.

Every mutation should be followed by validation. If validation reports a port
or type error, inspect `get_node_schema` and fix the graph instead of guessing.

## NVIDIA Workflow Pattern

For an NVIDIA demo, prefer these templates first:

- `nvidia-ai-mission-control`
- `nvidia-video-intelligence-mission-control`
- `nvidia-local-nim-launch`
- `nvidia-nim-benchmark`
- `nvidia-nim-mcp-demo`

Use hosted NIM for the fastest path:

```powershell
$env:NVIDIA_API_KEY="..."
```

Use local NIM when the user wants an on-prem or workstation story:

1. Open `nvidia-local-nim-launch`.
2. Cook the PowerShell or Bash output.
3. Start the generated Docker command in a terminal.
4. Point `NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark` at the local endpoint.

Keep local NIM container startup explicit: generate the command, show the
endpoint, and run it only when the user asks for container startup.

## File Rules

- Shared templates live in `templates/*.json`.
- Local user saves live in `workflows/*.json`.
- Run records live under `editor-server/runs/`.
- Keep API keys, run logs, editor session state, and scratch exports out of
  commits.
- Workflow JSON must keep `kind: "blacknode.workflow"` and `schema_version: 1`.

## Verification

After changing workflows or node behavior:

```powershell
python -m unittest discover -s tests
```

After changing the editor:

```powershell
cd editor
npm run build
```

After changing Rust:

```powershell
cargo test
```
