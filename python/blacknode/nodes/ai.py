from blacknode.node import node
from blacknode.providers import resolve, ToolDef


@node(
    inputs=["prompt:Text", "system:Text", "model:Model=claude-sonnet-4-6", "max_tokens:Int=4096", "temperature:Float=1.0"],
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
    inputs=["prompt:Text", "system:Text", "model:Model=claude-sonnet-4-6", "tools:List", "max_tokens:Int=4096", "max_iter:Int=5"],
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


@node(inputs=["code:Text", "name:Text", "description:Text"], outputs=["fn:Fn"], name="PythonFn")
def python_fn(ctx: dict) -> dict:
    """Write a Python function named 'run'; it becomes a callable tool."""
    import inspect
    code        = (ctx.get("code") or "").strip()
    fn_name     = (ctx.get("name") or "tool").strip()
    description = (ctx.get("description") or "").strip()
    if not code:
        raise ValueError("PythonFn: 'code' param is empty — define a function named 'run'.")
    local_ns: dict = {}
    exec(compile(code, "<PythonFn>", "exec"), {"__builtins__": __builtins__}, local_ns)
    fn = local_ns.get("run") or next((v for v in local_ns.values() if callable(v)), None)
    if fn is None:
        raise ValueError("PythonFn: no callable found — define a function named 'run'.")
    fn.__name__ = fn_name
    fn.__doc__  = description
    # Build JSON schema from type annotations
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
    props: dict = {}
    required: list = []
    for pname, param in inspect.signature(fn).parameters.items():
        ann = param.annotation if param.annotation is not inspect.Parameter.empty else str
        props[pname] = {"type": type_map.get(ann, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    fn._bn_schema = {"type": "object", "properties": props, "required": required}
    return {"fn": fn}


@node(inputs=["subnet_label:Text", "name:Text", "description:Text"], outputs=["fn:Fn"], name="SubnetAsTool")
def subnet_as_tool(ctx: dict) -> dict:
    """Wrap a Subnet node (identified by its label) as a callable tool for AgentLoop."""
    graph         = ctx.get("__graph__")
    subnet_label  = (ctx.get("subnet_label") or "").strip()
    fn_name       = (ctx.get("name") or subnet_label or "subnet_tool").strip()
    description   = (ctx.get("description") or "").strip()
    if not graph:
        raise ValueError("SubnetAsTool: graph context unavailable.")
    if not subnet_label:
        raise ValueError("SubnetAsTool: 'subnet_label' param is required.")
    # Find subnet by label
    target_id: str | None = None
    for nid, ndef in graph._nodes.items():
        if ndef["type"] == "Subnet" and ndef.get("params", {}).get("label") == subnet_label:
            target_id = nid
            break
    if target_id is None:
        raise ValueError(f"SubnetAsTool: no Subnet with label '{subnet_label}' found.")
    # Derive parameter schema from SubnetInput's output ports
    inner_meta = graph._nodes[target_id].get("subgraph", {}).get("node_meta", {})
    props: dict = {}
    output_port = "output"
    for m in inner_meta.values():
        if m.get("type") == "SubnetInput":
            for p in m.get("outputs", []):
                t = m.get("output_types", {}).get(p, "string")
                type_map = {"Text": "string", "Int": "integer", "Float": "number", "Bool": "boolean"}
                props[p] = {"type": type_map.get(t, "string")}
        elif m.get("type") == "SubnetOutput":
            ins = m.get("inputs", [])
            if ins:
                output_port = ins[0]
    def _make_tool(sid: str, oport: str):
        def tool(**kwargs):
            result = graph._cook_subnet(sid, oport, kwargs)
            return result.get(oport)
        return tool
    fn = _make_tool(target_id, output_port)
    fn.__name__ = fn_name
    fn.__doc__  = description
    fn._bn_schema = {"type": "object", "properties": props, "required": list(props.keys())}
    return {"fn": fn}


@node(
    inputs=["tool_1:Fn", "tool_2:Fn", "tool_3:Fn", "tool_4:Fn"],
    outputs=["tools:List"],
    name="ToolBox",
)
def toolbox(ctx: dict) -> dict:
    """Collect up to 4 Fn values into a list for AgentLoop.tools."""
    tools = [v for k in ("tool_1", "tool_2", "tool_3", "tool_4")
             if callable(v := ctx.get(k))]
    return {"tools": tools}


@node(inputs=["text:Text", "model:Model"],
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
