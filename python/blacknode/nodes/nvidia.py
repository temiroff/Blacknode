from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from blacknode.node import node
from blacknode.providers.keys import api_key_for_provider
from blacknode.providers.openai_provider import OpenAIProvider

HOSTED_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NIM_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_NIM_IMAGE = "nvcr.io/nim/meta/llama-3.1-8b-instruct:latest"
DEFAULT_NEMOTRON_MODEL = "nim:nvidia/llama-3.3-nemotron-super-49b-v1.5"


def _clean_model(model: Any) -> str:
    value = str(model or DEFAULT_NIM_MODEL).strip()
    return value.removeprefix("nim:") or DEFAULT_NIM_MODEL


def _base_url(value: Any) -> str:
    raw = str(value or HOSTED_NIM_BASE_URL).strip()
    return raw.rstrip("/") or HOSTED_NIM_BASE_URL


def _nim_api_key(explicit: Any = None) -> str:
    return api_key_for_provider("NVIDIA NIM", "NVIDIA_API_KEY", str(explicit or "").strip())


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_csv(value: Any, default: list[str]) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return default
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or default


def _manifest_files(manifest: Any) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    files = manifest.get("files")
    return [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "off", "")


def _dataset_stats(path_value: Any) -> dict[str, Any] | None:
    """Report existence and JSONL record count for a local dataset file."""
    raw = str(path_value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        return {"path": raw, "exists": False, "records": 0}
    try:
        with open(path, encoding="utf-8") as handle:
            records = sum(1 for line in handle if line.strip())
    except OSError:
        records = 0
    return {"path": str(path), "exists": True, "records": records}


def _post_json(url: str, api_key: str, body: dict, timeout: float) -> tuple[bool, int, dict]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib_request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            status = int(getattr(res, "status", 200))
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"error": raw}
        return False, int(exc.code), parsed if isinstance(parsed, dict) else {"error": raw}
    except Exception as exc:
        return False, 0, {"error": f"{type(exc).__name__}: {exc}"}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw": raw}
    return 200 <= status < 300, status, parsed if isinstance(parsed, dict) else {"raw": raw}


def _customizer_curl(url: str, body: dict) -> str:
    payload = json.dumps(body)
    return (
        f"curl -X POST '{url}' "
        "-H 'Authorization: Bearer $NVIDIA_API_KEY' "
        "-H 'Content-Type: application/json' "
        f"-d '{payload}'"
    )


def _run_check(args: list[str], timeout: float = 2.0) -> tuple[bool, str]:
    executable = args[0]
    if shutil.which(executable) is None:
        return False, f"{executable} not found"
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


@node(
    inputs=[],
    outputs=["summary:Text", "has_gpu:Bool", "gpu_count:Int", "docker:Bool", "details:Dict"],
    name="NVIDIASystemCheck",
)
def nvidia_system_check(ctx: dict) -> dict:
    """Check local NVIDIA GPU, driver, and Docker visibility without changing the system."""
    gpu_ok, gpu_output = _run_check(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        timeout=3.0,
    )
    names = [line.strip() for line in gpu_output.splitlines() if line.strip()] if gpu_ok else []
    docker_ok, docker_output = _run_check(["docker", "--version"], timeout=2.0)

    details = {
        "gpu_names": names,
        "nvidia_smi": gpu_output,
        "docker_version": docker_output if docker_ok else "",
        "docker_error": "" if docker_ok else docker_output,
        "nim_api_key": "present" if _nim_api_key() else "missing",
        "ngc_api_key": "present" if os.environ.get("NGC_API_KEY") else "missing",
    }
    summary = (
        f"GPU: {'yes' if gpu_ok and names else 'no'}"
        f" ({len(names)} detected); Docker: {'yes' if docker_ok else 'no'}; "
        f"NVIDIA_API_KEY: {details['nim_api_key']}; NGC_API_KEY: {details['ngc_api_key']}"
    )
    return {
        "summary": summary,
        "has_gpu": bool(gpu_ok and names),
        "gpu_count": len(names),
        "docker": docker_ok,
        "details": details,
    }


@node(
    inputs=["folder:Text=videos", "extensions:Text=.mp4,.mov,.mkv,.avi,.webm"],
    outputs=["manifest:Dict", "files:List", "summary:Text"],
    name="VideoFolderInput",
)
def video_folder_input(ctx: dict) -> dict:
    """Describe a local video folder for a visual NVIDIA planning workflow."""
    folder = str(ctx.get("folder") or "videos").strip()
    extensions = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in _split_csv(
        ctx.get("extensions"),
        [".mp4", ".mov", ".mkv", ".avi", ".webm"],
    )]
    path = Path(folder).expanduser()
    exists = path.exists()
    is_dir = path.is_dir()
    file_rows: list[dict[str, Any]] = []

    if exists and is_dir:
        for candidate in sorted(path.rglob("*")):
            if len(file_rows) >= 200:
                break
            if candidate.is_file() and candidate.suffix.lower() in extensions:
                try:
                    size = candidate.stat().st_size
                except OSError:
                    size = 0
                file_rows.append({
                    "path": str(candidate),
                    "name": candidate.name,
                    "extension": candidate.suffix.lower(),
                    "bytes": size,
                })

    status = "ready" if file_rows else "folder not found" if not exists else "no matching videos"
    summary = (
        f"Video folder: {folder}; status: {status}; "
        f"files: {len(file_rows)}; extensions: {', '.join(extensions)}"
    )
    manifest = {
        "folder": folder,
        "exists": exists,
        "is_dir": is_dir,
        "extensions": extensions,
        "files": file_rows,
        "file_count": len(file_rows),
        "status": status,
    }
    return {"manifest": manifest, "files": file_rows, "summary": summary}


@node(
    inputs=[
        "mode:Text=hosted",
        "endpoint_url:Text=https://integrate.api.nvidia.com/v1",
        "local_endpoint_url:Text=http://127.0.0.1:8000/v1",
        f"model:Model={DEFAULT_NEMOTRON_MODEL}",
    ],
    outputs=["route:Text", "endpoint_url:Text", "stack:List", "requirements:List", "blueprint:Dict"],
    name="NVIDIADeploymentChoice",
)
def nvidia_deployment_choice(ctx: dict) -> dict:
    """Select a hosted, local, or hybrid NVIDIA NIM deployment route."""
    mode = str(ctx.get("mode") or "hosted").strip().lower()
    hosted_endpoint = _base_url(ctx.get("endpoint_url"))
    local_endpoint = _base_url(ctx.get("local_endpoint_url") or "http://127.0.0.1:8000/v1")
    model = str(ctx.get("model") or DEFAULT_NEMOTRON_MODEL).strip()

    if mode.startswith("local"):
        route = "Local NIM"
        endpoint = local_endpoint
        stack = ["local NIM container", "NVIDIA Container Toolkit", "NGC image", model]
        requirements = ["Docker", "NVIDIA GPU and driver", "NVIDIA Container Toolkit", "NGC_API_KEY"]
    elif mode.startswith("hybrid"):
        route = "Hybrid hosted/local NIM"
        endpoint = hosted_endpoint
        stack = ["hosted NIM fallback", "local NIM endpoint", "OpenAI-compatible routing", model]
        requirements = ["NVIDIA_API_KEY", "optional local NIM container", "health check before routing"]
    else:
        route = "Hosted NIM"
        endpoint = hosted_endpoint
        stack = ["NVIDIA hosted NIM", "OpenAI-compatible endpoint", model]
        requirements = ["NVIDIA_API_KEY"]

    blueprint = {
        "route": route,
        "mode": mode,
        "endpoint_url": endpoint,
        "model": model,
        "stack": stack,
        "requirements": requirements,
    }
    route_text = (
        f"{route}\nEndpoint: {endpoint}\nModel: {model}\n"
        f"Requirements: {', '.join(requirements)}"
    )
    return {
        "route": route_text,
        "endpoint_url": endpoint,
        "stack": stack,
        "requirements": requirements,
        "blueprint": blueprint,
    }


@node(
    inputs=["manifest:Dict", "goal:Text", "deployment:Dict"],
    outputs=["plan:Text", "cosmos_path:Text", "vlm_path:Text", "blueprint:Dict"],
    name="NVIDIAVideoSummaryPlan",
)
def nvidia_video_summary_plan(ctx: dict) -> dict:
    """Plan the video understanding stage for Cosmos or VLM NIM services."""
    manifest = _dict_value(ctx.get("manifest"))
    files = _manifest_files(manifest)
    goal = str(ctx.get("goal") or "Summarize video events and prepare them for retrieval.").strip()
    deployment = _dict_value(ctx.get("deployment"))
    route = str(deployment.get("route") or "Hosted NIM")
    file_count = len(files)
    cosmos_path = "Cosmos video/world model path: segment videos, create video-text embeddings, attach timestamps."
    vlm_path = "VLM NIM path: sample frames or clips, caption events, emit timestamped scene summaries."
    steps = [
        "1. Read the video folder manifest and split each file into searchable time ranges.",
        "2. Use Cosmos-style video embeddings or a vision-language NIM path for event descriptions.",
        "3. Attach file, timestamp, caption, and confidence metadata to each segment.",
        "4. Send segment summaries to the retriever stage for indexing and reranking.",
    ]
    plan = (
        "NVIDIA video understanding plan\n"
        f"Goal: {goal}\n"
        f"Files discovered: {file_count}\n"
        f"Deployment route: {route}\n"
        + "\n".join(steps)
    )
    blueprint = {
        "goal": goal,
        "file_count": file_count,
        "folder": manifest.get("folder"),
        "deployment_route": route,
        "cosmos_path": cosmos_path,
        "vlm_path": vlm_path,
        "steps": steps,
    }
    return {"plan": plan, "cosmos_path": cosmos_path, "vlm_path": vlm_path, "blueprint": blueprint}


@node(
    inputs=["manifest:Dict", "video_plan:Text", "query:Text"],
    outputs=["index_plan:Text", "retriever_stack:List", "blueprint:Dict"],
    name="NVIDIARetrieverIndexPlan",
)
def nvidia_retriever_index_plan(ctx: dict) -> dict:
    """Plan a NeMo Retriever-style index and rerank stage for video segments."""
    manifest = _dict_value(ctx.get("manifest"))
    files = _manifest_files(manifest)
    query = str(ctx.get("query") or "What important events happened in these videos?").strip()
    stack = [
        "NeMo Retriever embedding path",
        "metadata-aware vector index",
        "reranking NIM",
        "timestamp and source-file filters",
    ]
    steps = [
        "1. Convert timestamped video summaries into retrievable chunks.",
        "2. Store file, timestamp, event labels, and generated captions as metadata.",
        "3. Use retriever embeddings for recall and reranking for answer quality.",
        "4. Return top segments to the NIM LLM question-answer stage.",
    ]
    index_plan = (
        "NVIDIA retrieval plan\n"
        f"Query: {query}\n"
        f"Video files: {len(files)}\n"
        f"Stack: {', '.join(stack)}\n"
        + "\n".join(steps)
    )
    blueprint = {
        "query": query,
        "file_count": len(files),
        "retriever_stack": stack,
        "steps": steps,
        "video_plan": str(ctx.get("video_plan") or ""),
    }
    return {"index_plan": index_plan, "retriever_stack": stack, "blueprint": blueprint}


@node(
    inputs=[
        "question:Text",
        "index_plan:Text",
        f"model:Model={DEFAULT_NEMOTRON_MODEL}",
        "deployment:Dict",
    ],
    outputs=["answer_plan:Text", "prompt:Text", "blueprint:Dict"],
    name="NVIDIAQuestionAnswerPlan",
)
def nvidia_question_answer_plan(ctx: dict) -> dict:
    """Plan a NIM/Nemotron question-answer step over retrieved video segments."""
    question = str(ctx.get("question") or "What happened in the video set?").strip()
    model = str(ctx.get("model") or DEFAULT_NEMOTRON_MODEL).strip()
    deployment = _dict_value(ctx.get("deployment"))
    route = str(deployment.get("route") or "Hosted NIM")
    endpoint = str(deployment.get("endpoint_url") or HOSTED_NIM_BASE_URL)
    prompt = (
        "Use the retrieved video segments as evidence. Answer the question, cite "
        "file names and timestamps when available, and separate observed events "
        "from inferred conclusions.\n\n"
        f"Question: {question}"
    )
    answer_plan = (
        "NVIDIA NIM/Nemotron question-answer plan\n"
        f"Route: {route}\nEndpoint: {endpoint}\nModel: {model}\n"
        "Inputs: top retrieved video segments, captions, timestamps, and source metadata.\n"
        "Outputs: answer, cited evidence, uncertainty notes, and follow-up queries."
    )
    blueprint = {
        "question": question,
        "model": model,
        "route": route,
        "endpoint_url": endpoint,
        "prompt": prompt,
        "index_plan": str(ctx.get("index_plan") or ""),
    }
    return {"answer_plan": answer_plan, "prompt": prompt, "blueprint": blueprint}


@node(
    inputs=[
        "goal:Text",
        "folder_summary:Text",
        "video_plan:Text",
        "retriever_plan:Text",
        "qa_plan:Text",
        "deployment_route:Text",
    ],
    outputs=["report:Text", "checklist:List", "blueprint:Dict"],
    name="NVIDIAMissionReport",
)
def nvidia_mission_report(ctx: dict) -> dict:
    """Assemble the visual NVIDIA AI mission-control report."""
    goal = str(ctx.get("goal") or "").strip()
    folder_summary = str(ctx.get("folder_summary") or "").strip()
    video_plan = str(ctx.get("video_plan") or "").strip()
    retriever_plan = str(ctx.get("retriever_plan") or "").strip()
    qa_plan = str(ctx.get("qa_plan") or "").strip()
    deployment_route = str(ctx.get("deployment_route") or "").strip()
    checklist = [
        "Video input manifest prepared",
        "Cosmos or VLM NIM understanding path selected",
        "NeMo Retriever index plan prepared",
        "NIM/Nemotron question-answer path prepared",
        "Hosted/local deployment route visible",
        "Run replay captures each cooked node",
        "Workflow can export to Python",
    ]
    report = "\n\n".join([
        "Blacknode NVIDIA AI Mission Control",
        f"Goal:\n{goal}",
        f"Input:\n{folder_summary}",
        f"Deployment:\n{deployment_route}",
        f"Video understanding:\n{video_plan}",
        f"Retrieval:\n{retriever_plan}",
        f"Question answering:\n{qa_plan}",
        "Checklist:\n- " + "\n- ".join(checklist),
    ])
    blueprint = {
        "goal": goal,
        "folder_summary": folder_summary,
        "deployment_route": deployment_route,
        "checklist": checklist,
    }
    return {"report": report, "checklist": checklist, "blueprint": blueprint}


@node(
    inputs=[
        "image:Text",
        "container_name:Text",
        "port:Int=8000",
        "cache_dir:Text",
        "ngc_api_key_env:Text=NGC_API_KEY",
    ],
    outputs=["powershell:Text", "bash:Text", "endpoint_url:Text", "notes:Text"],
    name="NIMDockerCommand",
)
def nim_docker_command(ctx: dict) -> dict:
    """Generate local NIM Docker commands without launching a container."""
    image = str(ctx.get("image") or DEFAULT_NIM_IMAGE).strip()
    container_name = str(ctx.get("container_name") or "blacknode-nim").strip()
    port = max(1, min(_int_value(ctx.get("port"), 8000), 65535))
    cache_dir = str(ctx.get("cache_dir") or ".cache/nim").strip()
    env_name = str(ctx.get("ngc_api_key_env") or "NGC_API_KEY").strip()
    endpoint_url = f"http://127.0.0.1:{port}/v1"

    powershell = (
        f"$env:LOCAL_NIM_CACHE='{cache_dir}'; "
        f"docker run --rm -it --name {container_name} --gpus all "
        f"--shm-size=16GB -e {env_name} "
        f"-v ${{env:LOCAL_NIM_CACHE}}:/opt/nim/.cache "
        f"-p {port}:8000 {image}"
    )
    bash = (
        f"export LOCAL_NIM_CACHE='{cache_dir}' && "
        f"docker run --rm -it --name {container_name} --gpus all "
        f"--shm-size=16GB -e {env_name} "
        f"-v \"$LOCAL_NIM_CACHE:/opt/nim/.cache\" "
        f"-p {port}:8000 {image}"
    )
    notes = (
        "Requires Docker, NVIDIA Container Toolkit, a supported NVIDIA GPU, "
        f"and {env_name} with NGC access. Use the endpoint output as the "
        "NIMHealthCheck or NIMAgent endpoint_url."
    )
    return {
        "powershell": powershell,
        "bash": bash,
        "endpoint_url": endpoint_url,
        "notes": notes,
    }


@node(
    inputs=[
        "endpoint_url:Text=https://integrate.api.nvidia.com/v1",
        "api_key:Text",
        "timeout:Float=5",
    ],
    outputs=["ok:Bool", "status:Int", "text:Text", "models:List"],
    name="NIMHealthCheck",
)
def nim_health_check(ctx: dict) -> dict:
    """Check a hosted or local NIM OpenAI-compatible /models endpoint."""
    endpoint = _base_url(ctx.get("endpoint_url"))
    timeout = max(0.5, min(_float_value(ctx.get("timeout"), 5.0), 30.0))
    headers = {"Accept": "application/json"}
    api_key = _nim_api_key(ctx.get("api_key"))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib_request.Request(f"{endpoint}/models", headers=headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            status = int(getattr(res, "status", 200))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": int(exc.code), "text": body, "models": []}
    except Exception as exc:
        return {"ok": False, "status": 0, "text": f"{type(exc).__name__}: {exc}", "models": []}

    models: list[str] = []
    try:
        data = json.loads(raw)
        items = data.get("data") if isinstance(data, dict) else None
        if isinstance(items, list):
            models = [str(item.get("id", "")) for item in items if isinstance(item, dict) and item.get("id")]
    except json.JSONDecodeError:
        pass

    return {"ok": 200 <= status < 300, "status": status, "text": raw, "models": models}


@node(
    inputs=[
        "prompt:Text",
        "system:Text",
        "model:Model=nim:meta/llama-3.1-8b-instruct",
        "endpoint_url:Text=https://integrate.api.nvidia.com/v1",
        "api_key:Text",
        "max_tokens:Int=1024",
        "temperature:Float=0.2",
    ],
    outputs=["text:Text"],
    name="NIMAgent",
)
def nim_agent(ctx: dict) -> dict:
    """Call hosted or local NVIDIA NIM through an OpenAI-compatible endpoint."""
    model = _clean_model(ctx.get("model"))
    endpoint = _base_url(ctx.get("endpoint_url"))
    max_tokens = max(1, min(_int_value(ctx.get("max_tokens"), 1024), 8192))
    temperature = _float_value(ctx.get("temperature"), 0.2)
    client = OpenAIProvider(api_key=_nim_api_key(ctx.get("api_key")), base_url=endpoint)

    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=model,
            provider="NVIDIA NIM",
            tool_count=0,
        )

    response = client.complete(
        [{"role": "user", "content": str(ctx.get("prompt", ""))}],
        model=model,
        system=str(ctx.get("system") or "You are a helpful NVIDIA NIM assistant."),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return {"text": response.text}


@node(
    inputs=[
        "prompt:Text",
        "system:Text",
        "model:Model=nim:meta/llama-3.1-8b-instruct",
        "endpoint_url:Text=https://integrate.api.nvidia.com/v1",
        "api_key:Text",
        "repetitions:Int=3",
        "max_tokens:Int=512",
        "temperature:Float=0.2",
    ],
    outputs=["text:Text", "metrics:Dict", "latency_ms:Float"],
    name="NIMBenchmark",
)
def nim_benchmark(ctx: dict) -> dict:
    """Run a small latency benchmark against hosted or local NVIDIA NIM."""
    repetitions = max(1, min(_int_value(ctx.get("repetitions"), 3), 10))
    latencies: list[float] = []
    texts: list[str] = []

    for _ in range(repetitions):
        started = time.perf_counter()
        result = nim_agent(ctx)
        latencies.append((time.perf_counter() - started) * 1000)
        texts.append(str(result.get("text", "")))

    avg = sum(latencies) / len(latencies)
    metrics = {
        "provider": "NVIDIA NIM",
        "model": _clean_model(ctx.get("model")),
        "endpoint_url": _base_url(ctx.get("endpoint_url")),
        "repetitions": repetitions,
        "latency_ms": {
            "avg": round(avg, 3),
            "min": round(min(latencies), 3),
            "max": round(max(latencies), 3),
            "samples": [round(v, 3) for v in latencies],
        },
    }
    return {"text": texts[-1], "metrics": metrics, "latency_ms": avg}


@node(
    inputs=["goal:Text"],
    outputs=["plan:Text", "technologies:List", "blueprint:Dict"],
    name="NVIDIABlueprintPlan",
)
def nvidia_blueprint_plan(ctx: dict) -> dict:
    """Map a product goal to NVIDIA technologies that can be represented as a workflow."""
    goal = str(ctx.get("goal") or "").strip()
    lower = goal.lower()
    technologies: list[str] = ["NVIDIA NIM", "NVIDIA AI Enterprise"]

    if any(word in lower for word in ("rag", "search", "retrieval", "document", "knowledge")):
        technologies.extend(["NeMo Retriever", "embedding NIM", "reranking NIM"])
    if any(word in lower for word in ("video", "vision", "camera", "image", "visual")):
        technologies.extend(["Cosmos", "vision-language NIM", "GPU video preprocessing"])
    if any(word in lower for word in ("speech", "voice", "audio")):
        technologies.extend(["speech NIM", "Riva-compatible speech services"])
    if any(word in lower for word in ("deploy", "serve", "latency", "throughput", "benchmark")):
        technologies.extend(["Triton Inference Server", "TensorRT-LLM", "NVIDIA Container Toolkit"])
    if any(word in lower for word in ("dataframe", "etl", "analytics", "gpu data")):
        technologies.extend(["RAPIDS", "cuDF"])

    seen: set[str] = set()
    technologies = [t for t in technologies if not (t in seen or seen.add(t))]
    steps = [
        "1. Select hosted NIM for the first demo or local NIM when the workstation has Docker, GPU drivers, and NGC access.",
        "2. Add input nodes for the workload and route them through NVIDIA model/service nodes.",
        "3. Add health, benchmark, and run-replay outputs so latency and failures are visible on the graph.",
        "4. Export the workflow to Python when the demo needs a handoff artifact.",
    ]
    blueprint = {
        "goal": goal,
        "technologies": technologies,
        "recommended_templates": [
            "nvidia-ai-mission-control",
            "nvidia-video-intelligence-mission-control",
            "nvidia-local-nim-launch",
            "nvidia-nim-benchmark",
        ],
        "steps": steps,
    }
    plan = "NVIDIA workflow plan\n" + "\n".join(steps) + "\nStack: " + ", ".join(technologies)
    return {"plan": plan, "technologies": technologies, "blueprint": blueprint}


DEFAULT_CUSTOMIZER_CONFIG = "meta/llama-3.1-8b-instruct@v1.0.0+A100"


@node(
    inputs=[
        "base_url:Text",
        f"config:Text={DEFAULT_CUSTOMIZER_CONFIG}",
        "dataset:Text",
        "dataset_file:Text",
        "namespace:Text=default",
        "output_model:Text",
        "training_type:Text=sft",
        "finetuning_type:Text=lora",
        "epochs:Int=3",
        "batch_size:Int=16",
        "learning_rate:Float=0.0001",
        "adapter_dim:Int=16",
        "api_key:Text",
        "api_version:Text=v1",
        "dry_run:Bool=true",
        "timeout:Float=30",
    ],
    outputs=["job_id:Text", "status:Text", "request:Dict", "curl:Text", "response:Dict", "notes:Text"],
    name="NIMFineTune",
)
def nim_fine_tune(ctx: dict) -> dict:
    """Submit a fine-tuning job to NVIDIA NeMo Customizer (dry-run by default).

    Closes the Blacknode loop: ``export-training`` produces ``dataset.jsonl``,
    this node launches an ``sft`` or ``dpo`` customization job for it. Defaults
    to a dry run that returns the exact POST request and a runnable ``curl`` —
    set ``dry_run=false`` with ``base_url``, ``api_key``, and a registered
    ``dataset`` to actually launch.
    """
    base = str(ctx.get("base_url") or "").strip().rstrip("/")
    api_version = str(ctx.get("api_version") or "v1").strip().strip("/") or "v1"
    config = str(ctx.get("config") or DEFAULT_CUSTOMIZER_CONFIG).strip()
    dataset = str(ctx.get("dataset") or "").strip()
    namespace = str(ctx.get("namespace") or "default").strip()
    output_model = str(ctx.get("output_model") or "").strip()
    training_type = str(ctx.get("training_type") or "sft").strip().lower()
    finetuning_type = str(ctx.get("finetuning_type") or "lora").strip().lower()
    epochs = max(1, _int_value(ctx.get("epochs"), 3))
    batch_size = max(1, _int_value(ctx.get("batch_size"), 16))
    learning_rate = _float_value(ctx.get("learning_rate"), 1e-4)
    adapter_dim = max(1, _int_value(ctx.get("adapter_dim"), 16))
    timeout = max(1.0, min(_float_value(ctx.get("timeout"), 30.0), 600.0))
    api_key = _nim_api_key(ctx.get("api_key"))
    dataset_stats = _dataset_stats(ctx.get("dataset_file"))

    hyperparameters: dict[str, Any] = {
        "training_type": training_type,
        "finetuning_type": finetuning_type,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
    }
    if finetuning_type.startswith("lora"):
        hyperparameters["lora"] = {"adapter_dim": adapter_dim}
    body: dict[str, Any] = {
        "config": config,
        "dataset": {"name": dataset, "namespace": namespace},
        "hyperparameters": hyperparameters,
    }
    if output_model:
        body["output_model"] = output_model

    url = f"{base}/{api_version}/customization/jobs" if base else f"/{api_version}/customization/jobs"
    request: dict[str, Any] = {"method": "POST", "url": url, "body": body}
    if dataset_stats is not None:
        request["dataset_file"] = dataset_stats
    curl = _customizer_curl(url, body)

    notes: list[str] = []
    if dataset_stats is not None:
        if not dataset_stats["exists"]:
            notes.append(f"dataset_file '{dataset_stats['path']}' not found")
        else:
            notes.append(
                f"local dataset_file has {dataset_stats['records']} records; register it in the "
                f"NeMo Data Store as '{namespace}/{dataset or '<dataset>'}' before launching"
            )

    prerequisites_ok = bool(base and api_key and dataset)
    wants_live = not _bool_value(ctx.get("dry_run"), True)
    if wants_live and not prerequisites_ok:
        missing = [name for name, value in (("base_url", base), ("api_key", api_key), ("dataset", dataset)) if not value]
        notes.append("cannot launch live: missing " + ", ".join(missing))

    if not wants_live or not prerequisites_ok:
        notes.insert(0, "dry run: no job submitted")
        return {
            "job_id": "",
            "status": "dry_run",
            "request": request,
            "curl": curl,
            "response": {},
            "notes": "; ".join(notes),
        }

    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=config,
            provider="NVIDIA NeMo Customizer",
            action="customization",
        )
    ok, status_code, response = _post_json(url, api_key, body, timeout)
    job_id = str(response.get("id") or response.get("job_id") or "")
    status = str(response.get("status") or ("submitted" if ok else "error"))
    notes.insert(0, f"HTTP {status_code}")
    return {
        "job_id": job_id,
        "status": status,
        "request": request,
        "curl": curl,
        "response": response,
        "notes": "; ".join(notes),
    }


@node(
    inputs=[
        "base_url:Text",
        "job_id:Text",
        "api_key:Text",
        "api_version:Text=v1",
        "timeout:Float=10",
    ],
    outputs=["ok:Bool", "status:Text", "percent:Float", "response:Dict"],
    name="NIMFineTuneStatus",
)
def nim_fine_tune_status(ctx: dict) -> dict:
    """Poll a NeMo Customizer customization job's status."""
    base = str(ctx.get("base_url") or "").strip().rstrip("/")
    api_version = str(ctx.get("api_version") or "v1").strip().strip("/") or "v1"
    job_id = str(ctx.get("job_id") or "").strip()
    timeout = max(0.5, min(_float_value(ctx.get("timeout"), 10.0), 60.0))
    api_key = _nim_api_key(ctx.get("api_key"))
    if not base or not job_id:
        return {"ok": False, "status": "missing base_url or job_id", "percent": 0.0, "response": {}}

    url = f"{base}/{api_version}/customization/jobs/{job_id}/status"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib_request.Request(url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            status_code = int(getattr(res, "status", 200))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": f"HTTP {exc.code}", "percent": 0.0, "response": {"error": body}}
    except Exception as exc:
        return {"ok": False, "status": f"{type(exc).__name__}: {exc}", "percent": 0.0, "response": {}}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    data = data if isinstance(data, dict) else {"raw": raw}
    status = str(data.get("status") or "")
    percent = _float_value(data.get("percentage_done"), 0.0)
    return {"ok": 200 <= status_code < 300, "status": status or f"HTTP {status_code}", "percent": percent, "response": data}
