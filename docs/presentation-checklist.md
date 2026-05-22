# Blacknode Presentation Checklist

Use this as the fast live-demo order. It keeps the flow focused on proof:
local runtime, visual editor, run replay, NVIDIA workflows, MCP agent control,
and self-hosted deployment.

## Opening Position

Blacknode is the visual workflow editor for agent stacks. Agents are strong at
intent and reasoning; workflow construction needs typed structure, validation,
visible state, run history, and exportable artifacts.

Core identity:

```text
Blacknode turns agent intent into typed, visible, runnable workflows.
```

NVIDIA identity:

```text
Blacknode is the visual workflow editor for the NVIDIA agent stack.
```

## Quick Demo Order

| Step | Action | Proof |
|---:|---|---|
| 1 | Open README | Short intro, 2x2 image grid, playable demos, walkthrough link. |
| 2 | Run `blacknode doctor` | Colored `[OK]`, `[WARN]`, `[NOT OK]` environment status. |
| 3 | Run `blacknode demo` | Local runtime returns `Hello World`. |
| 4 | Start `start.bat` or `./start.sh` | Editor opens at `http://localhost:3000`. |
| 5 | Open **Templates** -> **Text Pipeline** -> **Cook** | Visible graph returns `Hello World`. |
| 6 | Build Text -> Text -> Concat -> Output by hand | Typed handles connect and validate visually. |
| 7 | Open **Runs** after cooking | Run history, event timeline, replay, result, errors. |
| 8 | Save in **Workflows** | Workflow becomes a reusable JSON artifact. |
| 9 | Open **NVIDIA Video Intelligence Mission Control** | No-key video stack plan: input, Cosmos/VLM, NeMo Retriever, NIM/Nemotron QA, deployment, report. |
| 10 | Open **NVIDIA AI Mission Control** | No-key NVIDIA workflow plan and readiness surface. |
| 11 | Open **NVIDIA Local NIM Launch** | Docker command and local endpoint wiring. |
| 12 | Open **NVIDIA NIM** with `NVIDIA_API_KEY` | Hosted NIM model result and model-call run events. |
| 13 | Open **NVIDIA NIM Benchmark** | Text, latency, metrics, and raw samples. |
| 14 | Run `blacknode mcp` | Agent can list nodes, inspect schemas, build, validate, run, export. |
| 15 | Run streamable HTTP MCP | AI-Q, NeMo Agent Toolkit, and HTTP MCP clients can connect. |
| 16 | Run Docker Compose | Self-hosted editor, backend, run store, and HTTP MCP endpoint. |

## Terminal Checks

### Local Runtime

```powershell
blacknode doctor
blacknode demo
```

Expected:

- Doctor prints colored status labels.
- Demo prints `Blacknode demo OK`.
- Demo result is `Hello World`.

### Validate, Run, Export

Windows:

```powershell
blacknode validate templates\text-pipeline.json
blacknode run templates\text-pipeline.json
blacknode export-python templates\text-pipeline.json --output workflow.py
python workflow.py
```

macOS/Linux:

```bash
blacknode validate templates/text-pipeline.json
blacknode run templates/text-pipeline.json
blacknode export-python templates/text-pipeline.json --output workflow.py
python workflow.py
```

Expected:

- Validation returns `"ok": true`.
- Run returns `"value": "Hello World"`.
- Exported Python prints `Hello World`.

## Editor Checks

### Template Run

1. Start the editor.
2. Open **Templates**.
3. Click **Text Pipeline**.
4. Click the Output node.
5. Click **Cook**.

Expected:

- Output node shows `Hello World`.
- Runs tab records the execution.
- Results on unrelated nodes stay visible until those nodes cook again.

### Manual Graph Build

1. Click **Clear**.
2. Add **Text**, **Text**, **Concat**, **Output**.
3. Set Text values to `Hello` and ` World`.
4. Connect Text `value` -> Concat `a`.
5. Connect Text `value` -> Concat `b`.
6. Connect Concat `value` -> Output `value`.
7. Click **Organize**.
8. Click **Cook** on Output.

Expected:

- Graph lays out cleanly.
- Typed handles match by color/type.
- Output shows `Hello World`.

### Workflow Save

1. Open **Workflows**.
2. Name the workflow.
3. Click **Save**.
4. Reopen it from the saved workflow list.
5. Right-click the row for **Insert**, **Rename**, **Duplicate**, **Delete**.

Expected:

- Saved workflow appears under `workflows/*.json`.
- Workflow can be reopened or inserted.

### Run Replay

1. Cook any workflow.
2. Open **Runs**.
3. Open the newest run.
4. Use step/play/scrub controls.
5. Use **Open workflow** when a run snapshot is available.

Expected:

- Node highlights follow the execution timeline.
- Model calls and tool calls are counted.
- Result or error is visible in the run record.

## NVIDIA Checks

### No-Key Planning

Windows:

```powershell
blacknode run templates\nvidia-ai-mission-control.json
blacknode run templates\nvidia-video-intelligence-mission-control.json
blacknode run templates\nvidia-local-nim-launch.json
```

macOS/Linux:

```bash
blacknode run templates/nvidia-ai-mission-control.json
blacknode run templates/nvidia-video-intelligence-mission-control.json
blacknode run templates/nvidia-local-nim-launch.json
```

Expected:

- Mission Control returns an NVIDIA stack plan.
- Video Intelligence Mission Control returns the folder input, Cosmos/VLM,
  NeMo Retriever, NIM/Nemotron QA, deployment, and report plan.
- Local NIM Launch returns Docker command text and endpoint output.

### Hosted NIM

Windows:

```powershell
$env:NVIDIA_API_KEY="your-key"
start.bat
```

macOS/Linux:

```bash
export NVIDIA_API_KEY="your-key"
./start.sh
```

Editor path:

1. Open **Templates**.
2. Click **NVIDIA NIM** or **NVIDIA NIM MCP Demo**.
3. Confirm the **Model** node uses a `nim:` model.
4. Click **Cook** on Output.
5. Open **Runs** and inspect model-call timing.

Expected:

- Output shows the NIM model response.
- Runs panel records model-call events.

### Local NIM

1. Open **Templates**.
2. Click **NVIDIA Local NIM Launch**.
3. Click **Cook**.
4. Copy the generated Docker command.
5. Start the NIM container in a separate terminal.
6. Point `NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark` at the local endpoint.

Expected:

- Local command and endpoint are generated in the graph.
- Same workflow surface can route to hosted or local NIM.

## MCP Checks

### Stdio MCP

```powershell
blacknode mcp
```

Agent prompt:

```text
Using the blacknode MCP tools, list the available node types, show the schema
for Text, Concat, and Output, then create a workflow that concatenates "Hello"
and " World", validates it, runs it, and exports it as Python.
```

Expected:

- Agent lists node types.
- Agent creates a typed workflow.
- Validation passes.
- Run returns `Hello World`.
- Export returns Python.

### Streamable HTTP MCP

```powershell
blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp
```

Endpoint:

```text
http://127.0.0.1:9901/mcp
```

Expected:

- Same Blacknode MCP tool surface over HTTP.
- AI-Q, NeMo Agent Toolkit, or another streamable HTTP MCP client can connect.

## Custom Node Check

1. Open **Script**.
2. Paste:

```python
from blacknode.node import node

@node(inputs=["text:Text", "n:Int"], outputs=["result:Text"])
def FirstNWords(ctx: dict) -> dict:
    words = ctx.get("text", "").split()
    n = int(ctx.get("n", 10))
    return {"result": " ".join(words[:n])}
```

3. Click **Run** or press **Ctrl+Enter**.
4. Add the new Custom node to the canvas.
5. Connect and cook it.

Expected:

- Custom node appears without server restart.
- Typed ports work like built-in nodes.

## Tool Workflow Checks

Templates:

- **Python Tool Agent**
- **Visual Tool Agent**
- **Subnet Tool Call**
- **Subnet Tool Agent**

Expected:

- `PythonFn` exposes Python code as a callable tool.
- `SubnetAsTool` turns a visual subgraph into a tool.
- `ToolBox` collects tools.
- `ToolCall` tests a tool directly.
- `AgentLoop` can call tools through the graph.

## Docker Check

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:3000
```

Services:

| Service | Port | Purpose |
|---|---:|---|
| `editor` | `3000` | Browser editor. |
| `editor-server` | `7777` | Backend, workflow store, run store, cook API. |
| `blacknode-mcp` | `9901` | Streamable HTTP MCP server at `/mcp`. |

Expected:

- Self-hosted editor works.
- Run history persists through the backend.
- HTTP MCP endpoint is available at `/mcp`.

## Closing Proof

Blacknode provides one visible workflow surface across:

- local CLI checks
- browser graph editing
- typed validation
- run replay
- model routing
- NVIDIA hosted and local NIM flows
- MCP agent control
- streamable HTTP MCP
- Docker Compose deployment
- Python export
