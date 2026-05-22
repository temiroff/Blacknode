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
