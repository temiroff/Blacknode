"""Same graph with an explicit NVIDIA NIM model."""
from _bootstrap import NIM_MODEL, require_nim_api_key

import blacknode as bn

require_nim_api_key()


def build_graph(model: str):
    g = bn.Graph()
    q = g.node("Literal", value="Name three benefits of node-based programming.")
    a = g.node("LLMAgent", model=model)
    p = g.node("Print")
    q.out("value") >> a.inp("prompt")
    a.out("text")  >> p.inp("value")
    return g, p

g, out = build_graph(NIM_MODEL)
print("=== NVIDIA NIM ===")
g.cook(out, "value")

# To try a different NIM model, change NIM_MODEL in _bootstrap.py.
