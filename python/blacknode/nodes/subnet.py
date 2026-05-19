from blacknode.node import node


@node(
    inputs=["value:Any"],
    outputs=["value:Any"],
    name="SubgraphInput",
)
def subgraph_input(ctx: dict) -> dict:
    return {"value": ctx.get("value")}


@node(
    inputs=["value:Any"],
    outputs=["value:Any"],
    name="SubgraphOutput",
)
def subgraph_output(ctx: dict) -> dict:
    return {"value": ctx.get("value")}
