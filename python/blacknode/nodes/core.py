"""Core utility nodes: Literal, Print, Merge, Switch, ForEach."""
from blacknode.node import node


@node(inputs=["value"], outputs=["value"], name="Literal")
def literal_node(ctx: dict) -> dict:
    return {"value": ctx.get("value")}


@node(inputs=["value"], outputs=["value"], name="Print")
def print_node(ctx: dict) -> dict:
    val = ctx.get("value")
    print(val)
    return {"value": val}


@node(inputs=["a", "b"], outputs=["value"], name="Concat")
def concat_node(ctx: dict) -> dict:
    return {"value": str(ctx.get("a", "")) + str(ctx.get("b", ""))}


@node(inputs=["condition", "true_value", "false_value"], outputs=["value"], name="Switch")
def switch_node(ctx: dict) -> dict:
    cond = ctx.get("condition")
    return {"value": ctx.get("true_value") if cond else ctx.get("false_value")}


@node(inputs=["items", "template"], outputs=["results"], name="ForEach")
def foreach_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn = ctx.get("template")  # callable passed as param
    results = [fn(item) if callable(fn) else item for item in items]
    return {"results": results}
