# Training Data Loop

Blacknode turns agent runs into training data. Every workflow execution can be
recorded, rated, exported as a fine-tuning dataset, and submitted to NVIDIA NeMo
Customizer — closing the loop between **inference** and **training**:

```
[Input] → [AgentLoop] → [TrajectoryRecorder] → [Output]
                       → [RateOutput]  (NIM / Claude / GPT judge)
                              │
                     trajectories/run_NNN.jsonl   (labeled)
                              │
   blacknode export-training trajectories/ -f dpo -o dataset.jsonl
                              │
                       [NIMFineTune] → NeMo Customizer job → [NIMFineTuneStatus]
                              │
                     deploy fine-tuned model back to NIM → repeat
```

Without this, every run is disposable. With it, every run is training data: run a
workflow 100×, keep the good ones, export, fine-tune.

## The pieces

| Piece | What it does |
|---|---|
| **TrajectoryRecorder** (node) | Wraps any agent run and writes the full input → tool calls → outputs → final answer as a JSONL trajectory under `trajectories/`. Passive — passes `result` through unchanged. |
| **RateOutput** (node) | LLM-as-judge. Scores an output with any model (NIM, Claude, GPT, Ollama, local) and saves a **labeled** trajectory for DPO/RLHF. |
| **`blacknode export-training`** (CLI) | Converts recorded trajectories into TRL / Unsloth / OpenPipe datasets, with filtering. |
| **NIMFineTune** / **NIMFineTuneStatus** (nodes) | Submit a NeMo Customizer fine-tuning job for the exported dataset and poll its status. |

## TrajectoryRecorder

Drop it inline between an `AgentLoop` and an `Output`. It reads the loop's
`steps` plus the run logger's timed events and writes one `run_NNN.jsonl` per run
(auto-incrementing counter).

| Port | Direction | Notes |
|---|---|---|
| `result`, `steps`, `prompt` | in | from `AgentLoop` |
| `system`, `model`, `tags` | in | metadata for the trajectory |
| `dir` | in | output directory (default `trajectories`) |
| `include_events` | in | also write raw timed logger events |
| `result` | out | passthrough |
| `path` | out | written JSONL file |
| `trajectory` | out | the structured record |

**File format** — one JSON object per line:

```jsonl
{"type":"meta","schema":"blacknode.trajectory/1","run_id":"…","model":"…","tags":[],"tool_calls":1,"model_outputs":1,"run_duration_ms":…}
{"type":"input","role":"user","content":"Summarize this article"}
{"type":"model_output","role":"assistant","content":"Let me look that up.","tool_calls":[{"name":"fetch_url","arguments":{…}}]}
{"type":"tool_result","role":"tool","name":"fetch_url","content":"Article text here…"}
{"type":"final","role":"assistant","content":"The article says…"}
```

## RateOutput

A pluggable **LLM-as-judge**: a second model rates the agent's output against a
rubric. Runs at full speed with no human in the loop, so it scales for bulk
preference-data generation.

| Port | Direction | Notes |
|---|---|---|
| `result`, `steps`, `prompt` | in | the run to rate |
| `judge_model` | in | any resolvable model: `nim:…`, `claude-…`, `gpt-…`, `ollama:…`, `local:…` |
| `rubric` | in | scoring instructions |
| `scale` | in | `1-5`, `1-10`, or `updown` (thumbs) |
| `review_band` | in | e.g. `2-3` flags low scores as `needs_human_review` |
| `dir`, `save` | in | where/whether to write the labeled trajectory |
| `score`, `label`, `reason`, `rating`, `path` | out | parsed verdict + labeled file |
| `result` | out | passthrough |

The judge is asked to return strict JSON; parsing falls back to a number/verdict
scan so a chatty model still yields a usable score. The score is written into the
trajectory's `meta.label` and as a trailing `{"type":"rating", …}` line.

> **Human rating mode is not implemented.** Blacknode's graph cook is synchronous
> with no suspend/resume, so a true in-editor pause is a separate task. The
> `review_band` flag is the hook for routing edge cases to a future human queue.

## `blacknode export-training`

Reads the trajectory JSONL files and emits a training-ready dataset.

```bash
blacknode export-training trajectories/ --format jsonl --output dataset.jsonl
blacknode export-training trajectories/ -f dpo --min-score 4 -o prefs.jsonl
```

**Formats** (`--format`):

| Format | Record shape | Compatible with |
|---|---|---|
| `chat` (default; `jsonl` aliases it) | `{"messages": [...], "metadata": {...}}` | TRL `SFTTrainer`, Unsloth (messages), OpenPipe |
| `sharegpt` | `{"conversations": [{"from","value"}]}` | Unsloth native ShareGPT |
| `dpo` | `{"prompt","chosen","rejected","metadata"}` | TRL `DPOTrainer` |

Tool calls survive in the `chat` format as OpenAI `tool_calls` linked to the
following `tool` message via `tool_call_id`.

**DPO pairing** groups trajectories with the same input prompt and pairs the
highest-scored response (`chosen`) against each strictly lower-scored one
(`rejected`). To generate pairs at scale, run each input several times (varying
model/temperature) and rate them before exporting.

**Filters:** `--min-score N`, `--label up`, `--tag X`, `--rated-only`. A summary
is printed to stderr so stdout stays a clean dataset for piping.

## NIMFineTune / NIMFineTuneStatus

Submit the exported dataset to **NVIDIA NeMo Customizer** as a fine-tuning job.

| Port (NIMFineTune) | Notes |
|---|---|
| `base_url` | your NeMo Customizer deployment |
| `config` | base model config, e.g. `meta/llama-3.1-8b-instruct@v1.0.0+A100` |
| `dataset` / `namespace` | dataset registered in the NeMo Data Store |
| `dataset_file` | optional local `dataset.jsonl`; its record count is reported |
| `training_type` | `sft` or `dpo` (matches the two export formats) |
| `finetuning_type`, `epochs`, `batch_size`, `learning_rate`, `adapter_dim` | hyperparameters |
| `dry_run` | **default `true`** |
| `job_id`, `status`, `request`, `curl`, `response`, `notes` | outputs |

**Dry-run by default.** Launching a training job is expensive and hard to
reverse, so the node returns the exact `POST .../v1/customization/jobs` request
and a runnable `curl` without calling anything. Set `dry_run=false` with
`base_url`, `api_key`, and a registered `dataset` to actually launch; missing
prerequisites fall back to dry-run with a note. The API key is never written into
the `curl` output.

`NIMFineTuneStatus` polls `GET .../v1/customization/jobs/{id}/status` and returns
`ok`, `status`, `percent`, and the raw response.

> **Not verified against a live deployment.** The request is built against the
> documented NeMo Customizer job shape; NVIDIA's customization API is
> self-hosted/managed and evolves. `base_url`, `api_version`, and `config` are
> inputs so you can adapt without code changes. A dataset-upload step to the NeMo
> Data Store is intentionally left out rather than guessed.

## Capability matrix

| Capability | Status |
|---|---|
| Record full agent trajectories to JSONL | ✅ Real |
| Model-as-judge rating (NIM / Claude / GPT / local) | ✅ Real |
| Export to TRL / Unsloth / OpenPipe (chat, sharegpt, dpo) | ✅ Real |
| Automatic DPO preference pairing from scores | ✅ Real |
| Submit NeMo Customizer job (dry-run request + curl) | ✅ Real |
| Live job submit + status poll (against your endpoint) | ✅ Real (unverified API shape) |
| Human-in-the-loop rating with editor pause/resume | ⏳ Planned |
| Dataset upload to NeMo Data Store | ⏳ Planned |
