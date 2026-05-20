"""Show how to define and use a custom node."""
import _bootstrap  # noqa: F401

import blacknode as bn
from blacknode.node import node


@node(inputs=["text", "uppercase"], outputs=["text"], name="TextTransform")
def text_transform(ctx: dict) -> dict:
    text = ctx.get("text", "")
    if ctx.get("uppercase", False):
        text = text.upper()
    return {"text": text.strip()}


g = bn.Graph()

src       = g.node("Literal", value="  hello, blacknode world  ")
transform = g.node("TextTransform", uppercase=True)
output    = g.node("Print")

src.out("value")       >> transform.inp("text")
transform.out("text")  >> output.inp("value")

result = g.cook(output, "value")
# prints: HELLO, BLACKNODE WORLD
