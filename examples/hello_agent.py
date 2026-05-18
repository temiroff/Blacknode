"""Minimal example: one LLM agent node."""
import blacknode as bn

g = bn.Graph()

question = g.node("Literal", value="What is the capital of France? Answer in one word.")
agent    = g.node("LLMAgent", model="claude-haiku-4-5-20251001")
output   = g.node("Print")

question.out("value") >> agent.inp("prompt")
agent.out("text")     >> output.inp("value")

result = g.cook(output, "value")
