# Framework Export

Blacknode keeps the visual workflow as the source of truth and exports the same
typed graph into other agent frameworks when you want to run or extend it
outside the editor.

## Editor

1. Start Blacknode with `start.bat` on Windows or `./start.sh` on macOS/Linux.
2. Open or build a workflow that ends in an `Output` or `OutputImage` node.
3. Press `Export` in the top bar.
4. Choose `Plain Python`, `Python Class`, `LangGraph`, `CrewAI`, `AutoGen`, `OpenAI Swarm`, or `NVIDIA Agent Stack`.
5. The generated file downloads from the browser.

Editor export infers an entrypoint for common multi-output graphs. It preserves
an explicit workflow `entrypoint` when one exists, otherwise it prefers visible
display nodes such as `overlay_out.image`, `reason_dashboard_out.image`, and
other `OutputImage` nodes before falling back to an `Output.value` node. This
keeps live robotics/vision dashboards exportable even when the graph contains
several output panels.

## CLI

Export a LangGraph `StateGraph`:

```powershell
blacknode export-framework templates\text-pipeline.json --target langgraph --output workflow.langgraph.py
```

Export plain Blacknode Python:

```powershell
blacknode export-framework templates\text-pipeline.json --target python --output workflow.python.py
blacknode export-framework templates\text-pipeline.json --target python-class --output workflow.class.py
```

Import a Blacknode Python export back into workflow JSON:

```powershell
blacknode import-python workflow.python.py --output imported.workflow.json
blacknode import-python workflow.langgraph.py --output imported-langgraph.workflow.json
```

The editor `Import` button and canvas file drop use the same importer, so
Blacknode-generated Python and LangGraph files can be reopened as visual
workflow tabs.

For CLI exports, workflow JSON should still include an explicit `entrypoint`
when it has multiple `Output` nodes. The editor adds one automatically for the
current graph before calling the same exporter.

Export framework maps:

```powershell
blacknode export-framework templates\text-pipeline.json --target crewai --output workflow.crewai.py
blacknode export-framework templates\text-pipeline.json --target autogen --output workflow.autogen.py
blacknode export-framework templates\text-pipeline.json --target swarm --output workflow.swarm.py
blacknode export-framework templates\text-pipeline.json --target nvidia-agent-stack --output workflow.nvidia-agent-stack.py
```

## HTTP

List targets:

```powershell
Invoke-RestMethod http://127.0.0.1:7777/export/frameworks
```

Export the current editor graph:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:7777/export/framework `
  -ContentType application/json `
  -Body '{"target":"langgraph"}'
```

Direct non-MCP workflow API:

| Endpoint | Purpose |
|---|---|
| `GET /api/workflows/current` | Current workflow JSON plus validation. |
| `POST /api/workflows/current/nodes` | Add a node with `type_name`, `params`, and `pos`. |
| `POST /api/workflows/current/edges` | Connect two ports. |
| `GET /api/workflows/current/validate` | Validate the current workflow. |
| `POST /api/workflows/current/run` | Cook a selected node and port. |
| `POST /api/workflows/current/export` | Export the current workflow to a framework target. |
| `POST /api/workflows/current/import-python` | Import a Blacknode Python export into workflow JSON. |
| `WS /api/workflows/current/ws` | WebSocket state, validation, and export actions. |

## Target Behavior

| Target | Output |
|---|---|
| `python` | Runnable Blacknode `bn.Graph()` script with round-trip metadata and optional live sync. |
| `python-class` | Runnable class-based Blacknode script for cleaner embedding. |
| `langgraph` | LangGraph `StateGraph` with `START`, `END`, node functions, edges, and final result print. |
| `crewai` | CrewAI task descriptors mapped from Blacknode nodes and upstream context. |
| `autogen` | AutoGen agent descriptors with handoff targets from graph edges. |
| `swarm` | OpenAI Swarm-style handoff descriptors from graph edges. |
| `nvidia-agent-stack` | AI-Q, NeMo Agent Toolkit, and NIM integration manifest with MCP commands and readable workflow steps. |
