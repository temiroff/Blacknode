# Workflow Schema

Blacknode workflow files are portable JSON documents that describe graph structure. They must not contain API keys, transient cook status, cached node results, or run logs.

The canonical schema lives at [`docs/workflow.schema.json`](workflow.schema.json).

## Version 1

Version 1 keeps the editor's current graph shape and adds a stable header:

```json
{
  "kind": "blacknode.workflow",
  "schema_version": 1,
  "name": "Text Pipeline",
  "saved_at": "2026-05-20T12:00:00",
  "entrypoint": { "node_id": "out", "port": "value" },
  "node_meta": {},
  "edges": []
}
```

Required top-level fields:

| Field | Type | Purpose |
|---|---|---|
| `kind` | string | Must be `blacknode.workflow`. |
| `schema_version` | number | Must be `1` for this schema. |
| `name` | string | Human-facing workflow name. |
| `saved_at` | string | ISO 8601 timestamp written by the editor server. |
| `node_meta` | object | Map of node ID to node metadata. |
| `edges` | array | Connections between node ports. |

Optional top-level fields:

| Field | Type | Purpose |
|---|---|---|
| `entrypoint` | object | Preferred node and port for CLI execution. If omitted, a validator or runner may infer an `Output` node. |
| `metadata` | object | Extra JSON metadata that does not affect execution. |

## Node Metadata

Each `node_meta` entry stores the editor/runtime-neutral description of one node:

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Node ID. Must match the key in `node_meta`. |
| `type` | string | Registered Blacknode node type, such as `Text`, `LLMAgent`, or `SubnetAsTool`. |
| `params` | object | JSON-serializable node parameters. |
| `pos` | `[number, number]` | Editor canvas position. |
| `inputs` | string array | Input port names. |
| `outputs` | string array | Output port names. |
| `input_types` | object | Map of input port name to port type. |
| `output_types` | object | Map of output port name to port type. |
| `input_defaults` | object | JSON-serializable default values for input ports. |

Optional node fields:

| Field | Type | Purpose |
|---|---|---|
| `multi_input_ports` | string array | Dynamic ports that accept multiple connections. |
| `subgraph` | object | Nested graph for `Subnet`, `SubnetAsTool`, and `VisualAgentLoop` nodes. |
| `metadata` | object | Extra JSON metadata that does not affect execution. |

Runtime-only fields such as `cookResult`, `cookError`, `cooking`, and `cookPort` are intentionally excluded.

## Workflow Templates

Reusable editor templates live in `templates/*.json` and use this same workflow format. Template metadata is stored in the optional `metadata` object:

```json
{
  "metadata": {
    "template": true,
    "description": "Concatenate two strings and print",
    "color": "#0891b2"
  }
}
```

Because templates are ordinary workflow files, they can be checked with:

```powershell
blacknode validate .\templates\text-pipeline.json
blacknode export-python .\templates\text-pipeline.json --output .\workflow.py
```

From a repo checkout where Blacknode is not installed as a package yet, set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli validate templates\text-pipeline.json
python -m blacknode.cli export-python templates\text-pipeline.json --output workflow.py
python workflow.py
```

`text-pipeline.json` prints `Hello World`. A tool/subgraph template can be tested the same way:

```powershell
$env:PYTHONPATH="python"
python -m blacknode.cli export-python templates\subnet-tool-call.json --output subnet_tool_call.py
python subnet_tool_call.py
```

That exported script prints `59.0`. LLM templates export the same way, but running them requires the relevant model provider API key.

The repository also includes `examples/converted_text_pipeline.py` and `examples/converted_nvidia_nim.py` as checked-in Python exports of template workflows. The NIM example requires a NVIDIA API key when run outside tests.

The editor's Workflows tab saves personal files under `workflows/`, which is ignored by git. Copy a saved workflow JSON into `templates/` when it should become a shared starter template.

## Edges

Each edge connects one output port to one input port:

```json
{
  "from": "text",
  "from_port": "value",
  "to": "out",
  "to_port": "value"
}
```

## Validation Rules

The JSON Schema validates document shape. The semantic validator lives in `blacknode.workflow`:

```python
from blacknode.workflow import validate_workflow

report = validate_workflow(workflow_data)
if not report.ok:
    print(report.to_dict())
```

The editor server also exposes validation reports:

```text
GET /validate
GET /workflows/{slug}/validate
```

The command-line interface uses the same validator and runtime:

```powershell
blacknode validate workflow.json
blacknode run workflow.json --output result.json
blacknode export-python workflow.json --output workflow.py
```

## Run Results

`blacknode run` writes a structured result object. This is intentionally separate from saved workflow files, so portable workflows stay free of run logs, cached values, and transient errors.

```json
{
  "run_id": "e5e7b3e2-77a0-40c3-bbd7-02c22b61d5d2",
  "node_id": "out",
  "port": "value",
  "value": "hello",
  "events": [
    {
      "type": "node_finish",
      "run_id": "e5e7b3e2-77a0-40c3-bbd7-02c22b61d5d2",
      "node_id": "agent",
      "node_type": "LLMAgent",
      "port": "text",
      "duration_ms": 118.42,
      "output_ports": ["text"],
      "cached": false
    }
  ]
}
```

Top-level result fields:

| Field | Purpose |
|---|---|
| `run_id` | Unique ID shared by every event emitted during the run. |
| `node_id` / `port` | Cooked entrypoint. |
| `value` | Final cooked value returned from the entrypoint port. |
| `events` | Ordered event log for the run. |

The `events` array includes:

| Event | Purpose |
|---|---|
| `run_start` / `run_finish` / `run_error` | Run-level lifecycle. |
| `node_start` / `node_finish` / `node_error` | Node execution lifecycle with `duration_ms`. |
| `model_call` | Model invocation metadata, including model/provider/action. |
| `tool_call` | Tool invocation metadata, including tool name and JSON arguments. |

Errors raised by the runtime keep the same structured events on `WorkflowRunError.events`, including `node_error` and `run_error`.

Semantic validation enforces:

- every `node_meta` key equals its node's `id`
- every edge references existing `from` and `to` nodes
- every edge references existing source and target ports
- source and target port types are compatible
- node IDs are unique within each graph or subgraph
- `entrypoint.node_id` exists and `entrypoint.port` can be cooked
- workflow files do not include secrets or runtime-only status fields
- top-level graphs include an `Output` node or explicit `entrypoint`
- nested subgraphs include a `SubnetOutput` node

## Compatibility

The editor server can still load old workflow files that only contain `name`, `saved_at`, `node_meta`, and `edges`. New saves write the v1 header.
