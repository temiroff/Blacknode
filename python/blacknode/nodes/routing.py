from blacknode.node import node


@node(
    inputs=["task:Text", "routes:Dict", "default_model:Text"],
    outputs=["model:Model", "route:Text"],
    name="LLMModelRouter",
    category="AI",
)
def llm_model_router(ctx: dict) -> dict:
    task = str(ctx.get("task") or "").lower()
    routes = ctx.get("routes") if isinstance(ctx.get("routes"), dict) else {}
    for route, model in routes.items():
        keywords = [part.strip().lower() for part in str(route).replace(",", "|").split("|") if part.strip()]
        if any(keyword in task for keyword in keywords):
            return {"model": str(model), "route": str(route)}
    return {"model": str(ctx.get("default_model") or ""), "route": "default"}
