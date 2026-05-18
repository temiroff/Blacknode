from blacknode.node import node
from blacknode.providers import resolve, ToolDef


@node(
    inputs=["prompt:Text", "system:Text", "model:Text", "max_tokens:Int", "temperature:Float"],
    outputs=["text:Text"],
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


@node(
    inputs=["prompt:Text", "system:Text", "model:Text", "tools:List", "max_tokens:Int", "max_iter:Int"],
    outputs=["result:Text", "steps:List"],
    name="AgentLoop",
)
def agent_loop(ctx: dict) -> dict:
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
            messages, model=clean_model, system=system,
            max_tokens=max_tokens, tools=tool_defs or None,
        )
        steps.append({"role": "assistant", "text": resp.text,
                      "tool_calls": [{"name": tc.name, "arguments": tc.arguments}
                                     for tc in resp.tool_calls]})
        if resp.stop_reason == "end_turn" or not resp.tool_calls:
            return {"result": resp.text, "steps": steps}

        tool_results = []
        for tc in resp.tool_calls:
            fn = tool_map.get(tc.name)
            output = fn(**tc.arguments) if fn else f"[error] unknown tool '{tc.name}'"
            tool_results.append({"tool_call_id": tc.id, "name": tc.name, "output": str(output)})
            steps.append({"role": "tool", "name": tc.name, "output": str(output)})

        messages.append({"role": "assistant", "content": resp.text or "[tool use]"})
        messages.append({
            "role": "user",
            "content": "\n".join(f"[{r['name']} result]: {r['output']}" for r in tool_results),
        })

    return {"result": "max iterations reached", "steps": steps}


@node(inputs=["fn:Fn", "args:Dict"], outputs=["result:Any"], name="ToolCall")
def tool_call(ctx: dict) -> dict:
    fn   = ctx.get("fn")
    args = ctx.get("args", {})
    if not callable(fn):
        raise ValueError("'fn' input must be a callable")
    result = fn(**args) if isinstance(args, dict) else fn(args)
    return {"result": result}


@node(inputs=["text:Text", "model:Text"],
      outputs=["embedding:Embedding"], name="EmbedText")
def embed_text(ctx: dict) -> dict:
    from openai import OpenAI
    import os
    text     = ctx.get("text", "")
    model    = ctx.get("model", "text-embedding-3-small")
    client = OpenAI(
        api_key=ctx.get("api_key") or os.environ.get("OPENAI_API_KEY", "sk-local"),
        base_url=ctx.get("base_url"),
    )
    resp = client.embeddings.create(input=text, model=model)
    return {"embedding": resp.data[0].embedding}
