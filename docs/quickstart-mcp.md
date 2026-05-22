# Blacknode MCP Quickstart

This is the shortest path for trying Blacknode as an agent-controllable visual workflow builder.

## What You Need

- Python 3.11 or newer
- Node.js 20.19+ or 22.12+
- A local MCP client such as Claude Desktop or Cursor
- Optional: a NVIDIA NIM, OpenAI, or Anthropic API key for LLM demos

The no-API-key smoke test works without model credentials.

## Start Blacknode

From the repository root on Windows:

```bat
start.bat
```

From the repository root on macOS/Linux:

```bash
chmod +x start.sh
./start.sh
```

These launchers install local dependencies if needed, start the FastAPI backend at `http://127.0.0.1:7777`, restart an old Blacknode editor on port 3000 if needed, start the Vite editor at `http://localhost:3000`, and open the browser. On Windows, `start.bat` keeps one launcher window open and writes service logs to `.local-logs/`.

If you see `Stopping existing visual editor on port 3000...`, the launcher
found an old Blacknode Vite server and restarted it so the editor stays on
`http://localhost:3000`.

If the same checkout is used from Windows and WSL/Linux/macOS, the launchers
check Vite's native dependency for the current OS and run `npm install` when
that dependency needs repair.

Manual start:

```powershell
cd editor-server
python server.py
```

In another terminal:

```powershell
cd editor
npm run dev
```

## Configure MCP

Install the package locally so `blacknode mcp` is available:

```powershell
pip install -e ".[mcp]"
```

Add this to your MCP client config:

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

Restart the MCP client after saving the config.

For MCP clients that require streamable HTTP, including NVIDIA AI-Q or NeMo
Agent Toolkit workflows, start the same tool surface over HTTP:

```powershell
blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp
```

Endpoint:

```text
http://127.0.0.1:9901/mcp
```

## No-API-Key Smoke Prompt

Use this first. It proves the agent can inspect schemas, build a graph, validate it, run it, and export Python without external services.

```text
Using the blacknode MCP tools, list the available node types, show the schema for Text, Concat, and Output, then create a simple workflow that concatenates "Hello" and " World", validates it, runs it, and exports it as Python.
```

Expected result:

- `list_nodes` returns registered node types.
- `get_node_schema` returns typed ports.
- The workflow validates.
- `run_workflow` returns `Hello World`.
- `export_python` returns a runnable Python script.

## Visual Editor Smoke Prompt

Use this after the editor backend and browser are running.

```text
Using the blacknode MCP tools, open a new organized editor tab named "MCP Preview Smoke" with a Text node connected to an Output node. The Text value should be "Blacknode MCP works". Then cook out.value in the editor.
```

Expected result:

- A new tab opens in the editor.
- The graph is organized on the canvas.
- The Output node displays the cooked value.
- The Runs panel records the execution.

## NVIDIA NIM Demo Prompt

Requires a NVIDIA API key saved in the editor Model node or available as `NVIDIA_API_KEY`.

```text
Using the blacknode MCP tools, run the template nvidia-nim-mcp-demo in the running editor as an organized tab named "NVIDIA NIM MCP Demo", then cook out.value.
```

Expected result:

- The tracked template opens visually.
- The graph cooks through NVIDIA NIM.
- The Output node shows the model result.
- The Runs panel shows model-call events and timings.

## Local Verification

From the repository root:

```powershell
python scripts\smoke_test_mcp.py
python -m pytest tests\test_mcp_tools.py
```

Expected result:

- MCP smoke test reports the server as healthy.
- MCP tests pass.

## Troubleshooting

If the MCP client cannot find `blacknode`, run:

```powershell
pip install -e ".[mcp]"
blacknode mcp
```

If editor tools fail, make sure `editor-server/server.py` is running at `http://127.0.0.1:7777`.

If model calls fail, confirm the provider key is saved in the editor or present in the environment:

- `NVIDIA_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
