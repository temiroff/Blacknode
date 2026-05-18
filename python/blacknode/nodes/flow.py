"""Control-flow nodes: Branch, Gate, Reduce, Filter, Map."""
from blacknode.node import node


@node(inputs=["condition", "if_true", "if_false"], outputs=["value"], name="Branch")
def branch(ctx: dict) -> dict:
    cond = ctx.get("condition")
    return {"value": ctx.get("if_true") if cond else ctx.get("if_false")}


@node(inputs=["value", "enabled"], outputs=["value"], name="Gate")
def gate(ctx: dict) -> dict:
    enabled = ctx.get("enabled", True)
    return {"value": ctx.get("value") if enabled else None}


@node(inputs=["items", "fn", "initial"], outputs=["value"], name="Reduce")
def reduce_node(ctx: dict) -> dict:
    import functools
    items   = ctx.get("items", [])
    fn      = ctx.get("fn")
    initial = ctx.get("initial")
    if initial is not None:
        result = functools.reduce(fn, items, initial)
    else:
        result = functools.reduce(fn, items)
    return {"value": result}


@node(inputs=["items", "fn"], outputs=["items"], name="Filter")
def filter_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn    = ctx.get("fn", lambda x: x)
    return {"items": [x for x in items if fn(x)]}


@node(inputs=["items", "fn"], outputs=["items"], name="Map")
def map_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn    = ctx.get("fn", lambda x: x)
    return {"items": [fn(x) for x in items]}
