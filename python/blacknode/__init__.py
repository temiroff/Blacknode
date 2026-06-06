from .graph import Graph, NodeProxy
from .node import Any, Bool, Dict, Embedding, Enum, Float, Fn, Image, Int, List, Model, Number, Text, _NODE_REGISTRY, node
from .workflow import validate_graph, validate_workflow

# Auto-register built-in node libraries
import blacknode.nodes.values  # noqa: F401
import blacknode.nodes.core    # noqa: F401
import blacknode.nodes.ai      # noqa: F401
import blacknode.nodes.nvidia  # noqa: F401
import blacknode.nodes.cuda    # noqa: F401
import blacknode.nodes.image   # noqa: F401
import blacknode.nodes.api     # noqa: F401
import blacknode.nodes.database  # noqa: F401
import blacknode.nodes.flow    # noqa: F401
import blacknode.nodes.io      # noqa: F401
import blacknode.nodes.math    # noqa: F401
import blacknode.nodes.messaging  # noqa: F401
import blacknode.nodes.rag     # noqa: F401
import blacknode.nodes.routing  # noqa: F401
import blacknode.nodes.search  # noqa: F401
import blacknode.nodes.subnet  # noqa: F401

from .discovery import discover_node_modules  # noqa: E402

_DISCOVERY_REPORT = discover_node_modules()

from .learned.registry import load_all as _load_learned_nodes  # noqa: E402

_LEARNED_REPORT = _load_learned_nodes()

__version__ = "0.1.0"
__all__ = [
    "Any",
    "Bool",
    "Dict",
    "Embedding",
    "Enum",
    "Float",
    "Fn",
    "Graph",
    "Image",
    "Int",
    "List",
    "Model",
    "NodeProxy",
    "Number",
    "Text",
    "_DISCOVERY_REPORT",
    "_LEARNED_REPORT",
    "_NODE_REGISTRY",
    "discover_node_modules",
    "node",
    "validate_graph",
    "validate_workflow",
]
