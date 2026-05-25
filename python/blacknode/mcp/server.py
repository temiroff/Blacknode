"""FastMCP server exposing the Blacknode workflow toolkit to MCP clients.

Launch with ``blacknode mcp`` for stdio transport, or with
``blacknode mcp --transport streamable-http`` for HTTP MCP clients such as
NVIDIA AI-Q/NeMo Agent Toolkit workflows. The tools call into
``blacknode.mcp.tools`` so behavior matches the unit-tested surface.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import guidance
    raise SystemExit(
        "The 'mcp' package is required to run the Blacknode MCP server.\n"
        "Install it with:  pip install 'mcp>=1.0'"
    ) from exc

from . import tools

WORKFLOW_BUILDER_INSTRUCTIONS = """When building Blacknode workflows:

1. Always inspect the existing node catalog first with list_nodes and
   get_node_schema.
2. Use built-in nodes whenever they can solve the task exactly.
3. If the task needs a reusable capability that is missing from the catalog,
   create a learned node with create_node_type instead of using one-off Python
   code.
4. Do not treat a brittle approximation as a match. For example, if the user
   asks to parse RSS article titles and only a generic regex extractor exists,
   create a learned node that parses RSS structurally instead of returning feed
   metadata or other false positives.
5. Do not create or modify files under nodes/learned directly. Use
   create_node_type, list_learned_nodes, get_learned_node_source,
   promote_learned_node, and delete_learned_node.
6. Before creating a learned node, keep the interface small and typed, use
   requires_network=false unless network is strictly required, generate only a
   def run(...) function, and make sure the function parameters match the
   declared inputs. Set category to the palette group where the node should
   appear, such as RAG, Search, Vision, Parsing, or Research.
7. After creating a learned node, call list_learned_nodes, use it in the visual
   workflow, validate the graph, open it in the editor, and cook the final
   Output node.

Learned-node code is registered as a node type, but it never runs in the
Blacknode host process. It executes through the Docker sandbox wrapper.
"""

mcp = FastMCP("blacknode", instructions=WORKFLOW_BUILDER_INSTRUCTIONS)


def _json_resource(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _safe_editor_resource(name: str, payload_fn: Any) -> str:
    try:
        return _json_resource(payload_fn())
    except Exception as exc:  # pragma: no cover - depends on live editor state
        return _json_resource({"ok": False, "resource": name, "error": str(exc)})


@mcp.resource(
    "blacknode://agent-instructions",
    mime_type="text/plain",
    description="Recommended MCP agent instructions for building Blacknode workflows.",
)
def agent_instructions_resource() -> str:
    """Recommended MCP agent instructions as plain text."""
    return WORKFLOW_BUILDER_INSTRUCTIONS


@mcp.resource(
    "blacknode://nodes",
    mime_type="application/json",
    description="Registered Blacknode node types grouped by category with port schemas.",
)
def nodes_resource() -> str:
    """Registered node schemas as JSON."""
    return _json_resource(tools.list_nodes())


@mcp.resource(
    "blacknode://templates",
    mime_type="application/json",
    description="Tracked workflow templates available from templates/*.json.",
)
def templates_resource() -> str:
    """Tracked workflow templates as JSON."""
    return _json_resource(tools.list_templates())


@mcp.resource(
    "blacknode://workflows",
    mime_type="application/json",
    description="Saved editor workflows from the running Blacknode editor backend.",
)
def workflows_resource() -> str:
    """Saved editor workflows as JSON."""
    return _safe_editor_resource("blacknode://workflows", tools.list_saved_workflows)


@mcp.resource(
    "blacknode://editor/graph",
    mime_type="application/json",
    description="Current graph loaded in the running Blacknode editor backend.",
)
def editor_graph_resource() -> str:
    """Current editor graph as JSON."""
    return _safe_editor_resource("blacknode://editor/graph", tools.get_editor_graph)


@mcp.resource(
    "blacknode://runs",
    mime_type="application/json",
    description="Recent run summaries from the running Blacknode editor backend.",
)
def runs_resource() -> str:
    """Recent editor run summaries as JSON."""
    return _safe_editor_resource("blacknode://runs", tools.list_recent_runs)


@mcp.prompt(
    name="blacknode_workflow_builder",
    title="Blacknode Workflow Builder",
    description="Use built-in nodes first; create learned nodes only for reusable missing capabilities.",
)
def blacknode_workflow_builder_prompt() -> str:
    """Instructions for building Blacknode workflows through MCP."""
    return WORKFLOW_BUILDER_INSTRUCTIONS


@mcp.tool()
def list_nodes() -> dict[str, Any]:
    """List every Blacknode node type with category and port schema."""
    return tools.list_nodes()


@mcp.tool()
def get_node_schema(type_name: str) -> dict[str, Any]:
    """Return input/output ports and defaults for one node type."""
    return tools.get_node_schema(type_name)


@mcp.tool()
def list_templates() -> dict[str, Any]:
    """List shipped workflow templates with their descriptions."""
    return tools.list_templates()


@mcp.tool()
def load_workflow(path: str) -> dict[str, Any]:
    """Load a workflow JSON file from disk and return its dict form."""
    return tools.load_workflow_tool(path)


@mcp.tool()
def save_workflow(
    workflow: dict[str, Any],
    path: str,
    validate: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate and save a workflow JSON file to disk."""
    return tools.save_workflow_tool(
        workflow,
        path,
        validate=validate,
        overwrite=overwrite,
    )


@mcp.tool()
def create_workflow(name: str = "Untitled", description: str = "") -> dict[str, Any]:
    """Create an empty workflow scaffold that already contains an Output node."""
    return tools.create_workflow(name=name, description=description)


@mcp.tool()
def add_node(
    workflow: dict[str, Any],
    type_name: str,
    params: dict[str, Any] | None = None,
    pos: list[float] | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Add a node to a workflow and return the updated workflow plus validation."""
    return tools.add_node(
        workflow,
        type_name,
        params=params,
        pos=tuple(pos) if pos else None,
        node_id=node_id,
    )


@mcp.tool()
def connect_nodes(
    workflow: dict[str, Any],
    from_node: str,
    from_port: str,
    to_node: str,
    to_port: str,
) -> dict[str, Any]:
    """Add a typed edge between two existing nodes; rejects incompatible types."""
    return tools.connect_nodes(workflow, from_node, from_port, to_node, to_port)


@mcp.tool()
def validate_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Run full schema + port-type validation and return errors/warnings."""
    return tools.validate_workflow_tool(workflow)


@mcp.tool()
def run_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Execute the workflow; returns cooked value, run id, and event log."""
    return tools.run_workflow_tool(workflow)


@mcp.tool()
def export_python(workflow: dict[str, Any]) -> dict[str, Any]:
    """Convert the workflow to a standalone Python script using blacknode.Graph."""
    return tools.export_python_tool(workflow)


@mcp.tool()
def create_node_type(
    name: str,
    description: str,
    inputs: list[str],
    outputs: list[str],
    code: str,
    requires_network: bool = False,
    category: str = "Learned",
) -> dict[str, Any]:
    """Create a permanent learned node type that executes in the Docker sandbox."""
    return tools.create_node_type(
        name=name,
        description=description,
        inputs=inputs,
        outputs=outputs,
        code=code,
        requires_network=requires_network,
        category=category,
    )


@mcp.tool()
def list_learned_nodes() -> dict[str, Any]:
    """List learned nodes stored on disk."""
    return tools.list_learned_nodes()


@mcp.tool()
def delete_learned_node(name: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a learned node from disk and unregister it; requires confirm=True."""
    return tools.delete_learned_node(name=name, confirm=confirm)


@mcp.tool()
def get_learned_node_source(name: str) -> dict[str, Any]:
    """Return the Python source for a learned node."""
    return tools.get_learned_node_source(name=name)


@mcp.tool()
def promote_learned_node(
    name: str,
    category: str | None = None,
    target: str = "custom-nodes",
    overwrite: bool = False,
    keep_learned: bool = False,
) -> dict[str, Any]:
    """Promote a learned node into custom-nodes or community-nodes."""
    return tools.promote_learned_node(
        name=name,
        category=category,
        target=target,
        overwrite=overwrite,
        keep_learned=keep_learned,
    )


@mcp.tool()
def create_editor_workflow_tab(
    name: str = "Untitled",
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to open a new unsaved workflow tab."""
    return tools.create_editor_workflow_tab(name=name, editor_url=editor_url)


@mcp.tool()
def open_workflow_in_editor_tab(
    workflow: dict[str, Any],
    name: str | None = None,
    editor_url: str | None = None,
    organize: bool = True,
) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to open and optionally organize a populated workflow tab."""
    return tools.open_workflow_in_editor_tab(
        workflow=workflow,
        name=name,
        editor_url=editor_url,
        organize=organize,
    )


@mcp.tool()
def run_template_in_editor(
    template: str,
    name: str | None = None,
    editor_url: str | None = None,
    organize: bool = True,
    cook: bool = False,
    cook_node_id: str = "out",
    cook_port: str = "value",
) -> dict[str, Any]:
    """Open a tracked template in the editor and optionally cook a node."""
    return tools.run_template_in_editor(
        template=template,
        name=name,
        editor_url=editor_url,
        organize=organize,
        cook=cook,
        cook_node_id=cook_node_id,
        cook_port=cook_port,
    )


@mcp.tool()
def cook_editor_node(
    node_id: str = "out",
    port: str = "value",
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to cook a node and update the canvas."""
    return tools.cook_editor_node(node_id=node_id, port=port, editor_url=editor_url)


@mcp.tool()
def get_editor_graph(editor_url: str | None = None) -> dict[str, Any]:
    """Return the graph currently loaded in a running Blacknode editor backend."""
    return tools.get_editor_graph(editor_url=editor_url)


@mcp.tool()
def save_editor_workflow(
    name: str = "Untitled",
    previous_slug: str | None = None,
    editor_url: str | None = None,
) -> dict[str, Any]:
    """Save the graph currently loaded in a running Blacknode editor backend."""
    return tools.save_editor_workflow(
        name=name,
        previous_slug=previous_slug,
        editor_url=editor_url,
    )


@mcp.tool()
def list_saved_workflows(editor_url: str | None = None) -> dict[str, Any]:
    """List workflows saved by a running Blacknode editor backend."""
    return tools.list_saved_workflows(editor_url=editor_url)


@mcp.tool()
def list_recent_runs(limit: int = 20, editor_url: str | None = None) -> dict[str, Any]:
    """List recent run summaries from a running Blacknode editor backend."""
    return tools.list_recent_runs(limit=limit, editor_url=editor_url)


@mcp.tool()
def get_run(run_id: str, editor_url: str | None = None) -> dict[str, Any]:
    """Return a full run record, including events, from a running editor backend."""
    return tools.get_run(run_id=run_id, editor_url=editor_url)


@mcp.tool()
def load_saved_workflow_in_editor(
    slug: str,
    name: str | None = None,
    editor_url: str | None = None,
    organize: bool = True,
) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to open a saved workflow tab."""
    return tools.load_saved_workflow_in_editor(
        slug=slug,
        name=name,
        editor_url=editor_url,
        organize=organize,
    )


@mcp.tool()
def organize_editor_graph(editor_url: str | None = None) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to organize and fit the current graph."""
    return tools.organize_editor_graph(editor_url=editor_url)


@mcp.tool()
def rename_editor_tab(name: str, editor_url: str | None = None) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to rename its active workflow tab."""
    return tools.rename_editor_tab(name=name, editor_url=editor_url)


@mcp.tool()
def close_editor_tab(editor_url: str | None = None) -> dict[str, Any]:
    """Ask a running Blacknode editor UI to close its active workflow tab."""
    return tools.close_editor_tab(editor_url=editor_url)


def main(
    *,
    transport: str = "stdio",
    host: str | None = None,
    port: int | None = None,
    path: str | None = None,
    allowed_hosts: list[str] | None = None,
) -> None:
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("transport must be one of: stdio, sse, streamable-http")
    if host:
        mcp.settings.host = host
    if port is not None:
        mcp.settings.port = int(port)
    if path:
        if transport == "streamable-http":
            mcp.settings.streamable_http_path = path
        elif transport == "sse":
            mcp.settings.sse_path = path
    if allowed_hosts and mcp.settings.transport_security is not None:
        mcp.settings.transport_security.allowed_hosts = allowed_hosts
    _write_stdio_terminal_hint(transport)
    mcp.run(transport=transport)


def _write_stdio_terminal_hint(transport: str) -> None:
    if transport != "stdio":
        return
    if os.environ.get("BLACKNODE_MCP_QUIET"):
        return
    if not getattr(sys.stdin, "isatty", lambda: False)():
        return
    if not getattr(sys.stderr, "isatty", lambda: False)():
        return

    print(
        "Blacknode MCP stdio server is running.\n"
        "This terminal is waiting for an MCP client over stdin/stdout; no browser opens here.\n"
        "Visual editor: .\\start.bat\n"
        "HTTP MCP: blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp\n"
        "Press Ctrl+C to stop.",
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    main()
