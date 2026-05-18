from .graph import Graph, NodeProxy
from .node import node, _NODE_REGISTRY

# Auto-register built-in node libraries
import blacknode.nodes.values  # noqa: F401
import blacknode.nodes.core    # noqa: F401
import blacknode.nodes.ai      # noqa: F401
import blacknode.nodes.flow    # noqa: F401
import blacknode.nodes.io      # noqa: F401

__version__ = "0.1.0"
__all__ = ["Graph", "NodeProxy", "node", "_NODE_REGISTRY"]
