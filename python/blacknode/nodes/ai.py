"""AI agent nodes: LLMAgent, EmbedText, AgentLoop, ToolCall."""
from blacknode.node import node


@node(inputs=["prompt", "system", "model", "max_tokens"], outputs=["text"], name="LLMAgent")
def llm_agent(ctx: dict) -> dict:
    import anthropic

    prompt     = ctx.get("prompt", "")
    system     = ctx.get("system", "You are a helpful assistant.")
    model      = ctx.get("model", "claude-sonnet-4-6")
    max_tokens = int(ctx.get("max_tokens", 4096))

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"text": msg.content[0].text}


@node(inputs=["text", "model"], outputs=["embedding"], name="EmbedText")
def embed_text(ctx: dict) -> dict:
    import anthropic

    text  = ctx.get("text", "")
    # Anthropic doesn't have a direct embed API yet — placeholder using hash for structure
    # Replace with your preferred embedding provider
    embedding = [hash(text) % 1000 / 1000.0] * 1536
    return {"embedding": embedding}


@node(inputs=["prompt", "tools", "system", "model", "max_iter"], outputs=["result", "steps"], name="AgentLoop")
def agent_loop(ctx: dict) -> dict:
    """ReAct-style agent loop. 'tools' is a list of callables with __name__ and __doc__."""
    import anthropic
    import json

    prompt   = ctx.get("prompt", "")
    tools    = ctx.get("tools", [])
    system   = ctx.get("system", "You are a helpful agent. Use the available tools.")
    model    = ctx.get("model", "claude-sonnet-4-6")
    max_iter = int(ctx.get("max_iter", 5))

    client = anthropic.Anthropic()

    tool_defs = [
        {
            "name": t.__name__,
            "description": t.__doc__ or "",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }
        for t in tools
    ]
    tool_map = {t.__name__: t for t in tools}

    messages = [{"role": "user", "content": prompt}]
    steps = []

    for _ in range(max_iter):
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=tool_defs,
            messages=messages,
        )
        steps.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            result = next((b.text for b in resp.content if hasattr(b, "text")), "")
            return {"result": result, "steps": steps}

        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                fn = tool_map.get(block.name)
                output = fn(**block.input) if fn else f"Unknown tool: {block.name}"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})

    return {"result": "max iterations reached", "steps": steps}


@node(inputs=["fn", "args"], outputs=["result"], name="ToolCall")
def tool_call(ctx: dict) -> dict:
    fn   = ctx.get("fn")
    args = ctx.get("args", {})
    if not callable(fn):
        raise ValueError("'fn' input must be a callable")
    result = fn(**args) if isinstance(args, dict) else fn(args)
    return {"result": result}
