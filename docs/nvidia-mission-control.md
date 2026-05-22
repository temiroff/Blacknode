# NVIDIA Mission Control

Blacknode can present NVIDIA AI as a visual control plane: an agent or user can
plan a workflow, check local readiness, choose hosted or local NIM, run a model,
benchmark latency, inspect the run trace, and export the workflow to Python.

## What Is Implemented

The NVIDIA node category includes:

| Node | Purpose |
|---|---|
| `NVIDIASystemCheck` | Checks local `nvidia-smi`, Docker, `NVIDIA_API_KEY`, and `NGC_API_KEY` visibility without changing the system. |
| `NVIDIABlueprintPlan` | Maps a goal to an NVIDIA-oriented workflow plan using NIM, NeMo Retriever, Cosmos, Triton, TensorRT-LLM, RAPIDS, or speech services where relevant. |
| `NIMDockerCommand` | Generates PowerShell and Bash commands for launching a local NIM container. It does not start Docker by itself. |
| `NIMHealthCheck` | Checks a hosted or local OpenAI-compatible NIM `/models` endpoint. |
| `NIMAgent` | Calls hosted or local NVIDIA NIM through an OpenAI-compatible endpoint. |
| `NIMBenchmark` | Runs repeated NIM calls and returns text, average latency, min/max latency, and raw samples. |

## Templates

| Template | Use |
|---|---|
| `nvidia-ai-mission-control` | No-key planning template for a full NVIDIA-backed AI workflow. |
| `nvidia-local-nim-launch` | No-key local NIM setup helper that generates launch commands and endpoint output. |
| `nvidia-nim-benchmark` | Live hosted/local NIM benchmark. Requires `NVIDIA_API_KEY` for hosted NIM or a running local endpoint. |
| `nvidia-nim` | Simple prompt-to-NIM workflow through the general `LLMAgent`. |
| `nvidia-nim-mcp-demo` | MCP-oriented demo that opens and cooks a visible NVIDIA NIM workflow. |

## Quick Demo Path

No key required:

```powershell
python -m blacknode.cli run templates\nvidia-ai-mission-control.json
python -m blacknode.cli run templates\nvidia-local-nim-launch.json
```

Hosted NIM:

```powershell
$env:NVIDIA_API_KEY="..."
python -m blacknode.cli run templates\nvidia-nim-benchmark.json
```

Visual editor:

```powershell
start.bat
```

Then open the **Templates** tab and load **NVIDIA AI Mission Control** or
**NVIDIA Local NIM Launch**.

## Hosted NIM vs Local NIM

Hosted NIM is the fastest demo path: set `NVIDIA_API_KEY`, keep the endpoint at
`https://integrate.api.nvidia.com/v1`, and use a `nim:<model>` model string.

Local NIM is the most impressive platform path: use `NIMDockerCommand` to
generate the container command, start it in a terminal, then point
`NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark` at the local endpoint such as
`http://127.0.0.1:8000/v1`.

## Honest Boundary

Blacknode now exposes NVIDIA-oriented workflow nodes, hosted/local NIM calls,
local readiness checks, benchmark metrics, and local NIM launch commands. It
does not yet provide a hardened sandbox, authenticated enterprise deployment,
automatic Docker lifecycle management, TensorRT-LLM graph compilation, Triton
model repository management, or NVIDIA AI Enterprise policy integration.
