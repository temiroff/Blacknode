from __future__ import annotations
from typing import Callable, Any

_NODE_REGISTRY: dict[str, Callable[[dict], Any]] = {}


def _parse_ports(ports: list[str]) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Parse ["name:Type=default", ...] into (names, {name: type}, {name: default}).
    Ports without a colon default to type "Any". The =default part is optional.
    """
    names: list[str] = []
    types: dict[str, str] = {}
    defaults: dict[str, object] = {}
    for p in ports:
        default_val = None
        has_default = False
        if '=' in p:
            p, raw = p.rsplit('=', 1)
            has_default = True
            try:
                default_val = int(raw)
            except ValueError:
                try:
                    default_val = float(raw)
                except ValueError:
                    if raw.lower() == 'true':
                        default_val = True
                    elif raw.lower() == 'false':
                        default_val = False
                    else:
                        default_val = raw
        if ':' in p:
            name, typ = p.split(':', 1)
        else:
            name, typ = p, 'Any'
        names.append(name)
        types[name] = typ
        if has_default:
            defaults[name] = default_val
    return names, types, defaults


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

        # Use `is not None` so that an explicit empty list [] is honoured
        # (the `or` idiom treats [] as falsy, giving a wrong default).
        in_names,  in_types,  in_defaults  = _parse_ports(inputs  if inputs  is not None else [])
        out_names, out_types, _            = _parse_ports(outputs if outputs is not None else ["output:Any"])

        fn._bn_inputs          = in_names
        fn._bn_input_types     = in_types
        fn._bn_input_defaults  = in_defaults
        fn._bn_outputs         = out_names
        fn._bn_output_types    = out_types
        return fn
    return decorator
