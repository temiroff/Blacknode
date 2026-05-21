# MCP Test Prompts

Use these prompts from Claude Desktop, Cursor, or any MCP client configured with:

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

The editor bridge prompts require the visual editor backend to be running at
`http://127.0.0.1:7777` and the browser editor to be open.

## Smoke Test

```text
Using the blacknode MCP tools, list the available node types, show the schema for Text, LLMAgent, Model, and Output, then create a simple workflow that concatenates "Hello" and " World", validates it, runs it, and exports it as Python.
```

Expected result: the workflow validates, `run_workflow` returns `Hello World`, and `export_python` returns a runnable script.

## Open A Blank Editor Tab

```text
Using the blacknode MCP tools, open a new unsaved workflow tab in the running Blacknode editor named "MCP Smoke Tab".
```

Expected tool call: `create_editor_workflow_tab`.

## NVIDIA NIM Editor Demo

```text
Using the blacknode MCP tools, create a workflow named "NVIDIA NIM MCP Demo" with:

- a Text prompt node containing: Write a crisp launch brief for Blacknode: 4 bullets, one risk, one next action. Mention that it was assembled through MCP and powered by NVIDIA NIM.
- a Text system node containing: You are a concise product strategist. Keep the answer concrete, technical, and under 120 words.
- a Model node set to nim:meta/llama-3.1-8b-instruct
- an Int max_tokens node set to 350
- a Float temperature node set to 0.35
- an LLMAgent node
- an Output node

Connect prompt.value to LLMAgent.prompt, system.value to LLMAgent.system, model.value to LLMAgent.model, max_tokens.value to LLMAgent.max_tokens, temperature.value to LLMAgent.temperature, and LLMAgent.text to Output.value.

Validate the workflow, open it in the running Blacknode editor as a new tab, let the editor organize the graph, then cook out.value in the editor.
```

Expected tool sequence:

1. `create_workflow`
2. `add_node`
3. `connect_nodes`
4. `validate_workflow`
5. `open_workflow_in_editor_tab`
6. `cook_editor_node`

Expected result: the editor opens an organized workflow tab and the Output node displays a NVIDIA NIM-generated launch brief.

## Inspect And Save The Editor Graph

```text
Using the blacknode MCP tools, inspect the graph currently loaded in the running Blacknode editor. Tell me the node count, edge count, whether validation is OK, then save it as "MCP Saved Graph".
```

Expected tool sequence:

1. `get_editor_graph`
2. `save_editor_workflow`

Expected result: the tool returns a workflow slug such as `MCP_Saved_Graph`, and the saved JSON appears under `workflows/`.

## Saved Workflow Round Trip

```text
Using the blacknode MCP tools, list saved workflows, load the saved workflow with slug "MCP_Saved_Graph" into the running editor as a new organized tab, rename the active tab to "Round Trip Check", organize the current graph, then close the active tab.
```

Expected tool sequence:

1. `list_saved_workflows`
2. `load_saved_workflow_in_editor`
3. `rename_editor_tab`
4. `organize_editor_graph`
5. `close_editor_tab`

Expected result: the saved workflow opens in the editor, is organized and renamed, then the active tab closes.

## Tracked NVIDIA NIM Template

```text
Using the blacknode MCP tools, load templates/nvidia-nim-mcp-demo.json, validate it, open it as an organized editor tab, and cook out.value.
```

Expected result: the tracked NVIDIA NIM MCP demo template validates, opens in the editor, and cooks the Output node.

## Direct Local Verification

From the repo root:

```powershell
python scripts\smoke_test_mcp.py
python -m pytest tests\test_mcp_tools.py
```
