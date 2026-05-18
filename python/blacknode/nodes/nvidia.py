"""NVIDIA NIM nodes — run NVIDIA-hosted models via the NIM inference API.

Get a free API key at: https://build.nvidia.com
"""
from __future__ import annotations
from blacknode.node import node

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

# curated list of popular NIM models
NIM_MODELS = [
    "meta/llama-3.1-8b-instruct",            # free tier, reliable
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.3-70b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1", # NVIDIA flagship (2025)
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "microsoft/phi-3-mini-128k-instruct",
    "google/gemma-2-9b-it",
    "deepseek-ai/deepseek-r1",
    "qwen/qwen2.5-72b-instruct",
]


@node(
    inputs=["prompt:Text", "system:Text", "model:Model", "max_tokens:Int", "temperature:Float"],
    outputs=["text:Text"],
    name="NIMAgent",
)
def nim_agent(ctx: dict) -> dict:
    """Call any NVIDIA NIM model. Get your API key at build.nvidia.com."""
    import os
    from openai import OpenAI

    model       = ctx.get("model", "meta/llama-3.1-8b-instruct")
    if ':' in model: model = model.split(':', 1)[1]  # strip "nim:" prefix from Model picker
    system      = ctx.get("system", "You are a helpful assistant.")
    prompt      = ctx.get("prompt", "")
    api_key     = ctx.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
    max_tokens  = int(ctx.get("max_tokens", 1024))
    temperature = float(ctx.get("temperature", 0.7))

    if not api_key:
        raise ValueError(
            "NVIDIA API key required. "
            "Set NVIDIA_API_KEY env var or pass it as the api_key param. "
            "Get one free at https://build.nvidia.com"
        )

    client = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return {"text": resp.choices[0].message.content or ""}


@node(inputs=[], outputs=["models:List"], name="NIMModels")
def nim_models(ctx: dict) -> dict:
    """Outputs the list of popular NIM model names — wire into NIMAgent's model port."""
    return {"models": NIM_MODELS}


@node(
    inputs=["prompt:Text", "model:Model", "max_tokens:Int"],
    outputs=["text:Text"],
    name="NIMStream",
)
def nim_stream(ctx: dict) -> dict:
    """Streaming NIM call — collects the full streamed response."""
    import os
    from openai import OpenAI

    model      = ctx.get("model", "meta/llama-3.1-8b-instruct")
    if ':' in model: model = model.split(':', 1)[1]
    prompt     = ctx.get("prompt", "")
    api_key    = ctx.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
    max_tokens = int(ctx.get("max_tokens", 1024))

    if not api_key:
        raise ValueError("NVIDIA_API_KEY required. Get one free at https://build.nvidia.com")

    client = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)
    chunks = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        stream=True,
    )
    text = "".join(
        c.choices[0].delta.content or ""
        for c in chunks
        if c.choices
    )
    return {"text": text}
