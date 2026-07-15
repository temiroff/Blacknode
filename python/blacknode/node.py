from __future__ import annotations
import functools
import inspect
from dataclasses import dataclass
from typing import Any as TypingAny
from typing import Callable, Mapping

_NODE_REGISTRY: dict[str, Callable[[dict], TypingAny]] = {}


@dataclass(frozen=True)
class PortSpec:
    type_name: str
    default: TypingAny = None
    has_default: bool = False
    choices: tuple = ()


class PortType:
    def __init__(self, type_name: str):
        self.type_name = type_name

    def __call__(self, default: TypingAny = None) -> PortSpec:
        return PortSpec(self.type_name, default, True)

    def __getitem__(self, _item: TypingAny) -> PortSpec:
        return PortSpec(self.type_name)

    def __repr__(self) -> str:
        return self.type_name

    def __str__(self) -> str:
        return self.type_name


Text = PortType("Text")
Int = PortType("Int")
Float = PortType("Float")
Bool = PortType("Bool")
Color = PortType("Color")
List = PortType("List")
Dict = PortType("Dict")
Embedding = PortType("Embedding")
Fn = PortType("Fn")
Model = PortType("Model")
Number = PortType("Number")
Image = PortType("Image")
Any = PortType("Any")


def Enum(choices: TypingAny, default: TypingAny = None, type_name: str = "Text") -> PortSpec:
    """A fixed-choice param rendered as a dropdown in the editor.

    The wire type stays ``Text`` (default) so validation and code export are
    unchanged; the editor renders a ``<select>`` when a port carries choices::

        @node(inputs={"op": Enum(["vector_add", "matmul"], default="vector_add")})

    """
    opts = tuple(str(c) for c in choices)
    chosen = default if default is not None else (opts[0] if opts else None)
    return PortSpec(type_name, chosen, True, opts)


def _parse_ports(ports: list[str] | Mapping[str, TypingAny]) -> tuple[list[str], dict[str, str], dict[str, object], dict[str, list]]:
    """Parse port specs into (names, {name: type}, {name: default}, {name: choices}).

    Supports the original compact syntax:

        ["name:Type=default"]

    And the richer mapping syntax:

        {"name": Text, "limit": Int(default=5), "items": List[Dict]}

    Ports without a colon default to type "Any". The =default part is optional.
    Only the mapping syntax can carry dropdown choices (via ``Enum(...)``).
    """
    if isinstance(ports, Mapping):
        return _parse_mapping_ports(ports)

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
    return names, types, defaults, {}


def _parse_mapping_ports(ports: Mapping[str, TypingAny]) -> tuple[list[str], dict[str, str], dict[str, object], dict[str, list]]:
    names: list[str] = []
    types: dict[str, str] = {}
    defaults: dict[str, object] = {}
    choices: dict[str, list] = {}
    for raw_name, value in ports.items():
        name = str(raw_name)
        spec = _coerce_port_spec(value)
        names.append(name)
        types[name] = spec.type_name
        if spec.has_default:
            defaults[name] = spec.default
        if spec.choices:
            choices[name] = list(spec.choices)
    return names, types, defaults, choices


def _coerce_port_spec(value: TypingAny) -> PortSpec:
    if isinstance(value, PortSpec):
        return value
    if isinstance(value, PortType):
        return PortSpec(value.type_name)
    if isinstance(value, str):
        type_name, default, has_default = _parse_type_string(value)
        return PortSpec(type_name, default, has_default)
    builtin_map = {
        str: "Text",
        int: "Int",
        float: "Float",
        bool: "Bool",
        list: "List",
        dict: "Dict",
    }
    if value in builtin_map:
        return PortSpec(builtin_map[value])
    if value is None:
        return PortSpec("Any")
    return PortSpec(getattr(value, "__name__", str(value)))


def _parse_type_string(value: str) -> tuple[str, object, bool]:
    if "=" not in value:
        return value or "Any", None, False
    type_name, raw = value.rsplit("=", 1)
    return type_name or "Any", _parse_default(raw), True


def _parse_default(raw: str) -> object:
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            if raw.lower() == "true":
                return True
            if raw.lower() == "false":
                return False
            return raw


def node(
    inputs: list[str] | Mapping[str, TypingAny] | None = None,
    outputs: list[str] | Mapping[str, TypingAny] | None = None,
    name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    hidden: bool = False,
    live: bool = False,
):
    """Decorator that registers a function as a Blacknode node type.

    Ports use "name:Type" syntax::

        @bn.node(inputs=["prompt:Text", "temp:Float"], outputs=["text:Text"])
        def MyNode(ctx: dict) -> dict:
            return {"text": ctx["prompt"].upper()}

    Rich mapping syntax is also supported::

        @node(
            name="Web Search",
            category="Tools",
            inputs={"query": Text, "num_results": Int(default=5)},
            outputs={"results": List[Dict]},
        )
        def web_search(query: str, num_results: int):
            return []
    """
    def decorator(fn: Callable) -> Callable:
        type_name = name or fn.__name__

        # Use `is not None` so that an explicit empty list [] is honoured
        # (the `or` idiom treats [] as falsy, giving a wrong default).
        in_names,  in_types,  in_defaults,  in_choices = _parse_ports(inputs  if inputs  is not None else [])
        out_names, out_types, _,            _          = _parse_ports(outputs if outputs is not None else ["output:Any"])

        runtime_fn = fn if _expects_context(fn) else _wrap_direct_node(fn, in_names, in_defaults, out_names)
        _NODE_REGISTRY[type_name] = runtime_fn
        _attach_metadata(runtime_fn, type_name, in_names, in_types, in_defaults, in_choices, out_names, out_types, category, description, hidden, live)
        if runtime_fn is not fn:
            _attach_metadata(fn, type_name, in_names, in_types, in_defaults, in_choices, out_names, out_types, category, description, hidden, live)
        return fn
    return decorator


def _expects_context(fn: Callable) -> bool:
    params = [
        p
        for p in inspect.signature(fn).parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(params) == 1 and params[0].name in {"ctx", "context"}


def _wrap_direct_node(fn: Callable, inputs: list[str], defaults: dict[str, object], outputs: list[str]) -> Callable[[dict], TypingAny]:
    @functools.wraps(fn)
    def wrapper(ctx: dict) -> dict:
        kwargs = {
            name: ctx[name] if name in ctx else defaults.get(name)
            for name in inputs
        }
        result = fn(**kwargs)
        return _normalize_result(result, outputs)

    return wrapper


def _normalize_result(result: TypingAny, outputs: list[str]) -> dict:
    if isinstance(result, dict):
        return result
    if result is None:
        return {}
    if len(outputs) == 1:
        return {outputs[0]: result}
    if isinstance(result, (list, tuple)):
        return {port: result[index] if index < len(result) else None for index, port in enumerate(outputs)}
    return {"output": result}


def _attach_metadata(
    fn: Callable,
    type_name: str,
    inputs: list[str],
    input_types: dict[str, str],
    input_defaults: dict[str, object],
    input_choices: dict[str, list],
    outputs: list[str],
    output_types: dict[str, str],
    category: str | None,
    description: str | None,
    hidden: bool,
    live: bool,
) -> None:
    fn._bn_node = True
    fn._bn_type_name = type_name
    fn._bn_inputs = inputs
    fn._bn_input_types = input_types
    fn._bn_input_defaults = input_defaults
    fn._bn_input_choices = input_choices
    fn._bn_outputs = outputs
    fn._bn_output_types = output_types
    fn._bn_hidden = hidden
    fn._bn_live_capable = live
    if category:
        fn._bn_category = category
    if description:
        fn._bn_description = description


__all__ = [
    "Any",
    "Bool",
    "Color",
    "Dict",
    "Embedding",
    "Enum",
    "Float",
    "Fn",
    "Image",
    "Int",
    "List",
    "Model",
    "Number",
    "PortSpec",
    "PortType",
    "Text",
    "_NODE_REGISTRY",
    "node",
]
