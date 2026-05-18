from blacknode.node import node


@node(inputs=["value:Any"], outputs=["value:Any"], name="Literal")
def literal_node(ctx: dict) -> dict:
    return {"value": ctx.get("value")}


@node(inputs=["value:Any"], outputs=["value:Any"], name="Print")
def print_node(ctx: dict) -> dict:
    val = ctx.get("value")
    print(val)
    return {"value": val}


@node(inputs=["a:Text", "b:Text"], outputs=["value:Text"], name="Concat")
def concat_node(ctx: dict) -> dict:
    return {"value": str(ctx.get("a", "")) + str(ctx.get("b", ""))}


@node(inputs=["condition:Bool", "true_value:Any", "false_value:Any"], outputs=["value:Any"], name="Switch")
def switch_node(ctx: dict) -> dict:
    return {"value": ctx.get("true_value") if ctx.get("condition") else ctx.get("false_value")}


@node(inputs=["items:List", "template:Fn"], outputs=["results:List"], name="ForEach")
def foreach_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn    = ctx.get("template")
    return {"results": [fn(item) if callable(fn) else item for item in items]}


@node(inputs=["value:Any"], outputs=[], name="Output")
def output_node(ctx: dict) -> dict:
    """Terminal display node — cook it to see the result on the canvas."""
    return {"value": ctx.get("value")}
