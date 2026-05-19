# Blacknode Future Ideas

Date captured: 2026-05-19

This note collects future product and architecture ideas for Blacknode, with rough recommendations and dependencies.

## Direction

Blacknode should grow in two complementary directions:

1. A visual editor for building and understanding graphs.
2. A scriptable/runtime system that can run, export, automate, and optimize those graphs outside the editor.

The strongest near-term path is to make graphs portable and executable first, then add faster storage and compiled execution once the graph format is stable.

## Ideas And Recommendations

### Command-line graph execution

Recommendation: yes, this is a good idea and should be high priority.

Running graphs from the command line would make Blacknode useful outside the browser editor. It enables automation, scheduled jobs, CI workflows, agent-created workflows, and reproducible examples.

Possible CLI shape:

```bash
blacknode run workflow.json --output result.json
blacknode run workflow.json --input question="Explain CUDA streams"
blacknode validate workflow.json
blacknode export-python workflow.json > workflow.py
```

Why this should come before binary export:

- It forces the graph format to be stable.
- It proves graphs can run without editor state.
- It creates the same execution entry point that MCP and AI agents can use later.

### Graph to Python export

Recommendation: yes, high priority.

Python export is valuable because it makes visual graphs readable, editable, versionable, and easy to run without the editor. It also helps users trust what the graph is doing.

Good first target:

- Export a graph into a Python script using the public `blacknode` Python API.
- Preserve node IDs, node labels, params, edges, and chosen output node.
- Generate clear code, not overly clever code.
- Include comments for node labels and graph structure.

This can become the main bridge between visual workflows and normal software development.

### Binary graph export

Recommendation: useful later, not urgent now.

Binary export could be valuable for fast loading, compact distribution, signed packages, and embedding graphs into native runtimes. But it should not be the first portable format.

Use JSON or another readable schema as the canonical graph format first. Add binary export later as a compiled/package format derived from the canonical schema.

Possible binary use cases:

- Fast startup for large graphs.
- Shipping a graph as a runtime artifact.
- Prevalidated graph packages.
- Caching compiled execution plans.
- Embedding graph payloads in Rust, C++, or CUDA-backed apps.

Risk if done too early:

- The format will churn while the graph model is still changing.
- Debugging becomes harder.
- It can hide schema problems that would be obvious in readable JSON.

Suggested future design:

- `workflow.blacknode.json` as canonical source.
- `workflow.blacknode.bin` as optional packed artifact.
- Include schema version, node registry version, dependency metadata, and checksum.

### CUDA and native accelerated nodes

Recommendation: yes, but after the graph schema and runtime boundary are cleaner.

CUDA nodes could make Blacknode powerful for GPU workflows, especially if the project targets NVIDIA, model inference, image/video processing, tensor transforms, and simulation.

Possible node categories:

- CUDA kernel node: runs a custom kernel.
- Tensor operation node: wraps common GPU operations.
- NIM/inference node: calls NVIDIA-hosted or local inference.
- Native plugin node: calls Rust/C++/CUDA code through a stable ABI.
- Precompiled node: uses a compiled implementation for fast execution.
- Live compile node: compiles user-provided code during development.

Important distinction:

- Live compile is useful for experimentation.
- Precompiled nodes are better for production and fast execution.

Good implementation direction:

1. Define a stable node capability model.
2. Add a node registry that can describe whether a node is Python, Rust, CUDA, remote, or precompiled.
3. Add runtime checks for required hardware, drivers, libraries, and model assets.
4. Cache compiled artifacts by source hash, parameters, target GPU, and compiler version.

Avoid making CUDA nodes depend on editor-specific behavior. They should run through the same runtime path as CLI execution.

### AI agent documentation

Recommendation: yes, high priority and low risk.

Blacknode should include documentation written specifically for AI agents so an assistant can understand how to create, edit, validate, and run graphs.

This should be a machine-friendly guide, not only human docs.

Suggested file:

- `docs/agent-guide.md`

Suggested contents:

- Core concepts: graph, node, port, edge, subnet, output.
- Graph JSON schema and examples.
- Available built-in nodes and their ports.
- Rules for valid connections.
- How to run a graph from Python.
- How to run a graph from CLI once available.
- How to convert a user request into a graph.
- Common graph patterns, such as LLM chat, tool agent, CUDA pipeline, and batch workflow.
- Error handling and validation rules.

This should come before MCP because MCP tools need stable behavior and documentation anyway.

### MCP server for Blacknode

Recommendation: yes, but build it after the CLI and agent docs.

An MCP server would let AI agents inspect available nodes, create graphs, validate graphs, run graphs, and modify workflows through a standard tool interface.

Possible MCP tools:

- `list_nodes`
- `get_node_schema`
- `create_graph`
- `load_graph`
- `save_graph`
- `validate_graph`
- `connect_nodes`
- `run_graph`
- `export_python`
- `explain_graph`

This is a strong fit for the project because Blacknode is already a graph-building tool, and agents are good at assembling structured workflows when they have clear schemas and validation feedback.

Recommended dependency order:

1. Stable graph schema.
2. CLI execution and validation.
3. Agent guide.
4. MCP server.

### Precompiled and live-compiled nodes

Recommendation: yes, but separate development mode from production mode.

Precompiled nodes are good for speed, reliability, and deployment. Live-compiled nodes are good for creative iteration, but they increase security and reproducibility risk.

Suggested model:

- Development: allow live compile with clear sandboxing and compiler logs.
- Production: prefer precompiled nodes with versioned metadata.
- Cache: store compiled artifacts by source hash and target environment.
- Safety: make live compilation explicit and disabled by default in untrusted graphs.

Metadata to track:

- Node implementation language.
- Source hash or package version.
- Required runtime.
- Required device capabilities.
- Input and output types.
- Whether the node is deterministic.
- Whether the node has side effects.

### Graph package format

Recommendation: useful as a future umbrella feature.

Instead of thinking only about "binary export," consider a graph package that can include:

- Canonical graph JSON.
- Optional binary packed graph.
- Python export.
- Node dependency manifest.
- Model/provider requirements.
- Assets and local files.
- Compiled node artifacts.
- README or agent instructions.

This gives Blacknode a clean path from visual prototype to portable runnable workflow.

## Suggested Priority

1. Stabilize the graph schema.
2. Add graph validation.
3. Add CLI execution.
4. Add Python export.
5. Write `docs/agent-guide.md`.
6. Add an MCP server using the CLI/runtime as its backend.
7. Add native/precompiled node support.
8. Add CUDA nodes and compile cache.
9. Add binary/package export.

## Open Questions

- What is the canonical graph file format: current editor JSON, Python `Graph.to_dict()`, or a new versioned schema?
- Should workflows be single files, folders, or packages?
- Which runtime is canonical: Python first, Rust first, or hybrid?
- How should node versions be tracked?
- Should graph execution be deterministic by default?
- How should secrets and API keys be represented in portable graphs?
- Should AI agents modify graph files directly, or only through validated tools?

## Current Best Answer

The best near-term investment is not binary export yet. Build a stable, readable graph format, CLI runner, and Python exporter first. Then AI docs and MCP become straightforward. After that, binary graph packages, CUDA nodes, and precompiled execution will have a solid foundation instead of becoming separate one-off systems.
