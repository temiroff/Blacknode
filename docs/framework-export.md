# Framework Export

Blacknode keeps the visual workflow as the source of truth and exports the same
typed graph into other agent frameworks when you want to run or extend it
outside the editor.

## Editor

1. Start Blacknode with `start.bat` on Windows or `./start.sh` on macOS/Linux.
2. Open or build a workflow that ends in an `Output` node.
3. Press `Export` in the top bar.
4. Choose `Plain Python`, `LangGraph`, `CrewAI`, `AutoGen`, or `OpenAI Swarm`.
5. The generated file downloads from the browser.

## CLI

Export a LangGraph `StateGraph`:

```powershell
blacknode export-framework templates\text-pipeline.json --target langgraph --output workflow.langgraph.py
```

Export plain Blacknode Python:

```powershell
blacknode export-framework templates\text-pipeline.json --target python --output workflow.python.py
```

Export framework maps:

```powershell
blacknode export-framework templates\text-pipeline.json --target crewai --output workflow.crewai.py
blacknode export-framework templates\text-pipeline.json --target autogen --output workflow.autogen.py
blacknode export-framework templates\text-pipeline.json --target swarm --output workflow.swarm.py
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
| `WS /api/workflows/current/ws` | WebSocket state, validation, and export actions. |

## Target Behavior

| Target | Output |
|---|---|
| `python` | Runnable Blacknode `bn.Graph()` script. |
| `langgraph` | LangGraph `StateGraph` with `START`, `END`, node functions, edges, and final result print. |
| `crewai` | CrewAI task descriptors mapped from Blacknode nodes and upstream context. |
| `autogen` | AutoGen agent descriptors with handoff targets from graph edges. |
| `swarm` | OpenAI Swarm-style handoff descriptors from graph edges. |
