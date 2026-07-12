from blacknode.node import node


@node(inputs=["condition:Bool", "if_true:Any", "if_false:Any"], outputs=["value:Any"], name="Branch")
def branch(ctx: dict) -> dict:
    return {"value": ctx.get("if_true") if ctx.get("condition") else ctx.get("if_false")}


@node(inputs=["value:Any", "enabled:Bool"], outputs=["value:Any"], name="Gate")
def gate(ctx: dict) -> dict:
    return {"value": ctx.get("value") if ctx.get("enabled", True) else None}


@node(inputs=["items:List", "fn:Fn", "initial:Any"], outputs=["value:Any"], name="Reduce")
def reduce_node(ctx: dict) -> dict:
    import functools
    items   = ctx.get("items", [])
    fn      = ctx.get("fn")
    initial = ctx.get("initial")
    result  = functools.reduce(fn, items, initial) if initial is not None else functools.reduce(fn, items)
    return {"value": result}


@node(inputs=["items:List", "fn:Fn"], outputs=["items:List"], name="Filter")
def filter_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn    = ctx.get("fn", lambda x: x)
    return {"items": [x for x in items if fn(x)]}


@node(inputs=["items:List", "fn:Fn"], outputs=["items:List"], name="Map")
def map_node(ctx: dict) -> dict:
    items = ctx.get("items", [])
    fn    = ctx.get("fn", lambda x: x)
    return {"items": [fn(x) for x in items]}


@node(inputs=["items:List", "index:Int"], outputs=["value:Any", "found:Bool"], name="ListIndex")
def list_index_node(ctx: dict) -> dict:
    items = ctx.get("items") or []
    try:
        value = items[int(ctx.get("index", 0))]
    except (TypeError, ValueError, IndexError):
        return {"value": None, "found": False}
    return {"value": value, "found": True}
