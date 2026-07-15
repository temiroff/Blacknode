# Blacknode Beginner Walkthrough

This is the click-by-click path for trying every main Blacknode feature. Start
with the no-key steps first, then add NVIDIA NIM, MCP, or Docker when the local
workflow is working.

## What You Need

| Tool | Version | Why |
|---|---:|---|
| Python | 3.11+ | Runs the workflow runtime, CLI, editor backend, and MCP server. |
| Node.js | 20.19+ or 22.12+ | Runs the visual editor. |
| npm | Ships with Node.js | Installs editor dependencies. |
| Docker | Optional | Runs the Compose stack and local NIM containers. |
| NVIDIA API key | Optional | Runs hosted NVIDIA NIM model calls. |

## 1. Open the Project Folder

Open a terminal in the Blacknode repository.

Windows:

```powershell
cd path\to\Blacknode
```

macOS/Linux:

```bash
cd path/to/Blacknode
```

## 2. Install Blacknode

Run this once. It installs the Python package, the `blacknode` command, and MCP
support.

Windows:

```powershell
pip install -e ".[mcp]"
cd editor-server
pip install -r requirements.txt
cd ..\editor
npm install
cd ..
```

macOS/Linux:

```bash
pip install -e ".[mcp]"
cd editor-server
pip install -r requirements.txt
cd ../editor
npm install
cd ..
```

What this does:

- `pip install -e ".[mcp]"` creates the `blacknode` terminal command from
  `pyproject.toml`.
- `editor-server` dependencies run the local backend on port `7777`.
- `editor` dependencies run the browser UI on port `3000`.

## 3. Check the Local Setup

Run:

```powershell
blacknode doctor
```

Expected result:

- Green `[OK]` means that part is ready.
- Red `[NOT OK]` means install or fix that required part.
- Yellow `[WARN] Editor server: not running` is normal before starting the
  editor.
- The final line should say `Required checks passed.`

## 4. Run the First Workflow Without the Browser

Run:

```powershell
blacknode demo
```

Expected result:

```text
Blacknode demo OK
Result: Hello World
```

Now validate, run, and export the same workflow:

Windows:

```powershell
blacknode validate templates\text-pipeline.json
blacknode run templates\text-pipeline.json
blacknode export-python templates\text-pipeline.json --output workflow.py
blacknode import-python workflow.py --output imported.workflow.json
python workflow.py
```

macOS/Linux:

```bash
blacknode validate templates/text-pipeline.json
blacknode run templates/text-pipeline.json
blacknode export-python templates/text-pipeline.json --output workflow.py
blacknode import-python workflow.py --output imported.workflow.json
python workflow.py
```

Expected result:

- `validate` returns `"ok": true`.
- `run` returns a JSON result with `"value": "Hello World"`.
- `import-python` recreates workflow JSON from the exported Python file.
- `python workflow.py` prints `Hello World`.

## 5. Start the Visual Editor

Windows:

```bat
start.bat
```

macOS/Linux:

```bash
chmod +x start.sh
./start.sh
```

Expected result:

- Backend starts at `http://127.0.0.1:7777`.
- Editor starts at `http://localhost:3000`.
- Browser opens automatically when possible.
- If an old Blacknode editor is already on port `3000`, the launcher restarts
  it and keeps the same URL.

If the browser does not open, open this manually:

```text
http://localhost:3000
```

## 6. Load and Run a Template in the Editor

In the browser:

1. Look at the left sidebar.
2. Click the **Templates** tab.
3. Click **Text Pipeline**.
4. Click the **Output** node on the canvas.
5. In the right **Properties** panel, click **Cook**.

Expected result:

- The Output node shows `Hello World`.
- A small run status appears while the graph cooks once.
- The run is saved in the **Runs** tab.

## 7. Build the Same Workflow by Hand

In the editor:

1. Click **Clear** in the top bar.
2. Right-click the empty canvas.
3. Search for `Text`.
4. Click **Text** or press Enter.
5. Click the new Text node and set `value` to `Hello`.
6. Add a second **Text** node and set `value` to ` World`.
7. Add a **Concat** node.
8. Add an **Output** node.
9. Drag from the first Text `value` handle to Concat `a`.
10. Drag from the second Text `value` handle to Concat `b`.
11. Drag from Concat `value` to Output `value`.
12. Click **Organize** in the top bar.
13. Click **Cook** on the Output node.

Expected result:

- The graph lays out cleanly.
- The Output node shows `Hello World`.
- The connection handles stay color-coded by type.

Useful edit controls:

- Press **Ctrl+Z** to undo.
- Select a line and press **Delete** or **Backspace** to remove it.
- Double-click a line to remove it immediately.
- Hold **Alt** while dragging a node to clone it.
- Press **Ctrl+C** and **Ctrl+V** to copy and paste selected nodes.

## 8. Save, Reopen, Duplicate, and Insert Workflows

In the left sidebar:

1. Click the **Workflows** tab.
2. Type a name such as `Hello World Test`.
3. Click **Save**.
4. Click the saved workflow row to reopen it in a tab.
5. Right-click the saved workflow row to see **Insert**, **Rename**,
   **Duplicate**, and **Delete**.

Expected result:

- Saved workflows appear in `workflows/*.json`.
- Clicking a workflow opens it as a tab.
- **Insert** drops a saved graph into the current canvas.

File import:

- Drag a Blacknode `.json` workflow onto the canvas to open it in a new tab.
- Drag a Blacknode-generated `.py` export, including LangGraph, onto the canvas
  to restore it as a visual workflow.

## 9. Inspect Run History and Replay

After any cook:

1. Click the **Runs** tab in the left sidebar.
2. Click the newest run row.
3. Look at status, duration, node count, model calls, and tool calls.
4. Use the replay controls to step or play through the execution.
5. Click **Open workflow** when a run has a saved workflow snapshot.

Expected result:

- The canvas highlights nodes as replay moves through events.
- Model calls and tool calls are counted.
- Successful runs show the returned value.
- Error runs show the error event and traceback.

Run records are written to:

```text
editor-server/runs/
```

## 10. Add API Keys for Model Workflows

In the editor:

1. Add a **Model** node from the **AI** category or load an LLM template.
2. Pick a model from the dropdown.
3. Paste the provider API key into the key field.
4. Click the eye button to verify the key.
5. Press Enter or click away to save.

Provider keys:

| Provider | Key |
|---|---|
| NVIDIA NIM | `NVIDIA_API_KEY` from https://build.nvidia.com |
| OpenAI | `OPENAI_API_KEY` from https://platform.openai.com/api-keys |
| Anthropic | `ANTHROPIC_API_KEY` from https://console.anthropic.com |

Expected result:

- The key is saved in browser local storage for that provider.
- The editor sends the key to the local backend for model calls.
- The workflow result appears on the cooked node.

## 11. Try NVIDIA Planning Workflows Without an API Key

These templates prove the NVIDIA workflow surface before you call a hosted
model.

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

Expected result:

- **NVIDIA AI Mission Control** returns a workflow plan and local readiness
  information.
- **NVIDIA Video Intelligence Mission Control** returns a video workflow plan
  for folder input, Cosmos/VLM understanding, NeMo Retriever indexing,
  NIM/Nemotron QA, deployment routing, and final report output.
- **NVIDIA Local NIM Launch** returns a Docker command and endpoint path.

In the editor:

1. Open **Templates**.
2. Click **NVIDIA Video Intelligence Mission Control** or **NVIDIA AI Mission Control**.
3. Click **Cook** on the Output node.
4. Open **Runs** and inspect the recorded execution.

## 12. Run Hosted NVIDIA NIM

Set a key in the editor Model node, or set it in the terminal before starting
the backend.

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

In the editor:

1. Open **Templates**.
2. Click **NVIDIA NIM** or **NVIDIA NIM MCP Demo**.
3. Click the **Model** node and confirm the NVIDIA model.
4. Click **Cook** on the Output node.
5. Open **Runs** and check model-call timing.
6. Open **NVIDIA NIM Benchmark** when you want repeated calls and latency
   metrics.

Expected result:

- The graph routes through NVIDIA NIM.
- The Output node shows the model response.
- The Runs panel records model-call events.
- The benchmark template returns text, latency, and metrics for the endpoint.

## 13. Generate a Local NIM Launch Command

Use this when you want the local NVIDIA NIM story.

In the editor:

1. Open **Templates**.
2. Click **NVIDIA Local NIM Launch**.
3. Click **Cook** on the Output node.
4. Copy the Docker command from the result.
5. Run that command in a separate terminal when you are ready to start the NIM
   container.
6. Use the shown endpoint in `NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark`.
7. Open **NVIDIA NIM Benchmark** and set the endpoint to the local NIM URL when
   you want local latency metrics.

Expected result:

- Blacknode gives the command and endpoint wiring.
- The local endpoint can be checked before model calls are routed to it.

## 14. Connect an Agent Through MCP

Install MCP support first:

```powershell
pip install -e ".[mcp]"
```

Start the MCP server:

```powershell
blacknode mcp
```

Add this to an MCP client config:

```json
{
  "mcpServers": {
    "blacknode": {
      "command": "blacknode",
      "args": ["mcp"]
    }
  }
}
```

Restart the MCP client, then ask:

```text
Using the blacknode MCP tools, list the available node types, show the schema
for Text, Concat, and Output, then create a workflow that concatenates "Hello"
and " World", validates it, runs it, and exports it as Python.
```

Expected result:

- The agent lists node types.
- The agent creates a typed workflow.
- Validation passes.
- Running the workflow returns `Hello World`.
- Export returns runnable Python.

## 15. Connect AI-Q or NeMo Agent Toolkit With Streamable HTTP

Start Blacknode MCP over HTTP:

```powershell
blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp
```

Endpoint:

```text
http://127.0.0.1:9901/mcp
```

Use that endpoint in MCP clients that support streamable HTTP.

Expected result:

- The same Blacknode tool surface is available over HTTP.
- AI-Q, NeMo Agent Toolkit, or another MCP client can use Blacknode as the
  visual workflow editor.

## 16. Run the Docker Compose Stack

Use this for the self-hosted demo path.

Windows:

```powershell
.\docker-up.ps1
```

macOS/Linux:

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

To add NVIDIA credentials:

Windows:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Edit `.env`, set `NVIDIA_API_KEY`, then run:

```powershell
.\docker-up.ps1
```

## 17. Create a Custom Node

In the editor:

1. Click the **Script** tab in the left sidebar.
2. Paste this code:

```python
from blacknode.node import node

@node(inputs=["text:Text", "n:Int"], outputs=["result:Text"])
def FirstNWords(ctx: dict) -> dict:
    words = ctx.get("text", "").split()
    n = int(ctx.get("n", 10))
    return {"result": " ".join(words[:n])}
```

3. Click **Run** or press **Ctrl+Enter** to register it immediately.
4. Set a file name and click **Save** to keep it in `custom-nodes/`.
5. Open the node palette and find the new node in its category.
6. Add it to the canvas and cook it like any other node.

Expected result:

- The custom node appears without restarting the server.
- Saved custom nodes auto-load on the next Blacknode start.
- Its typed inputs and outputs can connect to compatible handles.

## 18. Try Tool and Agent Templates

In the editor:

1. Open **Templates**.
2. Click **Python Tool Agent**.
3. Inspect **PythonFn**, **ToolBox**, and **AgentLoop**.
4. Click **Cook** on the Output node.

For a no-model tool test:

1. Open **Templates**.
2. Click **Subnet Tool Call**.
3. Click **Cook** on the Output node.

Expected result:

- **PythonFn** exposes Python code as a callable tool.
- **ToolBox** collects one or more tools.
- **ToolCall** tests a tool directly with a dictionary of arguments.
- **SubnetAsTool** turns a visual subgraph into a callable tool.

## 19. Share a Workflow

Before sharing a workflow:

Windows:

```powershell
blacknode validate workflows\your-workflow.json
blacknode export-python workflows\your-workflow.json --output exported_workflow.py
python exported_workflow.py
```

macOS/Linux:

```bash
blacknode validate workflows/your-workflow.json
blacknode export-python workflows/your-workflow.json --output exported_workflow.py
python exported_workflow.py
```

Expected result:

- Validation passes.
- Exported Python runs.
- The workflow JSON can be copied, committed, or promoted into `templates/`.

## Troubleshooting

### `blacknode` command not found

Run:

```powershell
pip install -e ".[mcp]"
```

Then close and reopen the terminal. The command is created by the package entry
point:

```text
blacknode = "blacknode.cli:main"
```

### Port `3000` is busy

Run the launcher again:

```powershell
start.bat
```

or:

```bash
./start.sh
```

The launcher restarts an old Blacknode editor on port `3000`. If another app is
using the port, close that app or start it on a different port.

### Editor server is not green

Start the backend manually:

```powershell
cd editor-server
python server.py
```

Then refresh:

```text
http://localhost:3000
```

### Model calls do not run

Check that the matching key is saved in the Model node or set in the
environment:

```text
NVIDIA_API_KEY
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

## Feature Checklist

Use this as the demo checklist:

| Feature | Where to try it |
|---|---|
| Local environment check | `blacknode doctor` |
| No-key workflow run | `blacknode demo` |
| Visual graph editing | Editor canvas |
| Templates | **Templates** tab |
| Save/reopen workflows | **Workflows** tab |
| Run replay | **Runs** tab |
| Python export | `blacknode export-python` |
| API keys and provider routing | **Model** node |
| NVIDIA NIM workflows | NVIDIA templates |
| NVIDIA video mission control | **NVIDIA Video Intelligence Mission Control** template |
| Local NIM command generation | **NVIDIA Local NIM Launch** template |
| Agent-controlled workflow building | `blacknode mcp` |
| AI-Q / NeMo MCP HTTP path | `blacknode mcp --transport streamable-http ...` |
| Docker deployment | `.\docker-up.ps1` on Windows, `docker compose up --build` elsewhere |
| Custom nodes | **Script** tab |
| Tool workflows | Python Tool Agent and Subnet Tool templates |
