# NVIDIA Agent Stack

Blacknode connects NVIDIA model, retrieval, GPU, and agent integrations to typed
visual workflows. Each workflow remains executable through the editor and
runtime, observable through run replay, and available to external agents
through MCP.

## Choose an Integration

| Integration | Use it for | Guide |
|---|---|---|
| NVIDIA NIM | Call hosted or local models from workflow nodes | [NVIDIA NIM Quickstart](nvidia-nim-demo.md) |
| NVIDIA AI-Q and NeMo Agent Toolkit | Create, inspect, run, and export Blacknode workflows through streamable HTTP MCP | [AI-Q Integration](aiq-integration.md) |
| NVIDIA mission workflows | Check local readiness, prepare NIM launches, and run benchmark templates | [NVIDIA Mission Control](nvidia-mission-control.md) |
| NVIDIA retrieval | Compare retrieval, reranking, cited answers, and replay data | [NVIDIA Visual RAG](nvidia-visual-rag.md) |
| NVIDIA GPUs | Run CUDA kernels, image operations, Tensor Core GEMM, and capability checks | [NVIDIA GPU Blocks](nvidia-gpu-blocks.md) |

## Integration Shape

```text
NVIDIA model or agent client
              │
              ▼
    Blacknode MCP / model nodes
              │
              ▼
 Typed workflow runtime and packages
              │
       ┌──────┴──────┐
       ▼             ▼
 Robot capability   Run artifacts,
 workflows          metrics, and replay
```

Agent clients can use Blacknode's MCP surface to inspect available nodes,
construct and validate a graph, run it, and review the result. Model nodes can
call NVIDIA NIM endpoints as part of the same workflow. GPU nodes provide local
compute capabilities through the `blacknode-cuda` extension package.

## Start Here

- For a hosted model call, follow the
  [NVIDIA NIM Quickstart](nvidia-nim-demo.md).
- For an agent controlling Blacknode, follow the
  [AI-Q and NeMo Agent Toolkit integration](aiq-integration.md).
- For local GPU workflows, install `blacknode-cuda` and follow
  [NVIDIA GPU Blocks](nvidia-gpu-blocks.md).

Credentials, endpoints, and runtime requirements remain specific to each
integration guide. Keep API keys in environment variables or secret stores;
workflow files and templates should contain only configuration references.
