# Blacknode Public Preview Demo Script

Use this as the recording or live-demo path for a public preview. Keep the demo short and technical.

## One-Sentence Positioning

Blacknode is a visual workflow builder for AI agents: an MCP-connected agent can create a graph, validate it, run it, inspect the run history, save it, and export it as Python.

## 90-Second Demo

1. Start with the editor open.
   - Show the node palette, templates, canvas, inspector, and Runs tab.
   - Say that workflows are local files and can also run from the CLI.

2. Switch to the MCP client.
   - Use the NVIDIA NIM template prompt from `docs/quickstart-mcp.md`.
   - Let the agent call `run_template_in_editor`.

3. Return to the editor.
   - Show the organized graph tab.
   - Point out typed, color-coded ports and the model node.

4. Press the top-bar Run button.
   - Show the result in the Output node.
   - Let the first run animate the executed nodes on the canvas.
   - Open the Runs tab and show model/tool events, status, timing, payload preview, and Replay.

5. Show portability.
   - Use MCP or CLI to export the workflow as Python.
   - State that the visual graph is not locked inside the editor.

Close with:

```text
Blacknode is for people who want agent workflows they can see, debug, run locally, and export.
```

## No-API-Key Backup Demo

Use this if model credentials or network access are unavailable.

```powershell
pip install -e .
python -m blacknode.cli validate templates\text-pipeline.json
python -m blacknode.cli run templates\text-pipeline.json
python -m blacknode.cli export-python templates\subnet-tool-call.json --output subnet_tool_call.py
python subnet_tool_call.py
```

Expected outputs:

- `text-pipeline.json` validates.
- `text-pipeline.json` returns `Hello World`.
- `subnet_tool_call.py` prints `59.0`.

## What To Emphasize

- Agent-controllable: MCP tools build real workflows, not screenshots.
- Inspectable: visual graph plus run timeline and replay.
- Portable: workflow JSON and Python export.
- Local execution: editor, runtime, keys, and run history stay on your machine by default.
- Practical: templates cover chat, NVIDIA NIM, research, Python tools, and subnets.

## What Not To Claim Yet

- Do not call it production-stable.
- Do not claim cloud collaboration.
- Do not claim mature CUDA acceleration yet.
- Do not claim security sandboxing for arbitrary Python tools.
- Do not claim graph APIs are frozen.

## Recording Checklist

- Browser zoom around 100%.
- Use dark theme for the NVIDIA NIM demo screenshot path.
- Keep one graph centered and organized.
- Hide or blur API keys.
- Keep the prompt/result short enough to read.
- Show the Runs panel at least once.
- End on the GitHub repo or README quickstart.
