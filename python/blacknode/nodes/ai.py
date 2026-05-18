"""AI agent nodes — provider-agnostic.

Supported via the `model` name or explicit `provider` param:
  claude-*               → Anthropic
  gpt-* / o1-* / o4-*   → OpenAI
  ollama:<name>          → Ollama  (localhost:11434)
  local:<name>           → any OpenAI-compat endpoint (set base_url)
"""
from __future__ import annotations
from blacknode.node import node
from blacknode.providers import resolve, ToolDef


# ── LLMAgent ──────────────────────────────────────────────────────────────────

@node(
    inputs=["prompt", "system", "model", "provider", "base_url", "api_key", "max_tokens", "temperature"],
    outputs=["text"],
    name="LLMAgent",
)
def llm_agent(ctx: dict) -> dict:
    model       = ctx.get("model", "claude-sonnet-4-6")
    system      = ctx.get("system", "You are a helpful assistant.")
    prompt      = ctx.get("prompt", "")
    max_tokens  = int(ctx.get("max_tokens", 4096))
    temperature = float(ctx.get("temperature", 1.0))

    provider, clean_model = resolve(
        model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )

    resp = provider.complete(
        messages=[{"role": "user", "content": prompt}],
        model=clean_model,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return {"text": resp.text}


# ── AgentLoop (ReAct) ─────────────────────────────────────────────────────────

@node(
    inputs=["prompt", "tools", "system", "model", "provider", "base_url", "api_key", "max_tokens", "max_iter"],
    outputs=["result", "steps"],
    name="AgentLoop",
)
def agent_loop(ctx: dict) -> dict:
    """Provider-agnostic ReAct loop. `tools` is a list of callables."""
    model      = ctx.get("model", "claude-sonnet-4-6")
    system     = ctx.get("system", "You are a helpful agent. Use the available tools.")
    prompt     = ctx.get("prompt", "")
    tools      = ctx.get("tools") or []
    max_tokens = int(ctx.get("max_tokens", 4096))
    max_iter   = int(ctx.get("max_iter", 5))

    provider, clean_model = resolve(
        model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )

    tool_defs = [
        ToolDef(
            name=t.__name__,
            description=(t.__doc__ or "").strip(),
            parameters=getattr(t, "_bn_schema", {"type": "object", "properties": {}}),
        )
        for t in tools
    ]
    tool_map = {t.__name__: t for t in tools}

    messages: list[dict] = [{"role": "user", "content": prompt}]
    steps: list[dict] = []

    for _ in range(max_iter):
        resp = provider.complete(
            messages,
            model=clean_model,
            system=system,
            max_tokens=max_tokens,
            tools=tool_defs or None,
        )
        steps.append({"role": "assistant", "text": resp.text, "tool_calls": [
            {"name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls
        ]})

        if resp.stop_reason == "end_turn" or not resp.tool_calls:
            return {"result": resp.text, "steps": steps}

        # execute tool calls and build the next user turn
        tool_results = []
        for tc in resp.tool_calls:
            fn = tool_map.get(tc.name)
            if fn is None:
                output = f"[error] unknown tool '{tc.name}'"
            else:
                try:
                    output = fn(**tc.arguments)
                except Exception as exc:
                    output = f"[error] {exc}"
            tool_results.append({"tool_call_id": tc.id, "name": tc.name, "output": str(output)})
            steps.append({"role": "tool", "name": tc.name, "output": str(output)})

        # append the assistant turn + tool results as a user turn
        messages.append({"role": "assistant", "content": resp.text or "[tool use]"})
        messages.append({
            "role": "user",
            "content": "\n".join(f"[{r['name']} result]: {r['output']}" for r in tool_results),
        })

    return {"result": "max iterations reached", "steps": steps}


# ── ToolCall ──────────────────────────────────────────────────────────────────

@node(inputs=["fn", "args"], outputs=["result"], name="ToolCall")
def tool_call(ctx: dict) -> dict:
    fn   = ctx.get("fn")
    args = ctx.get("args", {})
    if not callable(fn):
        raise ValueError("'fn' input must be a callable")
    result = fn(**args) if isinstance(args, dict) else fn(args)
    return {"result": result}


# ── EmbedText ─────────────────────────────────────────────────────────────────

@node(inputs=["text", "model", "provider", "base_url", "api_key"], outputs=["embedding"], name="EmbedText")
def embed_text(ctx: dict) -> dict:
    text     = ctx.get("text", "")
    model    = ctx.get("model", "text-embedding-3-small")
    api_key  = ctx.get("api_key")
    base_url = ctx.get("base_url")

    from openai import OpenAI
    import os
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY", "sk-local"),
        base_url=base_url,
    )
    resp = client.embeddings.create(input=text, model=model)
    return {"embedding": resp.data[0].embedding}
