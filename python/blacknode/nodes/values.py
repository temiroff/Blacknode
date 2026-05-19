"""Primitive value nodes — drop one on the canvas and type a value directly."""
from blacknode.node import node


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


@node(inputs=[], outputs=["value:Model"], name="Model")
def model_value(ctx: dict) -> dict:
    return {"value": str(ctx.get("value", "claude-sonnet-4-6"))}


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
