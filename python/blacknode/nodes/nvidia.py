from __future__ import annotations

import json
import os
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
            "nvidia-local-nim-launch",
            "nvidia-nim-benchmark",
        ],
        "steps": steps,
    }
    plan = "NVIDIA workflow plan\n" + "\n".join(steps) + "\nStack: " + ", ".join(technologies)
    return {"plan": plan, "technologies": technologies, "blueprint": blueprint}
