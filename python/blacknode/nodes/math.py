from blacknode.node import node


@node(inputs=["a:Float", "b:Float"], outputs=["value:Float"], name="Add")
def add_node(ctx: dict) -> dict:
    return {"value": float(ctx.get("a", 0.0)) + float(ctx.get("b", 0.0))}


@node(inputs=["a:Float", "b:Float"], outputs=["value:Float"], name="Subtract")
def subtract_node(ctx: dict) -> dict:
    return {"value": float(ctx.get("a", 0.0)) - float(ctx.get("b", 0.0))}


@node(inputs=["a:Float", "b:Float"], outputs=["value:Float"], name="Multiply")
def multiply_node(ctx: dict) -> dict:
    return {"value": float(ctx.get("a", 0.0)) * float(ctx.get("b", 0.0))}


@node(inputs=["a:Float", "b:Float"], outputs=["value:Float"], name="Divide")
def divide_node(ctx: dict) -> dict:
    b = float(ctx.get("b", 0.0))
    if b == 0.0:
        raise ValueError("Divide: b must not be zero.")
    return {"value": float(ctx.get("a", 0.0)) / b}
