# Custom Nodes and Community Nodes

Blacknode nodes are ordinary Python functions registered with `@node`. You can
run a node instantly in the editor, save it as a persistent file, or submit it
as a community node through GitHub.

## Create in the Editor

1. Start Blacknode.
2. Open the **Script** tab.
3. Paste a node definition.
4. Press `Run` to register it immediately.
5. Press `Save` to write it into `custom-nodes/`.
6. Open the node palette and add the new node from its category.

Starter node:

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

## Auto-Discovery

Blacknode loads node files from:

| Folder | Purpose |
|---|---|
| `custom-nodes/` | Local nodes saved from the editor or written by hand. |
| `community-nodes/` | Repository-reviewed nodes, the marketplace MVP. |
| `nodes/` | Optional project-local node folder. |
| `packages/` | [Extension packages](packages.md) — multi-file node libraries in their own git repos, with deps and templates. |

You can also set `BLACKNODE_NODE_PATH` to one or more folders separated by the
platform path separator.

For anything bigger than a single file — a node library with pip dependencies,
its own templates, versioning, and its own repository — write an
[extension package](packages.md) instead.

## Decorator Formats

Original compact format:

```python
@node(inputs=["query:Text", "limit:Int=5"], outputs=["results:List"], name="Search")
def search(ctx: dict) -> dict:
    return {"results": []}
```

Typed mapping format:

```python
@node(
    name="Search",
    category="Tools",
    inputs={"query": Text, "limit": Int(default=5)},
    outputs={"results": List[Dict]},
)
def search(query: str, limit: int = 5) -> list:
    return []
```

Variadic input format for collector nodes:

```python
from blacknode.node import Dict, List, node


@node(
    name="CameraList",
    category="Vision",
    inputs={},
    outputs={"cameras": List[Dict]},
    variadic_input=Dict,
    variadic_prefix="camera",
)
def camera_list(ctx: dict) -> dict:
    cameras = [
        value
        for name, value in sorted(ctx.items())
        if name.startswith("camera_") and isinstance(value, dict)
    ]
    return {"cameras": cameras}
```

The editor renders a `camera_N · connect to add` socket and creates numbered
inputs as connections are made, so the node can accept any number of cameras.
The built-in `List` node uses the same contract with `item_N` inputs while
retaining its literal JSON-list input for saved-workflow compatibility.

Large nodes can declare their initial compact canvas surface while retaining
all parameters in Properties:

```python
from blacknode.node import Any, Bool, Dict, Image, Int, Text, node


@node(
    name="Camera",
    inputs={"trigger": Any, "selection": Int(default=0), "backend": Text(default="auto")},
    outputs={"preview": Image, "frame_stream": Dict, "ready": Bool, "report": Text},
    primary_inputs=["trigger"],
    primary_outputs=["preview", "frame_stream", "report"],
)
```

In Properties, right-click a parameter or output—or use its diamond pin—to
promote or hide that socket. Connected sockets always remain visible. **Compact
node** hides unconnected sockets; **Show all** restores the full port surface.

Nodes with eight or more combined ports receive conservative compact defaults
when the author does not declare primary ports: required data-bearing inputs
remain wireable, configuration stays in Properties, and up to three payload
outputs are shown. Repetitive status and diagnostic outputs remain available
for promotion. Small nodes keep their complete socket surface.

For readable sequencing, the canvas displays the compatibility input
`trigger` as **run after** and the completion/report output `report` as
**done**. Saved workflows and runtime APIs retain the original stable port IDs.

## Community Node PRs

Community nodes live in `community-nodes/*.py`. A good PR includes:

- a clear node name and category,
- typed inputs and outputs,
- no network calls at import time,
- no secrets or hardcoded credentials,
- tests for parsing, retrieval, database, or API behavior.

## Promote Learned Nodes

When an MCP-created learned node is stable, use `promote_learned_node` to turn
it into a normal custom or community node:

```text
promote_learned_node(name="ParseRSS", target="custom-nodes", category="RAG")
```

Promotion writes a reviewed `@node` module, registers it live, and removes the
learned-node source by default. Pass `keep_learned=True` for a copy-only export.

## Built-In Expansion Nodes

The current extension-focused node set includes:

| Category | Nodes |
|---|---|
| Search | `WebSearchURL`, `SearchResultExtractor`, `SearchResultsFormat` |
| RAG | `TextChunker`, `KeywordIndex`, `KeywordSearch`, `RAGContext` |
| Database | `SQLiteQuery`, `SQLiteExec` |
| API | `HTTPRequest`, `APIRequestBuilder` |
| IO | `DirectoryList`, `FileInfo`, `CSVRead`, `CSVWrite`, plus existing file/JSON/HTTP nodes |
| Routing | `LLMModelRouter` |
