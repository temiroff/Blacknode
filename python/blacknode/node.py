from __future__ import annotations
from typing import Callable, Any

_NODE_REGISTRY: dict[str, Callable[[dict], Any]] = {}


def _parse_ports(ports: list[str]) -> tuple[list[str], dict[str, str]]:
    """Parse ["name:Type", ...] into (names, {name: type}).
    Ports without a colon default to type "Any".
    """
    names: list[str] = []
    types: dict[str, str] = {}
    for p in ports:
        if ':' in p:
            name, typ = p.split(':', 1)
        else:
            name, typ = p, 'Any'
        names.append(name)
        types[name] = typ
    return names, types


def node(
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    name: str | None = None,
):
    """Decorator that registers a function as a Blacknode node type.

    Ports use "name:Type" syntax::

        @bn.node(inputs=["prompt:Text", "temp:Float"], outputs=["text:Text"])
        def MyNode(ctx: dict) -> dict:
            return {"text": ctx["prompt"].upper()}
    """
    def decorator(fn: Callable) -> Callable:
        type_name = name or fn.__name__
        _NODE_REGISTRY[type_name] = fn
        fn._bn_node = True
        fn._bn_type_name = type_name

        in_names,  in_types  = _parse_ports(inputs  or [])
        out_names, out_types = _parse_ports(outputs or ["output:Any"])

        fn._bn_inputs       = in_names
        fn._bn_input_types  = in_types
        fn._bn_outputs      = out_names
        fn._bn_output_types = out_types
        return fn
    return decorator
