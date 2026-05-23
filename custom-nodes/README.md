# Custom Nodes

Files saved from the editor Script tab are written here and auto-loaded when
Blacknode starts.

Rules:

- Use one or more `@node` definitions per `.py` file.
- Keep secrets out of node files.
- Restart Blacknode or press `Reload` in the Script tab after editing files by hand.

Example:

```python
from blacknode.node import Int, Text, node


@node(
    name="RepeatText",
    category="Tools",
    inputs={"text": Text, "times": Int(default=2)},
    outputs={"result": Text},
)
def repeat_text(text: str, times: int = 2) -> str:
    return str(text or "") * int(times or 1)
```
