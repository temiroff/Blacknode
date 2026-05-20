"""Minimal example: one NVIDIA NIM LLM agent node."""
from _bootstrap import NIM_MODEL, require_nim_api_key

import blacknode as bn

require_nim_api_key()

g = bn.Graph()

question = g.node("Literal", value="What is the capital of France? Answer in one word.")
agent    = g.node("LLMAgent", model=NIM_MODEL)
output   = g.node("Print")

question.out("value") >> agent.inp("prompt")
agent.out("text")     >> output.inp("value")

result = g.cook(output, "value")
