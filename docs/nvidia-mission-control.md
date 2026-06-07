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

## What we still need to build to actually run the pipeline

The advisory nodes describe a real NVIDIA pipeline; to make the Video
Intelligence Mission Control template *execute* instead of plan, each advisory
stage needs a matching **executing** node. All of these call documented,
OpenAI/HTTP-compatible NVIDIA services, so they fit the existing provider/HTTP
pattern (`NIMAgent` is the reference). They are listed in dependency order.

| New executing node | Replaces (advisory) | What it must do | NVIDIA service / endpoint | Inputs → Outputs |
|---|---|---|---|---|
| `VideoFrameSampler` | (new, feeds the chain) | Decode each file from the `VideoFolderInput` manifest and sample frames/clips at an interval. Pure local (ffmpeg/PyAV) — no service. | local ffmpeg | `manifest:Dict` → `frames:List` (path + timestamp) |
| `VLMCaptionNIM` | `NVIDIAVideoSummaryPlan` | Send sampled frames to a vision-language NIM and get a caption/events per timestamp. | VLM NIM (e.g. `nvidia/vila`, `microsoft/phi-3.5-vision`) on `integrate.api.nvidia.com/v1` (OpenAI vision messages) | `frames:List`, `model:Model` → `segments:List` (file, ts, caption) |
| `CosmosEmbedVideo` (optional, alt path) | `NVIDIAVideoSummaryPlan` | Produce video/world-model embeddings for segments via Cosmos. | Cosmos embedding NIM | `frames:List` → `embeddings:List` |
| `NeMoEmbedText` | part of `NVIDIARetrieverIndexPlan` | Embed segment captions with a NeMo Retriever embedding NIM. | embedding NIM (`nvidia/nv-embedqa-e5-v5`) `/embeddings` | `segments:List` → `vectors:List` |
| `VectorIndexUpsert` / `VectorSearch` | part of `NVIDIARetrieverIndexPlan` | Store vectors + metadata (file, ts) and do top-k recall for a query. Start with a local index (FAISS/sqlite-vss); swap a managed store later. | local FAISS, or NeMo Retriever index | `vectors:List` / `query` → `hits:List` |
| `NeMoRerankNIM` | part of `NVIDIARetrieverIndexPlan` | Rerank recalled segments against the query for answer quality. | reranking NIM (`nvidia/nv-rerankqa-mistral-4b-v3`) `/ranking` | `query`, `hits:List` → `ranked:List` |
| `NIMVideoQA` | `NVIDIAQuestionAnswerPlan` | Take the reranked evidence + question and **actually call** NIM/Nemotron, citing file + timestamp. This is `NIMAgent` with an evidence-formatting wrapper — the smallest real win. | NIM/Nemotron on `integrate.api.nvidia.com/v1` | `question`, `ranked:List`, `model:Model` → `answer:Text`, `citations:List` |
| `NVIDIAExecReport` | `NVIDIAMissionReport` | Same report, but built from **executed** results (real captions, real hits, real answer) instead of plan text. | none | executed outputs → `report:Text` |

Notes:

- **Smallest first step:** `NIMVideoQA` (or just dropping a `NIMAgent` after a
  `RAGContext`/`KeywordSearch` over the captions) turns the demo from "a plan"
  into "a real answer" using infra that already exists. `VLMCaptionNIM` is the
  next-highest-value node because it makes the *video* real.
- **Reuse what exists:** retrieval can start with the current `KeywordIndex` /
  `KeywordSearch` / `RAGContext` nodes (already real) before investing in
  `NeMoEmbedText` + `NeMoRerankNIM`. The advisory `NVIDIARetrieverIndexPlan`
  becomes a thin wrapper or is dropped.
- **Credentials/decisions needed before building:** which VLM + embedding +
  rerank NIM models to target, hosted vs local for each, and whether to use a
  managed vector store or a bundled local index. These are product calls, not
  code calls — confirm them before implementing the table above.
