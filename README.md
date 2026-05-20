# Blacknode

A node-based framework for building AI agent pipelines, typed data flows, and reusable Python tools - scriptable in Python, visual in the browser.

---

## Screenshots

### Light theme

![Blacknode light theme](docs/images/blacknode-light-theme.png)

### Dark theme

![Blacknode dark theme](docs/images/blacknode-dark-theme.png)

### Research pipeline

![Blacknode research pipeline template](docs/images/blacknode-research-pipeline.png)

---

## Quick Start

### Prerequisites

| Tool | Version | Download |
|---|---|---|
| Python | 3.10 + | https://python.org |
| Node.js | 18 + | https://nodejs.org |

### First-time setup (run once)

```bat
cd editor-server
pip install -r requirements.txt

cd ..\editor
npm install
```

### Starting the editor

**Windows — double-click `start.bat`** (at the repo root).

It opens two terminal windows (Python server + Vite dev server) and then launches the browser at `http://localhost:3000` automatically.

**Manual start (any OS):**

```bash
# Terminal 1 — Python backend
cd editor-server
python server.py
# → http://127.0.0.1:7777

# Terminal 2 — React frontend
cd editor
npm run dev
# → http://localhost:3000
```

Both must be running at the same time. The status indicator in the top bar turns green when the server is reachable.

> **After any Python code change** you must restart the Python server (`Ctrl+C` → `python server.py`) for the new node types and port colors to take effect.

---

## Setting up API keys

API keys are entered directly in the **Model node** on the canvas — no `.env` file needed.

1. Add a **Model** node from the AI category in the palette (or load any LLM template)
2. Pick your model from the dropdown
3. Paste your API key in the field below the dropdown
4. Click the 👁 button to verify it, then press Enter or click away

Keys are saved per provider in your browser's `localStorage` and automatically sent to the server on every page load.

| Provider | Where to get a key |
|---|---|
| Anthropic | https://console.anthropic.com |
| OpenAI | https://platform.openai.com/api-keys |
| NVIDIA NIM | https://build.nvidia.com (free tier available) |

---

## Using the editor

### Adding nodes

- **Right-click** the canvas → type to search → click or press Enter
- **Drag** a node from the left palette onto the canvas
- **Click** a node in the palette to place it at a random position
- Node categories in the palette start collapsed so larger node sets stay manageable

### Connecting nodes

Drag from an output handle (right side of a node) to an input handle (left side). Handles are color-coded by type — you can only connect matching types.

| Handle color | Type |
|---|---|
| 🟡 Amber | Text |
| 🟢 Green | Int / Float |
| 🟢 Bright green | Model (AI model identifier) |
| 🔵 Blue | Bool |
| 🟠 Orange | List |
| 🟣 Purple | Dict |
| 🩷 Pink | Embedding |
| 🔴 Red | Fn (callable) |
| ⚫ Grey | Any |

### Disconnecting lines

- **Click** an edge to select it, then press **Delete** or **Backspace**
- **Double-click** an edge to remove it immediately

### Running a graph

Click the **▶ Cook** button on any node (or on the **Output** node) to evaluate it. Each Cook run starts fresh so file writes, HTTP calls, and model calls do not replay stale cached values.

Results appear in the node's result area. Errors show in red with a full Python traceback.

### Panels and layout

- The left node palette can collapse or resize.
- The right **Properties** panel can collapse or resize the same way, while keeping its icon rail visible.
- Use **Organize** in the top bar to lay out the current graph or subnet.
- Use **Theme** to switch light/dark mode and **Clear** to reset the canvas.
- The server status stays at the right side of the top bar.
- Press **Ctrl+Z** on the canvas to undo graph edits step by step.
- Hold **Alt** while dragging a node to leave the original in place and drop a copy.
- Press **Ctrl+C** / **Ctrl+V** on the canvas to copy selected nodes and paste them at the cursor.

### Templates

Open the **Templates** tab in the left sidebar for one-click starter graphs:

| Template | What it does |
|---|---|
| LLM Chat | System prompt + user message → Anthropic / OpenAI |
| NVIDIA NIM | Same pipeline routed to a free NVIDIA NIM model |
| Text Pipeline | Concatenate two strings → Output |
| Research Pipeline | HTTPGet → LLMAgent → FileWrite → FileRead, with outputs for saved path and file text |
| Python Tool Agent | PythonFn → ToolBox → AgentLoop tool call |
| Visual Tool Agent | PythonFn → ToolBox → VisualAgentLoop compatibility path |
| Subnet Tool Call | Build a calculator inside SubnetAsTool and test it directly with ToolCall |
| Subnet Tool Agent | Build a calculator inside SubnetAsTool and pass it to AgentLoop |

Templates are auto-organized when loaded and framed with padding so the graph starts inside the visible canvas.

### Tool workflows

Tools live in the **Tools** category.

#### PythonFn

Use **PythonFn** when you want a quick inline Python tool.

1. Add a **PythonFn** node.
2. In `code`, define a callable named `run`.
3. Set `name` to the tool name the LLM should see.
4. Set `description` to explain when the tool should be used.
5. Wire `fn` into **ToolBox** for **AgentLoop**, or into **ToolCall** to test it directly.

Example:

```python
def run(query: str) -> str:
    import urllib.request
    return "result"
```

Type annotations on `run` are converted into the tool schema passed to the model.

#### SubnetAsTool

Use **SubnetAsTool** when you want to build the tool visually inside the node.

1. Add a **SubnetAsTool** node.
2. Set `name` and `description`.
3. Dive into the node.
4. Add **SubnetInput** and **SubnetOutput** nodes.
5. Build the internal graph between them.
6. Exit the subnet and wire `fn` into **ToolBox** or **ToolCall**.

The outputs on **SubnetInput** become the tool arguments. The first input on **SubnetOutput** becomes the returned value.

#### ToolBox and ToolCall

**ToolBox** collects any number of connected `Fn` tools into a `List` for `AgentLoop.tools`. It starts with no empty slots; connecting a tool creates a slot, and disconnecting removes the empty slot.

**ToolCall** runs one `Fn` directly with a `Dict` of arguments. Use it to test a PythonFn or SubnetAsTool before giving it to an AgentLoop.

#### VisualAgentLoop

**VisualAgentLoop** has the same inputs, outputs, and runtime behavior as **AgentLoop**. It appears as a diveable subnet-style node with an internal graph showing the agent loop pieces, while the outer node still cooks through the same shared implementation as **AgentLoop**:

| Node | Purpose |
|---|---|
| AgentMessages | Build the initial chat message list from a prompt |
| AgentChatStep | Run one model completion with optional tools |
| ToolDispatch | Execute tool calls against connected `Fn` tools |
| AgentAppendMessages | Append assistant tool calls and tool results to the message list |
| AgentStopCheck | Report whether a loop step should continue or stop |
| AgentFinalAnswer | Ask for a final answer after the tool-call limit |

Those pieces are intentionally available now so the black-box **AgentLoop** can be replaced with a fully visual loop when graph-level loop control is added.

### Custom nodes (Script tab)

Open the **Script** tab and write a Python `@node` function:

```python
from blacknode.node import node

@node(inputs=["text:Text", "n:Int"], outputs=["result:Text"])
def FirstNWords(ctx: dict) -> dict:
    words = ctx.get("text", "").split()
    n = int(ctx.get("n", 10))
    return {"result": " ".join(words[:n])}
```

Press **Ctrl + Enter** (or click Run). The node appears in the **Custom** section of the palette immediately — no server restart needed.

### File IO

**FileWrite** returns the resolved full path on its `path` output, even when the input path is relative. For example, writing `summary.txt` from the editor server returns a path like `F:\PROJECTS\NVDIA\Blacknode\editor-server\summary.txt`.

Wire that `path` output into **FileRead** to read the saved file back into the graph.

---

## Supported model providers

Connect a **Model** node to any `model` port. The model string is routed automatically:

| Model string | Routes to |
|---|---|
| `claude-sonnet-4-6`, `claude-opus-4-7`, … | Anthropic |
| `gpt-4o`, `o4-mini`, … | OpenAI |
| `nim:meta/llama-3.1-8b-instruct`, … | NVIDIA NIM |
| `ollama:llama3.2`, `ollama:mistral`, … | Ollama (local) |

---

## Running tests

The Python example tests use `unittest` and stub external LLM/network calls, so they do not require an API key:

```powershell
python -m unittest discover -s tests
```

To run the live NIM examples manually, save a NVIDIA NIM key in the editor's Model node API-key field, or set `NVIDIA_API_KEY`:

API keys are resolved in this order:

1. Explicit key passed in code.
2. Environment variable such as `NVIDIA_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`.
3. Editor-saved JSON at `editor-server/api_keys.json`.

```powershell
python .\examples\hello_agent.py
```

---

## Writing a custom node (Python API)

```python
import blacknode as bn

g = bn.Graph()

question = g.node("Text",     value="Summarise Dune in 3 bullets.")
agent    = g.node("LLMAgent", model="nim:meta/llama-3.1-8b-instruct")
output   = g.node("Output")

question.out("value") >> agent.inp("prompt")
agent.out("text")     >> output.inp("value")

g.cook(output, "value")
```

The `@node` decorator registers any Python function as a node type:

```python
from blacknode.node import node

@node(inputs=["prompt:Text", "temp:Float"], outputs=["text:Text"])
def MyNode(ctx: dict) -> dict:
    return {"text": ctx["prompt"].upper()}
```

---

## Project layout

```
blacknode/
├── start.bat                    ← double-click to launch everything
├── editor-server/
│   ├── server.py                ← FastAPI backend (port 7777)
│   └── requirements.txt
├── editor/                      ← React + Vite frontend (port 3000)
│   └── src/
│       ├── components/
│       │   ├── BlackNode.tsx    ← color-coded node with typed handles
│       │   ├── ModelNode.tsx    ← model picker with API key field
│       │   ├── OutputNode.tsx   ← result display node
│       │   ├── NodePalette.tsx  ← sidebar (Nodes / Templates / Script)
│       │   ├── ScriptEditor.tsx ← live @node code editor
│       │   └── TemplateGallery.tsx
│       ├── portColors.ts        ← type → hex color + compatibility rules
│       ├── models.ts            ← model picker options per provider
│       └── store.ts             ← Zustand state + server sync
├── python/blacknode/
│   ├── graph.py                 ← lazy DAG evaluation engine
│   ├── node.py                  ← @node decorator + registry
│   ├── providers/               ← LLM provider abstraction
│   │   ├── registry.py          ← auto-route from model string
│   │   ├── anthropic_provider.py
│   │   └── openai_provider.py   ← also covers Ollama, NIM, local
│   └── nodes/
│       ├── ai.py                ← LLMAgent, AgentLoop, VisualAgentLoop, tools
│       ├── core.py              ← Literal, Concat, Switch, ForEach, Output
│       ├── values.py            ← Text, Float, Int, Bool, Model
│       ├── flow.py              ← Branch, Gate, Map, Filter, Reduce
│       └── io.py                ← FileRead, FileWrite, HTTPGet, JSONParse
└── crates/                      ← Rust core (future milestone)
```

---

## License

Blacknode is licensed under the Apache License 2.0.
See [LICENSE](LICENSE) for the full license text.

---

## Roadmap

- [x] Pure-Python graph engine with per-run evaluation
- [x] Multi-provider LLM support (Anthropic, OpenAI, Ollama, NVIDIA NIM, local)
- [x] Typed ports with color-coded handles
- [x] React Flow visual editor — palette, templates, live cook, inspector
- [x] Model picker node with per-provider API key storage
- [x] Live custom node scripting (Script tab)
- [x] PythonFn, SubnetAsTool, ToolBox, and ToolCall tool workflows
- [x] VisualAgentLoop compatibility node and visible agent-step primitives
- [x] Collapsible/resizable side panels and auto-organized templates
- [ ] Rust core via maturin (milestone 2)
- [ ] Tauri desktop wrapper (milestone 3)
- [ ] `.bn` binary graph file format
