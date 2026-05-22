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
| `NIMDockerCommand` | Generates PowerShell and Bash commands for launching a local NIM container, plus the endpoint URL to wire into the workflow. |
| `NIMHealthCheck` | Checks a hosted or local OpenAI-compatible NIM `/models` endpoint. |
| `NIMAgent` | Calls hosted or local NVIDIA NIM through an OpenAI-compatible endpoint. |
| `NIMBenchmark` | Runs repeated NIM calls and returns text, average latency, min/max latency, and raw samples. |
| `VideoFolderInput` | Builds a local video-folder manifest for video-intelligence workflows. |
| `NVIDIADeploymentChoice` | Selects hosted, local, or hybrid NIM routing and exposes endpoint, stack, and requirements. |
| `NVIDIAVideoSummaryPlan` | Plans a Cosmos or VLM NIM video understanding stage. |
| `NVIDIARetrieverIndexPlan` | Plans a NeMo Retriever-style index and rerank stage for timestamped video segments. |
| `NVIDIAQuestionAnswerPlan` | Plans a NIM/Nemotron answer step over retrieved video evidence. |
| `NVIDIAMissionReport` | Combines input, deployment, video, retrieval, and QA plans into a mission-control report. |

## Templates

| Template | Use |
|---|---|
| `nvidia-ai-mission-control` | No-key planning template for a full NVIDIA-backed AI workflow. |
| `nvidia-video-intelligence-mission-control` | No-key video-intelligence mission-control graph across video input, Cosmos/VLM planning, NeMo Retriever planning, NIM/Nemotron QA planning, local NIM deployment, and final report. |
| `nvidia-local-nim-launch` | No-key local NIM setup helper that generates launch commands and endpoint output. |
| `nvidia-nim-benchmark` | Live hosted/local NIM benchmark. Requires `NVIDIA_API_KEY` for hosted NIM or a running local endpoint. |
| `nvidia-nim` | Simple prompt-to-NIM workflow through the general `LLMAgent`. |
| `nvidia-nim-mcp-demo` | MCP-oriented demo that opens and cooks a visible NVIDIA NIM workflow. |

## Quick Demo Path

### 1. Run no-key checks

```powershell
python -m blacknode.cli run templates\nvidia-ai-mission-control.json
python -m blacknode.cli run templates\nvidia-video-intelligence-mission-control.json
python -m blacknode.cli run templates\nvidia-local-nim-launch.json
```

Expected result:

- Mission Control returns an NVIDIA stack plan.
- Video Intelligence Mission Control returns a full visual plan for input,
  Cosmos/VLM understanding, NeMo Retriever indexing, NIM/Nemotron QA, and
  deployment routing.
- Local NIM Launch returns PowerShell and Bash Docker commands plus
  `http://127.0.0.1:8000/v1`.

### 2. Open the visual workflow

```powershell
start.bat
```

Then open the **Templates** tab and load **NVIDIA Video Intelligence Mission
Control**, **NVIDIA AI Mission Control**, or **NVIDIA Local NIM Launch**. Cook
the Output nodes to see the plan, launch command, endpoint, report, and
run-history events.

### 3. Run hosted NIM

```powershell
$env:NVIDIA_API_KEY="..."
python -m blacknode.cli run templates\nvidia-nim-benchmark.json
```

Expected result: the benchmark returns generated text, average latency, min/max
latency, and raw latency samples.

## Hosted NIM vs Local NIM

Hosted NIM is the fastest demo path: set `NVIDIA_API_KEY`, keep the endpoint at
`https://integrate.api.nvidia.com/v1`, and use a `nim:<model>` model string.

Local NIM is the most impressive platform path: use `NIMDockerCommand` to
generate the container command, start it in a terminal, then point
`NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark` at the local endpoint such as
`http://127.0.0.1:8000/v1`.

## Implemented Surface

Blacknode exposes NVIDIA-oriented workflow nodes, hosted/local NIM calls, local
readiness checks, benchmark metrics, local NIM launch commands, video
intelligence planning, retriever planning, templates, run-history visibility,
and Python export.
