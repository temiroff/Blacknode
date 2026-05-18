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
| **Provider-agnostic AI nodes** | `LLMAgent`, `AgentLoop` auto-route to Anthropic / OpenAI / Ollama / any OpenAI-compat server |
| **Custom nodes in one decorator** | `@bn.node(inputs=[...], outputs=[...])` registers any Python function as a node |
| **Rust core** | The graph engine, type system, and async executor are written in Rust (PyO3 bindings) |
| **Visual editor** | Tauri desktop app + React Flow — coming in milestone 3 |

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
├── examples/
│   ├── hello_agent.py        # minimal LLM node
│   ├── custom_node.py        # @node decorator usage
│   ├── multi_provider.py     # same graph, different backends
│   └── research_pipeline.py  # fetch → summarise → write
└── editor/                   # Tauri + React Flow (upcoming)
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

## Getting started

```bash
git clone git@github.com:temiroff/Blacknode.git
cd Blacknode
pip install anthropic openai   # whichever providers you need
cd python
python ../examples/hello_agent.py
```

To build the Rust core (optional — speeds up large graphs):

```bash
pip install maturin
maturin develop
```

---

## Writing a custom node

```python
from blacknode.node import node

@node(inputs=["text", "n"], outputs=["words"])
def FirstNWords(ctx: dict) -> dict:
    words = ctx.get("text", "").split()
    n = int(ctx.get("n", 10))
    return {"words": words[:n]}
```

Register it and use it in any graph — no class boilerplate, no inheritance.

---

## Roadmap

- [x] Pure-Python graph engine with lazy evaluation
- [x] Built-in node library (ai, flow, io, core)
- [x] Multi-provider LLM support (Anthropic, OpenAI, Ollama, local)
- [ ] Rust core compiled via maturin (milestone 2)
- [ ] Tauri + React Flow visual editor (milestone 3)
- [ ] Rust plugin nodes via `#[blacknode]` proc-macro (milestone 4)
- [ ] `.bn` binary graph file format
