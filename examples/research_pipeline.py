"""Multi-node research pipeline: fetch → summarise → write to file."""
from _bootstrap import NIM_MODEL, require_nim_api_key

import blacknode as bn

require_nim_api_key()

g = bn.Graph()

url      = g.node("Literal", value="https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles=Houdini_(software)&format=json&formatversion=2&origin=*")
fetcher  = g.node("HTTPGet")
summarise = g.node("LLMAgent",
                   system="You are a technical writer. Summarise the text in 3 bullet points.",
                   model=NIM_MODEL)
writer   = g.node("FileWrite", path="summary.txt")

url.out("value")       >> fetcher.inp("url")
fetcher.out("text")    >> summarise.inp("prompt")
summarise.out("text")  >> writer.inp("text")

result = g.cook(writer, "path")
print(f"Summary written to: {result}")
