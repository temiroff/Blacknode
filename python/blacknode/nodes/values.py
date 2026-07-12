"""Primitive value nodes — drop one on the canvas and type a value directly."""

from blacknode.node import node
from blacknode.providers.base import ProviderConfigError
from blacknode.providers.keys import api_key_for_provider


def _required_api_key(model: str) -> tuple[str, str] | None:
    if model.startswith("claude"):
        return "Anthropic", "ANTHROPIC_API_KEY"
    if model.startswith(("gpt", "o1", "o3", "o4", "chatgpt", "text-", "ft:gpt")):
        return "OpenAI", "OPENAI_API_KEY"
    if model.startswith("nim:"):
        return "NVIDIA NIM", "NVIDIA_API_KEY"
    return None


@node(inputs=[], outputs=["value:Text"], name="Text")
def text_value(ctx: dict) -> dict:
    return {"value": str(ctx.get("value", ""))}


@node(inputs=[], outputs=["value:Float"], name="Float")
def float_value(ctx: dict) -> dict:
    return {"value": float(ctx.get("value", 0.0))}


@node(inputs=[], outputs=["value:Int"], name="Int")
def int_value(ctx: dict) -> dict:
    return {"value": int(ctx.get("value", 0))}


@node(inputs=[], outputs=["value:Bool"], name="Bool")
def bool_value(ctx: dict) -> dict:
    v = ctx.get("value", False)
    return {"value": bool(v) if not isinstance(v, str) else v.lower() not in ("false", "0", "")}


@node(inputs=[], outputs=["value:Color"], name="Color")
def color_value(ctx: dict) -> dict:
    value = str(ctx.get("value") or "#22c55e").strip()
    return {"value": value or "#22c55e"}


@node(inputs=[], outputs=["value:Model"], name="Model")
def model_value(ctx: dict) -> dict:
    value = str(ctx.get("value", "claude-sonnet-4-6"))
    required = _required_api_key(value)
    if required:
        provider, env_var = required
        if not api_key_for_provider(provider, env_var):
            raise ProviderConfigError(
                f"{provider} API key is missing. Add it on the Model node, save it in the editor, or set {env_var}."
            )
    return {"value": value}


@node(inputs=[], outputs=["value:Dict"], name="Dict")
def dict_value(ctx: dict) -> dict:
    import json
    v = ctx.get("value", {})
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = {}
    return {"value": v if isinstance(v, dict) else {}}


@node(inputs=[], outputs=["value:List"], name="List")
def list_value(ctx: dict) -> dict:
    import json
    v = ctx.get("value", [])
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = []
    return {"value": v if isinstance(v, list) else []}
