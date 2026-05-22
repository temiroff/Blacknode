# NVIDIA NIM Demo

This page is the short public demo path for showing Blacknode with NVIDIA NIM through the existing Python runtime and MCP tools.

Demo video:

https://github.com/user-attachments/assets/9debbc72-68d7-4717-9a44-433ae65fd4d2

## What It Shows

- A visual workflow assembled and operated through MCP.
- Typed nodes for prompt, system message, model, token limit, temperature, LLM call, and output.
- NVIDIA NIM routed through the model/provider configuration.
- Run history with model-call visibility.
- Exportable workflow JSON and Python.

## Requirements

- Python 3.11+
- Node.js 20+ for the editor
- A NVIDIA NIM API key if you want the LLM node to call NIM

## Start Blacknode

For the Windows one-command path:

```bat
start.bat
```

For a manual two-terminal path:

```powershell
python editor-server/server.py
```

```powershell
cd editor
npm install
npm run dev
```

Then install MCP support and start the MCP server:

```powershell
pip install -e ".[mcp]"
blacknode mcp
```

## MCP Prompt

Use this prompt in an MCP-capable client after connecting the Blacknode server:

```text
Using the blacknode MCP tools, run the template nvidia-nim-mcp-demo in the running editor as an organized tab named "NVIDIA NIM MCP Demo", then cook out.value.
```

Expected result:

- The editor opens an organized NVIDIA NIM workflow tab.
- The Output node is cooked.
- The Runs tab records the execution.
- If a NIM key is configured, the LLM node returns a launch brief.

## No-Key Smoke Test

Use the deterministic text template to verify the local workflow runtime:

```powershell
python -m blacknode.cli validate templates\text-pipeline.json
python -m blacknode.cli run templates\text-pipeline.json
```

Or use the Rust no-server path:

```powershell
cargo run -p blacknode-cli -- run-pure templates\text-pipeline.json
```

## Demo Coverage

This demo covers the workflow format, MCP tools, visual editor, NVIDIA NIM
provider routing, run history, and Python export path.
