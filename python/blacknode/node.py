from __future__ import annotations
from typing import Callable, Any

_NODE_REGISTRY: dict[str, Callable[[dict], Any]] = {}


def node(
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    name: str | None = None,
):
    """Decorator that registers a function as a Blacknode node type.

    Usage::

        @bn.node(inputs=["prompt"], outputs=["text"])
        def MyNode(ctx: dict) -> dict:
            return {"text": ctx["prompt"].upper()}
    """
    def decorator(fn: Callable) -> Callable:
        type_name = name or fn.__name__
        _NODE_REGISTRY[type_name] = fn
        fn._bn_node = True
        fn._bn_inputs = inputs or []
        fn._bn_outputs = outputs or ["output"]
        fn._bn_type_name = type_name
        return fn
    return decorator
