"""Same graph — swap model/provider without touching the wiring."""
import blacknode as bn

def build_graph(model: str, **kwargs):
    g = bn.Graph()
    q = g.node("Literal", value="Name three benefits of node-based programming.")
    a = g.node("LLMAgent", model=model, **kwargs)
    p = g.node("Print")
    q.out("value") >> a.inp("prompt")
    a.out("text")  >> p.inp("value")
    return g, p

# Anthropic (auto-detected from model name)
g, out = build_graph("claude-haiku-4-5-20251001")
print("=== Anthropic ===")
g.cook(out, "value")

# OpenAI (auto-detected)
# g, out = build_graph("gpt-4o-mini")
# print("=== OpenAI ===")
# g.cook(out, "value")

# Ollama local  (ollama: prefix → localhost:11434)
# g, out = build_graph("ollama:llama3.2")
# print("=== Ollama ===")
# g.cook(out, "value")

# LM Studio / llama.cpp (explicit base_url)
# g, out = build_graph("local:my-model", base_url="http://localhost:1234/v1")
# print("=== Local ===")
# g.cook(out, "value")
