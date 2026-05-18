"""Multi-node research pipeline: fetch → summarise → write to file."""
import blacknode as bn

g = bn.Graph()

url      = g.node("Literal", value="https://en.wikipedia.org/wiki/Houdini_(software)")
fetcher  = g.node("HTTPGet")
parser   = g.node("JSONParse")
summarise = g.node("LLMAgent",
                   system="You are a technical writer. Summarise the text in 3 bullet points.",
                   model="claude-haiku-4-5-20251001")
writer   = g.node("FileWrite", path="summary.txt")

url.out("value")       >> fetcher.inp("url")
fetcher.out("text")    >> summarise.inp("prompt")
summarise.out("text")  >> writer.inp("text")

result = g.cook(writer, "path")
print(f"Summary written to: {result}")
