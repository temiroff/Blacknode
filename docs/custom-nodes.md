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
