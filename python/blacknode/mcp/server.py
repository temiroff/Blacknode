"""FastMCP server exposing the Blacknode workflow toolkit to MCP clients.

Launch with ``blacknode mcp`` (stdio transport) and point an MCP client such as
Claude Desktop or Cursor at the same command. The tools call into
``blacknode.mcp.tools`` so behavior matches the unit-tested surface.
"""
from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import guidance
    raise SystemExit(
        "The 'mcp' package is required to run the Blacknode MCP server.\n"
        "Install it with:  pip install 'mcp>=1.0'"
    ) from exc

from . import tools

mcp = FastMCP("blacknode")


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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
