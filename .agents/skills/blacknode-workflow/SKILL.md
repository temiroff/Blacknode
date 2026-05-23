---
name: blacknode-workflow
description: >
  Use this skill when the task asks an agent to create, edit, validate, run,
  export, debug, visualize, extend, or open Blacknode workflows. Trigger phrases
  include Blacknode, visual workflow, node graph, MCP workflow builder, run
  replay, NVIDIA NIM workflow, workflow JSON, custom node, open in editor, and
  framework export.
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
- Exporting or importing a workflow with Python round-trip, LangGraph, CrewAI, AutoGen, Swarm, or NVIDIA Agent Stack.
- Creating persistent custom nodes and community node packs.
- Creating NVIDIA NIM, local NIM, RAG, tool-agent, or research-pipeline demos.

Use the ordinary answer path for prose-only questions. Use this skill when the
workflow artifact, editor state, run trace, custom node, or framework export matters.

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
blacknode import-python workflow.py --output imported.workflow.json
blacknode export-framework templates\text-pipeline.json --target langgraph --output workflow.langgraph.py
blacknode import-python workflow.langgraph.py --output imported-langgraph.workflow.json
blacknode export-framework templates\text-pipeline.json --target nvidia-agent-stack --output workflow.nvidia-agent-stack.py
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
9. Use `blacknode import-python` or `/import/python` when a Python or LangGraph export should be restored as a visual graph.

Every mutation should be followed by validation. If validation reports a port
or type error, inspect `get_node_schema` and fix the graph instead of guessing.

## Agent Build Prompt

When an agent builds a workflow, use this operating prompt:

```text
You are building a typed Blacknode workflow. Keep planning reasoning internal,
then return a concise graph plan with node ids, node types, key params, edges,
entrypoint, and expected result.

Build loop:
1. Understand the user goal and choose the smallest runnable graph.
2. Inspect list_nodes or get_node_schema before using unfamiliar nodes.
3. Create or load a workflow.
4. Add nodes with stable, descriptive ids.
5. Connect only declared output ports to declared input ports.
6. Validate after each meaningful mutation.
7. If validation fails, read the code, path, message, and suggestion, then fix
   the graph instead of retrying the same edge.
8. Run the final Output or explicit entrypoint.
9. Open the workflow in the editor when the user needs visual proof.
10. Export Python or a framework target only after validation is clean.
```

## Node Catalog Quick Map

Use `list_nodes` for the live catalog. Current core groups:

| Category | Use for | Common nodes |
|---|---|---|
| Values | Constants and model handles | `Text`, `Int`, `Float`, `Bool`, `Dict`, `Model` |
| Core | Basic graph composition and output | `Concat`, `Output`, `Print`, `Switch`, `Literal`, `ForEach` |
| AI | LLM calls, agent loops, tool calls | `LLMAgent`, `PythonFn`, `ToolCall`, `ToolBox`, `AgentLoop`, `EmbedText` |
| NVIDIA | Hosted/local NIM and NVIDIA demo flows | `NIMAgent`, `NIMBenchmark`, `NIMDockerCommand`, `NIMHealthCheck`, `NVIDIASystemCheck` |
| RAG | Chunking, simple indexing, retrieval context | `TextChunker`, `KeywordIndex`, `KeywordSearch`, `RAGContext` |
| IO | Files, folders, HTTP, JSON, CSV | `FileRead`, `FileWrite`, `DirectoryList`, `HTTPGet`, `JSONParse`, `JSONDump`, `CSVRead`, `CSVWrite` |
| API | HTTP request construction | `APIRequestBuilder`, `HTTPRequest` |
| Database | SQLite operations | `SQLiteQuery`, `SQLiteExec` |
| Flow | Data routing and collection transforms | `Branch`, `Gate`, `Map`, `Filter`, `Reduce` |
| Search | Web/search result helpers | `WebSearchURL`, `SearchResultExtractor`, `SearchResultsFormat` |
| Routing | Model/provider choice | `LLMModelRouter` |
| Subnet | Visual subgraph boundaries | `SubnetInput`, `SubnetOutput`; build full `Subnet` nodes in the editor |

## Graph Reliability Rules

- Treat Blacknode workflows as DAGs. Do not create cycles or back-edges.
- Always connect from `outputs` to `inputs`; never invent port names.
- Respect types: `Any` accepts everything, exact type matches are valid, and
  Text/Number compatibility is limited by `ports_compatible`.
- Use adapter nodes when types do not match: `JSONParse`, `JSONDump`,
  `PythonFn`, `Concat`, `Branch`, `Gate`, or a purpose-built custom node.
- Keep ids stable and readable: `prompt`, `retriever`, `agent`, `report`,
  `out` are better than generated ids when constructing demos.
- Put the final user-visible value into an `Output` node or set an explicit
  `entrypoint`.
- Use `input_defaults` and params for fixed values; use edges for values that
  should come from upstream nodes.
- Do not save runtime-only fields such as `cookResult`, `cookError`,
  `cooking`, or `cookPort`.
- For NVIDIA demos, state clearly whether the workflow uses hosted NIM, a
  generated local NIM launch command, or a custom OpenAI-compatible endpoint.
- If MCP returns an error with `Suggestion:`, apply that suggestion before
  trying another mutation.

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
