# NVIDIA Mission Control

Blacknode can present NVIDIA AI as a visual control plane: an agent or user can
plan a workflow, check local readiness, choose hosted or local NIM, run a model,
benchmark latency, inspect the run trace, and export the workflow to Python.

## Executing vs Advisory nodes

The NVIDIA nodes split into two groups. **Executing** nodes do real work —
they call NVIDIA NIM over HTTP, run CUDA/Tensor Core kernels on the local GPU,
or query the system. **Advisory** nodes (palette group **NVIDIA Advisory**)
emit a written *plan* describing a pipeline; they run **no** Cosmos/VLM, NeMo
Retriever, or NIM inference. They are design aids, not execution. To execute an
advisory plan, wire the executing nodes (e.g. `NIMAgent`) into the graph — see
[What we still need to build](#what-we-still-need-to-build-to-actually-run-the-pipeline).

### Executing nodes

| Node | Purpose |
|---|---|
| `NVIDIASystemCheck` | Checks local `nvidia-smi`, Docker, `NVIDIA_API_KEY`, and `NGC_API_KEY` visibility without changing the system. |
| `NIMDockerCommand` | Generates PowerShell and Bash commands for launching a local NIM container, plus the endpoint URL to wire into the workflow. |
| `NIMHealthCheck` | Checks a hosted or local OpenAI-compatible NIM `/models` endpoint. |
| `NIMAgent` | Calls hosted or local NVIDIA NIM through an OpenAI-compatible endpoint. |
| `NIMBenchmark` | Runs repeated NIM calls and returns text, average latency, min/max latency, and raw samples. |
| `NIMQueryRewrite` | Extracts and expands retrieval queries with Nemotron, including Q2E. |
| `NVIDIAEmbedding` | Calls hosted or local NeMo Retriever Embedding NIM in query or passage mode. |
| `NVIDIAVectorSearch` | Runs inspectable cosine search over NVIDIA embeddings. |
| `NVIDIARerank` | Reranks candidate passages with hosted or local NeMo Retriever Reranking NIM. |
| `NIMCitationAnswer` | Generates an evidence-constrained NIM answer with numbered citations. |
| `RetrievalCompare` | Compares original, rewritten, and reranked result orders. |
| `NIMFineTune` / `NIMFineTuneStatus` | Submit and poll a NeMo Customizer fine-tuning job (dry-run by default). |
| `VideoFolderInput` | Builds a local video-folder manifest for video-intelligence workflows. |
| `CUDAKernelLab`, `CUDACustomKernel`, `CUDAImageFilter`, `TensorCoreGEMM`, `CUTLASS` | Run real GPU compute on the local NVIDIA GPU (NVRTC / CuPy / containerized CUTLASS). |

### Advisory nodes (plan only — no inference)

| Node | Purpose |
|---|---|
| `NVIDIABlueprintPlan` | Maps a goal to an NVIDIA-oriented workflow plan (NIM, NeMo Retriever, Cosmos, Triton, TensorRT-LLM, RAPIDS, speech). **Plan text only.** |
| `NVIDIADeploymentChoice` | Selects hosted/local/hybrid NIM routing and exposes endpoint, stack, and requirements. **Config/plan only.** |
| `NVIDIAVideoSummaryPlan` | Describes a Cosmos or VLM NIM video-understanding stage. **Does not process video.** |
| `NVIDIARetrieverIndexPlan` | Describes a NeMo Retriever index + rerank stage. **Does not embed, index, or rerank.** |
| `NVIDIAQuestionAnswerPlan` | Builds a NIM/Nemotron QA plan and prompt. **Emits the prompt but does not send it.** |
| `NVIDIAMissionReport` | Combines the planning stages into one written mission-control report. **Summary only.** |

## Templates

| Template | Use |
|---|---|
| `nvidia-ai-mission-control` | **Advisory plan (no inference).** No-key planning template for a full NVIDIA-backed AI workflow. |
| `nvidia-video-intelligence-mission-control` | **Advisory plan (no inference).** No-key video-intelligence graph: video input + Cosmos/VLM planning + NeMo Retriever planning + NIM/Nemotron QA planning + local NIM deployment + final report. Runs no Cosmos/VLM/retrieval/NIM — it produces the plan, not the answer. |
| `nvidia-local-nim-launch` | No-key local NIM setup helper that generates launch commands and endpoint output. |
| `nvidia-nim-benchmark` | Live hosted/local NIM benchmark. Requires `NVIDIA_API_KEY` for hosted NIM or a running local endpoint. |
| `nvidia-nim` | Simple prompt-to-NIM workflow through the general `LLMAgent`. |
| `nvidia-nim-mcp-demo` | MCP-oriented demo that opens and cooks a visible NVIDIA NIM workflow. |
| `nvidia-visual-rag-comparator` | Original-query versus Q2E semantic retrieval, NVIDIA reranking, cited generation, and visual comparison. |

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

### 4. Compare original and Q2E retrieval

Load `templates/nvidia-visual-rag-comparator.json` in the editor and cook the
Q2E query, retrieval comparison, cited answer, and citations outputs. See
[NVIDIA Visual RAG Comparator](nvidia-visual-rag.md).

## Hosted NIM vs Local NIM

Hosted NIM is the fastest demo path: set `NVIDIA_API_KEY`, keep the endpoint at
`https://integrate.api.nvidia.com/v1`, and use a `nim:<model>` model string.

Local NIM is the most impressive platform path: use `NIMDockerCommand` to
generate the container command, start it in a terminal, then point
`NIMHealthCheck`, `NIMAgent`, or `NIMBenchmark` at the local endpoint such as
`http://127.0.0.1:8000/v1`.

## Implemented Surface

Blacknode exposes NVIDIA-oriented workflow nodes, hosted/local NIM calls,
embedding and reranking adapters, visual RAG comparison, local readiness
checks, benchmark metrics, local NIM launch commands, video intelligence
planning, retriever planning, templates, run-history visibility, and Python
export.

## What remains for the video pipeline

The generic text retrieval path now has executing embedding, vector search,
reranking, query rewrite, and cited-answer nodes. To make the separate Video
Intelligence Mission Control template execute instead of plan, the remaining
video-specific stages need matching executing nodes.

| New executing node | Replaces (advisory) | What it must do | NVIDIA service / endpoint | Inputs → Outputs |
|---|---|---|---|---|
| `VideoFrameSampler` | (new, feeds the chain) | Decode each file from the `VideoFolderInput` manifest and sample frames/clips at an interval. Pure local (ffmpeg/PyAV) — no service. | local ffmpeg | `manifest:Dict` → `frames:List` (path + timestamp) |
| `VLMCaptionNIM` | `NVIDIAVideoSummaryPlan` | Send sampled frames to a vision-language NIM and get a caption/events per timestamp. | VLM NIM (e.g. `nvidia/vila`, `microsoft/phi-3.5-vision`) on `integrate.api.nvidia.com/v1` (OpenAI vision messages) | `frames:List`, `model:Model` → `segments:List` (file, ts, caption) |
| `CosmosEmbedVideo` (optional, alt path) | `NVIDIAVideoSummaryPlan` | Produce video/world-model embeddings for segments via Cosmos. | Cosmos embedding NIM | `frames:List` → `embeddings:List` |
| `PersistentVectorIndex` | part of `NVIDIARetrieverIndexPlan` | Store vectors + metadata (file, timestamp) in a durable vector database. The current `NVIDIAVectorSearch` is in-process and intended for inspectable demos. | Milvus, LanceDB, or another NeMo Retriever-compatible store | `vectors:List` / `query` → `hits:List` |
| `NIMVideoQA` | `NVIDIAQuestionAnswerPlan` | Adapt `NIMCitationAnswer` to cite file names and timestamps from real video segments. | NIM/Nemotron on `integrate.api.nvidia.com/v1` | `question`, `ranked:List`, `model:Model` → `answer:Text`, `citations:List` |
| `NVIDIAExecReport` | `NVIDIAMissionReport` | Same report, but built from **executed** results (real captions, real hits, real answer) instead of plan text. | none | executed outputs → `report:Text` |

Notes:

- **Reuse what exists:** `NVIDIAEmbedding`, `NVIDIAVectorSearch`,
  `NVIDIARerank`, and `NIMCitationAnswer` can operate on caption segments once
  `VLMCaptionNIM` produces them.
- **Credentials/decisions still needed:** which VLM to target and whether the
  production index should use Milvus, LanceDB, or another managed store.
