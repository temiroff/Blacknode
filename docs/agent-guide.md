# Blacknode Agent Guide

This guide is for AI agents and contributors that need to inspect, create, validate, run, export, or share Blacknode workflows.

## Current Contract

Blacknode workflows are portable JSON graph files. They are meant to run outside the browser editor through the Python runtime and CLI.

The current stable pieces are:

- workflow schema: `docs/workflow.schema.json`
- schema docs: `docs/workflow-schema.md`
- reusable templates: `templates/*.json`
- local user saves: `workflows/*.json`
- CLI: `python -m blacknode.cli`
- converted examples: `examples/converted_text_pipeline.py`, `examples/converted_nvidia_nim.py`
- validation/runtime module: `python/blacknode/workflow.py`
- MCP smoke prompts: `docs/mcp-test-prompts.md`

## File Rules

Use these paths consistently:

| Path | Purpose | Git status |
|---|---|---|
| `templates/*.json` | Shared reusable workflow templates | tracked |
| `workflows/*.json` | User-saved local workflows from the editor | ignored |
| `nodes/learned/*.py` | User-created learned nodes generated through MCP | ignored |
| `examples/learned/*` | Reference learned-node examples | tracked |
| `examples/*.py` | Human-readable Python examples | tracked |
| `docs/*.md` | Project documentation | tracked |
| `editor-server/blacknode_graph.json` | Last local editor session | ignored |
| `editor-server/api_keys.json` | Local saved provider keys | ignored |
| `workflow.py` | Common temporary export output | local unless intentionally added |

Do not commit local planning notes, generated scratch exports, API keys, run logs, cached results, or editor session state.

## Core Concepts

- Workflow: a JSON document with `kind: "blacknode.workflow"` and `schema_version: 1`.
- Node: one graph operation stored in `node_meta` with ID, type, params, position, ports, and port types.
- Port: a named input or output on a node, with a type such as `Text`, `Float`, `Dict`, `Fn`, `Model`, or `Any`.
- Edge: a connection from one output port to one input port.
- Entrypoint: the node and port cooked by the CLI. Prefer an explicit `entrypoint`.
- Output node: terminal node used by the editor and inferred by the CLI when there is exactly one.
- Subnet: nested workflow graph inside a node.
- Template: a tracked workflow JSON file in `templates/` with `metadata.template: true`.
- Learned node: a reusable MCP-created node type stored on disk and executed in
  Docker through the learned-node wrapper.
- Managed runtime service: a camera/CUDA stream, persistent controller, ROS
  process, or robot driver that continues after its starting cook completes.

## One-Shot Cooks And Managed Services

`run_workflow` and `cook_editor_node` each evaluate a graph target once. A
managed node can start a background service during that cook, but frames,
detections, joint feedback, and commands must flow through the service rather
than repeatedly re-cooking the graph.

Examples include `CV2CameraStream`, `CV2ColorObjectStream`,
`CUDAImageFilterStream`, robot-driver nodes, and
`ROS2ContinuousFollowDetectionJoint`.

For MCP-controlled demos:

1. Cook the persistent template or target once.
2. Call `get_editor_runtime_status` and verify the expected services are active.
3. Keep robot motion disarmed until the user explicitly authorizes it.
4. Call `stop_editor_runtime_services` on an explicit stop request, at the end
   of the physical demo, or when continued motion is unsafe.
5. Re-check runtime status after stopping.

The stop tool uses each package's normal shutdown path. A robot driver may
disable actuator torque, so support the arm when gravity could move it.

## Learned Nodes vs PythonFn

Default rule: inspect the catalog first, use built-in nodes when they solve the
task exactly, and create a learned node when a reusable missing capability is
needed. Do not treat brittle approximations as matches; for example, generic
regex extraction is not a structural RSS parser if the requested output is only
article titles.

Use `PythonFn` for one-shot code that belongs only to the current workflow.
Examples: a tiny adapter between two ports, a temporary formatting expression,
or exploratory code that should travel with one graph.

Use `create_node_type` when the capability is general and reusable across
workflows. Examples: parsing RSS, extracting a domain-specific CSV format,
normalizing a recurring API response, or wrapping a stable local calculation.

Before creating a learned node:

- call `list_nodes` and `get_node_schema` to confirm no built-in node fits
- do not create or modify files under `nodes/learned` directly; use
  `create_node_type`, `list_learned_nodes`, `get_learned_node_source`,
  `promote_learned_node`, and `delete_learned_node`
- keep the interface small and typed with `Text`, `Int`, `Float`, `Bool`,
  `List`, `Dict`, or `Any`
- set `requires_network=False` unless the code must reach the network
- set a useful `category` so the node lands in the right palette group instead
  of the default `Learned`
- generate only a `def run(...)` function and make sure its parameters match the
  declared input ports
- after creation, call `list_learned_nodes`, use the learned node in the visual
  workflow, validate the graph, open it in the editor, and cook the final
  `Output` node
- remember that learned-node code never runs in the host process; it runs in the
  Docker sandbox wrapper

Do not ask the editor to edit learned nodes. The UI is read-only by design; the
plain files in `nodes/learned/<Name>/` are the editing contract.

Promote stable learned nodes with `promote_learned_node` instead of moving files
by hand. Promotion writes a normal `@node` module into `custom-nodes/` or
`community-nodes/` and removes the learned-node source unless `keep_learned=True`
is requested.

## Workflow JSON Shape

A workflow file must include full node metadata, not just node type names.

Required top-level fields:

```json
{
  "kind": "blacknode.workflow",
  "schema_version": 1,
  "name": "Text Pipeline",
  "saved_at": "2026-05-20T00:00:00",
  "entrypoint": { "node_id": "out", "port": "value" },
  "node_meta": {},
  "edges": []
}
```

Each node should include:

- `id`
- `type`
- `params`
- `pos`
- `inputs`
- `outputs`
- `input_types`
- `output_types`
- `input_defaults`
- optional `subgraph`
- optional `metadata`
- optional `multi_input_ports`

When creating a workflow programmatically, start from an existing template or from editor output so ports stay complete and valid.

## Validation Commands

From a repo checkout:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli doctor
python -m blacknode.cli demo
python -m blacknode.cli validate templates\text-pipeline.json
```

Expected success:

```text
Blacknode demo OK
Result: Hello World
```

```json
{
  "ok": true,
  "errors": [],
  "warnings": []
}
```

Validate every tracked template through tests:

```powershell
python -m unittest tests.test_templates -v
```

## Run And Export

Run a workflow and write structured output:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli run templates\text-pipeline.json --output result.json
```

Export a workflow to Python:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli export-python templates\text-pipeline.json --output workflow.py
python workflow.py
```

`templates\text-pipeline.json` prints:

```text
Hello World
```

Tool/subgraph export example:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli export-python templates\subnet-tool-call.json --output subnet_tool_call.py
python subnet_tool_call.py
```

Expected output:

```text
59.0
```

LLM templates export the same way, but running them requires the relevant provider key.

## Run Logs

`blacknode run` returns a structured result with:

- `run_id`
- `node_id`
- `port`
- `value`
- `events`

Event types include:

- `run_start`
- `run_finish`
- `run_error`
- `node_start`
- `node_finish`
- `node_error`
- `model_call`
- `tool_call`

Run logs are output artifacts. They must not be saved back into workflow JSON.

## Secrets

Workflow JSON must not contain API keys.

Use these instead:

- environment variables such as `NVIDIA_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`
- editor-saved local keys in `editor-server/api_keys.json`

`editor-server/api_keys.json` is ignored by git.

## Template Workflow

To make a new shared template:

1. Build and save the workflow in the editor.
2. Find the saved JSON under `workflows/`.
3. Copy it into `templates/` with a clear slug, for example `templates/my-agent.json`.
4. Add or verify:
   - `kind: "blacknode.workflow"`
   - `schema_version: 1`
   - `entrypoint`
   - `metadata.template: true`
   - `metadata.description`
   - `metadata.color`
5. Run validation:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli validate templates\my-agent.json
python -m blacknode.cli export-python templates\my-agent.json --output workflow.py
```

6. Add a focused test if the template should be guaranteed.
7. Commit the template only after validation passes.

Do not commit the local `workflows/` copy unless the user explicitly wants local saves tracked.

## Common Patterns

LLM Chat:

- `Model` -> `LLMAgent.model`
- `Text` system -> `LLMAgent.system`
- `Text` prompt -> `LLMAgent.prompt`
- `LLMAgent.text` -> `Output.value`

NVIDIA NIM:

- use model string `nim:meta/llama-3.1-8b-instruct`
- requires `NVIDIA_API_KEY` or editor-saved NVIDIA NIM key

Python Tool Agent:

- `PythonFn.fn` -> `ToolBox.tool_1`
- `ToolBox.tools` -> `AgentLoop.tools`
- prompt/system/model -> `AgentLoop`
- `AgentLoop.result` -> `Output.value`

Subnet Tool:

- create `SubnetAsTool`
- inside it, use `SubnetInput` for tool arguments
- use `SubnetOutput` for returned value
- connect outer `SubnetAsTool.fn` into `ToolBox` or `ToolCall`

Visual Agent Loop:

- use `VisualAgentLoop` when a graph should show the agent-loop internals
- runtime behavior matches `AgentLoop`

## MCP Editor Smoke Tests

Use `docs/mcp-test-prompts.md` when verifying the MCP server from an agent
client. MCP exposes read-only resources for quick context:

- `blacknode://nodes`
- `blacknode://templates`
- `blacknode://workflows`
- `blacknode://editor/graph`
- `blacknode://runtime/status`

The NVIDIA NIM prompts exercise the full live-editor path:

- build workflow JSON through MCP tools
- validate the graph
- open it as a new organized editor tab
- cook `out.value` in the running editor
- inspect and save the currently loaded editor graph
- list and reopen saved workflows by slug
- organize, rename, and close live editor tabs

For tracked templates, prefer `run_template_in_editor` when the task is simply
"open this template, organize it, and optionally cook it." Use the lower-level
`load_workflow`, `validate_workflow`, `open_workflow_in_editor_tab`, and
`cook_editor_node` calls when the agent needs to inspect or modify the graph
before opening it.

The live editor tools require `editor-server/server.py` to be running at
`http://127.0.0.1:7777` or `BLACKNODE_EDITOR_URL` to point at the backend.
Use `get_editor_runtime_status` for managed services and
`stop_editor_runtime_services` for a safe global runtime shutdown.

## Editing Checklist For Agents

Before changing workflows or templates:

1. Check `git status -sb`.
2. Leave unrelated user files alone, especially untracked generated exports.
3. Use existing templates as examples.
4. Preserve full node metadata and edge fields.
5. Keep secrets out of JSON.

After changing workflows or templates:

```powershell
python -m unittest tests.test_templates -v
python -m unittest discover -s tests -v
```

After changing frontend template loading:

```powershell
cd editor
npm run build
```

Before committing:

```powershell
git diff --check
git status -sb
```

## Useful Source Files

- `python/blacknode/workflow.py`: validation, runtime execution, Python export, structured run logs.
- `python/blacknode/graph.py`: lazy graph execution engine.
- `python/blacknode/node.py`: node decorator and port parsing.
- `python/blacknode/nodes/*.py`: built-in node implementations and port definitions.
- `editor-server/server.py`: editor persistence, workflow routes, template routes.
- `editor/src/components/TemplateGallery.tsx`: UI that lists and loads tracked templates.
- `editor/src/api.ts`: frontend API client.
- `tests/test_templates.py`: template validation/export coverage.
- `tests/test_examples.py`: runnable example coverage with stubbed external calls.

## When Unsure

Prefer this order:

1. Copy or adapt an existing valid template.
2. Validate the workflow.
3. Export it to Python.
4. Run the exported script when it does not require live external services.
5. Add or update tests.

Do not invent a new file format until the existing workflow JSON schema cannot represent the use case.
