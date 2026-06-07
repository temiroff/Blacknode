import json
import re

from blacknode.node import node
from blacknode.providers import resolve, ToolCall, ToolDef, ToolResult

DEFAULT_MAX_TOKENS = 1024
NIM_CONTEXT_SAFE_MAX_TOKENS = 1024
_FINAL_ANSWER_RE = re.compile(r"\b(?:the\s+)?final answer is\s*:?\s*", re.IGNORECASE)
_TOOL_PROCESS_ONLY_RE = re.compile(
    r"^(?:"
    r"this response shows that .+ function was called.+"
    r"|the final answer is in the output of .+ tool call"
    r"|this is the result of .+ function call(?: with .+)?"
    r"|this is the final answer to (?:the )?user(?:'s)? prompt"
    r"|the output json is too long to be included here"
    r")\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _int_value(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _max_tokens_for_model(model: str, value) -> int:
    requested = max(1, _int_value(value, DEFAULT_MAX_TOKENS))
    # Some NIM models, including nemotron-mini-4b-instruct, expose a 4096-token
    # total context window. Treat the old 4096 completion default as unsafe.
    if str(model).startswith("nim:") and requested >= 4096:
        return NIM_CONTEXT_SAFE_MAX_TOKENS
    return requested


def _user_facing_answer(text: str) -> str:
    """Return only answer content, never a model's tool-processing narration."""
    value = str(text or "").strip()
    matches = list(_FINAL_ANSWER_RE.finditer(value))
    if matches:
        answer = value[matches[-1].end():].strip()
        if answer.lower().startswith(("in the output of ", "in the result of ")):
            return ""
        return answer
    if _TOOL_PROCESS_ONLY_RE.fullmatch(value):
        return ""
    return value


def _answer_or_tool_output(text: str, tool_output: str = "") -> str:
    return _user_facing_answer(text) or str(tool_output or "").strip()


def _tool_defs(tools: list) -> list[ToolDef]:
    return [
        ToolDef(
            name=t.__name__,
            description=(t.__doc__ or "").strip(),
            parameters=getattr(t, "_bn_schema", {"type": "object", "properties": {}}),
        )
        for t in tools
        if callable(t)
    ]


def _tool_call_dict(tc: ToolCall) -> dict:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


def _tool_call_signature(tool_calls: list) -> tuple:
    return tuple(
        (
            tc.name,
            json.dumps(tc.arguments, sort_keys=True, separators=(",", ":"), default=str),
        )
        for tc in (_tool_call(value) for value in tool_calls)
    )


def _tool_call(value) -> ToolCall:
    if isinstance(value, ToolCall):
        return value
    if not isinstance(value, dict):
        return ToolCall(id="", name="", arguments={})
    return ToolCall(
        id=str(value.get("id", "")),
        name=str(value.get("name", "")),
        arguments=value.get("arguments", {}) or {},
    )


def _tool_result(value) -> ToolResult:
    if isinstance(value, ToolResult):
        return value
    if not isinstance(value, dict):
        return ToolResult(tool_call_id="", name="", output=str(value or ""))
    return ToolResult(
        tool_call_id=str(value.get("tool_call_id", value.get("id", ""))),
        name=str(value.get("name", "")),
        output=str(value.get("output", "")),
    )


def _tool_result_dict(result: ToolResult) -> dict:
    return {"tool_call_id": result.tool_call_id, "name": result.name, "output": result.output}


def _chat_step(
    messages: list[dict],
    *,
    model: str,
    system: str,
    tools: list,
    max_tokens: int,
    provider_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    run_logger=None,
    node_id: str | None = None,
):
    provider, clean_model = resolve(model, provider=provider_name, base_url=base_url, api_key=api_key)
    if run_logger:
        run_logger.model_call(
            node_id=node_id,
            model=clean_model,
            provider=provider_name or provider.__class__.__name__,
            tool_count=len(_tool_defs(tools)),
        )
    resp = provider.complete(
        messages,
        model=clean_model,
        system=system,
        max_tokens=max_tokens,
        tools=_tool_defs(tools) or None,
    )
    step = {
        "role": "assistant",
        "text": resp.text,
        "tool_calls": [_tool_call_dict(tc) for tc in resp.tool_calls],
    }
    return provider, resp, step


def _dispatch_tools(tool_calls: list, tools: list, *, run_logger=None, node_id: str | None = None) -> tuple[list[ToolResult], list[dict]]:
    tool_map = {t.__name__: t for t in tools if callable(t)}
    results: list[ToolResult] = []
    steps: list[dict] = []
    for raw in tool_calls:
        tc = _tool_call(raw)
        fn = tool_map.get(tc.name)
        if run_logger:
            run_logger.tool_call(node_id=node_id, name=tc.name, arguments=tc.arguments)
        try:
            output = fn(**tc.arguments) if fn else f"[error] unknown tool '{tc.name}'"
        except Exception as exc:
            output = f"[error] {type(exc).__name__}: {exc}"
        result = ToolResult(tool_call_id=tc.id, name=tc.name, output=str(output))
        results.append(result)
        steps.append({"role": "tool", "name": tc.name, "output": result.output})
    return results, steps


def _append_tool_messages(
    messages: list[dict],
    *,
    model: str,
    assistant_text: str,
    tool_calls: list,
    tool_results: list,
    provider_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[dict]:
    provider, _ = resolve(model, provider=provider_name, base_url=base_url, api_key=api_key)
    calls = [_tool_call(tc) for tc in tool_calls]
    results = [_tool_result(r) for r in tool_results]
    return [
        *messages,
        *provider.tool_result_messages(assistant_text, calls, results),
    ]


def _agent_loop_run(ctx: dict) -> dict:
    model      = ctx.get("model", "claude-sonnet-4-6")
    system     = ctx.get("system", "You are a helpful agent. Use the available tools.")
    prompt     = ctx.get("prompt", "")
    tools      = ctx.get("tools") or []
    max_tokens = _max_tokens_for_model(model, ctx.get("max_tokens"))
    max_iter   = _int_value(ctx.get("max_iter"), 5)
    run_logger = ctx.get("__run_logger__")
    node_id = ctx.get("__node_id__")

    messages: list[dict] = [{"role": "user", "content": prompt}]
    steps: list[dict] = []
    last_tool_output = ""
    last_tool_signature: tuple = ()

    if not str(prompt or "").strip():
        return {"result": "", "steps": steps}

    for _ in range(max_iter):
        _, resp, step = _chat_step(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            provider_name=ctx.get("provider"),
            base_url=ctx.get("base_url"),
            api_key=ctx.get("api_key"),
            run_logger=run_logger,
            node_id=node_id,
        )
        steps.append({
            "role": "assistant",
            "text": resp.text,
            "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls],
        })
        if resp.stop_reason == "end_turn" or not resp.tool_calls:
            return {"result": _answer_or_tool_output(resp.text, last_tool_output), "steps": steps}

        tool_signature = _tool_call_signature(resp.tool_calls)
        if tool_signature == last_tool_signature and last_tool_output:
            return {"result": last_tool_output, "steps": steps}

        tool_results, tool_steps = _dispatch_tools(
            [_tool_call_dict(tc) for tc in resp.tool_calls],
            tools,
            run_logger=run_logger,
            node_id=node_id,
        )
        if tool_results:
            last_tool_output = tool_results[-1].output
            last_tool_signature = tool_signature
        steps.extend(tool_steps)
        messages = _append_tool_messages(
            messages,
            model=model,
            assistant_text=resp.text,
            tool_calls=[_tool_call_dict(tc) for tc in resp.tool_calls],
            tool_results=[_tool_result_dict(r) for r in tool_results],
            provider_name=ctx.get("provider"),
            base_url=ctx.get("base_url"),
            api_key=ctx.get("api_key"),
        )

    provider, clean_model = resolve(
        model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )
    if run_logger:
        run_logger.model_call(
            node_id=node_id,
            model=clean_model,
            provider=ctx.get("provider") or provider.__class__.__name__,
            tool_count=0,
        )
    final = provider.complete(
        [
            *messages,
            {
                "role": "user",
                "content": "The tool-call limit was reached. Give the final answer now using the tool results above. Do not call tools.",
            },
        ],
        model=clean_model,
        system=system,
        max_tokens=max_tokens,
        tools=None,
    )
    steps.append({"role": "assistant", "text": final.text, "tool_calls": []})
    return {"result": _answer_or_tool_output(final.text, last_tool_output), "steps": steps}


@node(
    inputs=["prompt:Text", "system:Text", "model:Model=claude-sonnet-4-6", "max_tokens:Int=1024", "temperature:Float=1.0"],
    outputs=["text:Text"],
    name="LLMAgent",
)
def llm_agent(ctx: dict) -> dict:
    model       = ctx.get("model", "claude-sonnet-4-6")
    system      = ctx.get("system", "You are a helpful assistant.")
    prompt      = ctx.get("prompt", "")
    max_tokens  = _max_tokens_for_model(model, ctx.get("max_tokens"))
    temperature = float(ctx.get("temperature", 1.0))

    provider, clean_model = resolve(
        model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=clean_model,
            provider=ctx.get("provider") or provider.__class__.__name__,
            tool_count=0,
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
    inputs=["prompt:Text", "system:Text", "model:Model=claude-sonnet-4-6", "tools:List", "max_tokens:Int=1024", "max_iter:Int=5"],
    outputs=["result:Text", "steps:List"],
    name="AgentLoop",
)
def agent_loop(ctx: dict) -> dict:
    return _agent_loop_run(ctx)


@node(
    inputs=["prompt:Text", "system:Text", "model:Model=claude-sonnet-4-6", "tools:List", "max_tokens:Int=1024", "max_iter:Int=5"],
    outputs=["result:Text", "steps:List"],
    name="VisualAgentLoop",
)
def visual_agent_loop(ctx: dict) -> dict:
    """AgentLoop-compatible node built from the same visible agent-step primitives."""
    return _agent_loop_run(ctx)


@node(inputs=["prompt:Text"], outputs=["messages:List"], name="AgentMessages")
def agent_messages(ctx: dict) -> dict:
    return {"messages": [{"role": "user", "content": ctx.get("prompt", "")}]}


@node(
    inputs=["messages:List", "system:Text", "model:Model=claude-sonnet-4-6", "tools:List", "max_tokens:Int=1024"],
    outputs=["assistant_text:Text", "tool_calls:List", "stop_reason:Text", "step:Dict"],
    name="AgentChatStep",
)
def agent_chat_step(ctx: dict) -> dict:
    model = ctx.get("model", "claude-sonnet-4-6")
    _, resp, step = _chat_step(
        ctx.get("messages") or [],
        model=model,
        system=ctx.get("system", "You are a helpful agent. Use the available tools."),
        tools=ctx.get("tools") or [],
        max_tokens=_max_tokens_for_model(model, ctx.get("max_tokens")),
        provider_name=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
        run_logger=ctx.get("__run_logger__"),
        node_id=ctx.get("__node_id__"),
    )
    return {
        "assistant_text": resp.text,
        "tool_calls": step["tool_calls"],
        "stop_reason": resp.stop_reason,
        "step": step,
    }


@node(inputs=["tool_calls:List", "tools:List"], outputs=["tool_results:List", "steps:List"], name="ToolDispatch")
def tool_dispatch(ctx: dict) -> dict:
    results, steps = _dispatch_tools(
        ctx.get("tool_calls") or [],
        ctx.get("tools") or [],
        run_logger=ctx.get("__run_logger__"),
        node_id=ctx.get("__node_id__"),
    )
    return {"tool_results": [_tool_result_dict(r) for r in results], "steps": steps}


@node(inputs=["start:Int=1"], outputs=["iteration:Int"], name="AgentIteration")
def agent_iteration(ctx: dict) -> dict:
    return {"iteration": _int_value(ctx.get("iteration", ctx.get("start")), 1)}


@node(
    inputs=["messages:List", "model:Model=claude-sonnet-4-6", "assistant_text:Text", "tool_calls:List", "tool_results:List"],
    outputs=["messages:List"],
    name="AgentAppendMessages",
)
def agent_append_messages(ctx: dict) -> dict:
    return {
        "messages": _append_tool_messages(
            ctx.get("messages") or [],
            model=ctx.get("model", "claude-sonnet-4-6"),
            assistant_text=ctx.get("assistant_text", ""),
            tool_calls=ctx.get("tool_calls") or [],
            tool_results=ctx.get("tool_results") or [],
            provider_name=ctx.get("provider"),
            base_url=ctx.get("base_url"),
            api_key=ctx.get("api_key"),
        )
    }


@node(
    inputs=["stop_reason:Text", "tool_calls:List", "iteration:Int=1", "max_iter:Int=5"],
    outputs=["continue:Bool", "done:Bool", "reason:Text"],
    name="AgentStopCheck",
)
def agent_stop_check(ctx: dict) -> dict:
    tool_calls = ctx.get("tool_calls") or []
    iteration = int(ctx.get("iteration", 1))
    max_iter = _int_value(ctx.get("max_iter"), 5)
    done = ctx.get("stop_reason") == "end_turn" or not tool_calls or iteration >= max_iter
    reason = "final" if ctx.get("stop_reason") == "end_turn" or not tool_calls else "max_iter" if done else "continue"
    return {"continue": not done, "done": done, "reason": reason}


@node(
    inputs=[
        "messages:List",
        "system:Text",
        "model:Model=claude-sonnet-4-6",
        "max_tokens:Int=1024",
        "assistant_text:Text",
        "stop_reason:Text",
        "reason:Text",
        "tool_calls:List",
    ],
    outputs=["result:Text", "step:Dict"],
    name="AgentFinalAnswer",
)
def agent_final_answer(ctx: dict) -> dict:
    model = ctx.get("model", "claude-sonnet-4-6")
    assistant_text = str(ctx.get("assistant_text") or "")
    reason = str(ctx.get("reason") or "")
    tool_calls = ctx.get("tool_calls") or []
    if reason == "final" or ctx.get("stop_reason") == "end_turn" or not tool_calls:
        step = {"role": "assistant", "text": assistant_text, "tool_calls": [], "reason": reason or "final"}
        return {"result": _user_facing_answer(assistant_text), "step": step}

    provider, clean_model = resolve(
        model,
        provider=ctx.get("provider"),
        base_url=ctx.get("base_url"),
        api_key=ctx.get("api_key"),
    )
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=clean_model,
            provider=ctx.get("provider") or provider.__class__.__name__,
            tool_count=0,
        )
    final = provider.complete(
        [
            *(ctx.get("messages") or []),
            {
                "role": "user",
                "content": "The tool-call limit was reached. Give the final answer now using the tool results above. Do not call tools.",
            },
        ],
        model=clean_model,
        system=ctx.get("system", "You are a helpful agent. Use the available tools."),
        max_tokens=_max_tokens_for_model(model, ctx.get("max_tokens")),
        tools=None,
    )
    step = {"role": "assistant", "text": final.text, "tool_calls": [], "reason": reason or "max_iter"}
    return {"result": _user_facing_answer(final.text), "step": step}


@node(inputs=["fn:Fn", "args:Dict"], outputs=["result:Any"], name="ToolCall")
def tool_call(ctx: dict) -> dict:
    fn   = ctx.get("fn")
    args = ctx.get("args", {})
    if not callable(fn):
        raise ValueError("'fn' input must be a callable")
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.tool_call(
            node_id=ctx.get("__node_id__"),
            name=getattr(fn, "__name__", "tool"),
            arguments=args if isinstance(args, dict) else {"value": args},
        )
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


@node(inputs=["name:Text=tool", "description:Text"], outputs=["fn:Fn"], name="SubnetAsTool")
def subnet_as_tool(ctx: dict) -> dict:
    """Expose this node's internal subgraph as a callable tool for AgentLoop."""
    graph       = ctx.get("__graph__")
    node_id     = ctx.get("__node_id__")
    fn_name     = (ctx.get("name") or "tool").strip()
    description = (ctx.get("description") or "").strip()
    if not graph:
        raise ValueError("SubnetAsTool: graph context unavailable.")
    if not node_id or node_id not in graph._nodes:
        raise ValueError("SubnetAsTool: current node context unavailable.")
    # Derive parameter schema from SubnetInput's output ports
    inner_meta = graph._nodes[node_id].get("subgraph", {}).get("node_meta", {})
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
    fn = _make_tool(node_id, output_port)
    fn.__name__ = fn_name
    fn.__doc__  = description
    fn._bn_schema = {"type": "object", "properties": props, "required": list(props.keys())}
    return {"fn": fn}


@node(
    inputs=[],
    outputs=["tools:List"],
    name="ToolBox",
)
def toolbox(ctx: dict) -> dict:
    """Collect connected Fn values into a list for AgentLoop.tools."""
    def sort_key(name: str) -> tuple[int, str]:
        try:
            return int(name.rsplit("_", 1)[1]), name
        except (IndexError, ValueError):
            return 999_999, name

    ports = sorted((k for k in ctx if k.startswith("tool_")), key=sort_key)
    tools = [ctx[k] for k in ports if callable(ctx.get(k))]
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
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=model,
            provider="OpenAI",
            action="embedding",
        )
    resp = client.embeddings.create(input=text, model=model)
    return {"embedding": resp.data[0].embedding}
