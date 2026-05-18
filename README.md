# Blacknode

A node-based framework for building AI agent pipelines — scriptable in Python, fast in Rust, visual in the browser.

---

## What it is

Blacknode lets you connect nodes together like building blocks. Each node does one thing — call an LLM, fetch a URL, filter a list, transform data — and outputs values that flow into the next node. The graph evaluates lazily: only nodes whose inputs changed are re-evaluated.

```python
import blacknode as bn

g = bn.Graph()

question = g.node("Literal",  value="Summarise the plot of Dune in 3 bullets.")
agent    = g.node("LLMAgent", model="claude-sonnet-4-6")
output   = g.node("Print")

question.out("value") >> agent.inp("prompt")
agent.out("text")     >> output.inp("value")

g.cook(output, "value")
```

Swap `model="claude-sonnet-4-6"` for `"gpt-4o"`, `"ollama:llama3.2"`, or `"local:my-model"` and nothing else changes.

---

## Key ideas

| Concept | Description |
|---|---|
| **Nodes and wires** | Each node has typed input/output ports; wires connect them into a graph |
| **Lazy evaluation** | Pulling a value from a node triggers its upstream chain automatically |
| **Smart caching** | Unchanged nodes return cached results; only dirty nodes re-run |
| **Typed ports** | Every port declares a type; handles are color-coded in the visual editor |
| **Provider-agnostic AI nodes** | `LLMAgent`, `AgentLoop` auto-route to Anthropic / OpenAI / Ollama / any OpenAI-compat server |
| **Custom nodes in one decorator** | `@bn.node(inputs=[...], outputs=[...])` registers any Python function as a node |
| **Rust core** | The graph engine, type system, and async executor are written in Rust (PyO3 bindings) |
| **Visual editor** | React Flow canvas with live cook, node palette, and inspector panel |

---

## Port types

Every input and output port has a declared type. Use `"name:Type"` syntax in the `@node` decorator:

```python
@bn.node(inputs=["prompt:Text", "max_tokens:Int"], outputs=["text:Text"])
def MyNode(ctx): ...
```

In the visual editor each handle is color-coded by type, and hovering a port shows its type badge — so you always know what connects where.

| Type | Color | Used for |
|---|---|---|
| `Text` | 🟡 amber | strings, prompts, responses |
| `Int` | 🟢 green | integer numbers |
| `Float` | 🟢 green | decimal numbers |
| `Bool` | 🔵 blue | true / false flags |
| `List` | 🟠 orange | arrays, sequences |
| `Dict` | 🟣 purple | key-value maps, JSON objects |
| `Embedding` | 🩷 pink | vector embeddings |
| `Fn` | 🔴 red | callable / function |
| `Any` | ⚫ grey | untyped or mixed |

---

## Project layout

```
blacknode/
├── crates/
│   ├── blacknode-types/     # Value enum (Text, Int, Float, Map, Bytes…)
│   ├── blacknode-core/      # DAG, Node trait, lazy evaluation, dirty flags
│   ├── blacknode-runtime/   # Async tokio executor for parallel branches
│   └── blacknode-py/        # PyO3 bindings — exposes Graph to Python
├── python/blacknode/
│   ├── graph.py             # Pure-Python Graph (works without Rust build)
│   ├── node.py              # @node decorator + registry
│   ├── providers/           # LLM provider abstraction
│   │   ├── base.py          # BaseProvider, CompletionResponse, ToolDef
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py   # also covers Ollama + LM Studio
│   │   └── registry.py         # auto-detect provider from model name
│   └── nodes/
│       ├── ai.py     # LLMAgent, AgentLoop, EmbedText, ToolCall
│       ├── core.py   # Literal, Print, Concat, Switch, ForEach
│       ├── flow.py   # Branch, Gate, Map, Filter, Reduce
│       └── io.py     # FileRead, FileWrite, HTTPGet, JSONParse
├── editor/                  # React Flow visual editor
│   └── src/
│       ├── components/
│       │   ├── BlackNode.tsx    # color-coded node with typed handles
│       │   ├── NodePalette.tsx  # drag-to-add sidebar
│       │   └── Inspector.tsx    # param editor + cook result
│       ├── portColors.ts        # type → hex color map
│       └── store.ts             # Zustand state + server sync
├── editor-server/           # FastAPI backend (bridges editor ↔ Python graph)
│   └── server.py
└── examples/
    ├── hello_agent.py        # minimal LLM node
    ├── custom_node.py        # @node decorator usage
    ├── multi_provider.py     # same graph, different backends
    └── research_pipeline.py  # fetch → summarise → write
```

---

## Supported providers

| Model prefix | Routes to |
|---|---|
| `claude-*` | Anthropic |
| `gpt-*`, `o1-*`, `o4-*` | OpenAI |
| `ollama:<name>` | Ollama at `localhost:11434` |
| `local:<name>` + `base_url=` | LM Studio, llama.cpp, vLLM, etc. |
| explicit `provider="anthropic"` | Override auto-detection |

---

## Running the visual editor

**Terminal 1 — Python backend:**
```bash
cd editor-server
pip install -r requirements.txt
python server.py
# → http://127.0.0.1:7777
```

**Terminal 2 — React frontend:**
```bash
cd editor
npm install
npm run dev
# → http://localhost:3000
```

Drag nodes from the left palette onto the canvas. Connect an output handle to an input handle of the same color. Click a node to edit its params and cook it from the inspector on the right.

---

## Writing a custom node

```python
from blacknode.node import node

@node(inputs=["text:Text", "n:Int"], outputs=["words:List"])
def FirstNWords(ctx: dict) -> dict:
    words = ctx.get("text", "").split()
    n = int(ctx.get("n", 10))
    return {"words": words[:n]}
```

Register it and use it in any graph — no class boilerplate, no inheritance. Port types are automatically picked up by the visual editor and color-coded.

---

## Roadmap

- [x] Pure-Python graph engine with lazy evaluation
- [x] Built-in node library (ai, flow, io, core)
- [x] Multi-provider LLM support (Anthropic, OpenAI, Ollama, local)
- [x] Typed ports with color-coded handles in visual editor
- [x] React Flow visual editor with live cook, palette, inspector
- [ ] Rust core compiled via maturin (milestone 2)
- [ ] Tauri desktop wrapper (milestone 3)
- [ ] Rust plugin nodes via `#[blacknode]` proc-macro (milestone 4)
- [ ] `.bn` binary graph file format
